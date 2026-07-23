"""Big Picture launcher for the steam_gaming plugin."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from app.plugins.installed.steam_gaming.launcher import BIG_PICTURE_URL, open_big_picture


class TestOpenBigPicture:
    def test_launches_steam_with_the_big_picture_url(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen, \
             patch("app.plugins.installed.steam_gaming.launcher.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = open_big_picture()

        assert ok is True
        args, kwargs = popen.call_args
        assert args[0] == ["steam", BIG_PICTURE_URL]

    def test_detaches_so_steam_does_not_hang_off_the_backend(self):
        """steam:// hands off to a running instance and exits - but if Steam is
        NOT running, the same call starts it in the foreground."""
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen, \
             patch("app.plugins.installed.steam_gaming.launcher.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            open_big_picture()

        kwargs = popen.call_args.kwargs
        assert kwargs["start_new_session"] is True
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "shell" not in kwargs  # never shell=True

    def test_passes_the_wayland_session_env(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen, \
             patch(
                 "app.plugins.installed.steam_gaming.launcher.wayland_session_env",
                 return_value={"XDG_RUNTIME_DIR": "/run/user/1000"},
             ):
            cfg.is_dev_mode = False
            open_big_picture()

        assert popen.call_args.kwargs["env"] == {"XDG_RUNTIME_DIR": "/run/user/1000"}

    def test_missing_steam_binary_is_reported_not_raised(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen", side_effect=FileNotFoundError()), \
             patch("app.plugins.installed.steam_gaming.launcher.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, detail = open_big_picture()

        assert ok is False
        assert "steam" in detail.lower()

    def test_unexpected_os_error_is_reported_not_raised(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen", side_effect=OSError("no display")), \
             patch("app.plugins.installed.steam_gaming.launcher.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            ok, _detail = open_big_picture()

        assert ok is False

    def test_dev_mode_does_not_spawn_anything(self):
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen") as popen:
            cfg.is_dev_mode = True
            ok, _detail = open_big_picture()

        assert ok is True
        popen.assert_not_called()

    def test_never_waits_for_the_process(self):
        handle = MagicMock()
        with patch("app.plugins.installed.steam_gaming.launcher.settings") as cfg, \
             patch("subprocess.Popen", return_value=handle), \
             patch("app.plugins.installed.steam_gaming.launcher.wayland_session_env", return_value={}):
            cfg.is_dev_mode = False
            open_big_picture()

        handle.wait.assert_not_called()
        handle.communicate.assert_not_called()
