"""Power management database models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Float, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class PowerProfileLog(Base):
    """
    Log of power profile changes.

    Tracks when and why power profiles changed for debugging
    and analytics purposes.
    """

    __tablename__ = "power_profile_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    profile: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Profile: idle, low, medium, surge

    previous_profile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    # Reason: demand_registered, demand_expired, manual, auto_scaling_cpu, service_start

    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    # Source: The demand source that triggered this change

    frequency_mhz: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # CPU frequency at time of change

    user: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # User who triggered manual change (if applicable)

    __table_args__ = (
        Index('idx_power_profile_timestamp', 'profile', 'timestamp'),
    )

    def __repr__(self) -> str:
        return f"<PowerProfileLog(id={self.id}, profile='{self.profile}', reason='{self.reason}')>"


class PowerDemandLog(Base):
    """
    Log of power demand registrations and unregistrations.

    Tracks which services requested which power levels
    for debugging and optimization.
    """

    __tablename__ = "power_demand_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # Action: registered, unregistered, expired

    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Demand source identifier

    level: Mapped[str] = mapped_column(String(20), nullable=False)
    # Requested power level

    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    timeout_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    resulting_profile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Profile after this demand action

    __table_args__ = (
        Index('idx_power_demand_source_timestamp', 'source', 'timestamp'),
    )

    def __repr__(self) -> str:
        return f"<PowerDemandLog(id={self.id}, action='{self.action}', source='{self.source}')>"


class PowerProfileConfig(Base):
    """
    Configurable power profile settings.

    Allows customization of profile parameters beyond defaults,
    stored in the database for persistence.
    """

    __tablename__ = "power_profile_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    profile: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    # Profile: idle, low, medium, surge

    governor: Mapped[str] = mapped_column(String(20), nullable=False, default="powersave")
    energy_performance_preference: Mapped[str] = mapped_column(
        String(30), nullable=False, default="balance_power"
    )
    min_freq_mhz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_freq_mhz: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Whether this custom config is active (vs using default)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<PowerProfileConfig(profile='{self.profile}', governor='{self.governor}')>"


class PowerAutoScalingConfig(Base):
    """
    Auto-scaling configuration settings.

    Stores the current auto-scaling settings persistently.
    Only one row should exist (singleton pattern).
    """

    __tablename__ = "power_auto_scaling_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    cpu_surge_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    # CPU usage % to trigger SURGE profile

    cpu_medium_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # CPU usage % to trigger MEDIUM profile

    cpu_low_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    # CPU usage % to trigger LOW profile

    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # Cooldown period before downscaling

    use_cpu_monitoring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Whether to use CPU monitoring for auto-scaling

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<PowerAutoScalingConfig(enabled={self.enabled}, surge={self.cpu_surge_threshold}%)>"


class PowerDynamicModeConfig(Base):
    """
    Dynamic mode configuration for kernel-governor-based CPU scaling.

    When enabled, bypasses the discrete profile system and lets the
    kernel governor (schedutil/conservative/ondemand) handle frequency
    scaling natively. Only one row should exist (singleton pattern).
    """

    __tablename__ = "power_dynamic_mode_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    governor: Mapped[str] = mapped_column(String(30), nullable=False, default="powersave")
    min_freq_mhz: Mapped[int] = mapped_column(Integer, nullable=False, default=400)
    max_freq_mhz: Mapped[int] = mapped_column(Integer, nullable=False, default=4600)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<PowerDynamicModeConfig(enabled={self.enabled}, governor='{self.governor}')>"
