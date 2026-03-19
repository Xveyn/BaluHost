"""Smart Device models for the generic smart device registry."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SmartDevice(Base):
    """Generic smart device registry, shared by all smart_device plugins."""
    __tablename__ = "smart_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plugin_name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_type_id: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    mac_address: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)

    capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    config_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Fernet-encrypted JSON

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_online: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    samples: Mapped[List["SmartDeviceSample"]] = relationship("SmartDeviceSample", back_populates="device", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_smart_device_plugin", "plugin_name", "is_active"),
    )

    def __repr__(self):
        return f"<SmartDevice(id={self.id}, name='{self.name}', plugin='{self.plugin_name}', type='{self.device_type_id}')>"


class SmartDeviceSample(Base):
    """Time-series state samples for any smart device."""
    __tablename__ = "smart_device_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("smart_devices.id", ondelete="CASCADE"), nullable=False)
    capability: Mapped[str] = mapped_column(String(50), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    device: Mapped["SmartDevice"] = relationship("SmartDevice", back_populates="samples")

    __table_args__ = (
        Index("idx_sample_device_time", "device_id", "timestamp"),
        Index("idx_sample_capability", "device_id", "capability", "timestamp"),
    )
