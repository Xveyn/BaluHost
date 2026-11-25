"""Gleitende Rotation von Geraete-Refresh-Tokens (#847, Design A1).

Das Tray fordert beim Refresh ``rotate=True`` an. In der zweiten Lebenshaelfte
bekommt es einen Nachfolger; der alte Token bleibt gueltig, bis der Nachfolger
zum ersten Mal benutzt wird ("lazy revoke"). Wird danach der alte Token erneut
vorgelegt, gilt das als Diebstahlsignal und die ganze Kopplung faellt.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import jwt as pyjwt

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.sync_state import SyncState
from app.models.user import User
from app.services import refresh_rotation
from app.services.token_service import token_service

REFRESH_URL = f"{settings.api_prefix}/auth/refresh"


def _jti(token: str) -> str:
    return pyjwt.decode(token, options={"verify_signature": False})["jti"]


def _row(db, token: str) -> RefreshToken:
    db.expire_all()
    return db.query(RefreshToken).filter(RefreshToken.jti == _jti(token)).one()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _paired_token(
    db, user: User, device_id: str, age_days: float, desktop: bool = True
) -> str:
    """Geraete-Token ausstellen und seine Zeile ``age_days`` altern lassen.

    ``desktop=True`` legt wie die Desktop-Kopplung eine SyncState-Zeile an;
    nur solche Kopplungen duerfen rotieren.
    """
    if desktop and not (
        db.query(SyncState)
        .filter(SyncState.user_id == user.id, SyncState.device_id == device_id)
        .first()
    ):
        db.add(SyncState(user_id=user.id, device_id=device_id, device_name="Tray"))
        db.commit()
    token = refresh_rotation.issue_device_refresh_token(db, user, device_id)
    row = _row(db, token)
    row.expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS - age_days
    )
    db.commit()
    return token


def _refresh(client, token: str, rotate: bool | None = None):
    body: dict = {"refresh_token": token}
    if rotate is not None:
        body["rotate"] = rotate
    return client.post(REFRESH_URL, json=body)


def test_without_rotate_flag_nothing_changes(client, db_session, regular_user):
    fresh = _paired_token(db_session, regular_user, "dev-a", age_days=0)
    old = _paired_token(db_session, regular_user, "dev-b", age_days=5)

    for token in (fresh, old):
        r = _refresh(client, token)
        assert r.status_code == 200, r.text
        assert r.json().get("refresh_token") is None

    assert db_session.query(RefreshToken).count() == 2


def test_rotate_in_first_half_returns_no_new_token(client, db_session, regular_user):
    token = _paired_token(db_session, regular_user, "dev-1", age_days=1)

    r = _refresh(client, token, rotate=True)

    assert r.status_code == 200, r.text
    assert r.json()["refresh_token"] is None
    assert db_session.query(RefreshToken).count() == 1


def test_rotate_in_second_half_returns_successor(client, db_session, regular_user):
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)

    r = _refresh(client, token, rotate=True)

    assert r.status_code == 200, r.text
    successor = r.json()["refresh_token"]
    assert successor and successor != token
    new_row = _row(db_session, successor)
    assert new_row.parent_jti == _jti(token)
    assert new_row.device_id == "dev-1"
    assert new_row.user_id == regular_user.id
    expected = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    assert abs((_aware(new_row.expires_at) - expected).total_seconds()) < 60
    # lazy revoke: der Vorgaenger ist noch nicht widerrufen
    assert _row(db_session, token).revoked is False


def test_token_without_device_id_is_never_rotated(client, db_session, regular_user):
    from app.core.security import create_refresh_token

    token, jti = create_refresh_token(regular_user)
    token_service.store_refresh_token(
        db_session,
        jti=jti,
        user_id=regular_user.id,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    r = _refresh(client, token, rotate=True)

    assert r.status_code == 200, r.text
    assert r.json()["refresh_token"] is None
    assert db_session.query(RefreshToken).count() == 1


def test_old_token_stays_valid_until_successor_is_used(client, db_session, regular_user):
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)
    assert _refresh(client, token, rotate=True).json()["refresh_token"]

    r = _refresh(client, token)

    assert r.status_code == 200, r.text


def test_first_use_of_successor_revokes_predecessor(client, db_session, regular_user):
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)
    successor = _refresh(client, token, rotate=True).json()["refresh_token"]

    r = _refresh(client, successor, rotate=True)

    assert r.status_code == 200, r.text
    # frischer Nachfolger: keine weitere Rotation
    assert r.json()["refresh_token"] is None
    old_row = _row(db_session, token)
    assert old_row.revoked is True
    assert old_row.revocation_reason == "rotated"
    assert _row(db_session, successor).revoked is False


def test_lost_rotation_response_does_not_cost_the_pairing(client, db_session, regular_user):
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)
    lost = _refresh(client, token, rotate=True).json()["refresh_token"]

    r = _refresh(client, token, rotate=True)

    assert r.status_code == 200, r.text
    second = r.json()["refresh_token"]
    assert second and second != lost
    lost_row = _row(db_session, lost)
    assert lost_row.revoked is True
    assert lost_row.revocation_reason == "superseded"

    r2 = _refresh(client, second)
    assert r2.status_code == 200, r2.text
    assert _row(db_session, token).revocation_reason == "rotated"


def test_reuse_of_rotated_token_revokes_the_device(client, db_session, regular_user):
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)
    other_device = _paired_token(db_session, regular_user, "dev-2", age_days=0)
    successor = _refresh(client, token, rotate=True).json()["refresh_token"]
    assert _refresh(client, successor).status_code == 200

    r = _refresh(client, token)

    assert r.status_code == 401
    db_session.expire_all()
    rows = db_session.query(RefreshToken).filter(RefreshToken.device_id == "dev-1").all()
    assert rows and all(row.revoked for row in rows)
    assert _row(db_session, successor).revocation_reason == "reuse_detected"
    # ein anderes Geraet desselben Nutzers bleibt unberuehrt
    assert _row(db_session, other_device).revoked is False

    # und auch der Nachfolger ist jetzt tot
    assert _refresh(client, successor).status_code == 401

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "refresh_token_reuse_detected")
        .all()
    )
    assert len(audit) == 1
    blob = json.dumps(
        [audit[0].details, audit[0].error_message, audit[0].user, audit[0].resource]
    )
    for secret in (token, successor):
        assert secret not in blob
    assert "dev-1" in (audit[0].details or "")


def test_rotation_is_audited_without_token(client, db_session, regular_user):
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)
    successor = _refresh(client, token, rotate=True).json()["refresh_token"]

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "refresh_token_rotated")
        .all()
    )
    assert len(audit) == 1
    blob = json.dumps([audit[0].details, audit[0].error_message, audit[0].user])
    assert token not in blob and successor not in blob
    assert "dev-1" in (audit[0].details or "")


def test_superseded_token_counts_as_reuse(client, db_session, regular_user):
    """Ein echtes Tray hat einen ueberholten Nachfolger nie erhalten — wer ihn
    vorlegt, hat die verlorene Antwort abgefangen."""
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)
    lost = _refresh(client, token, rotate=True).json()["refresh_token"]
    current = _refresh(client, token, rotate=True).json()["refresh_token"]

    r = _refresh(client, lost)

    assert r.status_code == 401
    db_session.expire_all()
    rows = db_session.query(RefreshToken).filter(RefreshToken.device_id == "dev-1").all()
    assert rows and all(row.revoked for row in rows)
    assert _row(db_session, current).revocation_reason == "reuse_detected"
    assert _refresh(client, token).status_code == 401
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "refresh_token_reuse_detected")
        .count()
        == 1
    )


def test_reuse_only_revokes_the_users_own_device(
    client, db_session, regular_user, another_user
):
    """device_id ist clientgewaehlt (Desktop) bzw. ein UUID-String (Mobile) —
    eine Reuse-Erkennung darf keine fremden Tokens mit gleicher ID treffen."""
    token = _paired_token(db_session, regular_user, "3", age_days=4)
    foreign = _paired_token(db_session, another_user, "3", age_days=0, desktop=False)
    successor = _refresh(client, token, rotate=True).json()["refresh_token"]
    assert _refresh(client, successor).status_code == 200

    assert _refresh(client, token).status_code == 401

    assert _row(db_session, successor).revoked is True
    assert _row(db_session, foreign).revoked is False
    assert _refresh(client, foreign).status_code == 200


def test_token_without_desktop_pairing_is_never_rotated(client, db_session, regular_user):
    """Mobile-Tokens tragen ein device_id, aber ihre Laufzeit setzt der Admin
    bei der Geraetefreigabe — sie duerfen nicht ueber Rotation weiterleben."""
    token = _paired_token(db_session, regular_user, "17", age_days=4, desktop=False)

    r = _refresh(client, token, rotate=True)

    assert r.status_code == 200, r.text
    assert r.json()["refresh_token"] is None
    assert db_session.query(RefreshToken).count() == 1


def test_mobile_token_is_never_rotated_even_with_syncstate(client, db_session, regular_user):
    """/sync/register-desktop legt SyncState frei an — auch unter der ID des
    eigenen Mobilgeraets. Die Admin-Freigabelaufzeit darf trotzdem nicht gleiten."""
    import uuid

    from app.models.mobile import MobileDevice

    mobile_id = str(uuid.uuid4())
    db_session.add(
        MobileDevice(
            id=mobile_id,
            user_id=regular_user.id,
            device_name="Phone",
            device_type="android",
        )
    )
    db_session.commit()
    # desktop=True legt die SyncState-Zeile fuer dieselbe ID an
    token = _paired_token(db_session, regular_user, mobile_id, age_days=4, desktop=True)

    r = _refresh(client, token, rotate=True)

    assert r.status_code == 200, r.text
    assert r.json()["refresh_token"] is None
    assert db_session.query(RefreshToken).count() == 1


def test_desktop_pairing_of_another_user_does_not_enable_rotation(
    client, db_session, regular_user, another_user
):
    _paired_token(db_session, another_user, "dev-x", age_days=0)  # SyncState gehoert another_user
    token = _paired_token(db_session, regular_user, "dev-x", age_days=4, desktop=False)

    r = _refresh(client, token, rotate=True)

    assert r.status_code == 200, r.text
    assert r.json()["refresh_token"] is None


def test_pairing_still_issues_a_storable_token(client, db_session, regular_user):
    from app.services import desktop_pairing

    _access, refresh = desktop_pairing._issue_tokens(db_session, regular_user, "dev-p")

    row = _row(db_session, refresh)
    assert row.device_id == "dev-p"
    assert row.parent_jti is None
    assert row.token_hash == RefreshToken.hash_token(refresh)
    assert _refresh(client, refresh).status_code == 200


def _non_raising(client):
    """TestClient, der 5xx als Antwort liefert statt die Exception zu werfen —
    nur so laesst sich pruefen, dass ein DB-Fehler *kein* 401 wird."""
    from fastapi.testclient import TestClient

    c = TestClient(client.app, raise_server_exceptions=False)
    c.headers.update(client.headers)
    return c


def test_db_error_during_refresh_is_not_a_401(client, db_session, regular_user, monkeypatch):
    """Ein 401 heisst fuer das Tray "Kopplung widerrufen" — es vergisst sie.
    Ein voruebergehender DB-Fehler darf deshalb nie als 401 enden."""
    from sqlalchemy.exc import OperationalError

    token = _paired_token(db_session, regular_user, "dev-1", age_days=1)

    def _boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(refresh_rotation, "use_refresh_token", _boom)

    r = _non_raising(client).post(REFRESH_URL, json={"refresh_token": token})

    assert r.status_code != 401
    assert r.status_code >= 500


def test_concurrent_rotation_orphan_is_superseded_on_first_use(
    client, db_session, regular_user
):
    """Zwei gleichzeitige Rotationen desselben Vorgaengers koennen je einen
    Nachfolger ausstellen. Sobald einer benutzt wird, darf der andere nicht
    sieben Tage lang gueltig bleiben (#847, I2b)."""
    token = _paired_token(db_session, regular_user, "dev-1", age_days=4)
    parent_jti = _jti(token)
    used = refresh_rotation.issue_device_refresh_token(
        db_session, regular_user, "dev-1", parent_jti=parent_jti
    )
    orphan = refresh_rotation.issue_device_refresh_token(
        db_session, regular_user, "dev-1", parent_jti=parent_jti
    )

    assert _refresh(client, used).status_code == 200

    orphan_row = _row(db_session, orphan)
    assert orphan_row.revoked is True
    assert orphan_row.revocation_reason == "superseded"
    assert _row(db_session, used).revoked is False
    assert _row(db_session, token).revocation_reason == "rotated"
