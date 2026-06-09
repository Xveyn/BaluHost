"""Route tests for /api/samba (admin-only SMB user management)."""
import pytest

from app.core.config import settings
from app.models.audit_log import AuditLog


@pytest.fixture
def audit_enabled():
    """Ensure the global audit logger is enabled (a prior test may have disabled it)."""
    from app.services.audit.logger_db import get_audit_logger_db
    get_audit_logger_db().enable()


@pytest.fixture
def mock_samba(monkeypatch):
    """Stub the system-touching Samba service calls so no real smbpasswd runs."""
    async def _noop(*args, **kwargs):
        return None

    from app.services import samba_service
    for fn in (
        "enable_smb_user", "disable_smb_user", "sync_smb_password",
        "regenerate_shares_config", "reload_samba",
    ):
        monkeypatch.setattr(samba_service, fn, _noop)


def _toggle(client, headers, user_id, enabled, password=None):
    body = {"enabled": enabled}
    if password is not None:
        body["password"] = password
    return client.post(
        f"{settings.api_prefix}/samba/users/{user_id}/toggle", json=body, headers=headers
    )


class TestSambaAuth:
    def test_toggle_forbidden_for_regular_user(self, client, user_headers, regular_user):
        r = _toggle(client, user_headers, regular_user.id, True)
        assert r.status_code == 403


class TestSambaToggleAudit:
    def test_enable_writes_audit(self, client, admin_headers, regular_user, db_session, audit_enabled, mock_samba):
        r = _toggle(client, admin_headers, regular_user.id, True)
        assert r.status_code == 200, r.text
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_enabled", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.event_type == "SYSTEM_CONFIG"
        assert row.resource == regular_user.username
        assert row.user == settings.admin_username

    def test_disable_writes_audit(self, client, admin_headers, regular_user, db_session, audit_enabled, mock_samba):
        r = _toggle(client, admin_headers, regular_user.id, False)
        assert r.status_code == 200, r.text
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_disabled", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == regular_user.username

    def test_toggle_missing_user_writes_failure(self, client, admin_headers, db_session, audit_enabled, mock_samba):
        r = _toggle(client, admin_headers, 999999, True)
        assert r.status_code == 404
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_enabled", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "999999"
        assert row.error_message == "User not found"

    def test_enable_with_password_records_synced_without_leaking_password(
        self, client, admin_headers, regular_user, db_session, audit_enabled, mock_samba
    ):
        secret = "SuperSecret123!"
        r = _toggle(client, admin_headers, regular_user.id, True, password=secret)
        assert r.status_code == 200, r.text
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_enabled", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        # details must record that a password was synced...
        assert '"password_synced": true' in (row.details or "")
        # ...but the password value itself must NEVER be persisted anywhere on the row.
        assert secret not in (row.details or "")
        assert secret not in (row.error_message or "")
        assert secret not in (row.resource or "")

    def test_enable_service_failure_writes_failure_audit(
        self, client, admin_headers, regular_user, db_session, audit_enabled, mock_samba, monkeypatch
    ):
        from app.services import samba_service

        async def _boom(*args, **kwargs):
            raise RuntimeError("smb enable failed")

        monkeypatch.setattr(samba_service, "enable_smb_user", _boom)

        with pytest.raises(Exception):
            _toggle(client, admin_headers, regular_user.id, True)

        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_enabled", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == regular_user.username
        assert "smb enable failed" in (row.error_message or "")
