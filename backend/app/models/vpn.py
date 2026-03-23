"""Database models for VPN configuration."""
from __future__ import annotations

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, relationship
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class VPNConfig(Base):
    """Server-wide VPN configuration (singleton)."""
    __tablename__ = "vpn_config"
    
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    server_private_key: Mapped[str] = Column(String(255), nullable=False)  # Fernet-encrypted if VPN_ENCRYPTION_KEY set
    server_public_key: Mapped[str] = Column(String(64), nullable=False, unique=True)
    server_ip: Mapped[str] = Column(String(15), nullable=False)  # e.g., "10.8.0.1"
    server_port: Mapped[int] = Column(Integer, nullable=False, default=51820)
    network_cidr: Mapped[str] = Column(String(18), nullable=False)  # e.g., "10.8.0.0/24"
    created_at: Mapped[Optional[datetime]] = Column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VPNClient(Base):
    """VPN client configuration for mobile devices."""
    __tablename__ = "vpn_clients"
    
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_name: Mapped[str] = Column(String(100), nullable=False)
    public_key: Mapped[str] = Column(String(64), nullable=False, unique=True)
    preshared_key: Mapped[str] = Column(String(255), nullable=False)  # Fernet-encrypted if VPN_ENCRYPTION_KEY set
    assigned_ip: Mapped[str] = Column(String(15), nullable=False, unique=True)  # e.g., "10.8.0.2"
    is_active: Mapped[bool] = Column(Boolean, default=True, nullable=False)
    created_at: Mapped[Optional[datetime]] = Column(DateTime, default=datetime.utcnow)
    last_handshake: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)  # Updated when client connects
    
    # Relationships
    user = relationship("User", back_populates="vpn_clients")
    
    def __repr__(self):
        return f"<VPNClient(id={self.id}, device={self.device_name}, ip={self.assigned_ip})>"


class FritzBoxVPNConfig(Base):
    """Fritz!Box WireGuard VPN configuration for shared client access."""
    __tablename__ = "fritzbox_vpn_configs"
    
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)

    # Encrypted sensitive data
    private_key_encrypted: Mapped[str] = Column(String(255), nullable=False)
    preshared_key_encrypted: Mapped[str] = Column(String(255), nullable=False)

    # Public config data
    address: Mapped[str] = Column(String(100), nullable=False)  # e.g., "192.168.178.201/24,fddc:c98b:ce8e::201/64"
    dns_servers: Mapped[str] = Column(String(255), nullable=False)  # Comma-separated DNS servers
    peer_public_key: Mapped[str] = Column(String(64), nullable=False)
    allowed_ips: Mapped[str] = Column(Text, nullable=False)  # Can be very long, e.g., "192.168.178.0/24,0.0.0.0/0,..."
    endpoint: Mapped[str] = Column(String(255), nullable=False)  # DynDNS:Port, e.g., "example.myfritz.net:58411"
    persistent_keepalive: Mapped[Optional[int]] = Column(Integer, default=25)

    # Metadata
    is_active: Mapped[bool] = Column(Boolean, default=True, nullable=False, index=True)
    uploaded_by_user_id: Mapped[Optional[int]] = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[Optional[datetime]] = Column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    uploaded_by = relationship("User")
    
    def __repr__(self):
        return f"<FritzBoxVPNConfig(id={self.id}, endpoint={self.endpoint}, active={self.is_active})>"

