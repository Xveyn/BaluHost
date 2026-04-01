"""Security tests for setup wizard endpoints."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, create_setup_token
from app.models.user import User
from app.services import users as user_service
from app.services.setup import service as setup_service
from app.schemas.user import UserCreate


@pytest.fixture(autouse=True)
def reset_setup_flag():
    """Reset the in-memory _setup_complete flag before each test."""
    setup_service._reset_setup_complete()
    yield
    setup_service._reset_setup_complete()


class TestSetupEndpointSecurity:
    """Verify all setup security invariants."""

    def test_setup_endpoints_blocked_after_users_exist(self, client: TestClient, db_session: Session):
        """All setup mutation endpoints return 401 or 403 when setup is complete.

        /admin returns 403 because users exist (is_setup_required → False).
        /users, /file-access, /complete, /users/<id> all require a setup token;
        without one they return 401 (get_setup_user raises 401 on missing token).
        """
        # Mark setup as complete so _require_setup_not_complete also blocks
        setup_service.complete_setup(db_session)

        endpoints = [
            # Use valid usernames (3+ chars) and strong passwords so Pydantic
            # validation passes and the route-level gate is what blocks the request.
            ("POST", "/api/setup/admin", {"username": "hacker", "password": "XPass123!"}),
            ("POST", "/api/setup/users", {"username": "alice", "password": "Alice123!"}),
            ("DELETE", "/api/setup/users/1", None),
            ("POST", "/api/setup/file-access", {"samba": {"enabled": True}}),
            ("POST", "/api/setup/complete", None),
        ]
        for method, path, body in endpoints:
            if method == "POST":
                resp = client.post(path, json=body)
            elif method == "DELETE":
                resp = client.delete(path)
            assert resp.status_code in (401, 403), (
                f"{method} {path} should be blocked (got {resp.status_code})"
            )

    def test_setup_token_rejected_on_regular_endpoints(self, client: TestClient, db_session: Session):
        """Setup token must not grant access to regular admin endpoints.

        get_current_user calls decode_token with token_type='access'; a setup
        token has type='setup' which causes InvalidTokenError → 401.
        """
        # Get any existing admin (client fixture creates one)
        admin = user_service.get_user_by_username("admin", db=db_session)
        if admin is None:
            admin = db_session.query(User).filter(User.role == "admin").first()
        assert admin is not None, "No admin user in test DB"

        token = create_setup_token(user_id=admin.id, username=admin.username)

        # /api/users/ is admin-only; a setup token must not work there
        resp = client.get(
            "/api/users/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_access_token_rejected_on_setup_endpoints(self, client: TestClient, db_session: Session):
        """Regular access token must not work on setup endpoints.

        get_setup_user calls decode_token with token_type='setup'; an access
        token has type='access' which causes InvalidTokenError → 401.
        """
        # Create a clean admin in an otherwise empty DB so /admin is available,
        # then use an access token (not setup token) against /users.
        db_session.query(User).delete()
        db_session.commit()
        admin = user_service.create_user(
            UserCreate(
                username="admin",
                email="a@example.com",
                password="Admin123!",
                role="admin",
            ),
            db=db_session,
        )
        token = create_access_token(admin)

        resp = client.post(
            "/api/setup/users",
            json={"username": "alice", "password": "Alice123!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_admin_endpoint_allows_remote_with_correct_secret(self, client: TestClient, db_session: Session):
        """Admin creation works when the correct setup secret is provided."""
        db_session.query(User).delete()
        db_session.commit()
        with patch("app.api.routes.setup.settings") as mock_settings:
            mock_settings.setup_secret = "my-secret"
            mock_settings.skip_setup = False
            mock_settings.is_dev_mode = True
            resp = client.post("/api/setup/admin", json={
                "username": "admin",
                "password": "SecurePass123!",
                "setup_secret": "my-secret",
            })
            assert resp.status_code == 201

    def test_admin_endpoint_rejects_wrong_secret(self, client: TestClient, db_session: Session):
        """Admin creation rejects a wrong setup secret with 403."""
        db_session.query(User).delete()
        db_session.commit()
        with patch("app.api.routes.setup.settings") as mock_settings:
            mock_settings.setup_secret = "correct-secret"
            mock_settings.skip_setup = False
            mock_settings.is_dev_mode = True
            resp = client.post("/api/setup/admin", json={
                "username": "admin",
                "password": "SecurePass123!",
                "setup_secret": "wrong-secret",
            })
            assert resp.status_code == 403

    def test_setup_token_cannot_be_used_after_setup_complete(self, client: TestClient, db_session: Session):
        """A valid setup token is rejected by /users once setup is marked complete."""
        db_session.query(User).delete()
        db_session.commit()
        resp = client.post("/api/setup/admin", json={
            "username": "admin",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 201
        token = resp.json()["setup_token"]

        # Mark setup as complete
        complete_resp = client.post(
            "/api/setup/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert complete_resp.status_code == 200

        # Now /users must be blocked even with a valid setup token
        resp = client.post(
            "/api/setup/users",
            json={"username": "late", "password": "Late123!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_setup_admin_endpoint_blocked_after_any_user_exists(self, client: TestClient, admin_user):
        """POST /api/setup/admin returns 403 if any user exists (uses _require_setup_mode)."""
        resp = client.post("/api/setup/admin", json={
            "username": "hacker",
            "password": "HackerPass123!",
        })
        assert resp.status_code == 403
