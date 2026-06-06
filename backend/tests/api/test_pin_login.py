from datetime import datetime, timezone, timedelta

import pyotp
from app.core.config import settings
from app.models.user import User
from app.services import totp_service, pin_service

LOGIN_PIN = f"{settings.api_prefix}/auth/login-pin"
VERIFY = f"{settings.api_prefix}/auth/verify-2fa"


def _user_with_pin(db_session, username=None):
    username = username or settings.admin_username
    user = db_session.query(User).filter(User.username == username).first()
    setup = totp_service.generate_setup(user)
    secret = setup["secret"]
    totp_service.verify_and_enable(db_session, user.id, secret, pyotp.TOTP(secret).now())
    pin_service.set_pin(db_session, user, "4827")
    return user, secret


def test_login_pin_within_window_returns_token(client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_pin_expired_window_requires_2fa(client, admin_user, db_session):
    user, secret = _user_with_pin(db_session)
    user.pin_grace_until = None
    db_session.commit()
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 200
    assert r.json().get("requires_2fa") is True
    pending = r.json()["pending_token"]
    # Completing TOTP returns a token AND opens the window
    v = client.post(VERIFY, json={"pending_token": pending, "code": pyotp.TOTP(secret).now()})
    assert v.status_code == 200 and "access_token" in v.json()
    db_session.refresh(user)
    assert pin_service.in_grace_window(user) is True


def test_login_pin_wrong_pin_401(client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "9999"})
    assert r.status_code == 401


def test_login_pin_no_pin_set_401(client, admin_user, db_session):
    r = client.post(LOGIN_PIN, json={"username": settings.admin_username, "pin": "4827"})
    assert r.status_code == 401


def test_login_pin_lockout(client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    for _ in range(5):
        client.post(LOGIN_PIN, json={"username": user.username, "pin": "9999"})
    # Even the correct PIN is now refused (locked)
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 401


def test_login_pin_disabled_by_policy(client, admin_user, db_session):
    from app.services.auth_policy import get_auth_policy
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    get_auth_policy(db_session).pin_login_enabled = False
    db_session.commit()
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 401


def test_login_pin_remote_channel_forbidden(remote_client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    r = remote_client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 403
