"""Einmal-Code-Handoff vom Tray in die Web-UI (#847, Design B1).

Das Tray weist sich mit dem Refresh-Token seiner Geraetekopplung aus, bekommt
einen 30 s gueltigen Einmal-Code, und der Browser tauscht ihn gegen eine
eigene, normale Sitzung.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from app.core.config import settings
from app.core.security import create_refresh_token
from app.models.audit_log import AuditLog
from app.models.session_handoff import SessionHandoffCode
from app.models.sync_state import SyncState
from app.models.user import User
from app.services import pin_service, refresh_rotation, session_handoff
from app.services.token_service import token_service

HANDOFF_URL = f"{settings.api_prefix}/auth/handoff"
REDEEM_URL = f"{settings.api_prefix}/auth/handoff/redeem"
ME_URL = f"{settings.api_prefix}/auth/me"
ADMIN_POLICY_URL = f"{settings.api_prefix}/admin/auth-policy"


def _ttl_minutes(token: str) -> float:
    claims = pyjwt.decode(
        token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False}
    )
    return (claims["exp"] - claims["iat"]) / 60


@pytest.fixture
def lan(monkeypatch):
    monkeypatch.setattr("app.api.routes.auth.is_private_or_local_ip", lambda ip: True)


@pytest.fixture
def wan(monkeypatch):
    monkeypatch.setattr("app.api.routes.auth.is_private_or_local_ip", lambda ip: False)


def _paired_token(db, user: User, device_id: str = "tray-1") -> str:
    db.add(SyncState(user_id=user.id, device_id=device_id, device_name="Tray"))
    db.commit()
    return refresh_rotation.issue_device_refresh_token(db, user, device_id)


def _handoff(client, token: str, pin: str | None = None):
    body: dict = {"refresh_token": token}
    if pin is not None:
        body["pin"] = pin
    return client.post(HANDOFF_URL, json=body)


def _code(client, token: str, pin: str | None = None) -> str:
    r = _handoff(client, token, pin)
    assert r.status_code == 200, r.text
    assert r.json()["expires_in"] == 30
    return r.json()["code"]


def test_paired_device_gets_a_code_and_browser_redeems_it(
    client, db_session, regular_user, lan
):
    code = _code(client, _paired_token(db_session, regular_user))

    r = client.post(REDEEM_URL, json={"code": code})

    assert r.status_code == 200, r.text
    access = r.json()["access_token"]
    assert r.json()["refresh_token"] is None
    me = client.get(ME_URL, headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    assert me.json()["username"] == regular_user.username
    actions = {a for (a,) in db_session.query(AuditLog.action).all()}
    assert {"session_handoff_issued", "session_handoff_redeemed"} <= actions


def test_access_token_alone_is_not_enough(client, db_session, regular_user, lan):
    r = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": "testuser", "password": "Testpass123!"},
    )
    access = r.json()["access_token"]

    r = _handoff(client, access)

    assert r.status_code == 401
    assert db_session.query(SessionHandoffCode).count() == 0


def test_refresh_token_without_device_id_is_refused(client, db_session, regular_user, lan):
    token, jti = create_refresh_token(regular_user, expires_delta=timedelta(days=7))
    token_service.store_refresh_token(
        db=db_session,
        jti=jti,
        user_id=regular_user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        device_id=None,
    )

    r = _handoff(client, token)

    assert r.status_code == 401
    assert db_session.query(SessionHandoffCode).count() == 0


def test_outside_lan_is_refused_and_audited(client, db_session, regular_user, wan):
    r = _handoff(client, _paired_token(db_session, regular_user))

    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "local_network_required"
    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "session_handoff_remote_denied")
        .one()
    )
    assert entry.success is False
    assert entry.ip_address
    assert db_session.query(SessionHandoffCode).count() == 0


def test_code_is_single_use(client, db_session, regular_user, lan):
    code = _code(client, _paired_token(db_session, regular_user))

    assert client.post(REDEEM_URL, json={"code": code}).status_code == 200
    second = client.post(REDEEM_URL, json={"code": code})

    assert second.status_code == 401
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "session_handoff_redeem_failed")
        .count()
        == 1
    )


def test_unknown_code_is_refused(client, db_session, lan):
    assert client.post(REDEEM_URL, json={"code": "nope"}).status_code == 401


def test_code_expires_after_30_seconds(client, db_session, regular_user, lan, monkeypatch):
    code = _code(client, _paired_token(db_session, regular_user))

    later = datetime.now(timezone.utc) + timedelta(seconds=31)
    monkeypatch.setattr(session_handoff, "_now", lambda: later)

    assert client.post(REDEEM_URL, json={"code": code}).status_code == 401


def test_inactive_user_cannot_redeem(client, db_session, regular_user, lan):
    code = _code(client, _paired_token(db_session, regular_user))
    regular_user.is_active = False
    db_session.commit()

    assert client.post(REDEEM_URL, json={"code": code}).status_code == 401


def test_pin_required_when_account_has_pin(client, db_session, regular_user, lan):
    pin_service.set_pin(db_session, regular_user, "4711")

    r = _handoff(client, _paired_token(db_session, regular_user))

    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "pin_required"


def test_wrong_pin_counts_towards_lock(client, db_session, regular_user, lan):
    pin_service.set_pin(db_session, regular_user, "4711")

    r = _handoff(client, _paired_token(db_session, regular_user), pin="0000")

    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "pin_invalid"
    db_session.refresh(regular_user)
    assert regular_user.pin_failed_attempts == 1


def test_locked_pin_is_reported(client, db_session, regular_user, lan):
    pin_service.set_pin(db_session, regular_user, "4711")
    regular_user.pin_locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    db_session.commit()

    # Auch die richtige PIN hilft nicht, solange gesperrt ist.
    r = _handoff(client, _paired_token(db_session, regular_user), pin="4711")

    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "pin_locked"


def test_correct_pin_gets_code(client, db_session, regular_user, lan):
    pin_service.set_pin(db_session, regular_user, "4711")
    regular_user.pin_failed_attempts = 2
    db_session.commit()

    code = _code(client, _paired_token(db_session, regular_user), pin="4711")

    assert code
    db_session.refresh(regular_user)
    assert regular_user.pin_failed_attempts == 0


def test_pin_ignored_without_account_pin(client, db_session, regular_user, lan):
    assert _code(client, _paired_token(db_session, regular_user), pin="1234")


def test_redeemed_session_honours_auth_policy_ttl(
    client, db_session, regular_user, admin_headers, lan
):
    client.put(ADMIN_POLICY_URL, headers=admin_headers, json={"access_token_minutes": 90})
    code = _code(client, _paired_token(db_session, regular_user))

    r = client.post(REDEEM_URL, json={"code": code})

    assert r.status_code == 200, r.text
    assert _ttl_minutes(r.json()["access_token"]) == pytest.approx(90, abs=0.2)


def test_code_is_never_stored_in_clear(client, db_session, regular_user, lan):
    code = _code(client, _paired_token(db_session, regular_user))

    row = db_session.query(SessionHandoffCode).one()
    assert row.token_hash != code
    assert len(row.token_hash) == 64


def test_issuing_purges_codes_older_than_a_day(db_session, regular_user):
    stale = SessionHandoffCode(
        user_id=regular_user.id,
        token_hash="0" * 64,
        expires_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db_session.add(stale)
    db_session.commit()

    session_handoff.issue_code(db_session, regular_user, ip="127.0.0.1")

    hashes = [h for (h,) in db_session.query(SessionHandoffCode.token_hash).all()]
    assert "0" * 64 not in hashes
    assert len(hashes) == 1


def test_db_error_during_handoff_is_not_a_401(
    client, db_session, regular_user, lan, monkeypatch
):
    """Das Tray wertet 401 als Widerruf. Ein DB-Fehler muss als 5xx enden."""
    from fastapi.testclient import TestClient
    from sqlalchemy.exc import OperationalError

    token = _paired_token(db_session, regular_user)

    def _boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(refresh_rotation, "use_refresh_token", _boom)
    c = TestClient(client.app, raise_server_exceptions=False)
    c.headers.update(client.headers)

    r = c.post(HANDOFF_URL, json={"refresh_token": token})

    assert r.status_code != 401
    assert r.status_code >= 500
    assert db_session.query(SessionHandoffCode).count() == 0


def test_handoff_with_rotated_token_triggers_reuse_detection(
    client, db_session, regular_user, lan
):
    """Der Handoff zaehlt als Nutzung — ein rotierter Token, dessen Nachfolger
    schon benutzt wurde, muss hier dieselbe Wiederverwendungserkennung
    ausloesen wie bei /auth/refresh."""
    from app.models.refresh_token import RefreshToken

    token = _paired_token(db_session, regular_user)
    jti = pyjwt.decode(token, options={"verify_signature": False})["jti"]
    row = db_session.query(RefreshToken).filter(RefreshToken.jti == jti).one()
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db_session.commit()
    refresh_url = f"{settings.api_prefix}/auth/refresh"
    successor = client.post(
        refresh_url, json={"refresh_token": token, "rotate": True}
    ).json()["refresh_token"]
    assert successor
    assert client.post(refresh_url, json={"refresh_token": successor}).status_code == 200

    r = _handoff(client, token)

    assert r.status_code == 401
    assert db_session.query(SessionHandoffCode).count() == 0
    db_session.expire_all()
    rows = db_session.query(RefreshToken).filter(RefreshToken.device_id == "tray-1").all()
    assert rows and all(rt.revoked for rt in rows)
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "refresh_token_reuse_detected")
        .count()
        == 1
    )
    assert client.post(refresh_url, json={"refresh_token": successor}).status_code == 401


def test_plaintext_code_never_reaches_the_audit_log(client, db_session, regular_user, lan):
    import json

    token = _paired_token(db_session, regular_user)
    code = _code(client, token)
    assert client.post(REDEEM_URL, json={"code": code}).status_code == 200
    # auch ein fehlgeschlagener Versuch schreibt den Code nicht mit
    assert client.post(REDEEM_URL, json={"code": code}).status_code == 401

    entries = db_session.query(AuditLog).all()
    assert entries
    blob = json.dumps(
        [
            [e.action, e.user, e.resource, e.details, e.error_message]
            for e in entries
        ],
        default=str,
    )
    assert code not in blob
    assert token not in blob
