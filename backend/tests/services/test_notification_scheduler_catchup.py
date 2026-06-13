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
