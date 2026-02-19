"""Tests for notification service."""
import pytest
from datetime import datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.orm import Session

from app.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationType,
    NotificationCategory,
)
from app.models.user import User
from app.services.notification_service import NotificationService, get_notification_service


@pytest.fixture
def notification_service():
    """Create a fresh notification service instance."""
    service = NotificationService()
    return service


@pytest.fixture
def mock_websocket_manager():
    """Create a mock WebSocket manager."""
    manager = AsyncMock()
    manager.broadcast_to_user = AsyncMock()
    manager.broadcast_to_admins = AsyncMock()
    return manager


@pytest.fixture
def mock_email_service():
    """Create a mock email service."""
    service = AsyncMock()
    service.send_notification_email = AsyncMock()
    return service


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.mark.asyncio
    async def test_create_notification(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test creating a notification."""
        notification = await notification_service.create(
            db=db_session,
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="Test Notification",
            message="This is a test message",
            priority=0,
        )

        assert notification is not None
        assert notification.id is not None
        assert notification.user_id == test_user.id
        assert notification.category == "system"
        assert notification.notification_type == "info"
        assert notification.title == "Test Notification"
        assert notification.message == "This is a test message"
        assert notification.is_read is False
        assert notification.is_dismissed is False

    @pytest.mark.asyncio
    async def test_create_notification_with_metadata(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test creating a notification with metadata."""
        metadata = {"array_name": "md0", "device": "sda1"}

        notification = await notification_service.create(
            db=db_session,
            user_id=test_user.id,
            category="raid",
            notification_type="warning",
            title="RAID Warning",
            message="Array degraded",
            metadata=metadata,
            priority=2,
        )

        assert notification.extra_data == metadata
        assert notification.priority == 2

    @pytest.mark.asyncio
    async def test_get_user_notifications(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test retrieving user notifications."""
        # Create multiple notifications
        for i in range(5):
            await notification_service.create(
                db=db_session,
                user_id=test_user.id,
                category="system",
                notification_type="info",
                title=f"Notification {i}",
                message=f"Message {i}",
            )

        notifications = notification_service.get_user_notifications(
            db=db_session,
            user_id=test_user.id,
        )

        assert len(notifications) == 5

    @pytest.mark.asyncio
    async def test_get_unread_count(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test getting unread notification count."""
        # Create notifications
        for i in range(3):
            await notification_service.create(
                db=db_session,
                user_id=test_user.id,
                category="system",
                notification_type="info",
                title=f"Notification {i}",
                message=f"Message {i}",
            )

        count = notification_service.get_unread_count(db_session, test_user.id)
        assert count == 3

    def test_mark_as_read(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test marking a notification as read."""
        # Create notification directly
        notification = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="Test",
            message="Test message",
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        # Mark as read
        result = notification_service.mark_as_read(
            db_session, notification.id, test_user.id
        )

        assert result is not None
        assert result.is_read is True

    def test_mark_as_read_wrong_user(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test that marking notification as read fails for wrong user."""
        notification = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="Test",
            message="Test message",
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        # Try to mark as read with wrong user
        result = notification_service.mark_as_read(
            db_session, notification.id, test_user.id + 9999
        )

        assert result is None

    def test_mark_all_as_read(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test marking all notifications as read."""
        # Create multiple notifications
        for i in range(5):
            notification = Notification(
                user_id=test_user.id,
                category="system",
                notification_type="info",
                title=f"Test {i}",
                message=f"Message {i}",
            )
            db_session.add(notification)
        db_session.commit()

        count = notification_service.mark_all_as_read(db_session, test_user.id)

        assert count == 5

        # Verify all are read
        unread = notification_service.get_unread_count(db_session, test_user.id)
        assert unread == 0

    def test_dismiss_notification(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test dismissing a notification."""
        notification = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="Test",
            message="Test message",
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        result = notification_service.dismiss(
            db_session, notification.id, test_user.id
        )

        assert result is not None
        assert result.is_dismissed is True
        assert result.is_read is True


class TestNotificationPreferences:
    """Tests for notification preferences."""

    def test_create_default_preferences(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test creating default preferences."""
        prefs = notification_service.update_user_preferences(
            db_session, test_user.id
        )

        assert prefs is not None
        assert prefs.user_id == test_user.id
        assert prefs.email_enabled is True
        assert prefs.push_enabled is True
        assert prefs.in_app_enabled is True
        assert prefs.quiet_hours_enabled is False

    def test_update_preferences(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test updating preferences."""
        prefs = notification_service.update_user_preferences(
            db_session,
            test_user.id,
            email_enabled=False,
            push_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(7, 0),
            min_priority=1,
        )

        assert prefs.email_enabled is False
        assert prefs.push_enabled is True
        assert prefs.quiet_hours_enabled is True
        assert prefs.quiet_hours_start == time(22, 0)
        assert prefs.quiet_hours_end == time(7, 0)
        assert prefs.min_priority == 1

    def test_channel_enabled_for_category(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test category-specific channel checking."""
        category_prefs = {
            "raid": {"email": True, "push": True, "in_app": False},
            "backup": {"email": False, "push": False, "in_app": True},
        }

        prefs = notification_service.update_user_preferences(
            db_session,
            test_user.id,
            category_preferences=category_prefs,
        )

        # RAID should have email enabled but not in_app
        assert prefs.is_channel_enabled_for_category("raid", "email") is True
        assert prefs.is_channel_enabled_for_category("raid", "in_app") is False

        # Backup should have only in_app enabled
        assert prefs.is_channel_enabled_for_category("backup", "email") is False
        assert prefs.is_channel_enabled_for_category("backup", "in_app") is True

        # System (not in category_prefs) should use defaults (all enabled)
        assert prefs.is_channel_enabled_for_category("system", "email") is True


class TestNotificationDispatch:
    """Tests for notification dispatch."""

    @pytest.mark.asyncio
    async def test_dispatch_to_websocket(
        self,
        notification_service: NotificationService,
        mock_websocket_manager,
        db_session: Session,
        test_user: User,
    ):
        """Test dispatching notification via WebSocket."""
        notification_service.set_websocket_manager(mock_websocket_manager)

        notification = await notification_service.create(
            db=db_session,
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="Test",
            message="Test message",
        )

        # WebSocket should have been called
        mock_websocket_manager.broadcast_to_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_admin_notification_broadcast(
        self,
        notification_service: NotificationService,
        mock_websocket_manager,
        db_session: Session,
    ):
        """Test that admin notifications are broadcast."""
        notification_service.set_websocket_manager(mock_websocket_manager)

        # Create notification without user_id (system notification)
        notification = await notification_service.create(
            db=db_session,
            user_id=None,
            category="system",
            notification_type="critical",
            title="System Alert",
            message="Critical system event",
        )

        # Should broadcast to admins
        mock_websocket_manager.broadcast_to_admins.assert_called_once()


class TestNotificationFiltering:
    """Tests for notification filtering."""

    @pytest.mark.asyncio
    async def test_filter_by_category(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test filtering notifications by category."""
        # Create notifications in different categories
        await notification_service.create(
            db=db_session,
            user_id=test_user.id,
            category="raid",
            notification_type="warning",
            title="RAID Warning",
            message="Test",
        )
        await notification_service.create(
            db=db_session,
            user_id=test_user.id,
            category="backup",
            notification_type="info",
            title="Backup Complete",
            message="Test",
        )

        raid_notifications = notification_service.get_user_notifications(
            db=db_session,
            user_id=test_user.id,
            category="raid",
        )

        assert len(raid_notifications) == 1
        assert raid_notifications[0].category == "raid"

    @pytest.mark.asyncio
    async def test_filter_unread_only(
        self,
        notification_service: NotificationService,
        db_session: Session,
        test_user: User,
    ):
        """Test filtering only unread notifications."""
        # Create notifications
        n1 = await notification_service.create(
            db=db_session,
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="Notification 1",
            message="Test",
        )
        await notification_service.create(
            db=db_session,
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="Notification 2",
            message="Test",
        )

        # Mark one as read
        notification_service.mark_as_read(db_session, n1.id, test_user.id)

        unread = notification_service.get_user_notifications(
            db=db_session,
            user_id=test_user.id,
            unread_only=True,
        )

        assert len(unread) == 1
        assert unread[0].title == "Notification 2"
