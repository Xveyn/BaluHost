from datetime import datetime, timezone, timedelta

from app.models.user import User
from app.services import pin_service, totp_service


def _user(db):
    u = User(username="pinuser", hashed_password="x", role="user", totp_enabled=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_hash_and_verify(db_session):
    u = _user(db_session)
    pin_service.set_pin(db_session, u, "4827")
    assert u.pin_hash and u.pin_hash != "4827"
    assert pin_service.verify_pin("4827", u.pin_hash) is True
    assert pin_service.verify_pin("4828", u.pin_hash) is False


def test_grace_window(db_session):
    u = _user(db_session)
    assert pin_service.in_grace_window(u) is False
    u.pin_grace_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert pin_service.in_grace_window(u) is True
    u.pin_grace_until = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert pin_service.in_grace_window(u) is False


def test_lockout_after_5_failures(db_session):
    u = _user(db_session)
    for _ in range(5):
        pin_service.register_pin_failure(db_session, u)
    assert pin_service.is_pin_locked(u) is True
    assert u.pin_failed_attempts == 0  # reset when lock applied


def test_reset_failures(db_session):
    u = _user(db_session)
    pin_service.register_pin_failure(db_session, u)
    pin_service.reset_pin_failures(db_session, u)
    assert u.pin_failed_attempts == 0
    assert u.pin_locked_until is None


def test_disable_2fa_clears_pin(db_session):
    u = _user(db_session)
    pin_service.set_pin(db_session, u, "4827")
    u.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    totp_service.disable(db_session, u.id)
    db_session.refresh(u)
    assert u.pin_hash is None
    assert u.pin_grace_until is None
    assert u.totp_enabled is False
