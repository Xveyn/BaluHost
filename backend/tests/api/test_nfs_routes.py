"""Route tests for /api/nfs (admin-only NFS export management)."""
import pytest
from app.core.config import settings
from app.models.audit_log import AuditLog


def _create(client, headers, **over):
    body = {"path": "Media", "clients": "192.168.1.0/24", "read_only": False,
            "root_squash": True, "enabled": True, "comment": None}
    body.update(over)
    return client.post(f"{settings.api_prefix}/nfs/exports", json=body, headers=headers)


class TestNfsAuth:
    def test_status_forbidden_for_regular_user(self, client, user_headers):
        r = client.get(f"{settings.api_prefix}/nfs/status", headers=user_headers)
        assert r.status_code == 403

    def test_list_forbidden_for_regular_user(self, client, user_headers):
        r = client.get(f"{settings.api_prefix}/nfs/exports", headers=user_headers)
        assert r.status_code == 403

    def test_create_forbidden_for_regular_user(self, client, user_headers):
        r = _create(client, user_headers)
        assert r.status_code == 403

    def test_update_forbidden_for_regular_user(self, client, user_headers):
        r = client.put(
            f"{settings.api_prefix}/nfs/exports/1",
            json={"path": "Media", "clients": "192.168.1.0/24", "read_only": False,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=user_headers,
        )
        assert r.status_code == 403

    def test_delete_forbidden_for_regular_user(self, client, user_headers):
        r = client.delete(f"{settings.api_prefix}/nfs/exports/1", headers=user_headers)
        assert r.status_code == 403


class TestNfsCrud:
    def test_status_ok_for_admin(self, client, admin_headers):
        r = client.get(f"{settings.api_prefix}/nfs/status", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["is_running"] is False
        assert isinstance(body["exports_count"], int)

    def test_create_list_update_delete(self, client, admin_headers):
        r = _create(client, admin_headers)
        assert r.status_code == 201, r.text
        created = r.json()
        export_id = created["id"]
        assert created["path"] == "Media"
        assert created["mount_target"].endswith("Media")

        r = client.get(f"{settings.api_prefix}/nfs/exports", headers=admin_headers)
        assert r.status_code == 200
        paths = {e["path"] for e in r.json()["exports"]}
        assert "Media" in paths

        r = client.put(
            f"{settings.api_prefix}/nfs/exports/{export_id}",
            json={"path": "Media", "clients": "192.168.1.0/24", "read_only": True,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["read_only"] is True

        r = client.delete(f"{settings.api_prefix}/nfs/exports/{export_id}", headers=admin_headers)
        assert r.status_code == 204
        r = client.get(f"{settings.api_prefix}/nfs/exports", headers=admin_headers)
        assert export_id not in {e["id"] for e in r.json()["exports"]}

    def test_duplicate_path_conflict(self, client, admin_headers):
        assert _create(client, admin_headers, path="Dup").status_code == 201
        assert _create(client, admin_headers, path="Dup").status_code == 409

    def test_traversal_path_rejected(self, client, admin_headers):
        r = _create(client, admin_headers, path="../etc")
        assert r.status_code == 422

    def test_bad_clients_rejected(self, client, admin_headers):
        r = _create(client, admin_headers, path="Bad", clients="not a host!")
        assert r.status_code == 422

    def test_update_missing_returns_404(self, client, admin_headers):
        r = client.put(
            f"{settings.api_prefix}/nfs/exports/999999",
            json={"path": "Ghost", "clients": "192.168.1.0/24", "read_only": False,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 404

    def test_delete_missing_returns_404(self, client, admin_headers):
        r = client.delete(f"{settings.api_prefix}/nfs/exports/999999", headers=admin_headers)
        assert r.status_code == 404

    def test_trailing_slash_path_deduplicated(self, client, admin_headers):
        assert _create(client, admin_headers, path="Media").status_code == 201
        # "Media/" normalizes to "Media" -> duplicate path -> 409
        assert _create(client, admin_headers, path="Media/").status_code == 409


@pytest.fixture
def audit_enabled():
    """Ensure the global audit logger is enabled (a prior test may have disabled it)."""
    from app.services.audit.logger_db import get_audit_logger_db
    get_audit_logger_db().enable()


class TestNfsAudit:
    def test_create_writes_audit(self, client, admin_headers, db_session, audit_enabled):
        r = _create(client, admin_headers, path="AuditMedia")
        assert r.status_code == 201, r.text
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_created", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.event_type == "SYSTEM_CONFIG"
        assert row.resource == "AuditMedia"
        assert row.user == settings.admin_username

    def test_update_writes_audit(self, client, admin_headers, db_session, audit_enabled):
        export_id = _create(client, admin_headers, path="AuditUpd").json()["id"]
        r = client.put(
            f"{settings.api_prefix}/nfs/exports/{export_id}",
            json={"path": "AuditUpd", "clients": "192.168.1.0/24", "read_only": True,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 200
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_updated", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "AuditUpd"

    def test_update_missing_writes_failure(self, client, admin_headers, db_session, audit_enabled):
        r = client.put(
            f"{settings.api_prefix}/nfs/exports/999777",
            json={"path": "Ghost", "clients": "192.168.1.0/24", "read_only": False,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 404
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_updated", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "999777"
        assert row.error_message == "Export not found"

    def test_update_duplicate_path_writes_failure(self, client, admin_headers, db_session, audit_enabled):
        first_id = _create(client, admin_headers, path="UpdDupA").json()["id"]
        _create(client, admin_headers, path="UpdDupB")
        # Try to rename the first export onto the second's path -> 409
        r = client.put(
            f"{settings.api_prefix}/nfs/exports/{first_id}",
            json={"path": "UpdDupB", "clients": "192.168.1.0/24", "read_only": False,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 409
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_updated", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "UpdDupB"
        assert row.error_message == "An export for this path already exists"

    def test_delete_writes_audit(self, client, admin_headers, db_session, audit_enabled):
        export_id = _create(client, admin_headers, path="AuditDel").json()["id"]
        r = client.delete(f"{settings.api_prefix}/nfs/exports/{export_id}", headers=admin_headers)
        assert r.status_code == 204
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_deleted", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "AuditDel"

    def test_delete_missing_writes_failure(self, client, admin_headers, db_session, audit_enabled):
        r = client.delete(f"{settings.api_prefix}/nfs/exports/888888", headers=admin_headers)
        assert r.status_code == 404
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_deleted", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "888888"
        assert row.error_message == "Export not found"

    def test_duplicate_create_writes_failure(self, client, admin_headers, db_session, audit_enabled):
        assert _create(client, admin_headers, path="AuditDup").status_code == 201
        assert _create(client, admin_headers, path="AuditDup").status_code == 409
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_created", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "AuditDup"
