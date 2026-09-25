"""User changes that invalidate a WebSocket snapshot close that user's sockets (#468).

The routes only have to ask the WebSocketManager; that the close then reaches
every process is covered in tests/services/test_ws_close_user.py.
"""
import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.core.security import create_ws_token
from app.services.websocket_manager import get_websocket_manager


@pytest.fixture
def closed_users(monkeypatch) -> list[int]:
    calls: list[int] = []

    async def _record(user_id: int) -> None:
        calls.append(user_id)

    monkeypatch.setattr(get_websocket_manager(), "close_user_connections", _record)
    return calls


class TestUpdateUser:
    def test_role_change_closes_sockets(self, client: TestClient, admin_headers, regular_user, closed_users):
        r = client.put(f"/api/users/{regular_user.id}", json={"role": "admin"}, headers=admin_headers)
        assert r.status_code == 200
        assert closed_users == [regular_user.id]

    def test_deactivation_closes_sockets(self, client: TestClient, admin_headers, regular_user, closed_users):
        r = client.put(f"/api/users/{regular_user.id}", json={"is_active": False}, headers=admin_headers)
        assert r.status_code == 200
        assert closed_users == [regular_user.id]

    def test_unrelated_change_leaves_sockets_open(self, client: TestClient, admin_headers, regular_user, closed_users):
        r = client.put(f"/api/users/{regular_user.id}", json={"email": "new@example.com"}, headers=admin_headers)
        assert r.status_code == 200
        assert closed_users == []

    def test_same_role_again_leaves_sockets_open(self, client: TestClient, admin_headers, regular_user, closed_users):
        r = client.put(f"/api/users/{regular_user.id}", json={"role": regular_user.role}, headers=admin_headers)
        assert r.status_code == 200
        assert closed_users == []


class TestUpdateUserAudit:
    """The audit details compared against old_user after update_user() had
    already mutated that same identity-mapped object, so role and email
    changes were never recorded."""

    @pytest.fixture
    def audit_details(self, monkeypatch) -> list[dict]:
        import app.api.routes.users as users_routes

        recorded: list[dict] = []

        class _Audit:
            def log_user_management(self, action, details=None, target_user=None, **kwargs):
                if action == "user_updated":
                    recorded.append(details or {})
                    self.last_target = target_user

        audit = _Audit()
        monkeypatch.setattr(users_routes, "get_audit_logger_db", lambda: audit)
        self.audit = audit
        return recorded

    def test_rename_is_audited_under_the_old_name(
        self, client: TestClient, admin_headers, regular_user, closed_users, audit_details
    ):
        old_name = regular_user.username
        r = client.put(f"/api/users/{regular_user.id}", json={"username": "renamed"}, headers=admin_headers)
        assert r.status_code == 200
        assert self.audit.last_target == old_name

    def test_role_change_is_audited(self, client: TestClient, admin_headers, regular_user, closed_users, audit_details):
        old_role = regular_user.role
        r = client.put(f"/api/users/{regular_user.id}", json={"role": "admin"}, headers=admin_headers)
        assert r.status_code == 200
        assert audit_details == [{"role_changed": f"{old_role} -> admin"}]

    def test_email_change_is_audited(self, client: TestClient, admin_headers, regular_user, closed_users, audit_details):
        r = client.put(f"/api/users/{regular_user.id}", json={"email": "new@example.com"}, headers=admin_headers)
        assert r.status_code == 200
        assert audit_details == [{"email_changed": True}]


class TestToggleActive:
    def test_toggle_closes_sockets(self, client: TestClient, admin_headers, regular_user, closed_users):
        r = client.patch(f"/api/users/{regular_user.id}/toggle-active", headers=admin_headers)
        assert r.status_code == 200
        assert closed_users == [regular_user.id]


class TestDelete:
    def test_delete_closes_sockets(self, client: TestClient, admin_headers, regular_user, closed_users):
        user_id = regular_user.id
        r = client.delete(f"/api/users/{user_id}", headers=admin_headers)
        assert r.status_code == 204
        assert closed_users == [user_id]

    def test_bulk_delete_closes_sockets_of_deleted_users_only(
        self, client: TestClient, admin_headers, regular_user, closed_users
    ):
        user_id = regular_user.id
        r = client.post("/api/users/bulk-delete", json=[str(user_id), "999999"], headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["deleted"] == 1 and r.json()["failed_ids"] == ["999999"]
        assert closed_users == [user_id]


@pytest.fixture
def ws_db(monkeypatch, db_session):
    """Point the WS endpoint's own SessionLocal() at the test database.

    The endpoint opens its session directly instead of via get_db, so the
    dependency override doesn't reach it; without this every token would be
    refused as "user not found" and the refusal test below would prove nothing.
    """
    from sqlalchemy.orm import sessionmaker

    import app.core.database as database

    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    )


class TestWsConnectInactiveUser:
    def test_active_user_connects(self, client: TestClient, ws_db, regular_user):
        # Control: shows the refusal below is about is_active, not the setup.
        token = create_ws_token(user_id=regular_user.id, username=regular_user.username)

        with client.websocket_connect(f"/api/notifications/ws?token={token}") as ws:
            ws.send_text("ping")

    def test_inactive_user_is_refused(self, client: TestClient, ws_db, db_session, regular_user):
        regular_user.is_active = False
        db_session.commit()
        token = create_ws_token(user_id=regular_user.id, username=regular_user.username)

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/api/notifications/ws?token={token}") as ws:
                ws.receive_text()
