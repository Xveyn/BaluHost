"""Update history and configuration database models."""
from datetime import datetime
from typing import Optional
import enum

from sqlalchemy import String, DateTime, Integer, Text, Index, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class UpdateStatus(str, enum.Enum):
    """Status of an update operation."""
    PENDING = "pending"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    BACKING_UP = "backing_up"
    INSTALLING = "installing"
    MIGRATING = "migrating"
    RESTARTING = "restarting"
    HEALTH_CHECK = "health_check"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class UpdateChannel(str, enum.Enum):
    """Update channel for version selection."""
    STABLE = "stable"
    BETA = "beta"


class UpdateHistory(Base):
    """Model for tracking update history."""

    __tablename__ = "update_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Version information
    from_version: Mapped[str] = mapped_column(String(50), nullable=False)
    to_version: Mapped[str] = mapped_column(String(50), nullable=False)
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UpdateChannel.STABLE.value
    )

    # Git commit references for rollback
    from_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    to_commit: Mapped[str] = mapped_column(String(40), nullable=False)

    # Timestamps
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
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UpdateStatus.PENDING.value,
        index=True
    )
    current_step: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )

    # Error handling and rollback
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    rollback_commit: Mapped[Optional[str]] = mapped_column(
        String(40),
        nullable=True
    )
    backup_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    # Who initiated the update
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )

    # Changelog and metadata
    changelog: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    extra_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
    )

    __table_args__ = (
        Index('idx_update_history_status_started', 'status', 'started_at'),
        Index('idx_update_history_user_started', 'user_id', 'started_at'),
    )

    def __repr__(self) -> str:
        return (
            f"<UpdateHistory(id={self.id}, "
            f"from='{self.from_version}', "
            f"to='{self.to_version}', "
            f"status='{self.status}')>"
        )

    def set_progress(self, percent: int, step: str) -> None:
        """Update progress information."""
        self.progress_percent = min(100, max(0, percent))
        self.current_step = step

    def complete(self) -> None:
        """Mark update as completed successfully."""
        self.status = UpdateStatus.COMPLETED.value
        self.completed_at = datetime.now(datetime.now().astimezone().tzinfo)
        self.progress_percent = 100
        self.current_step = "Update completed"
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())

    def fail(self, error: str) -> None:
        """Mark update as failed with error message."""
        self.status = UpdateStatus.FAILED.value
        self.completed_at = datetime.now(datetime.now().astimezone().tzinfo)
        self.error_message = error
        self.current_step = f"Failed: {error[:100]}"
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())

    def mark_rolled_back(self, commit: str) -> None:
        """Mark update as rolled back."""
        self.status = UpdateStatus.ROLLED_BACK.value
        self.completed_at = datetime.now(datetime.now().astimezone().tzinfo)
        self.rollback_commit = commit
        self.current_step = f"Rolled back to {commit[:8]}"
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())

    def cancel(self) -> None:
        """Mark update as cancelled."""
        self.status = UpdateStatus.CANCELLED.value
        self.completed_at = datetime.now(datetime.now().astimezone().tzinfo)
        self.current_step = "Update cancelled"
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())


class UpdateConfig(Base):
    """Model for storing update service configuration."""

    __tablename__ = "update_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Auto-check settings
    auto_check_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    check_interval_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=24
    )

    # Channel selection
    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UpdateChannel.STABLE.value
    )

    # Safety options
    auto_backup_before_update: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )
    require_healthy_services: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True
    )

    # Last check info
    last_check_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    last_available_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )

    # Auto-update settings (optional)
    auto_update_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    auto_update_window_start: Mapped[Optional[str]] = mapped_column(
        String(5),  # HH:MM format
        nullable=True
    )
    auto_update_window_end: Mapped[Optional[str]] = mapped_column(
        String(5),  # HH:MM format
        nullable=True
    )

    # Config metadata
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<UpdateConfig(channel='{self.channel}', "
            f"auto_check={self.auto_check_enabled}, "
            f"interval={self.check_interval_hours}h)>"
        )
