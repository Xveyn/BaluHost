"""
VPN Profile Model - For managing VPN configurations

Stores encrypted VPN profiles (OpenVPN, WireGuard) for secure remote access.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from app.models.base import Base


class VPNType(str, enum.Enum):
    """Supported VPN types"""
    OPENVPN = "openvpn"
    WIREGUARD = "wireguard"
    CUSTOM = "custom"


class VPNProfile(Base):
    """
    VPN Profile Model
    
    Stores encrypted VPN configurations for secure tunnel access.
    All sensitive data (config, certificates, keys) are encrypted before storage.
    """
    
    __tablename__ = "vpn_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)  # e.g., "Home OpenVPN", "Office WireGuard"
    vpn_type = Column(SQLEnum(VPNType), nullable=False)
    
    # Encrypted configurations
    config_file_encrypted = Column(Text, nullable=False)  # .ovpn or .conf file (encrypted)
    certificate_encrypted = Column(Text, nullable=True)  # Client certificate (encrypted)
    private_key_encrypted = Column(Text, nullable=True)  # Private key (encrypted)
    
    # Options
    auto_connect = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="vpn_profiles")
    server_profiles = relationship("ServerProfile", back_populates="vpn_profile")
    
    def __repr__(self) -> str:
        return f"<VPNProfile(id={self.id}, name={self.name}, type={self.vpn_type.value})>"
