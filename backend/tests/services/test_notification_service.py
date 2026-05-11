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
from app.services.notifications import NotificationService, get_notification_service


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
        assert notification.deleted_at is None

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
        assert result.deleted_at is not None
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
            push_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(7, 0),
            min_priority=1,
        )

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
            "raid": {"push": True, "in_app": False},
            "backup": {"push": False, "in_app": True},
        }

        prefs = notification_service.update_user_preferences(
            db_session,
            test_user.id,
            category_preferences=category_prefs,
        )

        # RAID should have push enabled but not in_app
        assert prefs.is_channel_enabled_for_category("raid", "push") is True
        assert prefs.is_channel_enabled_for_category("raid", "in_app") is False

        # Backup should have only in_app enabled
        assert prefs.is_channel_enabled_for_category("backup", "push") is False
        assert prefs.is_channel_enabled_for_category("backup", "in_app") is True

        # System (not in category_prefs) should use defaults (all enabled)
        assert prefs.is_channel_enabled_for_category("system", "push") is True


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


class TestGetCategoryPref:
    """Tests for _get_category_pref helper with backwards compatibility."""

    def test_no_prefs_returns_defaults(self):
        from app.services.notifications.service import NotificationService
        svc = NotificationService()
        result = svc._get_category_pref(None, "raid")
        assert result == {"error": True, "success": False, "mobile": True, "desktop": False}

    def test_no_prefs_backup_defaults_success_true(self):
        from app.services.notifications.service import NotificationService
        svc = NotificationService()
        result = svc._get_category_pref(None, "backup")
        assert result["success"] is True

    def test_old_format_migrated(self):
        """Old push/in_app format is auto-mapped to new fields."""
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"push": True, "in_app": False}}
        result = svc._get_category_pref(prefs, "raid")
        assert result == {"error": False, "success": False, "mobile": True, "desktop": False}

    def test_new_format_used_directly(self):
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"error": True, "success": True, "mobile": False, "desktop": True}}
        result = svc._get_category_pref(prefs, "raid")
        assert result == {"error": True, "success": True, "mobile": False, "desktop": True}

    def test_missing_category_returns_defaults(self):
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"error": True, "success": False, "mobile": True, "desktop": False}}
        result = svc._get_category_pref(prefs, "smart")
        assert result == {"error": True, "success": False, "mobile": True, "desktop": False}

    def test_partial_new_format_fills_defaults(self):
        from app.services.notifications.service import NotificationService
        from unittest.mock import MagicMock
        svc = NotificationService()
        prefs = MagicMock()
        prefs.category_preferences = {"raid": {"error": True, "success": True}}
        result = svc._get_category_pref(prefs, "raid")
        assert result == {"error": True, "success": True, "mobile": True, "desktop": False}


class TestDeliveryStatusEndpoint:
    """Tests for GET /api/notifications/delivery-status."""

    def test_returns_status_for_user(self, client, admin_headers):
        """Endpoint returns device availability."""
        from app.core.config import settings
        resp = client.get(
            f"{settings.api_prefix}/notifications/delivery-status",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "has_mobile_devices" in data
        assert "has_desktop_clients" in data
        assert isinstance(data["has_mobile_devices"], bool)
        assert isinstance(data["has_desktop_clients"], bool)

    def test_requires_authentication(self, client):
        """Endpoint requires auth."""
        from app.core.config import settings
        resp = client.get(f"{settings.api_prefix}/notifications/delivery-status")
        assert resp.status_code in (401, 403)


class TestTrashSemantics:
    """Tests for trash-based dismiss/restore/delete behavior."""

    def test_dismiss_sets_deleted_at(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()
        db_session.refresh(n)

        before = n.deleted_at
        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        assert before is None
        assert n.deleted_at is not None
        assert n.is_read is True

    def test_dismiss_idempotent_on_already_trashed(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()

        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        first = n.deleted_at

        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        # Second dismiss must not overwrite the original timestamp
        assert n.deleted_at == first

    def test_restore_clears_deleted_at(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()
        notification_service.dismiss(db_session, n.id, test_user.id)
        db_session.refresh(n)
        assert n.deleted_at is not None

        result = notification_service.restore(db_session, n.id, test_user.id)
        db_session.refresh(n)
        assert result is not None
        assert n.deleted_at is None

    def test_restore_idempotent_on_active(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()

        result = notification_service.restore(db_session, n.id, test_user.id)
        assert result is not None
        assert result.deleted_at is None

    def test_restore_returns_none_for_unknown_id(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        result = notification_service.restore(db_session, 9999999, test_user.id)
        assert result is None

    def test_delete_permanently_removes_row(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        n = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="T",
            message="M",
        )
        db_session.add(n)
        db_session.commit()
        notification_id = n.id

        deleted = notification_service.delete_permanently(
            db_session, notification_id, test_user.id
        )
        assert deleted is True
        assert (
            db_session.query(Notification)
            .filter(Notification.id == notification_id)
            .first()
            is None
        )

    def test_delete_permanently_returns_false_for_unknown_id(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        deleted = notification_service.delete_permanently(
            db_session, 9999999, test_user.id
        )
        assert deleted is False

    def test_empty_trash_removes_only_trashed_rows(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        count = notification_service.empty_trash(db_session, test_user.id)

        assert count == 1
        remaining = db_session.query(Notification).filter(
            Notification.user_id == test_user.id
        ).all()
        assert len(remaining) == 1
        assert remaining[0].title == "active"

    def test_empty_trash_isolates_users(
        self,
        notification_service,
        db_session,
        test_user,
        test_admin,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        user_trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="user-trash",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        other_trashed = Notification(
            user_id=test_admin.id,
            category="system",
            notification_type="info",
            title="admin-trash",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([user_trashed, other_trashed])
        db_session.commit()

        notification_service.empty_trash(db_session, test_user.id, is_admin=False)

        assert db_session.query(Notification).filter(
            Notification.user_id == test_user.id
        ).count() == 0
        assert db_session.query(Notification).filter(
            Notification.user_id == test_admin.id
        ).count() == 1

    def test_cleanup_expired_trash_respects_user_retention(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification, NotificationPreferences
        from datetime import datetime, timezone, timedelta

        # 3-day retention for this user
        prefs = NotificationPreferences(user_id=test_user.id, trash_retention_days=3)
        db_session.add(prefs)

        now = datetime.now(timezone.utc)
        old = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="old",
            message="m",
            deleted_at=now - timedelta(days=5),
        )
        recent = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="recent",
            message="m",
            deleted_at=now - timedelta(days=1),
        )
        db_session.add_all([old, recent])
        db_session.commit()

        count = notification_service.cleanup_expired_trash(db_session)

        assert count == 1
        titles = [
            n.title for n in db_session.query(Notification)
            .filter(Notification.user_id == test_user.id)
            .all()
        ]
        assert titles == ["recent"]

    def test_cleanup_expired_trash_default_when_no_prefs(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        too_old = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="too_old",
            message="m",
            deleted_at=now - timedelta(days=8),
        )
        within = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="within",
            message="m",
            deleted_at=now - timedelta(days=6),
        )
        db_session.add_all([too_old, within])
        db_session.commit()

        count = notification_service.cleanup_expired_trash(db_session)

        assert count == 1
        titles = [
            n.title for n in db_session.query(Notification)
            .filter(Notification.user_id == test_user.id)
            .all()
        ]
        assert titles == ["within"]

    def test_cleanup_expired_trash_system_notifications_fixed_7d(
        self,
        notification_service,
        db_session,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        old_system = Notification(
            user_id=None,
            category="system",
            notification_type="info",
            title="old_sys",
            message="m",
            deleted_at=now - timedelta(days=10),
        )
        fresh_system = Notification(
            user_id=None,
            category="system",
            notification_type="info",
            title="fresh_sys",
            message="m",
            deleted_at=now - timedelta(days=3),
        )
        db_session.add_all([old_system, fresh_system])
        db_session.commit()

        notification_service.cleanup_expired_trash(db_session)

        titles = [
            n.title for n in db_session.query(Notification)
            .filter(Notification.user_id.is_(None))
            .all()
        ]
        assert titles == ["fresh_sys"]

    def test_get_user_notifications_inbox_excludes_trashed(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        results = notification_service.get_user_notifications(
            db_session, test_user.id
        )
        titles = [n.title for n in results]
        assert "active" in titles
        assert "trashed" not in titles

    def test_get_user_notifications_trashed_only_returns_trash(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        active = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="active",
            message="m",
        )
        trashed = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="trashed",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([active, trashed])
        db_session.commit()

        results = notification_service.get_user_notifications(
            db_session, test_user.id, trashed_only=True
        )
        titles = [n.title for n in results]
        assert titles == ["trashed"]

    def test_get_unread_count_ignores_trashed(
        self,
        notification_service,
        db_session,
        test_user,
    ):
        from app.models.notification import Notification
        from datetime import datetime, timezone

        unread = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="unread",
            message="m",
        )
        unread_in_trash = Notification(
            user_id=test_user.id,
            category="system",
            notification_type="info",
            title="unread_in_trash",
            message="m",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add_all([unread, unread_in_trash])
        db_session.commit()

        count = notification_service.get_unread_count(db_session, test_user.id)
        assert count == 1
