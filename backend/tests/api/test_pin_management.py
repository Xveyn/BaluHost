import pyotp
from app.core.config import settings
from app.models.user import User
from app.services import totp_service

PIN_URL = f"{settings.api_prefix}/auth/pin"


def _enable_2fa(db_session, username) -> str:
    """Enable 2FA for a user, return the plain secret."""
    user = db_session.query(User).filter(User.username == username).first()
    setup = totp_service.generate_setup(user)
    secret = setup["secret"]
    totp_service.verify_and_enable(db_session, user.id, secret, pyotp.TOTP(secret).now())
    return secret


def test_status_false_then_true(client, admin_headers, db_session):
    secret = _enable_2fa(db_session, settings.admin_username)
    assert client.get(PIN_URL, headers=admin_headers).json()["pin_enabled"] is False
    r = client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    assert client.get(PIN_URL, headers=admin_headers).json()["pin_enabled"] is True


def test_set_pin_requires_2fa_enabled(client, admin_headers):
    r = client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": "000000"})
    assert r.status_code == 400


def test_set_pin_rejects_bad_totp(client, admin_headers, db_session):
    _enable_2fa(db_session, settings.admin_username)
    r = client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": "000000"})
    assert r.status_code == 401


def test_remove_pin(client, admin_headers, db_session):
    secret = _enable_2fa(db_session, settings.admin_username)
    client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": pyotp.TOTP(secret).now()})
    r = client.request("DELETE", PIN_URL, headers=admin_headers, json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    assert client.get(PIN_URL, headers=admin_headers).json()["pin_enabled"] is False
