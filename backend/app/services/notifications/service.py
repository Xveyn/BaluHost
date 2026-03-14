"""Notification service for BaluHost.

Handles creation, dispatch, and management of user notifications across
multiple channels (in-app, push).
"""

import logging
from datetime import datetime, time, timezone
from typing import Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, or_

from app.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationType,
    NotificationCategory,
)
from app.models.user import User

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing user notifications."""

    def __init__(self):
        """Initialize notification service."""
        self._websocket_manager = None

    @staticmethod
    def _user_filter(user_id: int, is_admin: bool = False):
        """Build SQLAlchemy filter for user-owned + system notifications.

        Admin/system notifications are stored with user_id=NULL.
        Admin users should see these alongside their personal notifications.

        Args:
            user_id: The current user's ID
            is_admin: Whether the user has admin role

        Returns:
            SQLAlchemy filter expression
        """
        if is_admin:
            return or_(
                Notification.user_id == user_id,
                Notification.user_id.is_(None),
            )
        return Notification.user_id == user_id

    def set_websocket_manager(self, manager: Any) -> None:
        """Set the WebSocket manager for real-time delivery.

        Args:
            manager: WebSocketManager instance
        """
        self._websocket_manager = manager

    async def create(
        self,
        db: Session,
        user_id: Optional[int],
        category: str,
        notification_type: str,
        title: str,
        message: str,
        action_url: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        priority: int = 0,
    ) -> Notification:
        """Create a new notification.

        Args:
            db: Database session
            user_id: User ID (None for system-wide/admin notifications)
            category: Notification category (raid, smart, backup, etc.)
            notification_type: Type (info, warning, critical)
            title: Notification title
            message: Notification message
            action_url: Optional URL for action button
            metadata: Optional metadata dict
            priority: Priority level (0=low, 1=medium, 2=high, 3=critical)

        Returns:
            Created Notification object
        """
        notification = Notification(
            user_id=user_id,
            category=category,
            notification_type=notification_type,
            title=title,
            message=message,
            action_url=action_url,
            extra_data=metadata,
            priority=priority,
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)

        logger.info(
            f"Created notification: id={notification.id}, "
            f"user_id={user_id}, category={category}, type={notification_type}"
        )

        # Dispatch to channels
        await self.dispatch(db, notification)

        return notification

    async def dispatch(self, db: Session, notification: Notification) -> None:
        """Dispatch notification to appropriate channels.

        Checks user preferences and sends to enabled channels:
        - In-app (WebSocket)
        - Push (Firebase FCM)

        Args:
            db: Database session
            notification: Notification to dispatch
        """
        if notification.user_id is None:
            # System notification - broadcast to all admins via WebSocket + Push
            await self._broadcast_to_admins(notification)
            await self._send_push_to_admins(db, notification)
            return

        # Get user preferences
        prefs = self.get_user_preferences(db, notification.user_id)

        # Check quiet hours (critical notifications with priority >= 3 bypass)
        if prefs and self._is_quiet_hours(prefs) and notification.priority < 3:
            logger.debug(f"Notification {notification.id} suppressed during quiet hours")
            # Still store, but don't dispatch actively
            return

        # Check priority threshold
        if prefs and notification.priority < prefs.min_priority:
            logger.debug(
                f"Notification {notification.id} below priority threshold "
                f"({notification.priority} < {prefs.min_priority})"
            )
            return

        # Dispatch to enabled channels
        if self._should_send_to_channel(prefs, notification.category, "in_app"):
            await self._send_in_app(notification)

        if self._should_send_to_channel(prefs, notification.category, "push"):
            await self._send_push(db, notification)

    async def _broadcast_to_admins(self, notification: Notification) -> None:
        """Broadcast notification to all admin users via WebSocket.

        Args:
            notification: Notification to broadcast
        """
        if self._websocket_manager:
            try:
                await self._websocket_manager.broadcast_to_admins(notification.to_dict())
            except Exception as e:
                logger.error(f"Failed to broadcast to admins: {e}")

    async def _send_push_to_admins(
        self, db: Session, notification: Notification
    ) -> None:
        """Send push notification to all admin users' mobile devices.

        Args:
            db: Database session
            notification: Notification to send
        """
        from app.services.notifications.firebase import FirebaseService
        from app.models.mobile import MobileDevice

        if not FirebaseService.is_available():
            return

        try:
            admin_ids = [
                uid for (uid,) in db.query(User.id).filter(
                    User.role == "admin",
                    User.is_active == True,
                ).all()
            ]
            if not admin_ids:
                return

            devices = db.query(MobileDevice).filter(
                MobileDevice.user_id.in_(admin_ids),
                MobileDevice.is_active == True,
                MobileDevice.push_token.isnot(None),
            ).all()

            for device in devices:
                result = FirebaseService.send_notification(
                    device_token=device.push_token,
                    title=notification.title,
                    body=notification.message,
                    category=notification.category,
                    priority=notification.priority,
                    notification_id=notification.id,
                    action_url=notification.action_url,
                    notification_type=notification.notification_type,
                )
                if result["success"]:
                    logger.debug(f"Admin push sent to device {device.id}")
                elif result["error"] == "unregistered":
                    logger.warning(
                        f"Device {device.id} token unregistered, clearing"
                    )
                    device.push_token = None
                    db.commit()
                else:
                    logger.error(
                        f"Admin push to device {device.id} failed: {result['error']}"
                    )
        except Exception as e:
            logger.error(f"Failed to send admin push notifications: {e}")

    async def _send_in_app(self, notification: Notification) -> None:
        """Send notification via WebSocket for in-app display.

        Args:
            notification: Notification to send
        """
        if not self._websocket_manager:
            return

        try:
            await self._websocket_manager.broadcast_to_user(
                notification.user_id,
                notification.to_dict()
            )
        except Exception as e:
            logger.error(f"Failed to send in-app notification: {e}")

    async def _send_push(self, db: Session, notification: Notification) -> None:
        """Send push notification via Firebase FCM.

        Args:
            db: Database session
            notification: Notification to send
        """
        from app.services.notifications.firebase import FirebaseService
        from app.models.mobile import MobileDevice

        if not FirebaseService.is_available():
            return

        # Get user's active mobile devices
        devices = db.query(MobileDevice).filter(
            MobileDevice.user_id == notification.user_id,
            MobileDevice.is_active == True,
            MobileDevice.push_token.isnot(None)
        ).all()

        for device in devices:
            try:
                result = FirebaseService.send_notification(
                    device_token=device.push_token,
                    title=notification.title,
                    body=notification.message,
                    category=notification.category,
                    priority=notification.priority,
                    notification_id=notification.id,
                    action_url=notification.action_url,
                    notification_type=notification.notification_type,
                )
                if result["success"]:
                    logger.debug(f"Push notification sent to device {device.id}")
                elif result["error"] == "unregistered":
                    logger.warning(
                        f"Device {device.id} token unregistered, clearing"
                    )
                    device.push_token = None
                    db.commit()
                else:
                    logger.error(
                        f"Failed to send push to device {device.id}: {result['error']}"
                    )
            except Exception as e:
                logger.error(f"Failed to send push to device {device.id}: {e}")

    def _should_send_to_channel(
        self,
        prefs: Optional[NotificationPreferences],
        category: str,
        channel: str
    ) -> bool:
        """Check if notification should be sent to a specific channel.

        Args:
            prefs: User preferences (None = use defaults)
            category: Notification category
            channel: Channel name (in_app, push)

        Returns:
            True if notification should be sent to channel
        """
        if prefs is None:
            return True  # Default: all channels enabled

        return prefs.is_channel_enabled_for_category(category, channel)

    def _is_quiet_hours(self, prefs: NotificationPreferences) -> bool:
        """Check if current time is within quiet hours.

        Args:
            prefs: User preferences

        Returns:
            True if currently in quiet hours
        """
        if not prefs.quiet_hours_enabled:
            return False

        if not prefs.quiet_hours_start or not prefs.quiet_hours_end:
            return False

        now = datetime.now(timezone.utc).time()
        start = prefs.quiet_hours_start
        end = prefs.quiet_hours_end

        # Handle overnight quiet hours (e.g., 22:00 - 07:00)
        if start > end:
            return now >= start or now <= end
        else:
            return start <= now <= end

    def get_user_notifications(
        self,
        db: Session,
        user_id: int,
        unread_only: bool = False,
        include_dismissed: bool = False,
        category: Optional[str] = None,
        notification_type: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        is_admin: bool = False,
    ) -> list[Notification]:
        """Get notifications for a user.

        Args:
            db: Database session
            user_id: User ID
            unread_only: Only return unread notifications
            include_dismissed: Include dismissed notifications
            category: Filter by category
            notification_type: Filter by type (info, warning, critical)
            created_after: Only return notifications created after this time
            created_before: Only return notifications created before this time
            limit: Maximum number of results
            offset: Number of results to skip
            is_admin: Whether the user is an admin (includes system notifications)

        Returns:
            List of Notification objects
        """
        query = db.query(Notification).filter(self._user_filter(user_id, is_admin))

        # Exclude snoozed notifications from default queries
        if hasattr(Notification, "snoozed_until"):
            query = query.filter(
                or_(
                    Notification.snoozed_until.is_(None),
                    Notification.snoozed_until <= datetime.now(timezone.utc),
                )
            )

        if unread_only:
            query = query.filter(Notification.is_read == False)

        if not include_dismissed:
            query = query.filter(Notification.is_dismissed == False)

        if category:
            query = query.filter(Notification.category == category)

        if notification_type:
            query = query.filter(Notification.notification_type == notification_type)

        if created_after:
            query = query.filter(Notification.created_at >= created_after)

        if created_before:
            query = query.filter(Notification.created_at <= created_before)

        query = query.order_by(desc(Notification.created_at))
        query = query.offset(offset).limit(limit)

        return query.all()

    def count_user_notifications(
        self,
        db: Session,
        user_id: int,
        unread_only: bool = False,
        include_dismissed: bool = False,
        category: Optional[str] = None,
        notification_type: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        is_admin: bool = False,
    ) -> int:
        """Count notifications for a user using SQL COUNT(*).

        Applies the same filters as get_user_notifications but returns
        only the count instead of loading all rows into memory.

        Args:
            db: Database session
            user_id: User ID
            unread_only: Only count unread notifications
            include_dismissed: Include dismissed notifications
            category: Filter by category
            notification_type: Filter by type (info, warning, critical)
            created_after: Only count notifications created after this time
            created_before: Only count notifications created before this time
            is_admin: Whether the user is an admin (includes system notifications)

        Returns:
            Integer count of matching notifications
        """
        query = db.query(func.count(Notification.id)).filter(
            self._user_filter(user_id, is_admin)
        )

        # Exclude snoozed notifications from default queries
        if hasattr(Notification, "snoozed_until"):
            query = query.filter(
                or_(
                    Notification.snoozed_until.is_(None),
                    Notification.snoozed_until <= datetime.now(timezone.utc),
                )
            )

        if unread_only:
            query = query.filter(Notification.is_read == False)

        if not include_dismissed:
            query = query.filter(Notification.is_dismissed == False)

        if category:
            query = query.filter(Notification.category == category)

        if notification_type:
            query = query.filter(Notification.notification_type == notification_type)

        if created_after:
            query = query.filter(Notification.created_at >= created_after)

        if created_before:
            query = query.filter(Notification.created_at <= created_before)

        return query.scalar() or 0

    def get_unread_counts(
        self,
        db: Session,
        user_id: int,
        is_admin: bool = False,
    ) -> dict[str, int]:
        """Get unread notification counts grouped by category in a single query.

        Uses SQL GROUP BY instead of issuing one query per category.

        Args:
            db: Database session
            user_id: User ID
            is_admin: Whether the user is an admin (includes system notifications)

        Returns:
            Dict mapping category names to their unread counts,
            plus a "total" key with the sum.
        """
        query = db.query(
            Notification.category,
            func.count(Notification.id),
        ).filter(
            self._user_filter(user_id, is_admin),
            Notification.is_read == False,
            Notification.is_dismissed == False,
        )

        # Exclude snoozed notifications
        if hasattr(Notification, "snoozed_until"):
            query = query.filter(
                or_(
                    Notification.snoozed_until.is_(None),
                    Notification.snoozed_until <= datetime.now(timezone.utc),
                )
            )

        results = query.group_by(Notification.category).all()

        counts = {cat: count for cat, count in results}
        counts["total"] = sum(counts.values())
        return counts

    def get_unread_count(
        self,
        db: Session,
        user_id: int,
        category: Optional[str] = None,
        is_admin: bool = False,
    ) -> int:
        """Get count of unread notifications for a user.

        Args:
            db: Database session
            user_id: User ID
            category: Optional category filter
            is_admin: Whether the user is an admin (includes system notifications)

        Returns:
            Count of unread notifications
        """
        query = db.query(Notification).filter(
            self._user_filter(user_id, is_admin),
            Notification.is_read == False,
            Notification.is_dismissed == False,
        )

        # Exclude snoozed notifications
        if hasattr(Notification, "snoozed_until"):
            query = query.filter(
                or_(
                    Notification.snoozed_until.is_(None),
                    Notification.snoozed_until <= datetime.now(timezone.utc),
                )
            )

        if category:
            query = query.filter(Notification.category == category)

        return query.count()

    def mark_as_read(
        self,
        db: Session,
        notification_id: int,
        user_id: int,
        is_admin: bool = False,
    ) -> Optional[Notification]:
        """Mark a notification as read.

        Args:
            db: Database session
            notification_id: Notification ID
            user_id: User ID (for ownership check)
            is_admin: Whether the user is an admin (can mark system notifications)

        Returns:
            Updated Notification or None if not found
        """
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            self._user_filter(user_id, is_admin),
        ).first()

        if notification:
            notification.is_read = True
            db.commit()
            db.refresh(notification)
            logger.debug(f"Marked notification {notification_id} as read")

        return notification

    def mark_all_as_read(
        self,
        db: Session,
        user_id: int,
        category: Optional[str] = None,
        is_admin: bool = False,
    ) -> int:
        """Mark all notifications as read for a user.

        Args:
            db: Database session
            user_id: User ID
            category: Optional category filter
            is_admin: Whether the user is an admin (includes system notifications)

        Returns:
            Number of notifications updated
        """
        query = db.query(Notification).filter(
            self._user_filter(user_id, is_admin),
            Notification.is_read == False,
        )

        if category:
            query = query.filter(Notification.category == category)

        count = query.update({Notification.is_read: True})
        db.commit()

        logger.info(f"Marked {count} notifications as read for user {user_id}")
        return count

    def dismiss(
        self,
        db: Session,
        notification_id: int,
        user_id: int,
        is_admin: bool = False,
    ) -> Optional[Notification]:
        """Dismiss a notification.

        Args:
            db: Database session
            notification_id: Notification ID
            user_id: User ID (for ownership check)
            is_admin: Whether the user is an admin (can dismiss system notifications)

        Returns:
            Updated Notification or None if not found
        """
        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            self._user_filter(user_id, is_admin),
        ).first()

        if notification:
            notification.is_dismissed = True
            notification.is_read = True
            db.commit()
            db.refresh(notification)
            logger.debug(f"Dismissed notification {notification_id}")

        return notification

    def snooze(
        self,
        db: Session,
        notification_id: int,
        user_id: int,
        duration_hours: int,
        is_admin: bool = False,
    ) -> Optional[Notification]:
        """Snooze a notification for a given duration.

        Args:
            db: Database session
            notification_id: Notification ID
            user_id: User ID (for ownership check)
            duration_hours: Number of hours to snooze
            is_admin: Whether the user is an admin (can snooze system notifications)

        Returns:
            Updated Notification or None if not found
        """
        from datetime import timedelta

        notification = db.query(Notification).filter(
            Notification.id == notification_id,
            self._user_filter(user_id, is_admin),
        ).first()

        if notification and hasattr(notification, "snoozed_until"):
            notification.snoozed_until = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
            db.commit()
            db.refresh(notification)
            logger.debug(f"Snoozed notification {notification_id} for {duration_hours}h")

        return notification

    def get_user_preferences(
        self,
        db: Session,
        user_id: int,
    ) -> Optional[NotificationPreferences]:
        """Get notification preferences for a user.

        Args:
            db: Database session
            user_id: User ID

        Returns:
            NotificationPreferences or None if not set
        """
        return db.query(NotificationPreferences).filter(
            NotificationPreferences.user_id == user_id
        ).first()

    def update_user_preferences(
        self,
        db: Session,
        user_id: int,
        push_enabled: Optional[bool] = None,
        in_app_enabled: Optional[bool] = None,
        category_preferences: Optional[dict[str, Any]] = None,
        quiet_hours_enabled: Optional[bool] = None,
        quiet_hours_start: Optional[time] = None,
        quiet_hours_end: Optional[time] = None,
        min_priority: Optional[int] = None,
    ) -> NotificationPreferences:
        """Update or create notification preferences for a user.

        Args:
            db: Database session
            user_id: User ID
            push_enabled: Enable push notifications
            in_app_enabled: Enable in-app notifications
            category_preferences: Category-specific settings
            quiet_hours_enabled: Enable quiet hours
            quiet_hours_start: Quiet hours start time
            quiet_hours_end: Quiet hours end time
            min_priority: Minimum priority level

        Returns:
            Updated NotificationPreferences
        """
        prefs = self.get_user_preferences(db, user_id)

        if not prefs:
            prefs = NotificationPreferences(user_id=user_id)
            db.add(prefs)

        if push_enabled is not None:
            prefs.push_enabled = push_enabled
        if in_app_enabled is not None:
            prefs.in_app_enabled = in_app_enabled
        if category_preferences is not None:
            prefs.category_preferences = category_preferences
        if quiet_hours_enabled is not None:
            prefs.quiet_hours_enabled = quiet_hours_enabled
        if quiet_hours_start is not None:
            prefs.quiet_hours_start = quiet_hours_start
        if quiet_hours_end is not None:
            prefs.quiet_hours_end = quiet_hours_end
        if min_priority is not None:
            prefs.min_priority = min_priority

        db.commit()
        db.refresh(prefs)

        logger.info(f"Updated notification preferences for user {user_id}")
        return prefs

    async def cleanup_old_notifications(
        self,
        db: Session,
        retention_days: int = 90,
    ) -> int:
        """Delete notifications older than retention period.

        Args:
            db: Database session
            retention_days: Number of days to retain notifications

        Returns:
            Number of notifications deleted
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        count = db.query(Notification).filter(
            Notification.created_at < cutoff
        ).delete()

        db.commit()
        logger.info(f"Cleaned up {count} old notifications")
        return count


# Singleton instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get the notification service singleton.

    Returns:
        NotificationService instance
    """
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
