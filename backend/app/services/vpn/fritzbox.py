"""Fritz!Box WireGuard VPN configuration management."""

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class FritzBoxVPNService:
    """Service for managing Fritz!Box WireGuard VPN configurations."""

    @staticmethod
    def parse_fritzbox_config(config_content: str, public_endpoint: Optional[str] = None) -> dict:
        """
        Parse Fritz!Box WireGuard config file.

        Args:
            config_content: Raw .conf file content

        Returns:
            dict with keys: private_key, address, dns_servers, peer_public_key,
                           preshared_key, allowed_ips, endpoint, persistent_keepalive
        """
        # Remove BOM if present and normalize line endings
        config_content = config_content.replace('\r\n', '\n').replace('\r', '\n')
        if config_content.startswith('\ufeff'):
            config_content = config_content[1:]

        config = {}
        current_section = None
        dns_list = []
        debug_lines = []  # Store all parsed lines for debugging
        listen_port = None  # For server configs

        for line_num, line in enumerate(config_content.split('\n'), 1):
            line = line.strip()

            if not line or line.startswith('#'):
                continue

            if line.startswith('['):
                current_section = line.lower()  # Normalize section name
                debug_lines.append(f"Line {line_num}: Section = {current_section}")
            elif current_section == '[interface]':
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip().lower()  # Case-insensitive key matching
                    value = value.strip()
                    debug_lines.append(f"Line {line_num}: [Interface] {key} = {value[:20]}..." if len(value) > 20 else f"Line {line_num}: [Interface] {key} = {value}")

                    if key == 'privatekey':
                        config['private_key'] = value
                    elif key == 'address':
                        config['address'] = value
                    elif key == 'dns':
                        dns_list.append(value)
                    elif key == 'listenport':
                        # This is a server config! Save the port
                        listen_port = value
                        debug_lines.append(f"  -> Found ListenPort (server config): {value}")
            elif current_section == '[peer]':
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip().lower()  # Case-insensitive key matching
                    value = value.strip()
                    debug_lines.append(f"Line {line_num}: [Peer] {key} = {value}")

                    if key == 'publickey':
                        config['peer_public_key'] = value
                    elif key == 'presharedkey':
                        config['preshared_key'] = value
                    elif key == 'allowedips':
                        config['allowed_ips'] = value
                    elif key == 'endpoint':
                        if value:  # Only add if not empty
                            config['endpoint'] = value
                            debug_lines.append(f"  -> Endpoint saved: {value}")
                        else:
                            debug_lines.append(f"  -> Endpoint EMPTY!")
                    elif key == 'persistentkeepalive':
                        try:
                            config['persistent_keepalive'] = int(value)
                        except ValueError:
                            pass  # Ignore invalid keepalive values

        # Join DNS servers
        config['dns_servers'] = ','.join(dns_list)

        # Handle server config (has ListenPort but no Endpoint)
        if 'endpoint' not in config and listen_port:
            if public_endpoint:
                # Strip any existing port/scheme from public_endpoint before appending listen_port
                ep = public_endpoint
                if "://" in ep:
                    from urllib.parse import urlparse
                    ep = urlparse(ep).hostname or ep
                elif ":" in ep:
                    ep = ep.split(":")[0]
                config['endpoint'] = f"{ep}:{listen_port}"
                debug_lines.append(f"Built Endpoint from server config: {config['endpoint']}")
            else:
                # Server config without public endpoint - need user to provide it
                config['listen_port'] = listen_port
                debug_lines.append(f"Server config detected (ListenPort={listen_port}). Public endpoint needed.")

        # Validate required fields
        # For server configs, we allow missing endpoint if listen_port is present
        if 'endpoint' not in config and 'listen_port' not in config:
            required = ['private_key', 'address', 'peer_public_key', 'allowed_ips']
            missing = [f for f in required if f not in config]
            if missing:
                found_keys = list(config.keys())
                debug_info = '\n'.join(debug_lines)
                error_msg = f"Missing required fields: {', '.join(missing)}. Found: {', '.join(found_keys)}.\n\nDebug:\n{debug_info}"
                raise ValueError(error_msg)

            # Missing endpoint but have other fields
            found_keys = list(config.keys())
            debug_info = '\n'.join(debug_lines)
            error_msg = (
                f"Server config detected (has ListenPort but no Endpoint). "
                f"Please provide the public endpoint (DynDNS or IP address).\n\n"
                f"Found: {', '.join(found_keys)}.\n\nDebug:\n{debug_info}"
            )
            raise ValueError(error_msg)

        return config

    @staticmethod
    def upload_fritzbox_config(
        db: Session,
        config_content: str,
        user_id: int,
        public_endpoint: Optional[str] = None
    ):
        """
        Parse and save Fritz!Box WireGuard config.

        Args:
            db: Database session
            config_content: Raw .conf file content
            user_id: User ID (admin)
            public_endpoint: Public endpoint (e.g., "myfritz.net" or "203.0.113.1")
                            Required for server configs that don't include Endpoint

        Returns:
            FritzBoxConfigResponse
        """
        from app.models.vpn import FritzBoxVPNConfig
        from app.schemas.vpn import FritzBoxConfigResponse
        from app.services.vpn.service import VPNService

        # Parse config
        parsed = FritzBoxVPNService.parse_fritzbox_config(config_content, public_endpoint)

        # Encrypt sensitive keys (use safe wrappers with fallback)
        private_key_encrypted = VPNService._encrypt_key(parsed['private_key'])
        preshared_key_encrypted = VPNService._encrypt_key(parsed.get('preshared_key', ''))

        # Deactivate old configs
        db.query(FritzBoxVPNConfig).update({"is_active": False})

        # Create new config
        config = FritzBoxVPNConfig(
            private_key_encrypted=private_key_encrypted,
            preshared_key_encrypted=preshared_key_encrypted,
            address=parsed['address'],
            dns_servers=parsed.get('dns_servers', ''),
            peer_public_key=parsed['peer_public_key'],
            allowed_ips=parsed['allowed_ips'],
            endpoint=parsed['endpoint'],
            persistent_keepalive=parsed.get('persistent_keepalive', 25),
            is_active=True,
            uploaded_by_user_id=user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        db.add(config)
        db.commit()
        db.refresh(config)

        # Generate config_base64 for response
        config_base64 = FritzBoxVPNService.get_fritzbox_config_base64(db, config.id)

        return FritzBoxConfigResponse(
            id=config.id,
            address=config.address,
            dns_servers=config.dns_servers,
            endpoint=config.endpoint,
            allowed_ips=config.allowed_ips,
            persistent_keepalive=config.persistent_keepalive,
            is_active=config.is_active,
            created_at=config.created_at,
            updated_at=config.updated_at,
            config_base64=config_base64
        )

    @staticmethod
    def get_fritzbox_config_base64(db: Session, config_id: Optional[int] = None) -> str:
        """
        Get Fritz!Box config as Base64 (for QR codes).

        Args:
            db: Database session
            config_id: Optional config ID. If None, returns active config.

        Returns:
            Base64 encoded config string
        """
        from app.models.vpn import FritzBoxVPNConfig
        from app.services.vpn.service import VPNService

        if config_id:
            config = db.query(FritzBoxVPNConfig).filter(
                FritzBoxVPNConfig.id == config_id
            ).first()
        else:
            config = db.query(FritzBoxVPNConfig).filter(
                FritzBoxVPNConfig.is_active == True
            ).first()

        if not config:
            raise ValueError("No Fritz!Box VPN config found")

        # Decrypt keys (use safe wrappers with fallback)
        private_key = VPNService._decrypt_key(config.private_key_encrypted)
        preshared_key = VPNService._decrypt_key(config.preshared_key_encrypted) if config.preshared_key_encrypted else ''

        # Rebuild config file
        dns_lines = '\n'.join([f"DNS = {dns.strip()}" for dns in config.dns_servers.split(',') if dns.strip()])

        config_parts = ["[Interface]"]
        config_parts.append(f"PrivateKey = {private_key}")
        config_parts.append(f"Address = {config.address}")
        if dns_lines:
            config_parts.append(dns_lines)

        config_parts.append("")
        config_parts.append("[Peer]")
        config_parts.append(f"PublicKey = {config.peer_public_key}")
        if preshared_key:
            config_parts.append(f"PresharedKey = {preshared_key}")
        config_parts.append(f"AllowedIPs = {config.allowed_ips}")
        config_parts.append(f"Endpoint = {config.endpoint}")
        config_parts.append(f"PersistentKeepalive = {config.persistent_keepalive}")

        config_content = '\n'.join(config_parts)

        # Base64 encode
        return base64.b64encode(config_content.encode()).decode()

    @staticmethod
    def get_active_fritzbox_config(db: Session):
        """Get currently active Fritz!Box config."""
        from app.models.vpn import FritzBoxVPNConfig
        return db.query(FritzBoxVPNConfig).filter(
            FritzBoxVPNConfig.is_active == True
        ).first()

    @staticmethod
    def delete_fritzbox_config(db: Session, config_id: int) -> bool:
        """Delete Fritz!Box config."""
        from app.models.vpn import FritzBoxVPNConfig
        config = db.query(FritzBoxVPNConfig).filter(
            FritzBoxVPNConfig.id == config_id
        ).first()

        if not config:
            return False

        db.delete(config)
        db.commit()
        return True
