"""Regression test: /api/logging/file-access must not leak other users' activity."""
from app.core.config import settings
from app.services.audit.logger_db import get_audit_logger_db


def _seed_file_access(db_session):
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="FILE_ACCESS", user=settings.admin_username,
        action="download", resource="/admin/secret.pdf", db=db_session,
    )
    audit.log_event(
        event_type="FILE_ACCESS", user="testuser",
        action="upload", resource="/testuser/note.txt", db=db_session,
    )
    db_session.commit()


def test_regular_user_only_sees_own_file_access(client, db_session, user_headers):
    _seed_file_access(db_session)
    resp = client.get(
        f"{settings.api_prefix}/logging/file-access?days=1&limit=100",
        headers=user_headers,
    )
    assert resp.status_code == 200
    users = {log["user"] for log in resp.json()["logs"]}
    assert users == {"testuser"}


def test_regular_user_cannot_widen_with_user_param(client, db_session, user_headers):
    _seed_file_access(db_session)
    resp = client.get(
        f"{settings.api_prefix}/logging/file-access?days=1&limit=100&user={settings.admin_username}",
        headers=user_headers,
    )
    assert resp.status_code == 200
    users = {log["user"] for log in resp.json()["logs"]}
    assert users <= {"testuser"}  # empty or only own — never the admin's


def test_regular_user_devmode_mock_is_scoped(client, db_session, user_headers):
    # No seeding: forces the dev-mode mock fallback (real logs == 0).
    resp = client.get(
        f"{settings.api_prefix}/logging/file-access?days=1&limit=100",
        headers=user_headers,
    )
    assert resp.status_code == 200
    users = {log["user"] for log in resp.json()["logs"]}
    # Non-admin must never see other users' (mock) rows.
    assert users <= {"testuser"}


def test_admin_sees_all_file_access(client, db_session, admin_headers):
    _seed_file_access(db_session)
    resp = client.get(
        f"{settings.api_prefix}/logging/file-access?days=1&limit=100",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    users = {log["user"] for log in resp.json()["logs"]}
    assert {settings.admin_username, "testuser"} <= users


def test_regular_user_stats_only_counts_own(client, db_session, user_headers):
    _seed_file_access(db_session)
    resp = client.get(f"{settings.api_prefix}/logging/stats?days=1", headers=user_headers)
    assert resp.status_code == 200
    by_user = resp.json()["file_access"]["by_user"]
    assert set(by_user.keys()) <= {"testuser"}


def test_admin_stats_counts_all_users(client, db_session, admin_headers):
    _seed_file_access(db_session)
    resp = client.get(f"{settings.api_prefix}/logging/stats?days=1", headers=admin_headers)
    assert resp.status_code == 200
    by_user = resp.json()["file_access"]["by_user"]
    assert {settings.admin_username, "testuser"} <= set(by_user.keys())
