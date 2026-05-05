"""Unit tests for CoreUptimeRtcGuard."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.power.core_uptime_rtc_guard import CoreUptimeRtcGuard


def _build_guard():
    """Build a guard with no-op callbacks; tests patch what they need."""
    return CoreUptimeRtcGuard(
        next_core_start_provider=lambda: None,
        is_baluhost_suspend_in_progress=lambda: False,
    )


class TestDelayInhibitor:
    """Subprocess lifecycle for the delay-mode systemd-inhibit lock."""

    def test_acquire_returns_false_when_systemd_inhibit_missing(self):
        guard = _build_guard()
        with patch("app.services.power.core_uptime_rtc_guard.shutil.which", return_value=None):
            ok = guard._acquire_delay_inhibitor()
        assert ok is False
        assert guard._delay_proc is None

    def test_acquire_spawns_subprocess_with_delay_mode(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        fake_proc.pid = 12345
        with patch("app.services.power.core_uptime_rtc_guard.shutil.which",
                   return_value="/usr/bin/systemd-inhibit"), \
             patch("app.services.power.core_uptime_rtc_guard.subprocess.Popen",
                   return_value=fake_proc) as mock_popen, \
             patch("app.services.power.core_uptime_rtc_guard.time.sleep"):
            ok = guard._acquire_delay_inhibitor()
        assert ok is True
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        assert "--mode=delay" in cmd
        assert "--what=sleep" in cmd
        assert "--who=BaluHost" in cmd

    def test_acquire_idempotent_when_already_held(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        guard._delay_proc = fake_proc
        with patch("app.services.power.core_uptime_rtc_guard.subprocess.Popen") as mock_popen:
            ok = guard._acquire_delay_inhibitor()
        assert ok is True
        mock_popen.assert_not_called()

    def test_acquire_detects_immediate_polkit_denial(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        # poll() returns None first (still alive after spawn), then 1 (exited
        # immediately during settle window — i.e. polkit denied).
        fake_proc.poll.side_effect = [1]
        fake_proc.returncode = 1
        fake_proc.stderr = None
        with patch("app.services.power.core_uptime_rtc_guard.shutil.which",
                   return_value="/usr/bin/systemd-inhibit"), \
             patch("app.services.power.core_uptime_rtc_guard.subprocess.Popen",
                   return_value=fake_proc), \
             patch("app.services.power.core_uptime_rtc_guard.time.sleep"):
            ok = guard._acquire_delay_inhibitor()
        assert ok is False
        assert guard._delay_proc is None

    def test_release_terminates_subprocess(self):
        guard = _build_guard()
        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        fake_proc.pid = 12345
        guard._delay_proc = fake_proc
        guard._release_delay_inhibitor()
        fake_proc.terminate.assert_called_once()
        assert guard._delay_proc is None

    def test_release_idempotent_when_no_proc(self):
        guard = _build_guard()
        guard._release_delay_inhibitor()
        # No exception means pass.
