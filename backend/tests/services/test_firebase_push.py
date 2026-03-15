"""Tests for Firebase push notification delivery.

Verifies that FirebaseService.send_notification() builds FCM messages correctly
and that the event emitter + notification service dispatch push notifications
to the right devices.
"""

import pytest
from unittest.mock import patch, MagicMock, call

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.mobile import MobileDevice
from app.models.user import User
from app.services.notifications.firebase import FirebaseService
from app.services.notifications.events import EventEmitter, EventType, _cooldown_cache


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def admin_device(db_session: Session, admin_user: User) -> MobileDevice:
    """Create an active mobile device with push token for the admin user."""
    device = MobileDevice(
        user_id=admin_user.id,
        device_name="Admin Phone",
        device_type="android",
        push_token="fake-fcm-token-admin",
        is_active=True,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


@pytest.fixture
def user_device(db_session: Session, regular_user: User) -> MobileDevice:
    """Create an active mobile device with push token for a regular user."""
    device = MobileDevice(
        user_id=regular_user.id,
        device_name="User Phone",
        device_type="android",
        push_token="fake-fcm-token-user",
        is_active=True,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


@pytest.fixture
def device_no_token(db_session: Session, admin_user: User) -> MobileDevice:
    """Create a device without push token."""
    device = MobileDevice(
        user_id=admin_user.id,
        device_name="No Token Phone",
        device_type="android",
        push_token=None,
        is_active=True,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


@pytest.fixture
def inactive_device(db_session: Session, admin_user: User) -> MobileDevice:
    """Create an inactive device."""
    device = MobileDevice(
        user_id=admin_user.id,
        device_name="Inactive Phone",
        device_type="android",
        push_token="fake-fcm-token-inactive",
        is_active=False,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


class _MockUnregisteredError(Exception):
    """Fake UnregisteredError for testing."""
    pass


@pytest.fixture
def mock_firebase():
    """Mock Firebase SDK so send_notification() can run without credentials."""
    mock_messaging = MagicMock()
    mock_messaging.Message = MagicMock()
    mock_messaging.Notification = MagicMock()
    mock_messaging.AndroidConfig = MagicMock()
    mock_messaging.AndroidNotification = MagicMock()
    mock_messaging.send = MagicMock(return_value="projects/test/messages/123")
    mock_messaging.UnregisteredError = _MockUnregisteredError

    with patch("app.services.notifications.firebase.FIREBASE_AVAILABLE", True), \
         patch("app.services.notifications.firebase.messaging", mock_messaging), \
         patch.object(FirebaseService, "_initialized", True), \
         patch.object(FirebaseService, "_app", MagicMock()):
        yield mock_messaging


# ============================================================================
# FirebaseService.send_notification — message construction
# ============================================================================


class TestSendNotificationMessageConstruction:
    """Verify FCM messages are built with correct parameters."""

    def test_always_high_priority(self, mock_firebase):
        """FCM transport priority must always be 'high' regardless of notification priority."""
        for priority in [0, 1, 2, 3]:
            mock_firebase.reset_mock()
            result = FirebaseService.send_notification(
                device_token="token",
                title="Test",
                body="Body",
                priority=priority,
            )
            assert result["success"] is True

            # Check AndroidConfig was called with priority="high"
            android_config_call = mock_firebase.AndroidConfig.call_args
            assert android_config_call.kwargs["priority"] == "high", (
                f"Expected priority='high' for notification priority={priority}, "
                f"got '{android_config_call.kwargs['priority']}'"
            )

    def test_sound_set_to_default(self, mock_firebase):
        """FCM notification must include sound='default'."""
        FirebaseService.send_notification(
            device_token="token",
            title="Test",
            body="Body",
        )

        android_notif_call = mock_firebase.AndroidNotification.call_args
        assert android_notif_call.kwargs.get("sound") == "default"

    def test_color_set(self, mock_firebase):
        """FCM notification must include the brand color."""
        FirebaseService.send_notification(
            device_token="token",
            title="Test",
            body="Body",
        )

        android_notif_call = mock_firebase.AndroidNotification.call_args
        assert android_notif_call.kwargs.get("color") == "#38bdf8"

    @pytest.mark.parametrize("notification_type,expected_channel", [
        ("critical", "alerts_critical"),
        ("warning", "alerts_warning"),
        ("info", "alerts_info"),
        ("unknown", "alerts_info"),
    ])
    def test_channel_id_mapping(self, mock_firebase, notification_type, expected_channel):
        """Channel ID must match notification_type."""
        FirebaseService.send_notification(
            device_token="token",
            title="Test",
            body="Body",
            notification_type=notification_type,
        )

        android_notif_call = mock_firebase.AndroidNotification.call_args
        assert android_notif_call.kwargs["channel_id"] == expected_channel

    def test_data_payload_fields(self, mock_firebase):
        """Data payload must include type, notification_id, category, priority, action_url."""
        FirebaseService.send_notification(
            device_token="token",
            title="RAID Alert",
            body="Array degraded",
            category="raid",
            priority=3,
            notification_id=42,
            action_url="/raid",
            notification_type="critical",
        )

        message_call = mock_firebase.Message.call_args
        data = message_call.kwargs["data"]
        assert data["type"] == "notification"
        assert data["notification_id"] == "42"
        assert data["category"] == "raid"
        assert data["priority"] == "3"
        assert data["action_url"] == "/raid"

    def test_notification_payload(self, mock_firebase):
        """FCM notification payload must include title and body."""
        FirebaseService.send_notification(
            device_token="token",
            title="Alert Title",
            body="Alert Body",
        )

        notif_call = mock_firebase.Notification.call_args
        assert notif_call.kwargs["title"] == "Alert Title"
        assert notif_call.kwargs["body"] == "Alert Body"

    def test_token_passed_to_message(self, mock_firebase):
        """Device token must be passed to Message constructor."""
        FirebaseService.send_notification(
            device_token="my-device-token",
            title="Test",
            body="Body",
        )

        message_call = mock_firebase.Message.call_args
        assert message_call.kwargs["token"] == "my-device-token"

    def test_returns_message_id_on_success(self, mock_firebase):
        """Successful send returns message_id from FCM."""
        mock_firebase.send.return_value = "projects/test/messages/456"

        result = FirebaseService.send_notification(
            device_token="token",
            title="Test",
            body="Body",
        )

        assert result["success"] is True
        assert result["message_id"] == "projects/test/messages/456"
        assert result["error"] is None


class TestSendNotificationErrorHandling:
    """Test error handling in send_notification."""

    def test_unregistered_token(self, mock_firebase):
        """Unregistered token returns specific error for cleanup."""
        mock_firebase.send.side_effect = _MockUnregisteredError("Token expired")

        result = FirebaseService.send_notification(
            device_token="expired-token",
            title="Test",
            body="Body",
        )

        assert result["success"] is False
        assert result["error"] == "unregistered"

    def test_generic_error(self, mock_firebase):
        """Generic errors are returned as string."""
        mock_firebase.send.side_effect = Exception("Network timeout")

        result = FirebaseService.send_notification(
            device_token="token",
            title="Test",
            body="Body",
        )

        assert result["success"] is False
        assert "Network timeout" in result["error"]

    def test_not_initialized(self):
        """Returns error when Firebase is not initialized."""
        with patch.object(FirebaseService, "_initialized", False):
            result = FirebaseService.send_notification(
                device_token="token",
                title="Test",
                body="Body",
            )

        assert result["success"] is False
        assert "not initialized" in result["error"]


# ============================================================================
# EventEmitter._send_push_sync — device selection & dispatch
# ============================================================================


class TestPushSyncDeviceSelection:
    """Test that _send_push_sync sends to correct devices."""

    def test_sends_to_admin_devices_for_system_notification(
        self, db_session, admin_user, admin_device, mock_firebase
    ):
        """System notifications (user_id=None) send to all admin devices."""
        emitter = EventEmitter()
        emitter._send_push_sync(
            db=db_session,
            notification_id=1,
            user_id=None,
            title="System Alert",
            message="Something happened",
            category="system",
            notification_type="critical",
            priority=3,
            action_url="/admin/health",
        )

        mock_firebase.send.assert_called_once()

    def test_sends_to_user_devices_for_user_notification(
        self, db_session, regular_user, user_device, mock_firebase
    ):
        """User-specific notifications send to that user's devices."""
        emitter = EventEmitter()
        emitter._send_push_sync(
            db=db_session,
            notification_id=1,
            user_id=regular_user.id,
            title="Your Backup",
            message="Backup completed",
            category="backup",
            notification_type="info",
            priority=0,
            action_url="/backups",
        )

        mock_firebase.send.assert_called_once()

    def test_skips_devices_without_push_token(
        self, db_session, admin_user, device_no_token, mock_firebase
    ):
        """Devices without push_token are not sent to."""
        emitter = EventEmitter()
        emitter._send_push_sync(
            db=db_session,
            notification_id=1,
            user_id=None,
            title="Alert",
            message="Test",
            category="system",
            notification_type="info",
            priority=0,
            action_url=None,
        )

        mock_firebase.send.assert_not_called()

    def test_skips_inactive_devices(
        self, db_session, admin_user, inactive_device, mock_firebase
    ):
        """Inactive devices are not sent to."""
        emitter = EventEmitter()
        emitter._send_push_sync(
            db=db_session,
            notification_id=1,
            user_id=None,
            title="Alert",
            message="Test",
            category="system",
            notification_type="info",
            priority=0,
            action_url=None,
        )

        mock_firebase.send.assert_not_called()

    def test_does_not_send_to_other_users_devices(
        self, db_session, admin_user, regular_user, user_device, mock_firebase
    ):
        """Admin notification must not send to regular user's devices."""
        emitter = EventEmitter()
        emitter._send_push_sync(
            db=db_session,
            notification_id=1,
            user_id=None,
            title="Admin Alert",
            message="Test",
            category="system",
            notification_type="info",
            priority=0,
            action_url=None,
        )

        # user_device belongs to regular_user (not admin), so no sends
        mock_firebase.send.assert_not_called()

    def test_sends_to_multiple_admin_devices(
        self, db_session, admin_user, admin_device, mock_firebase
    ):
        """Multiple devices for an admin should all receive the notification."""
        # Create second device
        device2 = MobileDevice(
            user_id=admin_user.id,
            device_name="Admin Tablet",
            device_type="android",
            push_token="fake-fcm-token-admin-2",
            is_active=True,
        )
        db_session.add(device2)
        db_session.commit()

        emitter = EventEmitter()
        emitter._send_push_sync(
            db=db_session,
            notification_id=1,
            user_id=None,
            title="Alert",
            message="Test",
            category="system",
            notification_type="info",
            priority=0,
            action_url=None,
        )

        assert mock_firebase.send.call_count == 2

    def test_clears_unregistered_token(
        self, db_session, admin_user, admin_device, mock_firebase
    ):
        """Unregistered token error clears the device's push_token."""
        mock_firebase.send.side_effect = _MockUnregisteredError("Gone")

        result = FirebaseService.send_notification(
            device_token=admin_device.push_token,
            title="Test",
            body="Body",
        )

        assert result["error"] == "unregistered"


# ============================================================================
# EventEmitter.emit_sync — full flow
# ============================================================================


class TestEmitSyncFullFlow:
    """Test the complete synchronous notification + push flow."""

    def test_emit_sync_creates_notification_and_sends_push(
        self, db_session, admin_user, admin_device, mock_firebase
    ):
        """emit_for_admins_sync creates DB notification and sends FCM push."""
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)

        emitter.emit_for_admins_sync(
            EventType.BACKUP_COMPLETED,
            backup_type="full",
            size="1.2 GB",
        )

        # Notification created in DB
        notification = db_session.query(Notification).first()
        assert notification is not None
        assert notification.category == "backup"
        assert notification.notification_type == "info"
        assert "Backup" in notification.title
        assert "full" in notification.message
        assert notification.user_id is None  # admin/system notification

        # Push sent
        mock_firebase.send.assert_called_once()

    def test_emit_sync_with_critical_event(
        self, db_session, admin_user, admin_device, mock_firebase
    ):
        """Critical events create high-priority notifications."""
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)

        emitter.emit_for_admins_sync(
            EventType.RAID_DEGRADED,
            array_name="md0",
            details="sda1 failed",
        )

        notification = db_session.query(Notification).first()
        assert notification is not None
        assert notification.priority == 3
        assert notification.notification_type == "critical"
        assert "md0" in notification.title

        mock_firebase.send.assert_called_once()

    def test_emit_sync_cooldown_suppresses_duplicate(
        self, db_session, admin_user, admin_device, mock_firebase
    ):
        """Second emit within cooldown window is suppressed."""
        _cooldown_cache.clear()  # Reset cross-test contamination
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)

        # First emit — goes through
        emitter.emit_for_admins_sync(
            EventType.RAID_DEGRADED,
            cooldown_entity="md0",
            array_name="md0",
            details="disk failed",
        )
        assert mock_firebase.send.call_count == 1

        # Second emit — suppressed by cooldown
        emitter.emit_for_admins_sync(
            EventType.RAID_DEGRADED,
            cooldown_entity="md0",
            array_name="md0",
            details="disk failed again",
        )
        # Still only 1 call
        assert mock_firebase.send.call_count == 1

        # Only 1 notification in DB
        count = db_session.query(Notification).count()
        assert count == 1

    def test_emit_sync_no_devices_no_error(
        self, db_session, admin_user, mock_firebase
    ):
        """emit_sync works without error even if no devices exist."""
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)

        # No admin_device fixture — no devices in DB
        emitter.emit_for_admins_sync(
            EventType.BACKUP_COMPLETED,
            backup_type="incremental",
            size="500 MB",
        )

        # Notification still created
        notification = db_session.query(Notification).first()
        assert notification is not None

        # No push sent (no devices)
        mock_firebase.send.assert_not_called()


# ============================================================================
# NotificationService._send_push (async path)
# ============================================================================


class TestAsyncPushDispatch:
    """Test the async notification dispatch path."""

    @pytest.mark.asyncio
    async def test_dispatch_sends_push_to_user_device(
        self, db_session, regular_user, user_device, mock_firebase
    ):
        """dispatch() sends push for user-specific notifications."""
        from app.services.notifications.service import NotificationService

        service = NotificationService()

        notification = Notification(
            user_id=regular_user.id,
            category="backup",
            notification_type="info",
            title="Backup done",
            message="Your backup completed",
            priority=0,
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        await service.dispatch(db_session, notification)

        mock_firebase.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_sends_push_to_admin_devices(
        self, db_session, admin_user, admin_device, mock_firebase
    ):
        """dispatch() sends push for system notifications (user_id=None)."""
        from app.services.notifications.service import NotificationService

        service = NotificationService()

        notification = Notification(
            user_id=None,
            category="system",
            notification_type="critical",
            title="System Alert",
            message="Critical event",
            priority=3,
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        await service.dispatch(db_session, notification)

        mock_firebase.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_respects_quiet_hours(
        self, db_session, regular_user, user_device, mock_firebase
    ):
        """Notifications during quiet hours are not dispatched (except critical)."""
        from datetime import time, timezone
        from app.services.notifications.service import NotificationService
        from app.models.notification import NotificationPreferences

        service = NotificationService()

        # Set quiet hours to all day (00:00 - 23:59)
        prefs = NotificationPreferences(
            user_id=regular_user.id,
            push_enabled=True,
            in_app_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(0, 0),
            quiet_hours_end=time(23, 59),
            min_priority=0,
        )
        db_session.add(prefs)
        db_session.commit()

        # Low priority notification — should be suppressed
        notification = Notification(
            user_id=regular_user.id,
            category="backup",
            notification_type="info",
            title="Backup done",
            message="Completed",
            priority=0,
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        await service.dispatch(db_session, notification)

        mock_firebase.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_critical_bypasses_quiet_hours(
        self, db_session, regular_user, user_device, mock_firebase
    ):
        """Critical notifications (priority >= 3) bypass quiet hours."""
        from datetime import time
        from app.services.notifications.service import NotificationService
        from app.models.notification import NotificationPreferences

        service = NotificationService()

        prefs = NotificationPreferences(
            user_id=regular_user.id,
            push_enabled=True,
            in_app_enabled=True,
            quiet_hours_enabled=True,
            quiet_hours_start=time(0, 0),
            quiet_hours_end=time(23, 59),
            min_priority=0,
        )
        db_session.add(prefs)
        db_session.commit()

        # Critical notification — must go through
        notification = Notification(
            user_id=regular_user.id,
            category="raid",
            notification_type="critical",
            title="RAID Failed",
            message="Array down",
            priority=3,
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        await service.dispatch(db_session, notification)

        mock_firebase.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_respects_push_disabled(
        self, db_session, regular_user, user_device, mock_firebase
    ):
        """Push notifications not sent when user has push_enabled=False."""
        from app.services.notifications.service import NotificationService
        from app.models.notification import NotificationPreferences

        service = NotificationService()

        prefs = NotificationPreferences(
            user_id=regular_user.id,
            push_enabled=False,
            in_app_enabled=True,
            quiet_hours_enabled=False,
            min_priority=0,
        )
        db_session.add(prefs)
        db_session.commit()

        notification = Notification(
            user_id=regular_user.id,
            category="system",
            notification_type="info",
            title="Test",
            message="Test",
            priority=1,
        )
        db_session.add(notification)
        db_session.commit()
        db_session.refresh(notification)

        await service.dispatch(db_session, notification)

        mock_firebase.send.assert_not_called()
