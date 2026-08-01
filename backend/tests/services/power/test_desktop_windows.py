"""Minimizing every window of the KDE session (KWin's showDesktop setter)."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.services.power import desktop_windows
from app.services.power.desktop_windows import SHOW_DESKTOP_CMD, show_desktop


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestShowDesktopCommand:
    def test_uses_qdbus6(self):
        """Measured on BaluNode: Plasma 6 on Debian 13 ships no plain qdbus."""
        assert SHOW_DESKTOP_CMD[0] == "qdbus6"

    def test_sets_the_state_instead_of_toggling_it(self):
        """kglobalaccel's "Show Desktop" shortcut is a TOGGLE - a second call
        would bring the windows back. A regression to it would make the exit
        action undo itself on a retry, which no behavioural test can see."""
        assert SHOW_DESKTOP_CMD[-2:] == ["org.kde.KWin.showDesktop", "true"]
        assert "invokeShortcut" not in SHOW_DESKTOP_CMD


class TestShowDesktop:
    def test_calls_the_setter_and_reports_success(self):
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", return_value=_completed()) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True
        assert run.call_args.args[0] == SHOW_DESKTOP_CMD

    def test_does_not_second_guess_kwin_afterwards(self):
        """Regression guard for the false alarm shipped in #497.

        The obvious verification - reading org.kde.KWin.showingDesktop back -
        is WRONG: measured on the box, it reads false right after a successful
        call with the windows visibly down, because it tracks KWin's temporary
        show-desktop mode. Every successful run reported failure to the user.
        One call, no read-back.
        """
        with patch("app.services.power.desktop_windows.settings") as cfg, \
             patch("subprocess.run", return_value=_completed()) as run, \
             patch("app.services.power.desktop_windows.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True
        assert run.call_count == 1
        assert "showingDesktop" not in " ".join(run.call_args.args[0])

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
             patch("subprocess.run", return_value=_completed(1, stderr="no such service")), \
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


def test_the_module_no_longer_exposes_a_read_back_command():
    """Belt and braces for the same regression: the constant is gone, so a
    future edit cannot quietly wire the misleading property back in."""
    assert not hasattr(desktop_windows, "SHOWING_DESKTOP_CMD")
