"""
Database models for sleep mode.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class SleepConfig(Base):
    """Singleton configuration for sleep mode (id=1)."""
    __tablename__ = "sleep_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Auto-idle detection
    auto_idle_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idle_timeout_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    idle_cpu_threshold: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    idle_disk_io_threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    idle_http_threshold: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)

    # Auto-escalation
    auto_escalation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalation_after_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # Schedule
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_sleep_time: Mapped[str] = mapped_column(String(5), default="23:00", nullable=False)
    schedule_wake_time: Mapped[str] = mapped_column(String(5), default="06:00", nullable=False)
    schedule_mode: Mapped[str] = mapped_column(String(20), default="soft", nullable=False)

    # WoL
    wol_mac_address: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    wol_broadcast_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Service pausing
    pause_monitoring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pause_disk_io: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reduced_telemetry_interval: Mapped[float] = mapped_column(Float, default=30.0, nullable=False)

    # Disk spindown
    disk_spindown_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Core Operating Hours (Kernbetriebszeit)
    core_uptime_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Always-awake override (manual override over all auto-sleep paths)
    always_awake_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    always_awake_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<SleepConfig(id={self.id}, auto_idle={self.auto_idle_enabled})>"


class SleepStateLog(Base):
    """History of sleep state transitions."""
    __tablename__ = "sleep_state_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    previous_state: Mapped[str] = mapped_column(String(30), nullable=False)
    new_state: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(30), nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<SleepStateLog({self.previous_state} -> {self.new_state}, {self.reason})>"


class CoreUptimeWindow(Base):
    """A recurring time window during which auto-sleep must NOT trigger."""
    __tablename__ = "core_uptime_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)    # "HH:MM"
    weekdays: Mapped[str] = mapped_column(String(15), nullable=False)   # CSV "0,1,2,3,4" (0=Mon..6=Sun)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CoreUptimeWindow(id={self.id}, {self.start_time}-{self.end_time}, weekdays={self.weekdays})>"
