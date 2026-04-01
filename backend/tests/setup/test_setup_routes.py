"""Integration tests for setup wizard API endpoints."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.setup import service as setup_service


@pytest.fixture(autouse=True)
def reset_setup_flag():
    """Reset the in-memory _setup_complete flag before each test."""
    setup_service._reset_setup_complete()
    yield
    setup_service._reset_setup_complete()


class TestSetupStatus:
    """Tests for GET /api/setup/status."""

    def test_setup_required_on_empty_db(self, client: TestClient, db_session: Session):
        """Returns setup_required=true with no users."""
        db_session.query(User).delete()
        db_session.commit()
        resp = client.get("/api/setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["setup_required"] is True

    def test_setup_not_required_with_users(self, client: TestClient, admin_user):
        """Returns setup_required=false when users exist."""
        resp = client.get("/api/setup/status")
        assert resp.status_code == 200
        assert resp.json()["setup_required"] is False

    def test_setup_not_required_with_skip_env(self, client: TestClient, db_session: Session):
        """Returns setup_required=false when SKIP_SETUP is set."""
        db_session.query(User).delete()
        db_session.commit()
        with patch("app.services.setup.service.settings") as mock_settings:
            mock_settings.skip_setup = True
            resp = client.get("/api/setup/status")
            assert resp.status_code == 200
            assert resp.json()["setup_required"] is False


class TestSetupAdmin:
    """Tests for POST /api/setup/admin."""

    def test_create_admin_success(self, client: TestClient, db_session: Session):
        """Creates admin and returns setup token."""
        db_session.query(User).delete()
        db_session.commit()
        resp = client.post("/api/setup/admin", json={
            "username": "myadmin",
            "password": "SecurePass123!",
            "email": "admin@example.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "setup_token" in data
        assert data["username"] == "myadmin"

    def test_create_admin_forbidden_when_users_exist(self, client: TestClient, admin_user):
        """Returns 403 if users already exist."""
        resp = client.post("/api/setup/admin", json={
            "username": "hacker",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 403

    def test_create_admin_rejects_weak_password(self, client: TestClient, db_session: Session):
        """Rejects admin creation with weak password."""
        db_session.query(User).delete()
        db_session.commit()
        resp = client.post("/api/setup/admin", json={
            "username": "admin",
            "password": "weak",
        })
        assert resp.status_code == 422

    def test_create_admin_requires_secret_when_configured(self, client: TestClient, db_session: Session):
        """Requires setup_secret when BALUHOST_SETUP_SECRET is set."""
        db_session.query(User).delete()
        db_session.commit()
        with patch("app.api.routes.setup.settings") as mock_settings:
            mock_settings.setup_secret = "my-secret-123"
            mock_settings.skip_setup = False
            resp = client.post("/api/setup/admin", json={
                "username": "admin",
                "password": "SecurePass123!",
            })
            assert resp.status_code == 403


class TestSetupUsers:
    """Tests for POST /api/setup/users and DELETE /api/setup/users/{id}."""

    def _create_admin_and_get_token(self, client: TestClient, db_session: Session) -> str:
        db_session.query(User).delete()
        db_session.commit()
        resp = client.post("/api/setup/admin", json={
            "username": "admin",
            "password": "SecurePass123!",
        })
        return resp.json()["setup_token"]

    def test_create_user_with_setup_token(self, client: TestClient, db_session: Session):
        """Creates a regular user with valid setup token."""
        token = self._create_admin_and_get_token(client, db_session)
        resp = client.post(
            "/api/setup/users",
            json={"username": "alice", "password": "Alice123!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "alice"

    def test_create_user_without_token_fails(self, client: TestClient, db_session: Session):
        """Rejects user creation without setup token."""
        self._create_admin_and_get_token(client, db_session)
        resp = client.post("/api/setup/users", json={
            "username": "alice",
            "password": "Alice123!",
        })
        assert resp.status_code == 401

    def test_delete_user_works(self, client: TestClient, db_session: Session):
        """Can delete a user created during setup."""
        token = self._create_admin_and_get_token(client, db_session)
        create_resp = client.post(
            "/api/setup/users",
            json={"username": "bob", "password": "BobPass123!"},
            headers={"Authorization": f"Bearer {token}"},
        )
        user_id = create_resp.json()["user_id"]
        del_resp = client.delete(
            f"/api/setup/users/{user_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 200


class TestSetupFileAccess:
    """Tests for POST /api/setup/file-access."""

    def _get_setup_token(self, client: TestClient, db_session: Session) -> str:
        db_session.query(User).delete()
        db_session.commit()
        resp = client.post("/api/setup/admin", json={
            "username": "admin",
            "password": "SecurePass123!",
        })
        return resp.json()["setup_token"]

    def test_activate_samba(self, client: TestClient, db_session: Session):
        """Activates Samba with config."""
        token = self._get_setup_token(client, db_session)
        resp = client.post(
            "/api/setup/file-access",
            json={"samba": {"enabled": True, "workgroup": "HOME"}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "samba" in resp.json()["active_services"]

    def test_activate_webdav(self, client: TestClient, db_session: Session):
        """Activates WebDAV with config."""
        token = self._get_setup_token(client, db_session)
        resp = client.post(
            "/api/setup/file-access",
            json={"webdav": {"enabled": True, "port": 9443}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "webdav" in resp.json()["active_services"]

    def test_rejects_neither_enabled(self, client: TestClient, db_session: Session):
        """Rejects request with no service enabled."""
        token = self._get_setup_token(client, db_session)
        resp = client.post(
            "/api/setup/file-access",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400


class TestSetupComplete:
    """Tests for POST /api/setup/complete."""

    def test_complete_setup(self, client: TestClient, db_session: Session):
        """Marks setup as complete."""
        db_session.query(User).delete()
        db_session.commit()
        resp = client.post("/api/setup/admin", json={
            "username": "admin",
            "password": "SecurePass123!",
        })
        token = resp.json()["setup_token"]
        resp = client.post(
            "/api/setup/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_endpoints_blocked_after_complete(self, client: TestClient, db_session: Session):
        """All setup endpoints return 403 after completion."""
        db_session.query(User).delete()
        db_session.commit()
        resp = client.post("/api/setup/admin", json={
            "username": "admin",
            "password": "SecurePass123!",
        })
        token = resp.json()["setup_token"]
        client.post("/api/setup/complete", headers={"Authorization": f"Bearer {token}"})

        status_resp = client.get("/api/setup/status")
        assert status_resp.json()["setup_required"] is False

        admin_resp = client.post("/api/setup/admin", json={
            "username": "hacker",
            "password": "HackerPass123!",
        })
        assert admin_resp.status_code == 403
