"""Tests for scoped WebSocket token authentication.

Verifies that:
- POST /api/notifications/ws-token returns a short-lived WS token
- The WS token has the correct type claim ("ws")
- The ws-token endpoint requires authentication (401 without auth)
- The WS token contains expected claims (sub, username)
"""

import jwt
import pytest
from app.core.config import settings
from app.core.security import create_ws_token


class TestWsTokenCreation:
    """Unit tests for create_ws_token() in core/security.py."""

    def test_ws_token_has_correct_type_claim(self):
        """WS token must have type='ws' to prevent token confusion."""
        token = create_ws_token(user_id=1, username="testuser")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["type"] == "ws"

    def test_ws_token_contains_sub_and_username(self):
        """WS token should contain the user's ID and username."""
        token = create_ws_token(user_id=42, username="alice")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"

    def test_ws_token_has_exp_claim(self):
        """WS token should have an expiration claim."""
        token = create_ws_token(user_id=1, username="testuser")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert "exp" in payload

    def test_ws_token_custom_expiry(self):
        """WS token should respect custom expiry seconds."""
        token = create_ws_token(user_id=1, username="testuser", expires_seconds=120)
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        # exp - iat should be ~120 seconds
        diff = payload["exp"] - payload["iat"]
        assert diff == 120


class TestWsTokenEndpoint:
    """Integration tests for POST /api/notifications/ws-token."""

    def test_ws_token_endpoint_returns_token(self, client, admin_headers):
        """Authenticated request should receive a WS token."""
        response = client.post("/api/notifications/ws-token", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert isinstance(data["token"], str)
        assert len(data["token"]) > 0

    def test_ws_token_endpoint_token_has_ws_type(self, client, admin_headers):
        """The token returned by the endpoint should have type='ws'."""
        response = client.post("/api/notifications/ws-token", headers=admin_headers)
        assert response.status_code == 200
        token = response.json()["token"]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["type"] == "ws"

    def test_ws_token_endpoint_requires_auth(self, client):
        """Request without auth should return 401."""
        response = client.post("/api/notifications/ws-token")
        assert response.status_code == 401

    def test_ws_token_endpoint_works_for_regular_user(self, client, user_headers):
        """Regular (non-admin) users should also be able to get a WS token."""
        response = client.post("/api/notifications/ws-token", headers=user_headers)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        # Decode to verify it's a valid WS token
        payload = jwt.decode(data["token"], settings.SECRET_KEY, algorithms=["HS256"])
        assert payload["type"] == "ws"
