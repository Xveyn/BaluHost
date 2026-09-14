"""The gaming-mode start sequence shared by menu action and launch route."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.plugins.installed.steam_gaming import gaming_state, launch

_P = "app.plugins.installed.steam_gaming.launch"


@pytest.fixture(autouse=True)
def _marker_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(gaming_state.settings, "nas_storage_path", str(tmp_path))


def _desktop(ok: bool = True, order: list[str] | None = None):
    service = MagicMock()

    async def _enable():
        if order is not None:
            order.append("displays")
        return ok, "ok" if ok else "kscreen-doctor not found"

    service.enable = AsyncMock(side_effect=_enable)
    return patch(f"{_P}.get_desktop_service", return_value=service)


class TestStartGamingMode:
    async def test_order_is_displays_unlock_bigpicture_marker(self):
        order: list[str] = []

        async def _unlock(**_kwargs):
            order.append("unlock")
            return True, "unlocked"

        with _desktop(order=order), patch(f"{_P}.unlock_if_permitted", _unlock), patch(
            f"{_P}.open_big_picture",
            side_effect=lambda: order.append("bigpicture") or (True, "requested"),
        ), patch(
            f"{_P}.gaming_state.mark_started", side_effect=lambda: order.append("marker"),
        ):
            result = await launch.start_gaming_mode(
                user=MagicMock(role="admin"), client_host="192.168.178.29", db=None
            )

        assert result == launch.GamingModeStart(ok=True, failed_step=None, detail="requested")
        assert order == ["displays", "unlock", "bigpicture", "marker"]

    async def test_dark_displays_stop_everything(self):
        with _desktop(ok=False), patch(f"{_P}.open_big_picture") as bigpicture:
            result = await launch.start_gaming_mode(user=None, client_host=None, db=None)

        bigpicture.assert_not_called()
        assert result.ok is False and result.failed_step == "displays"
        assert gaming_state.is_active() is False

    async def test_a_refused_unlock_is_not_a_failure(self):
        async def _unlock(**_kwargs):
            return False, "permission required: power:unlock_session"

        with _desktop(), patch(f"{_P}.unlock_if_permitted", _unlock), patch(
            f"{_P}.open_big_picture", return_value=(True, "requested")
        ):
            result = await launch.start_gaming_mode(
                user=MagicMock(role="user"), client_host="192.168.178.29", db=None
            )

        assert result.ok is True

    async def test_no_user_means_no_unlock_attempt(self):
        gate = AsyncMock(return_value=(True, "unlocked"))
        with _desktop(), patch(f"{_P}.unlock_if_permitted", gate), patch(
            f"{_P}.open_big_picture", return_value=(True, "requested")
        ):
            await launch.start_gaming_mode(user=None, client_host=None, db=None)

        gate.assert_not_awaited()

    async def test_steam_failure_sets_no_marker(self):
        with _desktop(), patch(f"{_P}.open_big_picture", return_value=(False, "steam could not be started")):
            result = await launch.start_gaming_mode(user=None, client_host=None, db=None)

        assert result.ok is False and result.failed_step == "steam"
        assert gaming_state.is_active() is False

    async def test_an_already_set_marker_does_not_change_the_sequence(self):
        """Big Picture already open: a second open/bigpicture is forwarded to
        the running client (measured M4) - the sequence just runs again."""
        gaming_state.mark_started()
        with _desktop(), patch(f"{_P}.open_big_picture", return_value=(True, "requested")) as bigpicture:
            result = await launch.start_gaming_mode(user=None, client_host=None, db=None)

        bigpicture.assert_called_once()
        assert result.ok is True
        assert gaming_state.is_active() is True
