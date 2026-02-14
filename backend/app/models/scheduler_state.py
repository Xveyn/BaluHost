"""Scheduler worker state tracking model.

Stores per-scheduler state written by the scheduler worker process,
read by the web API to display status without in-process globals.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class SchedulerState(Base):
    """Tracks the runtime state of each scheduler managed by the worker process."""

    __tablename__ = "scheduler_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Unique scheduler identifier (matches SCHEDULER_REGISTRY keys)
    scheduler_name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )

    # Whether the APScheduler job is registered and active
    is_running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Whether a job function is currently executing
    is_executing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Next scheduled run time (written by worker from APScheduler)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Worker heartbeat — updated every ~10s by the worker process
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # PID of the worker process that owns this state
    worker_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Auto-updated timestamp
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<SchedulerState(name='{self.scheduler_name}', "
            f"running={self.is_running}, executing={self.is_executing})>"
        )
