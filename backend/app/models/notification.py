"""Notification database models."""
from datetime import datetime, time
from enum import Enum
from typing import Optional, Any

from sqlalchemy import String, DateTime, Integer, Boolean, Text, Time, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class NotificationType(str, Enum):
    """Notification severity types."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NotificationCategory(str, Enum):
    """Notification categories."""
    RAID = "raid"
    SMART = "smart"
    BACKUP = "backup"
    SCHEDULER = "scheduler"
    SYSTEM = "system"
    SECURITY = "security"
    SYNC = "sync"
    VPN = "vpn"


class Notification(Base):
    """Central notification storage model."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=NotificationType.INFO.value
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extra_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationship
    user: Mapped[Optional["User"]] = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type='{self.notification_type}', category='{self.category}')>"

    def to_dict(self) -> dict[str, Any]:
        """Convert notification to dictionary for API response."""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "user_id": self.user_id,
            "notification_type": self.notification_type,
            "category": self.category,
            "title": self.title,
            "message": self.message,
            "action_url": self.action_url,
            "is_read": self.is_read,
            "is_dismissed": self.is_dismissed,
            "priority": self.priority,
            "metadata": self.extra_data,
        }


class NotificationPreferences(Base):
    """User notification preferences model."""

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Category preferences as JSON: {"raid": {"email": true, "push": true, "in_app": true}, ...}
    category_preferences: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Quiet hours
    quiet_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # Minimum priority for notifications (0 = all, 1 = warning+, 2 = critical only)
    min_priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="notification_preferences")

    def __repr__(self) -> str:
        return f"<NotificationPreferences(id={self.id}, user_id={self.user_id})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert preferences to dictionary for API response."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email_enabled": self.email_enabled,
            "push_enabled": self.push_enabled,
            "in_app_enabled": self.in_app_enabled,
            "category_preferences": self.category_preferences,
            "quiet_hours_enabled": self.quiet_hours_enabled,
            "quiet_hours_start": self.quiet_hours_start.isoformat() if self.quiet_hours_start else None,
            "quiet_hours_end": self.quiet_hours_end.isoformat() if self.quiet_hours_end else None,
            "min_priority": self.min_priority,
        }

    def is_channel_enabled_for_category(
        self,
        category: str,
        channel: str
    ) -> bool:
        """Check if a specific channel is enabled for a category.

        Args:
            category: Notification category (raid, smart, etc.)
            channel: Channel type (email, push, in_app)

        Returns:
            True if channel is enabled for category
        """
        # Check global channel setting first
        global_enabled = getattr(self, f"{channel}_enabled", True)
        if not global_enabled:
            return False

        # Check category-specific override
        if self.category_preferences:
            cat_prefs = self.category_preferences.get(category, {})
            return cat_prefs.get(channel, True)

        return True
