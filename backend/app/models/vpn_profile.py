"""
VPN Profile Model - For managing VPN configurations

Stores encrypted VPN profiles (OpenVPN, WireGuard) for secure remote access.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
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
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "Home OpenVPN", "Office WireGuard"
    vpn_type: Mapped[VPNType] = mapped_column(SQLEnum(VPNType), nullable=False)

    # Encrypted configurations
    config_file_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # .ovpn or .conf file (encrypted)
    certificate_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Client certificate (encrypted)
    private_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Private key (encrypted)

    # Options
    auto_connect: Mapped[Optional[bool]] = mapped_column(default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="vpn_profiles")
    server_profiles = relationship("ServerProfile", back_populates="vpn_profile")
    
    def __repr__(self) -> str:
        return f"<VPNProfile(id={self.id}, name={self.name}, type={self.vpn_type.value})>"
