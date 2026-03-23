"""
Server Profile Model - For managing remote BaluHost servers

Allows users to save multiple BaluHost server profiles with SSH credentials
and optional VPN configuration for remote access.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ServerProfile(Base):
    """
    Server Profile Model
    
    Stores SSH credentials and configuration for remote BaluHost servers.
    SSH keys and VPN references are encrypted before storage.
    """
    
    __tablename__ = "server_profiles"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "Home NAS", "Office Server"
    ssh_host: Mapped[str] = mapped_column(String(255), nullable=False)  # IP or hostname
    ssh_port: Mapped[Optional[int]] = mapped_column(Integer, default=22)
    ssh_username: Mapped[str] = mapped_column(String(255), nullable=False)
    ssh_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted private key

    # VPN Configuration
    vpn_profile_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("vpn_profiles.id"), nullable=True, index=True)

    # Server startup command
    power_on_command: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # e.g., "systemctl start baluhost-backend"

    # Wake-on-LAN fallback
    wol_mac_address: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)  # e.g., "AA:BB:CC:DD:EE:FF"

    # Metadata
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="server_profiles")
    vpn_profile = relationship("VPNProfile", back_populates="server_profiles")
    
    def __repr__(self) -> str:
        return f"<ServerProfile(id={self.id}, name={self.name}, ssh_host={self.ssh_host})>"
