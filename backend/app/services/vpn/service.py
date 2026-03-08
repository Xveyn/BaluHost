"""VPN service for WireGuard configuration and management."""

import logging
import os
import secrets
import base64
import subprocess
import tempfile
from typing import Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.vpn import VPNClient, VPNConfig
from app.schemas.vpn import VPNClientCreate, VPNConfigResponse

logger = logging.getLogger(__name__)


class VPNService:
    """Service for managing WireGuard VPN configurations."""

    # WireGuard default settings
    VPN_NETWORK = "10.8.0.0/24"
    VPN_SERVER_IP = "10.8.0.1"
    VPN_PORT = 51820
    VPN_DNS_FALLBACK = "1.1.1.1"  # Cloudflare DNS (fallback when Pi-hole is not active)

    # ------------------------------------------------------------------
    # Conditional encryption helpers
    # ------------------------------------------------------------------
    # VPN_ENCRYPTION_KEY may not be set (e.g. dev mode).  When absent we
    # fall back to storing plaintext and log a warning.

    @staticmethod
    def _encryption_available() -> bool:
        """Return True if VPN_ENCRYPTION_KEY is configured."""
        return bool(settings.vpn_encryption_key)

    @staticmethod
    def _encrypt_key(plaintext: str) -> str:
        """Encrypt *plaintext* if VPN_ENCRYPTION_KEY is available, else return as-is."""
        if not VPNService._encryption_available():
            logger.warning(
                "VPN_ENCRYPTION_KEY not set — storing VPN key in plaintext. "
                "Set VPN_ENCRYPTION_KEY in .env for production."
            )
            return plaintext
        from app.services.vpn.encryption import VPNEncryption
        return VPNEncryption.encrypt_key(plaintext)

    @staticmethod
    def _decrypt_key(stored: str) -> str:
        """Decrypt *stored* value.  Handles both encrypted and legacy plaintext values."""
        if not stored:
            return stored
        if not VPNService._encryption_available():
            # No encryption key — assume the value is plaintext.
            return stored
        from app.services.vpn.encryption import VPNEncryption
        try:
            return VPNEncryption.decrypt_key(stored)
        except Exception:
            # Value may be legacy plaintext that was never encrypted.
            # Return it as-is so existing configs keep working.
            logger.debug(
                "Could not decrypt VPN key — assuming legacy plaintext value."
            )
            return stored

    # ------------------------------------------------------------------
    # Server config generation & application
    # ------------------------------------------------------------------

    @staticmethod
    def get_lan_interface() -> str:
        """Detect the LAN interface for NAT rules.

        Uses ``vpn_lan_interface`` setting if set, otherwise auto-detects
        from the default route.  Returns ``"eth0"`` in dev mode.
        """
        if settings.vpn_lan_interface:
            return settings.vpn_lan_interface

        if settings.is_dev_mode:
            return "eth0"

        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=5,
            )
            # e.g. "default via 192.168.178.1 dev enp9s0 proto ..."
            for part in result.stdout.split():
                idx = result.stdout.split().index(part)
                if part == "dev" and idx + 1 < len(result.stdout.split()):
                    return result.stdout.split()[idx + 1]
        except Exception as exc:
            logger.warning("Failed to detect LAN interface: %s", exc)

        return "eth0"

    @staticmethod
    def generate_server_config(db: Session) -> str:
        """Generate a WireGuard server config from database state.

        Returns the config file content as a string.
        """
        server_config = db.query(VPNConfig).first()
        if not server_config:
            raise RuntimeError("No VPN server config in database. Generate a client first to initialise keys.")

        server_private = VPNService._decrypt_key(server_config.server_private_key)
        lan_iface = VPNService.get_lan_interface()

        lines: list[str] = [
            "[Interface]",
            f"PrivateKey = {server_private}",
            f"Address = {server_config.server_ip}/24",
            f"ListenPort = {server_config.server_port}",
        ]

        if settings.vpn_include_lan:
            lines.append(
                f"PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; "
                f"iptables -t nat -A POSTROUTING -o {lan_iface} -j MASQUERADE; "
                f"sysctl -w net.ipv4.ip_forward=1"
            )
            lines.append(
                f"PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; "
                f"iptables -t nat -D POSTROUTING -o {lan_iface} -j MASQUERADE"
            )

        # Add active client peers
        clients = db.query(VPNClient).filter(VPNClient.is_active == True).all()
        for client in clients:
            lines.append("")
            lines.append("[Peer]")
            lines.append(f"PublicKey = {client.public_key}")
            psk = VPNService._decrypt_key(client.preshared_key)
            if psk:
                lines.append(f"PresharedKey = {psk}")
            lines.append(f"AllowedIPs = {client.assigned_ip}/32")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def apply_server_config(db: Session) -> tuple[bool, str]:
        """Generate and apply WireGuard server config.

        In dev mode the config is generated but not written/applied.
        Returns ``(success, message)``.
        """
        try:
            config_content = VPNService.generate_server_config(db)
        except RuntimeError as exc:
            return False, str(exc)

        if settings.is_dev_mode:
            logger.info("Dev mode: generated WireGuard server config (not applying)")
            return True, "Server config generated (dev mode — not applied)"

        config_path = settings.vpn_config_path

        # Write config via sudo tee (backend user needs sudoers entry)
        try:
            proc = subprocess.run(
                ["sudo", "tee", config_path],
                input=config_content, capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                return False, f"Failed to write config: {proc.stderr.strip()}"
            # Restrict permissions
            subprocess.run(
                ["sudo", "chmod", "600", config_path],
                capture_output=True, text=True, timeout=5,
            )
        except Exception as exc:
            return False, f"Failed to write config: {exc}"

        # Check if wg0 interface is already up
        try:
            check = subprocess.run(
                ["ip", "link", "show", "wg0"],
                capture_output=True, text=True, timeout=5,
            )
            wg0_up = check.returncode == 0
        except Exception:
            wg0_up = False

        if wg0_up:
            # Live-reload without disconnecting clients
            # wg syncconf needs a stripped config (no Interface Address/PostUp/PostDown)
            try:
                strip_proc = subprocess.run(
                    ["sudo", "wg-quick", "strip", "wg0"],
                    capture_output=True, text=True, timeout=10,
                )
                if strip_proc.returncode != 0:
                    return False, f"wg-quick strip failed: {strip_proc.stderr.strip()}"

                # Write stripped config to temp file for syncconf
                with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp:
                    tmp.write(strip_proc.stdout)
                    tmp_path = tmp.name

                try:
                    sync_proc = subprocess.run(
                        ["sudo", "wg", "syncconf", "wg0", tmp_path],
                        capture_output=True, text=True, timeout=10,
                    )
                    if sync_proc.returncode != 0:
                        return False, f"wg syncconf failed: {sync_proc.stderr.strip()}"
                finally:
                    os.unlink(tmp_path)

                logger.info("WireGuard server config synced (live reload)")
                return True, "Server config synced (live reload)"
            except Exception as exc:
                return False, f"Failed to sync config: {exc}"
        else:
            # Interface not up — start it
            try:
                up_proc = subprocess.run(
                    ["sudo", "wg-quick", "up", "wg0"],
                    capture_output=True, text=True, timeout=15,
                )
                if up_proc.returncode != 0:
                    return False, f"wg-quick up failed: {up_proc.stderr.strip()}"
                logger.info("WireGuard interface wg0 started")
                return True, "Server config applied and wg0 started"
            except Exception as exc:
                return False, f"Failed to start wg0: {exc}"

    @staticmethod
    def _try_apply_server_config(db: Session) -> None:
        """Best-effort server config sync.  Errors are logged, not raised."""
        try:
            success, message = VPNService.apply_server_config(db)
            if not success:
                logger.warning("Server config sync failed: %s", message)
            else:
                logger.info("Server config sync: %s", message)
        except Exception as exc:
            logger.warning("Server config sync error: %s", exc)

    @staticmethod
    def get_vpn_dns(db: Optional['Session'] = None) -> str:
        """Get the DNS server to use for VPN clients.

        Returns Pi-hole IP (10.8.0.1) if Pi-hole is active and configured as VPN DNS,
        otherwise falls back to Cloudflare (1.1.1.1).
        """
        try:
            from app.services.pihole.service import PiholeService
            if db is None:
                from app.core.database import SessionLocal
                db = SessionLocal()
                try:
                    return PiholeService(db).get_vpn_dns()
                finally:
                    db.close()
            return PiholeService(db).get_vpn_dns()
        except Exception:
            return VPNService.VPN_DNS_FALLBACK

    @staticmethod
    def generate_wireguard_keypair() -> tuple[str, str]:
        """
        Generate WireGuard private and public key pair.
        
        Returns:
            tuple[str, str]: (private_key, public_key)
        """
        if settings.is_dev_mode:
            # Mock keys in dev mode
            private_key = base64.b64encode(secrets.token_bytes(32)).decode()
            public_key = base64.b64encode(secrets.token_bytes(32)).decode()
            return private_key, public_key
        
        try:
            # Generate private key
            private_result = subprocess.run(
                ["wg", "genkey"],
                capture_output=True,
                text=True,
                check=True
            )
            private_key = private_result.stdout.strip()
            
            # Generate public key from private key
            public_result = subprocess.run(
                ["wg", "pubkey"],
                input=private_key,
                capture_output=True,
                text=True,
                check=True
            )
            public_key = public_result.stdout.strip()
            
            return private_key, public_key
        except Exception as e:
            raise RuntimeError(f"Failed to generate WireGuard keys: {str(e)}")
    
    @staticmethod
    def generate_preshared_key() -> str:
        """Generate WireGuard preshared key for additional security."""
        if settings.is_dev_mode:
            return base64.b64encode(secrets.token_bytes(32)).decode()
        
        try:
            result = subprocess.run(
                ["wg", "genpsk"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except Exception as e:
            raise RuntimeError(f"Failed to generate preshared key: {str(e)}")
    
    @staticmethod
    def get_next_client_ip(db: Session) -> str:
        """
        Get the next available client IP address.
        
        Args:
            db: Database session
            
        Returns:
            str: Next available IP (e.g., "10.8.0.2")
        """
        # Get all assigned IPs
        clients = db.query(VPNClient).filter(VPNClient.is_active == True).all()
        assigned_ips = {client.assigned_ip for client in clients}
        
        # Find first available IP (starting from .2, .1 is server)
        for i in range(2, 255):
            ip = f"10.8.0.{i}"
            if ip not in assigned_ips:
                return ip
        
        raise RuntimeError("No available IP addresses in VPN network")
    
    @staticmethod
    def create_client_config(
        db: Session,
        user_id: int,
        device_name: str,
        server_public_endpoint: str,
    ) -> VPNConfigResponse:
        """
        Create a new WireGuard client configuration.

        Args:
            db: Database session
            user_id: User ID
            device_name: Device name (e.g., "iPhone 13 Pro")
            server_public_endpoint: Server public IP or domain

        Returns:
            VPNConfigResponse: Configuration with client keys and config file
        """
        # Strip protocol and port from endpoint URL to get bare hostname/IP
        from urllib.parse import urlparse
        endpoint = server_public_endpoint
        if "://" in endpoint:
            parsed = urlparse(endpoint)
            endpoint = parsed.hostname or endpoint
        elif ":" in endpoint:
            endpoint = endpoint.split(":")[0]
        server_public_endpoint = endpoint

        # Generate client keypair
        client_private, client_public = VPNService.generate_wireguard_keypair()
        preshared_key = VPNService.generate_preshared_key()
        
        # Get next available IP
        client_ip = VPNService.get_next_client_ip(db)
        
        # Get or create server config
        server_config = db.query(VPNConfig).first()
        if not server_config:
            server_private, server_public = VPNService.generate_wireguard_keypair()
            server_config = VPNConfig(
                server_private_key=VPNService._encrypt_key(server_private),
                server_public_key=server_public,
                server_ip=VPNService.VPN_SERVER_IP,
                server_port=VPNService.VPN_PORT,
                network_cidr=VPNService.VPN_NETWORK,
            )
            db.add(server_config)
            db.commit()
            db.refresh(server_config)

        # Create client entry — encrypt preshared key before storing
        client = VPNClient(
            user_id=user_id,
            device_name=device_name,
            public_key=client_public,
            preshared_key=VPNService._encrypt_key(preshared_key),
            assigned_ip=client_ip,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_handshake=None,
        )
        db.add(client)
        db.commit()
        db.refresh(client)

        # Build AllowedIPs — VPN network + optional LAN
        allowed_ips = VPNService.VPN_NETWORK
        if settings.vpn_include_lan and settings.vpn_lan_network:
            allowed_ips += f", {settings.vpn_lan_network}"

        # Generate WireGuard config file — use plaintext keys (not the encrypted DB values)
        config_content = f"""[Interface]
PrivateKey = {client_private}
Address = {client_ip}/32
DNS = {VPNService.get_vpn_dns(db)}

[Peer]
PublicKey = {server_config.server_public_key}
PresharedKey = {preshared_key}
Endpoint = {server_public_endpoint}:{server_config.server_port}
AllowedIPs = {allowed_ips}
PersistentKeepalive = 25
"""
        
        # Sync server config so the new client peer is active immediately
        VPNService._try_apply_server_config(db)

        # Base64 encode config for QR code
        config_base64 = base64.b64encode(config_content.encode()).decode()

        return VPNConfigResponse(
            client_id=client.id,
            device_name=device_name,
            assigned_ip=client_ip,
            client_public_key=client_public,
            server_public_key=server_config.server_public_key,
            server_endpoint=f"{server_public_endpoint}:{server_config.server_port}",
            config_content=config_content,
            config_base64=config_base64,
        )
    
    @staticmethod
    def get_client_by_id(db: Session, client_id: int) -> Optional[VPNClient]:
        """Get VPN client by ID."""
        return db.query(VPNClient).filter(VPNClient.id == client_id).first()
    
    @staticmethod
    def get_clients_by_user(db: Session, user_id: int) -> list[VPNClient]:
        """Get all VPN clients for a user."""
        return db.query(VPNClient).filter(VPNClient.user_id == user_id).all()
    
    @staticmethod
    def revoke_client(db: Session, client_id: int) -> bool:
        """Revoke a VPN client (deactivate)."""
        client = VPNService.get_client_by_id(db, client_id)
        if not client:
            return False

        client.is_active = False
        db.commit()
        VPNService._try_apply_server_config(db)
        return True
    
    @staticmethod
    def delete_client(db: Session, client_id: int) -> bool:
        """Delete a VPN client permanently."""
        client = VPNService.get_client_by_id(db, client_id)
        if not client:
            return False

        db.delete(client)
        db.commit()
        VPNService._try_apply_server_config(db)
        return True
    
    @staticmethod
    def get_server_config(db: Session) -> Optional[VPNConfig]:
        """Get the WireGuard server configuration."""
        return db.query(VPNConfig).first()
    
    @staticmethod
    def update_last_handshake(db: Session, client_id: int) -> None:
        """Update the last handshake timestamp for a client."""
        client = VPNService.get_client_by_id(db, client_id)
        if client:
            client.last_handshake = datetime.now(timezone.utc)
            db.commit()
    
    @staticmethod
    def parse_fritzbox_config(config_content: str, public_endpoint: str = None) -> dict:
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
            original_line = line
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
                # Build endpoint from public address and listen port
                config['endpoint'] = f"{public_endpoint}:{listen_port}"
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
        public_endpoint: str = None
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

        # Parse config
        parsed = VPNService.parse_fritzbox_config(config_content, public_endpoint)

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
        config_base64 = VPNService.get_fritzbox_config_base64(db, config.id)
        
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
    def get_fritzbox_config_base64(db: Session, config_id: int = None) -> str:
        """
        Get Fritz!Box config as Base64 (for QR codes).
        
        Args:
            db: Database session
            config_id: Optional config ID. If None, returns active config.
            
        Returns:
            Base64 encoded config string
        """
        from app.models.vpn import FritzBoxVPNConfig

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
