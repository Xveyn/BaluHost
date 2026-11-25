"""Desktop-Geraet entfernen widerruft die Kopplung (#847, A1b)."""
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.file_metadata import FileMetadata
from app.models.refresh_token import RefreshToken
from app.models.sync_state import SyncMetadata, SyncState
from app.services import refresh_rotation

DEVICES = f"{settings.api_prefix}/devices"
REFRESH = f"{settings.api_prefix}/auth/refresh"


def _pair(db, user, device_id="tray-1"):
    db.add(SyncState(user_id=user.id, device_id=device_id, device_name="Tray"))
    db.commit()
    return refresh_rotation.issue_device_refresh_token(db, user, device_id)


def _ids(client, headers):
    r = client.get(f"{DEVICES}/all", headers=headers)
    assert r.status_code == 200, r.text
    return [d["id"] for d in r.json()]


def test_owner_removes_own_desktop_device_and_its_tokens_die(
    client, db_session, regular_user, user_headers
):
    token = _pair(db_session, regular_user)
    assert "tray-1" in _ids(client, user_headers)

    r = client.delete(f"{DEVICES}/desktop/tray-1", headers=user_headers)
    assert r.status_code == 204, r.text

    assert client.post(REFRESH, json={"refresh_token": token}).status_code == 401
    assert "tray-1" not in _ids(client, user_headers)
    db_session.expire_all()
    row = db_session.query(RefreshToken).filter_by(device_id="tray-1").one()
    assert row.revoked is True


def test_user_cannot_remove_foreign_device(
    client, db_session, regular_user, another_user_headers
):
    token = _pair(db_session, regular_user)
    r = client.delete(f"{DEVICES}/desktop/tray-1", headers=another_user_headers)
    assert r.status_code == 403
    assert client.post(REFRESH, json={"refresh_token": token}).status_code == 200
    assert db_session.query(SyncState).filter_by(device_id="tray-1").count() == 1


def test_admin_can_remove_foreign_device(
    client, db_session, regular_user, admin_headers
):
    token = _pair(db_session, regular_user)
    r = client.delete(f"{DEVICES}/desktop/tray-1", headers=admin_headers)
    assert r.status_code == 204
    assert client.post(REFRESH, json={"refresh_token": token}).status_code == 401


def test_unknown_device_is_404(client, user_headers):
    r = client.delete(f"{DEVICES}/desktop/nope", headers=user_headers)
    assert r.status_code == 404


def test_requires_auth(client):
    assert client.delete(f"{DEVICES}/desktop/tray-1").status_code in (401, 403)


def test_removal_is_audited(client, db_session, regular_user, user_headers):
    token = _pair(db_session, regular_user)
    r = client.delete(f"{DEVICES}/desktop/tray-1", headers=user_headers)
    assert r.status_code == 204
    db_session.expire_all()
    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "desktop_device_removed")
        .one()
    )
    blob = f"{entry.user} {entry.resource} {entry.details} {entry.ip_address}"
    assert "tray-1" in blob
    assert regular_user.username in blob
    assert token not in blob


def test_dependent_sync_metadata_is_removed(
    client, db_session, regular_user, user_headers
):
    from datetime import datetime, timezone

    _pair(db_session, regular_user)
    state = db_session.query(SyncState).filter_by(device_id="tray-1").one()
    fm = FileMetadata(
        path="a.txt", name="a.txt", owner_id=regular_user.id, size_bytes=1,
        is_directory=False,
    )
    db_session.add(fm)
    db_session.commit()
    now = datetime.now(timezone.utc)
    db_session.add(SyncMetadata(
        file_metadata_id=fm.id, sync_state_id=state.id, content_hash="x" * 64,
        file_size=1, local_modified_at=now, server_modified_at=now,
    ))
    db_session.commit()

    r = client.delete(f"{DEVICES}/desktop/tray-1", headers=user_headers)
    assert r.status_code == 204
    assert db_session.query(SyncMetadata).count() == 0
