"""Minimizing every window of the KDE session (KWin's Show Desktop shortcut)."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.services.power import desktop_windows
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


def _visible() -> MagicMock:
    return _completed(stdout="false")


def _minimized() -> MagicMock:
    return _completed(stdout="true")


def _patch_run(*results):
    """Patch subprocess.run; consecutive calls get consecutive *results*."""
    return patch("subprocess.run", side_effect=list(results))


def _prod():
    return patch("app.services.power.desktop_windows.settings")


def _env():
    return patch("app.services.power.desktop_windows.wayland_session_env", return_value={})


class TestCommands:
    def test_uses_qdbus6(self):
        """Measured on BaluNode: Plasma 6 on Debian 13 ships no plain qdbus."""
        assert SHOW_DESKTOP_CMD[0] == "qdbus6"
        assert SHOWING_DESKTOP_CMD[0] == "qdbus6"

    def test_minimizes_through_the_shortcut_not_the_setter(self):
        """Regression guard for #497/#499. `org.kde.KWin.showDesktop(bool)`
        accepts the call and does nothing - it is Q_NOREPLY, so exit 0 means
        only that the message was sent. Measured on the box: the property
        stayed false and the windows stayed up. The shortcut works."""
        assert SHOW_DESKTOP_CMD[-2:] == ["invokeShortcut", "Show Desktop"]
        assert "showDesktop" not in " ".join(SHOW_DESKTOP_CMD)

    def test_reads_kwins_own_property_back(self):
        assert SHOWING_DESKTOP_CMD[-1] == "org.kde.KWin.showingDesktop"


class TestShowDesktop:
    def test_probes_first_then_invokes_then_verifies(self):
        with _prod() as cfg, _patch_run(_visible(), _completed(), _minimized()) as run, _env():
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True
        assert [call.args[0] for call in run.call_args_list] == [
            SHOWING_DESKTOP_CMD, SHOW_DESKTOP_CMD, SHOWING_DESKTOP_CMD,
        ]

    def test_does_not_fire_the_toggle_when_the_desktop_is_already_clear(self):
        """The shortcut TOGGLES - firing it now would bring the windows back."""
        with _prod() as cfg, _patch_run(_minimized()) as run, _env():
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is True
        assert "already" in detail
        assert run.call_count == 1

    def test_passes_the_wayland_session_env(self):
        with _prod() as cfg, \
             _patch_run(_visible(), _completed(), _minimized()) as run, \
             patch(
                 "app.services.power.desktop_windows.wayland_session_env",
                 return_value={"XDG_RUNTIME_DIR": "/run/user/1000"},
             ):
            cfg.is_dev_mode = False
            show_desktop()

        assert run.call_args_list[1].kwargs["env"] == {"XDG_RUNTIME_DIR": "/run/user/1000"}

    def test_never_uses_a_shell(self):
        with _prod() as cfg, _patch_run(_visible(), _completed(), _minimized()) as run, _env():
            cfg.is_dev_mode = False
            show_desktop()

        for call in run.call_args_list:
            assert "shell" not in call.kwargs

    def test_sets_a_timeout_so_a_stuck_session_cannot_hang_the_action(self):
        with _prod() as cfg, _patch_run(_visible(), _completed(), _minimized()) as run, _env():
            cfg.is_dev_mode = False
            show_desktop()

        for call in run.call_args_list:
            assert call.kwargs["timeout"] > 0

    def test_missing_qdbus_binary_is_reported_not_raised(self):
        with _prod() as cfg, \
             patch("subprocess.run", side_effect=FileNotFoundError()), _env():
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert "qdbus6" in detail

    def test_timeout_is_reported_not_raised(self):
        with _prod() as cfg, \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("qdbus6", 10)), _env():
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert "timed out" in detail

    def test_non_zero_exit_carries_the_stderr(self):
        with _prod() as cfg, \
             _patch_run(_visible(), _completed(1, stderr="no such service")), _env():
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert detail == "no such service"

    def test_dev_mode_does_not_spawn_anything(self):
        with _prod() as cfg, patch("subprocess.run") as run:
            cfg.is_dev_mode = True
            ok, _detail = show_desktop()

        assert ok is True
        run.assert_not_called()


class TestVerification:
    """The one step of ending gaming mode whose effect IS observable - and the
    reason #497 shipped a permanently failing action: the property was right,
    the setter was not."""

    def test_a_still_visible_desktop_is_a_failure(self):
        with _prod() as cfg, \
             patch("app.services.power.desktop_windows._VERIFY_TIMEOUT_SECONDS", 0), \
             _patch_run(_visible(), _completed(), _visible()), _env():
            cfg.is_dev_mode = False
            ok, detail = show_desktop()

        assert ok is False
        assert "visible" in detail

    def test_it_waits_for_kwin_instead_of_reading_once(self):
        """KWin applies the shortcut asynchronously; the manual measurement
        needed a moment. A single read would flag failures that never were."""
        with _prod() as cfg, \
             patch("time.sleep") as sleep, \
             _patch_run(_visible(), _completed(), _visible(), _minimized()), _env():
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True
        sleep.assert_called()

    def test_an_unreadable_property_does_not_invent_a_failure(self):
        """A property that cannot be read says nothing about the windows -
        a red toast for it would announce a problem that may not exist."""
        with _prod() as cfg, \
             _patch_run(_completed(1, stderr="boom"), _completed(), _completed(1)), _env():
            cfg.is_dev_mode = False
            ok, _detail = show_desktop()

        assert ok is True

    def test_an_unreadable_probe_still_fires_the_shortcut(self):
        with _prod() as cfg, \
             _patch_run(_completed(1), _completed(), _minimized()) as run, _env():
            cfg.is_dev_mode = False
            show_desktop()

        assert run.call_args_list[1].args[0] == SHOW_DESKTOP_CMD


def test_the_module_does_not_expose_the_useless_setter():
    """Belt and braces: nobody re-adds showDesktop(bool) from the interface
    listing without measuring it again."""
    for name in dir(desktop_windows):
        value = getattr(desktop_windows, name)
        if isinstance(value, list):
            assert "org.kde.KWin.showDesktop" not in value
