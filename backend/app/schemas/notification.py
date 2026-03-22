"""Notification request and response schemas."""
from datetime import datetime, time, timezone
from typing import Optional, Literal, Any

from pydantic import BaseModel, Field


# Literal types for validation
NotificationTypeEnum = Literal["info", "warning", "critical"]
NotificationCategoryEnum = Literal[
    "raid", "smart", "backup", "scheduler", "system", "security", "sync", "vpn"
]


class NotificationBase(BaseModel):
    """Base notification schema."""

    notification_type: NotificationTypeEnum = Field(
        default="info",
        description="Notification severity type"
    )
    category: NotificationCategoryEnum = Field(
        description="Notification category"
    )
    title: str = Field(
        max_length=255,
        description="Notification title"
    )
    message: str = Field(description="Notification message body")
    action_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="URL for action button"
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Priority level (0=low, 1=medium, 2=high, 3=critical)"
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional metadata"
    )


class NotificationCreate(NotificationBase):
    """Schema for creating a notification."""

    user_id: Optional[int] = Field(
        default=None,
        description="Target user ID (None for broadcast to admins)"
    )


class NotificationResponse(NotificationBase):
    """Schema for notification API responses."""

    id: int
    created_at: datetime
    user_id: Optional[int] = None
    is_read: bool = False
    is_dismissed: bool = False
    snoozed_until: Optional[datetime] = Field(
        default=None,
        description="Snooze expiry time (null if not snoozed)"
    )

    # Computed field for time ago display
    time_ago: Optional[str] = Field(
        default=None,
        description="Human-readable time since creation"
    )

    model_config = {"from_attributes": True}

    @classmethod
    def from_db(cls, notification) -> "NotificationResponse":
        """Convert database model to response schema."""
        time_ago = None
        if notification.created_at:
            created = notification.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - created
            if delta.days > 0:
                time_ago = f"{delta.days}d ago" if delta.days < 7 else notification.created_at.strftime("%d.%m.%Y")
            elif delta.seconds >= 3600:
                time_ago = f"{delta.seconds // 3600}h ago"
            elif delta.seconds >= 60:
                time_ago = f"{delta.seconds // 60}m ago"
            else:
                time_ago = "just now"

        return cls(
            id=notification.id,
            created_at=notification.created_at,
            user_id=notification.user_id,
            notification_type=notification.notification_type,
            category=notification.category,
            title=notification.title,
            message=notification.message,
            action_url=notification.action_url,
            is_read=notification.is_read,
            is_dismissed=notification.is_dismissed,
            priority=notification.priority,
            metadata=notification.extra_data,
            time_ago=time_ago,
            snoozed_until=getattr(notification, "snoozed_until", None),
        )


class NotificationListResponse(BaseModel):
    """Paginated notification list response."""

    notifications: list[NotificationResponse]
    total: int
    unread_count: int
    page: int = 1
    page_size: int = 50


class UnreadCountResponse(BaseModel):
    """Response for unread notification count."""

    count: int
    by_category: Optional[dict[str, int]] = Field(
        default=None,
        description="Breakdown by category"
    )


class MarkReadRequest(BaseModel):
    """Request to mark notifications as read."""

    notification_ids: Optional[list[int]] = Field(
        default=None,
        description="Specific notification IDs (None = mark all)"
    )
    category: Optional[NotificationCategoryEnum] = Field(
        default=None,
        description="Filter by category when marking all"
    )


class MarkReadResponse(BaseModel):
    """Response from marking notifications as read."""

    success: bool
    count: int = Field(description="Number of notifications marked as read")


# Preference schemas
class CategoryPreference(BaseModel):
    """Preferences for a single notification category."""

    push: bool = True
    in_app: bool = True


class NotificationPreferencesBase(BaseModel):
    """Base notification preferences schema."""

    push_enabled: bool = Field(
        default=True,
        description="Global push notifications enabled"
    )
    in_app_enabled: bool = Field(
        default=True,
        description="Global in-app notifications enabled"
    )
    quiet_hours_enabled: bool = Field(
        default=False,
        description="Enable quiet hours"
    )
    quiet_hours_start: Optional[str] = Field(
        default=None,
        description="Quiet hours start time (HH:MM)"
    )
    quiet_hours_end: Optional[str] = Field(
        default=None,
        description="Quiet hours end time (HH:MM)"
    )
    min_priority: int = Field(
        default=0,
        ge=0,
        le=3,
        description="Minimum priority level for notifications"
    )
    category_preferences: Optional[dict[str, CategoryPreference]] = Field(
        default=None,
        description="Per-category notification settings"
    )


class NotificationPreferencesUpdate(BaseModel):
    """Schema for updating notification preferences (all fields optional for partial updates)."""

    push_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    min_priority: Optional[int] = Field(default=None, ge=0, le=3)
    category_preferences: Optional[dict[str, CategoryPreference]] = None


class NotificationPreferencesResponse(NotificationPreferencesBase):
    """Schema for notification preferences API response."""

    id: int
    user_id: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_db(cls, prefs) -> "NotificationPreferencesResponse":
        """Convert database model to response schema."""
        return cls(
            id=prefs.id,
            user_id=prefs.user_id,
            push_enabled=prefs.push_enabled,
            in_app_enabled=prefs.in_app_enabled,
            quiet_hours_enabled=prefs.quiet_hours_enabled,
            quiet_hours_start=prefs.quiet_hours_start.isoformat() if prefs.quiet_hours_start else None,
            quiet_hours_end=prefs.quiet_hours_end.isoformat() if prefs.quiet_hours_end else None,
            min_priority=prefs.min_priority,
            category_preferences=prefs.category_preferences,
        )


# WebSocket message schemas
class WebSocketMessage(BaseModel):
    """WebSocket message format."""

    type: Literal["notification", "unread_count", "ping", "pong"] = Field(
        description="Message type"
    )
    payload: Any = Field(description="Message payload")


class NotificationWebSocketPayload(BaseModel):
    """Payload for notification WebSocket messages."""

    notification: NotificationResponse
    unread_count: int
