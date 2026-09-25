"""Failure paths of the expiry scheduler log above INFO (#495).

They used to log at INFO and were told apart from successes only by a leading
"❌". That emoji is gone (a cp1252 console dropped the whole line), so the log
level has to carry the signal instead.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.mobile import MobileDevice
from app.models.user import User
from app.services.notifications.scheduler import NotificationScheduler

LOGGER = "app.services.notifications.scheduler"


def _due_device(db: Session, user: User) -> MobileDevice:
    device = MobileDevice(
        user_id=user.id, device_name="Level Phone", device_type="android",
        push_token="fake-token", is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    db.add(device)
    db.commit()
    return device


def _levels(caplog, needle: str) -> list[int]:
    return [r.levelno for r in caplog.records if r.name == LOGGER and needle in r.getMessage()]


def test_failed_send_logs_a_warning(db_session, admin_user, monkeypatch, caplog):
    _due_device(db_session, admin_user)
    monkeypatch.setattr(
        NotificationScheduler, "_send_warning",
        classmethod(lambda cls, **kw: {"success": False, "error": "fcm down"}),
    )
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    NotificationScheduler.check_and_send_warnings(db_session)

    assert _levels(caplog, "Failed to send") == [logging.WARNING]


def test_device_error_logs_a_warning(db_session, admin_user, monkeypatch, caplog):
    _due_device(db_session, admin_user)

    def _boom(cls, **kw):
        raise RuntimeError("bad row")

    monkeypatch.setattr(NotificationScheduler, "_should_send_warning", classmethod(_boom))
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    NotificationScheduler.check_and_send_warnings(db_session)

    assert _levels(caplog, "Error processing device") == [logging.WARNING]


def test_critical_error_logs_an_error(monkeypatch, caplog):
    class _BrokenDB:
        def query(self, *a, **kw):
            raise RuntimeError("db gone")

    caplog.set_level(logging.DEBUG, logger=LOGGER)

    NotificationScheduler.check_and_send_warnings(_BrokenDB())

    assert _levels(caplog, "Critical error") == [logging.ERROR]
