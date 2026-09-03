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

    def test_a_raising_unlock_does_not_500_the_route(
        self, client, admin_headers, desktop_enabled
    ):
        """Before the guard, an OSError from the unlock path propagated to the
        global handler - a 500 on a call whose displays were already on."""
        from unittest.mock import AsyncMock, patch

        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(side_effect=OSError("boom")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/enable", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        assert response.json()["success"] is True


@pytest.fixture
def desktop_running():
    from app.schemas.desktop import DesktopState, DesktopStatus

    service = MagicMock()
    service.get_status = AsyncMock(
        return_value=DesktopStatus(
            state=DesktopState.RUNNING, display_manager="sddm", detail="1 active display(s)"
        )
    )
    with patch("app.api.routes.desktop.get_desktop_service", return_value=service):
        yield service


class TestStatusCarriesTheLockState:
    """The unlock button's visibility needs displays AND lock state in one read."""

    def test_locked_session_is_reported(self, client, admin_headers, desktop_running):
        with patch(
            "app.api.routes.desktop.current_lock_state", AsyncMock(return_value=True)
        ):
            response = client.get(
                "/api/system/sleep/desktop/status", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["state"] == "running"
        assert body["session_locked"] is True

    def test_unlocked_session_is_reported(self, client, admin_headers, desktop_running):
        with patch(
            "app.api.routes.desktop.current_lock_state", AsyncMock(return_value=False)
        ):
            response = client.get(
                "/api/system/sleep/desktop/status", headers=admin_headers
            )

        assert response.json()["session_locked"] is False

    def test_an_unknown_lock_state_stays_null(self, client, admin_headers, desktop_running):
        """null must not collapse to false - the frontend hides the button on
        null, and showing it on a box that cannot answer would be a dead end."""
        with patch(
            "app.api.routes.desktop.current_lock_state", AsyncMock(return_value=None)
        ):
            response = client.get(
                "/api/system/sleep/desktop/status", headers=admin_headers
            )

        assert response.json()["session_locked"] is None

    def test_the_desktop_service_is_never_asked_for_the_lock_state(
        self, client, admin_headers, desktop_running
    ):
        """The status bar polls the SERVICE every 10s; the lock read lives in
        the route so that poll never spawns a loginctl."""
        from app.services.power.desktop import DesktopService

        assert not hasattr(DesktopService, "is_locked")


class TestUnlockRoute:
    def test_admin_can_unlock(self, client, admin_headers):
        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(return_value=(True, "session 2 unlocked")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/unlock", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        assert response.json()["success"] is True

    def test_a_refused_unlock_is_a_200_with_success_false(self, client, admin_headers):
        """The gates live in the policy; a refusal is an outcome, not an error."""
        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(return_value=(False, "not permitted from this network")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/unlock", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is False
        assert body["message"] == "not permitted from this network"

    def test_a_raising_policy_does_not_500(self, client, admin_headers):
        with patch(
            "app.api.routes.desktop.unlock_if_permitted",
            AsyncMock(side_effect=OSError("boom")),
        ):
            response = client.post(
                "/api/system/sleep/desktop/unlock", headers=admin_headers
            )

        assert response.status_code == 200, response.text
        assert response.json()["success"] is False

    def test_the_client_ip_reaches_the_gate(self, client, admin_headers):
        gate = AsyncMock(return_value=(True, "unlocked"))
        with patch("app.api.routes.desktop.unlock_if_permitted", gate):
            client.post("/api/system/sleep/desktop/unlock", headers=admin_headers)

        assert gate.await_args.kwargs["client_host"] is not None

    def test_anonymous_callers_are_rejected(self, client):
        response = client.post("/api/system/sleep/desktop/unlock")

        assert response.status_code in (401, 403)

    def test_a_plain_user_reaches_the_policy_rather_than_a_role_gate(
        self, client, user_headers
    ):
        """Deliberately NOT gated on admin at the route: unlock_if_permitted is
        the single place both gates are evaluated and audited. A second gate in
        front would silently drift from the delegated can_unlock_session right."""
        gate = AsyncMock(return_value=(False, "permission required: power:unlock_session"))
        with patch("app.api.routes.desktop.unlock_if_permitted", gate):
            response = client.post(
                "/api/system/sleep/desktop/unlock", headers=user_headers
            )

        assert response.status_code == 200, response.text
        assert response.json()["success"] is False
        gate.assert_awaited_once()
