"""VPN service for WireGuard configuration and management."""

import secrets
import base64
import subprocess
from typing import Optional
from datetime import datetime, timedelta
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
            created_at=datetime.utcnow(),
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
            client.last_handshake = datetime.utcnow()
            db.commit()
