"""Power preset database model for preset-based power management."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class PowerPreset(Base):
    """
    Power preset configuration.

    Presets define CPU clock speeds for each service power property level.
    Users can switch between presets to control power consumption vs performance.

    System presets (Energy Saver, Balanced, Performance) cannot be deleted.
    Users can create custom presets with their own clock configurations.
    """

    __tablename__ = "power_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # System presets cannot be deleted
    is_system_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Only one preset can be active at a time
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    # Clock definitions per service power property (in MHz)
    base_clock_mhz: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    idle_clock_mhz: Mapped[int] = mapped_column(Integer, nullable=False, default=800)
    low_clock_mhz: Mapped[int] = mapped_column(Integer, nullable=False, default=1200)
    medium_clock_mhz: Mapped[int] = mapped_column(Integer, nullable=False, default=2500)
    surge_clock_mhz: Mapped[int] = mapped_column(Integer, nullable=False, default=4200)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    __table_args__ = (
        Index('idx_power_preset_active', 'is_active'),
        Index('idx_power_preset_system', 'is_system_preset'),
    )

    def __repr__(self) -> str:
        return f"<PowerPreset(id={self.id}, name='{self.name}', is_active={self.is_active})>"
