"""Smart Device models for the generic smart device registry."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.models.base import Base


class SmartDevice(Base):
    """Generic smart device registry, shared by all smart_device plugins."""
    __tablename__ = "smart_devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    plugin_name = Column(String(100), nullable=False)
    device_type_id = Column(String(100), nullable=False)
    address = Column(String(255), nullable=False)
    mac_address = Column(String(17), nullable=True)

    capabilities = Column(JSON, nullable=False, default=list)
    config_encrypted = Column(Text, nullable=True)  # Fernet-encrypted JSON

    is_active = Column(Boolean, default=True, nullable=False)
    is_online = Column(Boolean, default=False, nullable=False)
    last_seen = Column(DateTime, nullable=True)
    last_error = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    created_by_user_id = Column(Integer, nullable=False)

    samples = relationship("SmartDeviceSample", back_populates="device", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_smart_device_plugin", "plugin_name", "is_active"),
    )

    def __repr__(self):
        return f"<SmartDevice(id={self.id}, name='{self.name}', plugin='{self.plugin_name}', type='{self.device_type_id}')>"


class SmartDeviceSample(Base):
    """Time-series state samples for any smart device."""
    __tablename__ = "smart_device_samples"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("smart_devices.id", ondelete="CASCADE"), nullable=False)
    capability = Column(String(50), nullable=False)
    data_json = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    device = relationship("SmartDevice", back_populates="samples")

    __table_args__ = (
        Index("idx_sample_device_time", "device_id", "timestamp"),
        Index("idx_sample_capability", "device_id", "capability", "timestamp"),
    )
