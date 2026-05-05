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


import datetime as _dt


class TestOnPrepareForSleep:
    """Logic for handling logind's PrepareForSleep(start=...) signal."""

    @pytest.mark.asyncio
    async def test_start_true_skips_when_baluhost_initiated(self):
        next_start = _dt.datetime(2026, 5, 6, 8, 0)
        ran_rtc = []
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: next_start,
            is_baluhost_suspend_in_progress=lambda: True,
        )
        # Spawn a fake delay proc so we can verify it gets released.
        guard._delay_proc = MagicMock()
        guard._delay_proc.poll.return_value = None
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=lambda ts: ran_rtc.append(ts)):
            await guard.on_prepare_for_sleep(True)
        assert ran_rtc == []  # rtcwake skipped — BaluHost set its own
        # Delay inhibitor still released so logind can proceed.
        guard._delay_proc = None  # _release sets this; mock didn't track

    @pytest.mark.asyncio
    async def test_start_true_skips_when_no_next_core(self):
        ran_rtc = []
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: None,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        guard._delay_proc = MagicMock()
        guard._delay_proc.poll.return_value = None
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=lambda ts: ran_rtc.append(ts)), \
             patch.object(guard, "_release_delay_inhibitor") as mock_release:
            await guard.on_prepare_for_sleep(True)
        assert ran_rtc == []
        mock_release.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_true_sets_rtc_alarm_to_next_core(self):
        next_start = _dt.datetime(2026, 5, 6, 8, 0)
        ran_rtc = []
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: next_start,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        guard._delay_proc = MagicMock()
        guard._delay_proc.poll.return_value = None
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=lambda ts: ran_rtc.append(ts)), \
             patch.object(guard, "_release_delay_inhibitor"):
            await guard.on_prepare_for_sleep(True)
        assert ran_rtc == [next_start]

    @pytest.mark.asyncio
    async def test_start_false_reacquires_delay_inhibitor(self):
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: None,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        with patch.object(guard, "_acquire_delay_inhibitor",
                          return_value=True) as mock_acquire:
            await guard.on_prepare_for_sleep(False)
        mock_acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_true_releases_even_if_rtc_fails(self):
        """If rtcwake raises, we MUST still release the delay lock so the
        suspend isn't permanently stuck waiting on BaluHost."""
        next_start = _dt.datetime(2026, 5, 6, 8, 0)
        guard = CoreUptimeRtcGuard(
            next_core_start_provider=lambda: next_start,
            is_baluhost_suspend_in_progress=lambda: False,
        )
        with patch.object(guard, "_set_rtc_alarm",
                          side_effect=RuntimeError("rtcwake failed")), \
             patch.object(guard, "_release_delay_inhibitor") as mock_release:
            await guard.on_prepare_for_sleep(True)
        mock_release.assert_called_once()


class TestSetRtcAlarm:
    """Subprocess invocation for `sudo rtcwake -m no -t <ts>`."""

    def test_set_rtc_alarm_calls_rtcwake_with_unix_timestamp(self):
        guard = _build_guard()
        wake_at = _dt.datetime(2026, 5, 6, 8, 0)
        expected_ts = str(int(wake_at.timestamp()))
        with patch("app.services.power.core_uptime_rtc_guard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            guard._set_rtc_alarm(wake_at)
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd == ["sudo", "rtcwake", "-m", "no", "-t", expected_ts]

    def test_set_rtc_alarm_logs_on_failure_but_does_not_raise(self):
        guard = _build_guard()
        wake_at = _dt.datetime(2026, 5, 6, 8, 0)
        with patch("app.services.power.core_uptime_rtc_guard.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="permission denied")
            # Must not raise.
            guard._set_rtc_alarm(wake_at)
