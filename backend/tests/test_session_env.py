"""Wayland session environment helper."""
from __future__ import annotations

from app.services.power.session_env import wayland_session_env


class TestWaylandSessionEnv:
    def test_sets_runtime_dir_and_display_for_the_uid(self):
        env = wayland_session_env(uid=1000)
        assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"
        assert env["WAYLAND_DISPLAY"] == "wayland-0"

    def test_keeps_existing_environment(self, monkeypatch):
        monkeypatch.setenv("PATH", "/custom/bin")
        assert wayland_session_env(uid=1000)["PATH"] == "/custom/bin"

    def test_does_not_override_an_explicit_session(self, monkeypatch):
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-7")
        assert wayland_session_env(uid=1000)["WAYLAND_DISPLAY"] == "wayland-7"


class TestDesktopBackendUsesTheHelper:
    def test_linux_backend_env_matches_the_helper(self):
        from app.services.power.desktop_backend import LinuxDesktopBackend

        backend = LinuxDesktopBackend(uid=1000)
        assert backend._session_env() == wayland_session_env(uid=1000)
