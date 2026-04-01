"""Tests for the cloud OAuth admin list endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from tests.conftest import get_auth_headers


class TestCloudOAuthAdminEndpoint:
    """Tests for GET /api/cloud/oauth-configs/all."""

    def test_requires_admin(self, client: TestClient, user_headers: dict):
        """Regular users should get 403."""
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all", headers=user_headers)
        assert resp.status_code == 403

    def test_admin_gets_empty_list(self, client: TestClient, admin_headers: dict):
        """Admin should get an empty list when no configs exist."""
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_admin_sees_user_config(self, client: TestClient, admin_headers: dict, user_headers: dict):
        """Admin should see configs created by other users."""
        # Create a config as regular user
        client.put(
            f"{settings.api_prefix}/cloud/oauth-config",
            json={"provider": "google_drive", "client_id": "test-id-12345678", "client_secret": "test-secret"},
            headers=user_headers,
        )

        # Admin should see it
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        google_config = next((c for c in data if c["provider"] == "google_drive"), None)
        assert google_config is not None
        assert google_config["username"] == "testuser"
        assert google_config["client_id_hint"] is not None

    def test_unauthenticated_gets_401(self, client: TestClient):
        """No auth should get 401."""
        resp = client.get(f"{settings.api_prefix}/cloud/oauth-configs/all")
        assert resp.status_code in (401, 403)
