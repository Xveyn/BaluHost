"""VPN service for WireGuard configuration and management."""

import secrets
import base64
import subprocess
from typing import Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.vpn import VPNClient, VPNConfig
from app.schemas.vpn import VPNClientCreate, VPNConfigResponse


class VPNService:
    """Service for managing WireGuard VPN configurations."""
    
    # WireGuard default settings
    VPN_NETWORK = "10.8.0.0/24"
    VPN_SERVER_IP = "10.8.0.1"
    VPN_PORT = 51820
    VPN_DNS = "1.1.1.1"  # Cloudflare DNS
    
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
                server_private_key=server_private,
                server_public_key=server_public,
                server_ip=VPNService.VPN_SERVER_IP,
                server_port=VPNService.VPN_PORT,
                network_cidr=VPNService.VPN_NETWORK,
            )
            db.add(server_config)
            db.commit()
            db.refresh(server_config)
        
        # Create client entry
        client = VPNClient(
            user_id=user_id,
            device_name=device_name,
            public_key=client_public,
            preshared_key=preshared_key,
            assigned_ip=client_ip,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_handshake=None,
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        
        # Generate WireGuard config file
        config_content = f"""[Interface]
PrivateKey = {client_private}
Address = {client_ip}/32
DNS = {VPNService.VPN_DNS}

[Peer]
PublicKey = {server_config.server_public_key}
PresharedKey = {preshared_key}
Endpoint = {server_public_endpoint}:{server_config.server_port}
AllowedIPs = {VPNService.VPN_NETWORK}
PersistentKeepalive = 25
"""
        
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
        return True
    
    @staticmethod
    def delete_client(db: Session, client_id: int) -> bool:
        """Delete a VPN client permanently."""
        client = VPNService.get_client_by_id(db, client_id)
        if not client:
            return False
        
        db.delete(client)
        db.commit()
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
    def parse_fritzbox_config(config_content: str) -> dict:
        """
        Parse Fritz!Box WireGuard config file.
        
        Args:
            config_content: Raw .conf file content
            
        Returns:
            dict with keys: private_key, address, dns_servers, peer_public_key,
                           preshared_key, allowed_ips, endpoint, persistent_keepalive
        """
        config = {}
        current_section = None
        dns_list = []
        
        for line in config_content.split('\n'):
            line = line.strip()
            
            if not line or line.startswith('#'):
                continue
                
            if line.startswith('['):
                current_section = line
            elif current_section == '[Interface]':
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'PrivateKey':
                        config['private_key'] = value
                    elif key == 'Address':
                        config['address'] = value
                    elif key == 'DNS':
                        dns_list.append(value)
            elif current_section == '[Peer]':
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'PublicKey':
                        config['peer_public_key'] = value
                    elif key == 'PresharedKey':
                        config['preshared_key'] = value
                    elif key == 'AllowedIPs':
                        config['allowed_ips'] = value
                    elif key == 'Endpoint':
                        config['endpoint'] = value
                    elif key == 'PersistentKeepalive':
                        config['persistent_keepalive'] = int(value)
        
        # Join DNS servers
        config['dns_servers'] = ','.join(dns_list)
        
        # Validate required fields
        required = ['private_key', 'address', 'peer_public_key', 'allowed_ips', 'endpoint']
        missing = [f for f in required if f not in config]
        if missing:
            raise ValueError(f"Missing required fields in config: {', '.join(missing)}")
        
        return config
    
    @staticmethod
    def upload_fritzbox_config(
        db: Session,
        config_content: str,
        user_id: int
    ):
        """
        Parse and save Fritz!Box WireGuard config.
        
        Args:
            db: Database session
            config_content: Raw .conf file content
            user_id: User ID (admin)
            
        Returns:
            FritzBoxConfigResponse
        """
        from app.models.vpn import FritzBoxVPNConfig
        from app.services.vpn_encryption import VPNEncryption
        from app.schemas.vpn import FritzBoxConfigResponse
        
        # Parse config
        parsed = VPNService.parse_fritzbox_config(config_content)
        
        # Encrypt sensitive keys
        private_key_encrypted = VPNEncryption.encrypt_key(parsed['private_key'])
        preshared_key_encrypted = VPNEncryption.encrypt_key(parsed.get('preshared_key', ''))
        
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
        from app.services.vpn_encryption import VPNEncryption
        
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
        
        # Decrypt keys
        private_key = VPNEncryption.decrypt_key(config.private_key_encrypted)
        preshared_key = VPNEncryption.decrypt_key(config.preshared_key_encrypted) if config.preshared_key_encrypted else ''
        
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
