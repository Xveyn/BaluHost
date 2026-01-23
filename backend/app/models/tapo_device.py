"""
Tapo Device Model

SQLAlchemy model for Tapo smart devices (P115, P110, etc.)
used for power monitoring integration.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from app.models.base import Base


class TapoDevice(Base):
    """
    Represents a Tapo smart device configured for power monitoring.

    Credentials are stored encrypted using Fernet (AES-128) with the
    VPN_ENCRYPTION_KEY from environment.
    """
    __tablename__ = "tapo_devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)  # e.g. "NAS Power Monitor"
    device_type = Column(String(50), default="P115", nullable=False)
    ip_address = Column(String(45), nullable=False)  # IPv4 or IPv6

    # Encrypted credentials (Fernet/VPNEncryption pattern)
    email_encrypted = Column(Text, nullable=False)
    password_encrypted = Column(Text, nullable=False)

    # Device status
    is_active = Column(Boolean, default=True, nullable=False)
    is_monitoring = Column(Boolean, default=True, nullable=False)
    last_connected = Column(DateTime, nullable=True)
    last_error = Column(String(500), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, nullable=False)

    # Relationships
    power_samples = relationship("PowerSample", back_populates="device", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TapoDevice(id={self.id}, name='{self.name}', type='{self.device_type}', ip='{self.ip_address}')>"
