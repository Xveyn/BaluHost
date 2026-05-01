"""Integration tests: SleepManagerService respects core uptime windows."""
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from app.models.sleep import CoreUptimeWindow as CW, SleepConfig
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.schemas.sleep import SleepState, SleepTrigger


def _build_service():
    """Build a fresh SleepManagerService with a DevSleepBackend."""
    SleepManagerService._instance = None  # reset singleton
    return SleepManagerService(DevSleepBackend())


def _config(core_enabled: bool = True, auto_idle_enabled: bool = True, idle_timeout_minutes: int = 1):
    cfg = SleepConfig(
        id=1,
        auto_idle_enabled=auto_idle_enabled,
        idle_timeout_minutes=idle_timeout_minutes,
        idle_cpu_threshold=99.0,
        idle_disk_io_threshold=99.0,
        idle_http_threshold=999.0,
        auto_escalation_enabled=False,
        escalation_after_minutes=60,
        schedule_enabled=False,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=core_enabled,
    )
    return cfg


def _window_workdays_8_22() -> CW:
    return CW(
        id=1, enabled=True, label="Werktage",
        start_time="08:00", end_time="22:00", weekdays="0,1,2,3,4",
    )


def test_load_core_uptime_returns_empty_when_master_off():
    svc = _build_service()
    cfg = _config(core_enabled=False)
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch("app.services.power.sleep.SessionLocal") as mock_sl:
        # Should not even hit the DB for windows when master is off
        master, windows = svc._load_core_uptime()
    assert master is False
    assert windows == []


def test_load_core_uptime_returns_enabled_windows():
    svc = _build_service()
    cfg = _config(core_enabled=True)
    fake_session = MagicMock()
    fake_query = MagicMock()
    fake_query.scalars.return_value.all.return_value = [_window_workdays_8_22()]
    fake_session.execute.return_value = fake_query
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch("app.services.power.sleep.SessionLocal", return_value=fake_session):
        master, windows = svc._load_core_uptime()
    assert master is True
    assert len(windows) == 1
    assert windows[0].label == "Werktage"


import asyncio


@pytest.mark.asyncio
async def test_idle_detection_skips_when_in_core_uptime():
    """During core uptime, idle counter must NOT advance."""
    svc = _build_service()
    cfg = _config(core_enabled=True, auto_idle_enabled=True, idle_timeout_minutes=1)

    # Force "currently in core uptime"
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())):
        svc._is_running = True
        svc._consecutive_idle_checks = 5
        svc._idle_seconds = 150.0

        # Run one iteration manually (avoid the 30s asyncio.sleep).
        # First call: let the loop body run. Second call: stop the loop.
        call_count = 0

        async def fake_sleep(*_a, **_k):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                svc._is_running = False  # stop after first full iteration

        with patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
            await svc._idle_detection_loop()

        assert svc._consecutive_idle_checks == 0
        assert svc._idle_seconds == 0.0


@pytest.mark.asyncio
async def test_schedule_loop_skips_sleep_trigger_during_core_uptime():
    """Scheduled sleep_time match should NOT trigger sleep when in core uptime."""
    svc = _build_service()
    cfg = SleepConfig(
        id=1,
        auto_idle_enabled=False, idle_timeout_minutes=15, idle_cpu_threshold=5,
        idle_disk_io_threshold=0.5, idle_http_threshold=5,
        auto_escalation_enabled=False, escalation_after_minutes=60,
        schedule_enabled=True, schedule_sleep_time="12:00", schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None, wol_broadcast_address=None,
        pause_monitoring=False, pause_disk_io=False, reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=True,
    )

    enter_called = []

    async def fake_enter_soft_sleep(reason, trigger=None):
        enter_called.append((reason, trigger))
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())), \
         patch("app.services.power.sleep.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 6, 12, 0)  # Wed 12:00 — schedule match AND in core uptime
        svc.enter_soft_sleep = fake_enter_soft_sleep
        svc._is_running = True
        svc._current_state = SleepState.AWAKE

        ticks = [0]

        async def stop_after_one(*_a, **_k):
            ticks[0] += 1
            if ticks[0] >= 2:
                svc._is_running = False

        with patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one):
            await svc._schedule_check_loop()

    assert enter_called == []  # core uptime suppressed schedule trigger


@pytest.mark.asyncio
async def test_schedule_loop_auto_wake_on_core_uptime_start():
    """When transitioning into core uptime while in soft sleep, auto-wake fires."""
    svc = _build_service()
    cfg = _config(core_enabled=True)

    exit_called = []

    async def fake_exit_soft_sleep(reason):
        exit_called.append(reason)
        return True

    # Sequence: first iteration NOT in core uptime, second iteration IN core uptime
    in_core_sequence = iter([(False, None), (True, _window_workdays_8_22())])

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               side_effect=lambda *a, **k: next(in_core_sequence)):
        svc.exit_soft_sleep = fake_exit_soft_sleep
        svc._is_running = True
        svc._current_state = SleepState.SOFT_SLEEP
        svc._was_in_core_uptime = False

        ticks = [0]

        async def two_ticks(*_a, **_k):
            ticks[0] += 1
            if ticks[0] >= 3:
                svc._is_running = False

        with patch("app.services.power.sleep.asyncio.sleep", side_effect=two_ticks):
            await svc._schedule_check_loop()

    assert exit_called == ["core_uptime_started"]
    assert svc._was_in_core_uptime is True
