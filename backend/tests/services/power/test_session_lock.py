"""Unlocking the graphical KDE session via logind."""
from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import List

from app.services.power.session_lock import (
    DevSessionLockBackend,
    LinuxSessionLockBackend,
)

SHOW_USER = ["loginctl", "show-user", "1000", "-p", "Display", "--value"]
LIST_SESSIONS = ["loginctl", "list-sessions", "--no-legend"]

# Real output shape measured on the box (2026-07-24):
# SESSION UID USER SEAT LEADER CLASS TTY IDLE SINCE
LIST_OUTPUT = (
    "         1  993 ci-runner -     1975 manager-early -    no   -\n"
    "         2 1000 sven      seat0 2023 user          tty2 no   -\n"
    "        27 1000 sven      -    88823 user          -    no   -\n"
    "         3 1000 sven      -     2115 manager       -    no   -\n"
)


def _proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class FakeRunner:
    """Records commands and answers them from a table."""

    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: List[List[str]] = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        for key, value in self.responses.items():
            if list(key) == list(cmd):
                return value() if callable(value) else value
        # LockedHint reads are matched by prefix so tests can vary the session id
        if cmd[:2] == ["loginctl", "show-session"]:
            value = self.responses.get("locked_hint", _proc(stdout="no\n"))
            return value() if callable(value) else value
        return _proc(returncode=1, stderr="unexpected command")


def _backend(runner, monotonic_values=None):
    clock = iter(monotonic_values or [0.0] * 50)
    return LinuxSessionLockBackend(
        uid=1000,
        runner=runner,
        sleep=lambda _seconds: None,
        monotonic=lambda: next(clock),
    )


class TestSessionDiscovery:
    def test_uses_the_display_property_when_present(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
        })

        ok, detail = _backend(runner).unlock()

        assert ok is True
        assert "2" in detail
        assert LIST_SESSIONS not in runner.calls, "fallback must not run when Display works"

    def test_falls_back_to_list_sessions_when_display_is_empty(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="\n"),
            tuple(LIST_SESSIONS): _proc(stdout=LIST_OUTPUT),
            ("loginctl", "unlock-session", "2"): _proc(),
        })

        ok, _detail = _backend(runner).unlock()

        assert ok is True
        assert ["loginctl", "unlock-session", "2"] in runner.calls

    def test_fallback_skips_seatless_and_non_user_sessions(self):
        """Session 27 is the SSH login (no seat), 3 is the user manager,
        1 belongs to the CI runner - none of them may be picked."""
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="\n"),
            tuple(LIST_SESSIONS): _proc(stdout=LIST_OUTPUT),
            ("loginctl", "unlock-session", "2"): _proc(),
        })

        _backend(runner).unlock()

        unlocked = [c for c in runner.calls if c[:2] == ["loginctl", "unlock-session"]]
        assert unlocked == [["loginctl", "unlock-session", "2"]]

    def test_no_graphical_session_is_a_clean_failure(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="\n"),
            tuple(LIST_SESSIONS): _proc(stdout="         1  993 ci-runner - 1975 manager-early - no -\n"),
        })

        ok, detail = _backend(runner).unlock()

        assert ok is False
        assert "no graphical session" in detail


class TestUnlockVerification:
    def test_success_requires_locked_hint_to_flip(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
            "locked_hint": _proc(stdout="no\n"),
        })

        ok, _detail = _backend(runner).unlock()

        assert ok is True

    def test_a_locker_that_ignores_the_signal_is_reported_as_failure(self):
        """loginctl exits 0 as soon as the signal is SENT. Without reading the
        hint back the API would claim 'unlocked' over a locked screen."""
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
            "locked_hint": _proc(stdout="yes\n"),
        })

        ok, detail = _backend(runner, monotonic_values=[0.0, 0.0, 1.0, 2.0, 9.0]).unlock()

        assert ok is False
        assert "LockedHint" in detail

    def test_polls_until_the_hint_flips(self):
        """kscreenlocker needs a moment; a single immediate read would flap."""
        hints = iter([_proc(stdout="yes\n"), _proc(stdout="yes\n"), _proc(stdout="no\n")])
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(),
            "locked_hint": lambda: next(hints),
        })

        ok, _detail = _backend(runner).unlock()

        assert ok is True

    def test_nonzero_exit_is_reported(self):
        runner = FakeRunner({
            tuple(SHOW_USER): _proc(stdout="2\n"),
            ("loginctl", "unlock-session", "2"): _proc(returncode=1, stderr="Access denied"),
        })

        ok, detail = _backend(runner).unlock()

        assert ok is False
        assert "Access denied" in detail

    def test_missing_loginctl_is_reported(self):
        def _raise(_cmd):
            raise FileNotFoundError()

        ok, detail = _backend(_raise).unlock()

        assert ok is False
        assert "loginctl not found" in detail

    def test_timeout_is_reported(self):
        def _raise(_cmd):
            raise subprocess.TimeoutExpired(cmd="loginctl", timeout=10)

        ok, detail = _backend(_raise).unlock()

        assert ok is False
        assert "timed out" in detail


class TestDevBackend:
    def test_dev_backend_reports_success_without_loginctl(self):
        ok, detail = DevSessionLockBackend().unlock()

        assert ok is True
        assert "dev" in detail
