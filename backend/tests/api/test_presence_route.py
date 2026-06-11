"""Integration tests for POST /api/system/sleep/presence (issue #214)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_auth_headers
from app.core.config import settings

PRESENCE_URL = f"{settings.api_prefix}/system/sleep/presence"


@pytest.fixture
def user_headers(client: TestClient, regular_user) -> dict[str, str]:
    return get_auth_headers(client, "testuser", "Testpass123!")


class TestPresenceHeartbeat:
    def test_requires_auth(self, client: TestClient):
        r = client.post(PRESENCE_URL, json={"client_id": "tab-12345678", "client_type": "web"})
        assert r.status_code in (401, 403)

    def test_regular_user_can_heartbeat(self, client: TestClient, user_headers):
        with patch("app.api.routes.sleep.presence_service.record_heartbeat") as mock_record, \
             patch("app.api.routes.sleep.presence_service.get_presence_settings",
                   return_value=(True, "active", 3)):
            r = client.post(
                PRESENCE_URL, headers=user_headers,
                json={"client_id": "tab-12345678", "client_type": "web"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["present"] is True
        assert body["enabled"] is True
        assert body["mode"] == "active"
        assert body["heartbeat_interval_seconds"] == 45
        assert body["timeout_minutes"] == 3
        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs["client_id"] == "tab-12345678"
        assert kwargs["client_type"] == "web"

    def test_rejects_short_client_id(self, client: TestClient, user_headers):
        r = client.post(PRESENCE_URL, headers=user_headers,
                        json={"client_id": "x", "client_type": "web"})
        assert r.status_code == 422

    def test_rejects_invalid_chars_in_client_id(self, client: TestClient, user_headers):
        r = client.post(PRESENCE_URL, headers=user_headers,
                        json={"client_id": "tab/../../etc", "client_type": "web"})
        assert r.status_code == 422

    def test_rejects_unknown_client_type(self, client: TestClient, user_headers):
        r = client.post(PRESENCE_URL, headers=user_headers,
                        json={"client_id": "tab-12345678", "client_type": "toaster"})
        assert r.status_code == 422
