"""Scheduler execution history database model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Text, Index, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import enum

from app.models.base import Base


class SchedulerStatus(str, enum.Enum):
    """Status of a scheduler execution."""
    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TriggerType(str, enum.Enum):
    """How the scheduler execution was triggered."""
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class SchedulerExecution(Base):
    """Model for tracking scheduler execution history."""

    __tablename__ = "scheduler_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Which scheduler ran
    scheduler_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    # Optional job identifier for APScheduler job tracking
    job_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Execution timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Execution status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SchedulerStatus.RUNNING.value,
        index=True
    )

    # How it was triggered
    trigger_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TriggerType.SCHEDULED.value
    )

    # Results
    result_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    # For manual runs, who triggered it
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )

    # Duration in milliseconds (calculated field, stored for query efficiency)
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    __table_args__ = (
        Index('idx_scheduler_exec_name_started', 'scheduler_name', 'started_at'),
        Index('idx_scheduler_exec_status_started', 'status', 'started_at'),
        Index('idx_scheduler_exec_name_status', 'scheduler_name', 'status'),
    )

    def __repr__(self) -> str:
        return (
            f"<SchedulerExecution(id={self.id}, "
            f"scheduler='{self.scheduler_name}', "
            f"status='{self.status}')>"
        )

    def complete(self, result: Optional[str] = None) -> None:
        """Mark execution as completed successfully."""
        self.status = SchedulerStatus.COMPLETED.value
        self.completed_at = datetime.now(datetime.now().astimezone().tzinfo)
        self.result_summary = result
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)

    def fail(self, error: str) -> None:
        """Mark execution as failed with error message."""
        self.status = SchedulerStatus.FAILED.value
        self.completed_at = datetime.now(datetime.now().astimezone().tzinfo)
        self.error_message = error
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)

    def cancel(self) -> None:
        """Mark execution as cancelled."""
        self.status = SchedulerStatus.CANCELLED.value
        self.completed_at = datetime.now(datetime.now().astimezone().tzinfo)
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)


class SchedulerConfig(Base):
    """Model for storing dynamic scheduler configuration."""

    __tablename__ = "scheduler_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Unique scheduler identifier
    scheduler_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True
    )

    # Whether this scheduler is enabled
    is_enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=True
    )

    # Interval in seconds between runs
    interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    # JSON-encoded scheduler-specific configuration (e.g. {"backup_type": "full"})
    extra_config: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Last time config was updated
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Who updated the config
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<SchedulerConfig(name='{self.scheduler_name}', "
            f"enabled={self.is_enabled}, "
            f"interval={self.interval_seconds}s)>"
        )
