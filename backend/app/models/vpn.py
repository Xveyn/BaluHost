"""Database models for VPN configuration."""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class VPNConfig(Base):
    """Server-wide VPN configuration (singleton)."""
    __tablename__ = "vpn_config"
    
    id = Column(Integer, primary_key=True, index=True)
    server_private_key = Column(String(64), nullable=False)
    server_public_key = Column(String(64), nullable=False, unique=True)
    server_ip = Column(String(15), nullable=False)  # e.g., "10.8.0.1"
    server_port = Column(Integer, nullable=False, default=51820)
    network_cidr = Column(String(18), nullable=False)  # e.g., "10.8.0.0/24"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VPNClient(Base):
    """VPN client configuration for mobile devices."""
    __tablename__ = "vpn_clients"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_name = Column(String(100), nullable=False)
    public_key = Column(String(64), nullable=False, unique=True)
    preshared_key = Column(String(64), nullable=False)
    assigned_ip = Column(String(15), nullable=False, unique=True)  # e.g., "10.8.0.2"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_handshake = Column(DateTime, nullable=True)  # Updated when client connects
    
    # Relationships
    user = relationship("User", back_populates="vpn_clients")
    
    def __repr__(self):
        return f"<VPNClient(id={self.id}, device={self.device_name}, ip={self.assigned_ip})>"
