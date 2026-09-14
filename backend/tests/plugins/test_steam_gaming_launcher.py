"""steam:// dispatch for the steam_gaming plugin - through the user's systemd.

Measured on BaluNode (2026-09-14, M5 in the design doc): with an EMPTY caller
environment, ``systemd-run --user --collect steam steam://rungameid/400``
cold-starts Steam and the game appears. The unit runs in sven's user manager,
so Steam inherits neither the backend's secrets nor its cgroup.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.plugins.installed.steam_gaming import launcher
from app.plugins.installed.steam_gaming.launcher import (
    BIG_PICTURE_URL,
    CLOSE_BIG_PICTURE_URL,
    close_big_picture,
    open_big_picture,
)

_SETTINGS = "app.plugins.installed.steam_gaming.launcher.settings"


def _completed(returncode: int = 0, stderr: bytes = b"") -> MagicMock:
    return MagicMock(returncode=returncode, stderr=stderr)


@pytest.fixture
def prod(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    with patch(_SETTINGS) as cfg:
        cfg.is_dev_mode = False
        yield cfg


class TestArgv:
    def test_open_goes_through_the_user_manager(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            ok, _detail = open_big_picture()

        assert ok is True
        assert run.call_args.args[0] == [
            "systemd-run", "--user", "--collect", "--quiet", "steam", BIG_PICTURE_URL,
        ]

    def test_close_goes_through_the_user_manager(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            ok, _detail = close_big_picture()

        assert ok is True
        assert run.call_args.args[0][-1] == CLOSE_BIG_PICTURE_URL
        assert run.call_args.args[0][:5] == ["systemd-run", "--user", "--collect", "--quiet", "steam"]

    def test_close_url_is_not_the_open_url(self):
        """A copy-paste slip here would make the exit action re-open Big
        Picture, and nothing downstream could tell the difference."""
        assert CLOSE_BIG_PICTURE_URL != BIG_PICTURE_URL

    def test_never_a_shell(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert "shell" not in run.call_args.kwargs

    def test_is_bounded_by_a_timeout(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert run.call_args.kwargs["timeout"] == launcher._STEAM_RUN_TIMEOUT_SECONDS == 10
        assert run.call_args.kwargs["stdin"] == subprocess.DEVNULL


class TestEnvironment:
    def test_backend_secrets_never_reach_the_call(self, prod, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "must-not-leak")
        monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        env = run.call_args.kwargs["env"]
        assert "SECRET_KEY" not in env
        assert "DATABASE_URL" not in env
        assert set(env) <= set(launcher._ENV_ALLOWLIST)

    def test_keeps_the_runtime_dir_it_was_given(self, prod):
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert run.call_args.kwargs["env"]["XDG_RUNTIME_DIR"] == "/run/user/1000"

    def test_derives_the_runtime_dir_from_the_uid_when_missing(self, prod, monkeypatch):
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setattr(launcher.os, "getuid", lambda: 1234, raising=False)
        with patch("subprocess.run", return_value=_completed()) as run:
            open_big_picture()

        assert run.call_args.kwargs["env"]["XDG_RUNTIME_DIR"] == "/run/user/1234"


class TestFailures:
    def test_missing_systemd_run_is_reported_not_raised(self, prod):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            ok, detail = open_big_picture()

        assert ok is False
        assert "steam" in detail.lower()

    def test_a_timeout_is_reported_not_raised(self, prod):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("systemd-run", 10)):
            ok, _detail = open_big_picture()

        assert ok is False

    def test_an_os_error_is_reported_not_raised(self, prod):
        with patch("subprocess.run", side_effect=OSError("fork failed")):
            ok, _detail = open_big_picture()

        assert ok is False

    def test_a_non_zero_exit_is_a_failure_without_leaking_stderr(self, prod):
        """No user manager (nobody logged in) makes systemd-run exit non-zero."""
        failed = _completed(1, b"Failed to connect to bus: /run/user/1000/secret-path")
        with patch("subprocess.run", return_value=failed):
            ok, detail = close_big_picture()

        assert ok is False
        assert "secret-path" not in detail


class TestDevMode:
    def test_dev_mode_does_not_spawn_anything(self):
        with patch(_SETTINGS) as cfg, patch("subprocess.run") as run:
            cfg.is_dev_mode = True
            ok_open, _ = open_big_picture()
            ok_close, _ = close_big_picture()

        assert ok_open is True and ok_close is True
        run.assert_not_called()
