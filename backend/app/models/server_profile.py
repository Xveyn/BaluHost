"""
Server Profile Model - For managing remote BaluHost servers

Allows users to save multiple BaluHost server profiles with SSH credentials
and optional VPN configuration for remote access.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class ServerProfile(Base):
    """
    Server Profile Model
    
    Stores SSH credentials and configuration for remote BaluHost servers.
    SSH keys and VPN references are encrypted before storage.
    """
    
    __tablename__ = "server_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)  # e.g., "Home NAS", "Office Server"
    ssh_host = Column(String(255), nullable=False)  # IP or hostname
    ssh_port = Column(Integer, default=22)
    ssh_username = Column(String(255), nullable=False)
    ssh_key_encrypted = Column(Text, nullable=False)  # Encrypted private key
    
    # VPN Configuration
    vpn_profile_id = Column(Integer, ForeignKey("vpn_profiles.id"), nullable=True, index=True)
    
    # Server startup command
    power_on_command = Column(String(500), nullable=True)  # e.g., "systemctl start baluhost-backend"
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_used = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="server_profiles")
    vpn_profile = relationship("VPNProfile", back_populates="server_profiles")
    
    def __repr__(self) -> str:
        return f"<ServerProfile(id={self.id}, name={self.name}, ssh_host={self.ssh_host})>"
