"""
Database models for fan control.
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional

from app.models.base import Base


class FanConfig(Base):
    """Fan configuration storage."""
    __tablename__ = "fan_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fan_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)  # auto|manual|emergency
    curve_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of {temp, pwm} points
    min_pwm_percent: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_pwm_percent: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    emergency_temp_celsius: Mapped[float] = mapped_column(Float, default=85.0, nullable=False)
    temp_sensor_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<FanConfig(fan_id='{self.fan_id}', name='{self.name}', mode='{self.mode}')>"


class FanSample(Base):
    """Historical fan performance samples."""
    __tablename__ = "fan_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    fan_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pwm_percent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-100
    rpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature_celsius: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # auto|manual|emergency

    def __repr__(self) -> str:
        return f"<FanSample(fan_id='{self.fan_id}', rpm={self.rpm}, pwm={self.pwm_percent}%)>"
