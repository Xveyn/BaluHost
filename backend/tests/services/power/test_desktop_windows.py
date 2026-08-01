"""Minimizing every window of the KDE session ("Show Desktop")."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.services.power.desktop_windows import SHOW_DESKTOP_CMD, show_desktop


def _completed(returncode: int = 0, stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = ""
    result.stderr = stderr
    return result


class TestShowDesktop:
    def test_invokes_kwins_show_desktop_shortcut(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", return_value=_completed()) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True
        assert run.call_args.args[0] == SHOW_DESKTOP_CMD

    def test_uses_qdbus6_and_the_measured_shortcut_name(self):
        """Both were measured on BaluNode - Plasma 6 ships no plain `qdbus`,
        and the shortcut is registered as exactly "Show Desktop"."""
        assert SHOW_DESKTOP_CMD[0] == "qdbus6"
        assert SHOW_DESKTOP_CMD[-1] == "Show Desktop"

    def test_passes_the_wayland_session_env(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", return_value=_completed()) as run, \
             patch(
                 "app.services.power.desktop_windows.wayland_session_env",
                 return_value={"XDG_RUNTIME_DIR": "/run/user/1000"},
             ):
            cfg.is_dev_mode = False
            show_desktop()

        assert run.call_args.kwargs["env"] == {"XDG_RUNTIME_DIR": "/run/user/1000"}

    def test_never_uses_a_shell(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", return_value=_completed()) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            show_desktop()

        assert "shell" not in run.call_args.kwargs

    def test_sets_a_timeout_so_a_stuck_session_cannot_hang_the_action(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", return_value=_completed()) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            show_desktop()

        assert run.call_args.kwargs["timeout"] > 0

    def test_missing_qdbus_binary_is_reported_not_raised(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", side_effect=FileNotFoundError()), \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert "qdbus6" in detail

    def test_timeout_is_reported_not_raised(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("qdbus6", 10)), \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert "timed out" in detail

    def test_non_zero_exit_carries_the_stderr(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", return_value=_completed(1, "no such service")), \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert detail == "no such service"

    def test_dev_mode_does_not_spawn_anything(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run") as run:
            cfg.is_dev_mode = True
            ok, _detail = show_desktop()

        assert ok is True
        run.assert_not_called()
