"""
Tests for registration restriction via registration_enabled config flag.

Tests:
- Registration returns 403 when registration_enabled=False
- Registration works normally when registration_enabled=True
"""
import pytest
from fastapi.testclient import TestClient


REGISTER_URL = "/api/auth/register"
VALID_PAYLOAD = {
    "username": "newuser",
    "email": "new@test.com",
    "password": "Str0ngPass1",
}


class TestRegistrationRestriction:
    """Tests for the registration_enabled config guard."""

    def test_register_rejected_when_disabled(self, client: TestClient, monkeypatch):
        """Registration should return 403 when registration_enabled is False."""
        monkeypatch.setattr("app.api.routes.auth.settings.registration_enabled", False)

        response = client.post(REGISTER_URL, json=VALID_PAYLOAD)

        assert response.status_code == 403
        detail = response.json()["detail"]
        assert "disabled" in detail.lower()

    def test_register_allowed_when_enabled(self, client: TestClient, monkeypatch):
        """Registration should succeed (201) when registration_enabled is True."""
        monkeypatch.setattr("app.api.routes.auth.settings.registration_enabled", True)

        response = client.post(REGISTER_URL, json=VALID_PAYLOAD)

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["user"]["username"] == "newuser"

    def test_register_disabled_does_not_create_user(self, client: TestClient, monkeypatch):
        """When registration is disabled, no user record should be created."""
        monkeypatch.setattr("app.api.routes.auth.settings.registration_enabled", False)

        response = client.post(REGISTER_URL, json=VALID_PAYLOAD)
        assert response.status_code == 403

        # Re-enable registration and try to register the same user.
        # If the user was accidentally created above, this would return 409.
        monkeypatch.setattr("app.api.routes.auth.settings.registration_enabled", True)
        response = client.post(REGISTER_URL, json=VALID_PAYLOAD)
        assert response.status_code == 201

    def test_register_disabled_returns_proper_json(self, client: TestClient, monkeypatch):
        """The 403 response should be valid JSON with a detail field."""
        monkeypatch.setattr("app.api.routes.auth.settings.registration_enabled", False)

        response = client.post(REGISTER_URL, json=VALID_PAYLOAD)

        assert response.status_code == 403
        body = response.json()
        assert "detail" in body
        assert body["detail"] == "Public registration is disabled. Contact an administrator."
