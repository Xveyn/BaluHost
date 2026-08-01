"""Minimizing every window of the KDE session (KWin's showDesktop setter)."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.services.power.desktop_windows import (
    SHOW_DESKTOP_CMD,
    SHOWING_DESKTOP_CMD,
    show_desktop,
)


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _patch_run(*results):
    """Patch subprocess.run; consecutive calls get consecutive *results*."""
    if len(results) == 1:
        return patch("subprocess.run", return_value=results[0])
    return patch("subprocess.run", side_effect=list(results))


class TestShowDesktopCommands:
    def test_uses_qdbus6(self):
        """Measured on BaluNode: Plasma 6 on Debian 13 ships no plain qdbus."""
        assert SHOW_DESKTOP_CMD[0] == "qdbus6"
        assert SHOWING_DESKTOP_CMD[0] == "qdbus6"

    def test_sets_the_state_instead_of_toggling_it(self):
        """kglobalaccel's "Show Desktop" shortcut is a TOGGLE - a second call
        would bring the windows back. A regression to it would make the exit
        action undo itself on a retry, which no behavioural test can see."""
        assert SHOW_DESKTOP_CMD[-2:] == ["org.kde.KWin.showDesktop", "true"]
        assert "invokeShortcut" not in SHOW_DESKTOP_CMD

    def test_reads_kwins_own_property_back(self):
        assert SHOWING_DESKTOP_CMD[-1] == "org.kde.KWin.showingDesktop"


class TestShowDesktop:
    def test_calls_the_setter_and_reports_success(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             _patch_run(_completed(stdout=""), _completed(stdout="true")) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True
        assert run.call_args_list[0].args[0] == SHOW_DESKTOP_CMD

    def test_passes_the_wayland_session_env(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             _patch_run(_completed(), _completed(stdout="true")) as run, \
             patch(
                 "app.services.power.desktop_windows.wayland_session_env",
                 return_value={"XDG_RUNTIME_DIR": "/run/user/1000"},
             ):
            cfg.is_dev_mode = False
            show_desktop()

        assert run.call_args_list[0].kwargs["env"] == {"XDG_RUNTIME_DIR": "/run/user/1000"}

    def test_never_uses_a_shell(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             _patch_run(_completed(), _completed(stdout="true")) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            show_desktop()

        assert "shell" not in run.call_args_list[0].kwargs

    def test_sets_a_timeout_so_a_stuck_session_cannot_hang_the_action(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             _patch_run(_completed(), _completed(stdout="true")) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            show_desktop()

        assert run.call_args_list[0].kwargs["timeout"] > 0

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
             _patch_run(_completed(1, stderr="no such service")), \
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


class TestVerificationAgainstKwinsProperty:
    """The one step of ending gaming mode whose effect IS observable."""

    def test_kwin_contradicting_the_call_is_a_failure(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             _patch_run(_completed(), _completed(stdout="false")), \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert "visible" in detail

    def test_an_unreadable_property_does_not_invent_a_failure(self):
        """A property that cannot be read says nothing about the windows -
        reporting a red toast for it would announce a problem that may not
        exist."""
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             _patch_run(_completed(), _completed(1, stderr="boom")), \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True

    def test_a_property_read_that_raises_does_not_escape(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch(
                 "subprocess.run",
                 side_effect=[_completed(), subprocess.TimeoutExpired("qdbus6", 10)],
             ), \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True
