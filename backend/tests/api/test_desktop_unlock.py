"""The enable route unlocks the session - but never fails because of it."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def desktop_enabled():
    service = MagicMock()
    service.enable = AsyncMock(return_value=(True, "ok"))
    with patch("app.api.routes.desktop.get_desktop_service", return_value=service):
        yield service


class TestEnableUnlocksTheSession:
    def test_response_reports_a_successful_unlock(
        self, client, admin_headers, desktop_enabled
    ):
        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(return_value=(True, "session 2 unlocked")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/enable", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["session_unlocked"] is True

    def test_a_failed_unlock_does_not_fail_the_enable(
        self, client, admin_headers, desktop_enabled
    ):
        """Turning the displays on is the primary action. If it started failing
        because a lock screen would not budge, the feature would be a
        regression rather than a convenience."""
        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(return_value=(False, "not permitted from this network")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/enable", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["session_unlocked"] is False
        assert body["unlock_message"] == "not permitted from this network"

    def test_the_client_ip_is_passed_to_the_gate(
        self, client, admin_headers, desktop_enabled
    ):
        gate = AsyncMock(return_value=(True, "unlocked"))
        with patch("app.api.routes.desktop.unlock_if_permitted", gate):
            client.post("/api/system/sleep/desktop/enable", headers=admin_headers)

        assert gate.await_args.kwargs["client_host"] is not None
