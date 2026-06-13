"""Tests for the device-expiration warning catch-up logic (#229).

Covers _should_send_warning's due/overdue rule and check_and_send_warnings'
backlog collapse + post-expiry skip.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.mobile import MobileDevice, ExpirationNotification
from app.models.user import User
from app.services.notifications.scheduler import NotificationScheduler


def _make_device(db: Session, user: User, expires_at: datetime) -> MobileDevice:
    device = MobileDevice(
        user_id=user.id,
        device_name="Catchup Phone",
        device_type="android",
        push_token="fake-fcm-token-catchup",
        is_active=True,
        expires_at=expires_at,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


class TestShouldSendWarning:
    def test_not_yet_due(self, db_session: Session, admin_user: User):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(days=10))
        warning_time = now + timedelta(days=3)  # still in the future
        should_send, reason = NotificationScheduler._should_send_warning(
            db=db_session, device=device, warning_type="7_days",
            warning_time=warning_time, now=now,
        )
        assert should_send is False
        assert reason == "Not yet due"

    def test_overdue_unsent_sends(self, db_session: Session, admin_user: User):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(hours=2))
        warning_time = now - timedelta(hours=20)  # passed long ago (during sleep)
        should_send, reason = NotificationScheduler._should_send_warning(
            db=db_session, device=device, warning_type="7_days",
            warning_time=warning_time, now=now,
        )
        assert should_send is True

    def test_already_sent_skips(self, db_session: Session, admin_user: User):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(hours=2))
        db_session.add(ExpirationNotification(
            device_id=device.id, notification_type="7_days",
            sent_at=now, success=True, device_expires_at=device.expires_at,
        ))
        db_session.commit()
        warning_time = now - timedelta(hours=20)
        should_send, reason = NotificationScheduler._should_send_warning(
            db=db_session, device=device, warning_type="7_days",
            warning_time=warning_time, now=now,
        )
        assert should_send is False
        assert reason == "Warning already sent"


class TestCheckAndSendWarnings:
    @pytest.fixture
    def fake_send(self, monkeypatch):
        """Patch FirebaseService.send_expiration_warning; record calls."""
        calls = []

        def _send(device_token, device_name, expires_at, warning_type, server_url):
            calls.append(warning_type)
            return {"success": True, "message_id": "mid-1", "error": None}

        monkeypatch.setattr(
            "app.services.notifications.firebase.FirebaseService.send_expiration_warning",
            staticmethod(_send),
        )
        return calls

    def _rows(self, db, device):
        return db.query(ExpirationNotification).filter(
            ExpirationNotification.device_id == device.id
        ).all()

    def test_backlog_collapses_to_most_urgent(self, db_session, admin_user, fake_send):
        # Expires in 30 min → all three thresholds are overdue.
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(minutes=30))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 1
        assert fake_send == ["1_hour"]  # only the most urgent goes out
        rows = self._rows(db_session, device)
        by_type = {r.notification_type: r for r in rows}
        assert by_type["1_hour"].success is True
        assert by_type["3_days"].error_message == "superseded_by_more_urgent"
        assert by_type["7_days"].error_message == "superseded_by_more_urgent"

    def test_normal_single_threshold(self, db_session, admin_user, fake_send):
        # Expires in 5 days → only 7_days is due.
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(days=5))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 1
        assert fake_send == ["7_days"]
        types = {r.notification_type for r in self._rows(db_session, device)}
        assert types == {"7_days"}  # 3_days / 1_hour neither sent nor superseded

    def test_skips_when_already_expired(self, db_session, admin_user, fake_send):
        now = datetime.now(timezone.utc)
        _make_device(db_session, admin_user, now - timedelta(minutes=10))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 0
        assert fake_send == []

    def test_no_resend_when_already_sent(self, db_session, admin_user, fake_send):
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(minutes=30))
        db_session.add(ExpirationNotification(
            device_id=device.id, notification_type="1_hour",
            sent_at=now, success=True, device_expires_at=device.expires_at,
        ))
        db_session.commit()

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["sent"] == 0
        assert fake_send == []

    def test_failed_send_does_not_supersede(self, db_session, admin_user, monkeypatch):
        def _send_fail(device_token, device_name, expires_at, warning_type, server_url):
            return {"success": False, "message_id": None, "error": "boom"}

        monkeypatch.setattr(
            "app.services.notifications.firebase.FirebaseService.send_expiration_warning",
            staticmethod(_send_fail),
        )
        now = datetime.now(timezone.utc)
        device = _make_device(db_session, admin_user, now + timedelta(minutes=30))

        stats = NotificationScheduler.check_and_send_warnings(db_session)

        assert stats["failed"] == 1
        rows = {r.notification_type: r for r in db_session.query(ExpirationNotification).filter(
            ExpirationNotification.device_id == device.id).all()}
        assert rows["1_hour"].success is False
        # Less-urgent warnings must NOT be superseded — they retry next tick.
        assert "3_days" not in rows
        assert "7_days" not in rows
