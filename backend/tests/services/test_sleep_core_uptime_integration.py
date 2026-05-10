"""Integration tests: SleepManagerService respects core uptime windows."""
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

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


@pytest.mark.asyncio
async def test_escalation_aborts_during_core_uptime():
    """_escalation_monitor must return without escalating if in core uptime when timer fires."""
    svc = _build_service()
    cfg = SleepConfig(
        id=1,
        auto_idle_enabled=False, idle_timeout_minutes=15, idle_cpu_threshold=5,
        idle_disk_io_threshold=0.5, idle_http_threshold=5,
        auto_escalation_enabled=True, escalation_after_minutes=1,
        schedule_enabled=False, schedule_sleep_time="23:00", schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None, wol_broadcast_address=None,
        pause_monitoring=False, pause_disk_io=False, reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=True,
    )

    suspend_called = []

    async def fake_suspend(reason, trigger=None, wake_at=None):
        suspend_called.append((reason, trigger))
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())):
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.SOFT_SLEEP

        async def fast_sleep(*_a, **_k):
            return None
        with patch("app.services.power.sleep.asyncio.sleep", side_effect=fast_sleep):
            await svc._escalation_monitor()

    assert suspend_called == []


@pytest.mark.asyncio
async def test_schedule_loop_acquires_inhibitor_when_entering_window():
    """Edge OFF→ON in the schedule loop must acquire the logind inhibitor."""
    svc = _build_service()
    cfg = _config(core_enabled=True)
    in_core_sequence = iter([(False, None), (True, _window_workdays_8_22())])

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               side_effect=lambda *a, **k: next(in_core_sequence)), \
         patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire, \
         patch.object(svc._core_uptime_inhibitor, "release") as mock_release, \
         patch.object(svc._core_uptime_inhibitor, "is_held", side_effect=[False, False, True, True]):
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = False

        ticks = [0]

        async def two_ticks(*_a, **_k):
            ticks[0] += 1
            if ticks[0] >= 3:
                svc._is_running = False

        with patch("app.services.power.sleep.asyncio.sleep", side_effect=two_ticks):
            await svc._schedule_check_loop()

    mock_acquire.assert_called_once_with("core_uptime_active")
    mock_release.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_loop_releases_inhibitor_when_leaving_window():
    """Edge ON→OFF must release the logind inhibitor."""
    svc = _build_service()
    cfg = _config(core_enabled=True)
    in_core_sequence = iter([(True, _window_workdays_8_22()), (False, None)])

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               side_effect=lambda *a, **k: next(in_core_sequence)), \
         patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire, \
         patch.object(svc._core_uptime_inhibitor, "release") as mock_release, \
         patch.object(svc._core_uptime_inhibitor, "is_held", side_effect=[True, True, False, False]):
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        ticks = [0]

        async def two_ticks(*_a, **_k):
            ticks[0] += 1
            if ticks[0] >= 3:
                svc._is_running = False

        with patch("app.services.power.sleep.asyncio.sleep", side_effect=two_ticks):
            await svc._schedule_check_loop()

    mock_release.assert_called_once_with()
    mock_acquire.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_loop_releases_inhibitor_when_master_toggle_off():
    """Master toggle off mid-flight must release the inhibitor even if windows match."""
    svc = _build_service()
    cfg_off = _config(core_enabled=False)

    with patch.object(svc, "_load_config", return_value=cfg_off), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire, \
         patch.object(svc._core_uptime_inhibitor, "release") as mock_release, \
         patch.object(svc._core_uptime_inhibitor, "is_held", return_value=True):
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        ticks = [0]

        async def one_tick(*_a, **_k):
            ticks[0] += 1
            if ticks[0] >= 2:
                svc._is_running = False

        with patch("app.services.power.sleep.asyncio.sleep", side_effect=one_tick):
            await svc._schedule_check_loop()

    mock_release.assert_called()
    mock_acquire.assert_not_called()


@pytest.mark.asyncio
async def test_stop_releases_inhibitor():
    """SleepManagerService.stop() must release the logind inhibitor."""
    svc = _build_service()

    with patch.object(svc._core_uptime_inhibitor, "release") as mock_release:
        svc._is_running = True
        await svc.stop()

    mock_release.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [
    SleepTrigger.SCHEDULE,
    SleepTrigger.AUTO_IDLE,
    SleepTrigger.AUTO_ESCALATION,
    SleepTrigger.RTC_WAKE,
])
async def test_enter_true_suspend_blocks_non_manual_during_active_window(trigger):
    """Defense-in-depth: any automatic trigger must be blocked while in a
    core-uptime window, even if a per-loop guard somehow let it through."""
    svc = _build_service()
    cfg = _config(core_enabled=True)

    suspend_called = []

    async def fake_suspend_system(wake_at=None):
        suspend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock(return_value=None)):
        svc._current_state = SleepState.SOFT_SLEEP
        ok = await svc.enter_true_suspend("auto", trigger)

    assert ok is False
    assert suspend_called == []


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [
    SleepTrigger.SCHEDULE,
    SleepTrigger.AUTO_IDLE,
    SleepTrigger.AUTO_ESCALATION,
    SleepTrigger.RTC_WAKE,
])
async def test_enter_true_suspend_blocks_non_manual_when_inhibitor_held_even_if_db_fails_open(trigger):
    """If `_load_core_uptime` fails open (returns master=False due to a transient
    DB error) but the logind inhibitor is still held from a previous successful
    tick, non-MANUAL paths must still be blocked AND no lifecycle.suspend
    notification must fire. Without this guard the user sees a phantom
    "NAS wird suspended" push while the kernel suspend is silently blocked
    by the inhibitor at logind level."""
    svc = _build_service()
    cfg = _config(core_enabled=True)

    suspend_called: list = []
    emit_called: list = []

    async def fake_suspend_system(wake_at=None):
        suspend_called.append(wake_at)
        return True

    async def fake_emit(*args, **kwargs):
        emit_called.append(kwargs.get("trigger") or args)

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._core_uptime_inhibitor, "is_held", return_value=True), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend",
               new=AsyncMock(side_effect=fake_emit)):
        svc._current_state = SleepState.SOFT_SLEEP
        ok = await svc.enter_true_suspend("auto", trigger)

    assert ok is False
    assert suspend_called == []
    assert emit_called == [], "lifecycle.suspend must NOT fire when suspend will be blocked"


@pytest.mark.asyncio
async def test_enter_true_suspend_allows_manual_during_active_window():
    """Manual admin trigger must still suspend during core uptime (spec F8) —
    the only exception to the defense-in-depth block."""
    svc = _build_service()
    cfg = _config(core_enabled=True)
    next_start = datetime(2026, 5, 7, 8, 0)

    suspend_called = []

    async def fake_suspend_system(wake_at=None):
        suspend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())), \
         patch("app.services.power.sleep.core_uptime_helpers.next_core_uptime_start",
               return_value=next_start), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock(return_value=None)):
        svc._current_state = SleepState.SOFT_SLEEP
        ok = await svc.enter_true_suspend("manual", SleepTrigger.MANUAL)

    assert ok is True
    assert suspend_called == [next_start]  # wake_at clamped to next_start


@pytest.mark.asyncio
async def test_enter_true_suspend_clamps_wake_at_to_next_core_start():
    """If wake_at is after next core uptime start, it is clamped to that start."""
    svc = _build_service()
    cfg = _config(core_enabled=True)
    next_start = datetime(2026, 5, 7, 8, 0)
    user_wake = datetime(2026, 5, 7, 23, 0)  # later than next_start

    captured_wake_at = []

    async def fake_suspend_system(wake_at=None):
        captured_wake_at.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.next_core_uptime_start",
               return_value=next_start), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock(return_value=None)):
        svc._current_state = SleepState.SOFT_SLEEP  # skip implicit enter_soft_sleep
        await svc.enter_true_suspend("manual", SleepTrigger.MANUAL, wake_at=user_wake)

    assert captured_wake_at == [next_start]


@pytest.mark.asyncio
async def test_enter_true_suspend_uses_next_core_start_when_no_wake_at_given():
    svc = _build_service()
    cfg = _config(core_enabled=True)
    next_start = datetime(2026, 5, 7, 8, 0)

    captured_wake_at = []

    async def fake_suspend_system(wake_at=None):
        captured_wake_at.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.next_core_uptime_start",
               return_value=next_start), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock(return_value=None)):
        svc._current_state = SleepState.SOFT_SLEEP
        await svc.enter_true_suspend("manual", SleepTrigger.MANUAL, wake_at=None)

    assert captured_wake_at == [next_start]


def test_get_status_returns_core_uptime_block_when_active():
    svc = _build_service()
    cfg = _config(core_enabled=True)
    win = _window_workdays_8_22()

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [win])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, win)), \
         patch("app.services.power.sleep.core_uptime_helpers.current_window_end",
               return_value=datetime(2026, 5, 6, 22, 0)), \
         patch("app.services.power.sleep.core_uptime_helpers.next_core_uptime_start",
               return_value=datetime(2026, 5, 7, 8, 0)):
        status = svc.get_status()

    assert status.core_uptime.enabled is True
    assert status.core_uptime.active is True
    assert status.core_uptime.current_window_label == "Werktage"
    assert status.core_uptime.current_window_ends_at == datetime(2026, 5, 6, 22, 0)
    assert status.core_uptime.next_start == datetime(2026, 5, 7, 8, 0)


def test_get_status_returns_empty_core_uptime_when_master_off():
    svc = _build_service()
    cfg = _config(core_enabled=False)

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])):
        status = svc.get_status()

    assert status.core_uptime.enabled is False
    assert status.core_uptime.active is False
    assert status.core_uptime.next_start is None


def test_get_config_returns_core_uptime_enabled_field():
    svc = _build_service()
    cfg = _config(core_enabled=True)

    with patch.object(svc, "_load_config", return_value=cfg):
        result = svc.get_config()

    assert result.core_uptime_enabled is True


@pytest.mark.asyncio
async def test_rtc_guard_started_with_sleep_service(monkeypatch):
    """SleepManagerService.start() must call CoreUptimeRtcGuard.start()."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend
    from unittest.mock import AsyncMock, patch as _patch

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    with _patch.object(svc._core_uptime_rtc_guard, "start",
                       new=AsyncMock()) as mock_start, \
         _patch.object(svc, "_idle_detection_loop", new=AsyncMock()), \
         _patch.object(svc, "_schedule_check_loop", new=AsyncMock()):
        await svc.start(monitoring=True)
        await svc.stop()

    mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_rtc_guard_stopped_with_sleep_service(monkeypatch):
    """SleepManagerService.stop() must call CoreUptimeRtcGuard.stop()."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend
    from unittest.mock import AsyncMock, patch as _patch

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    with _patch.object(svc._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         _patch.object(svc._core_uptime_rtc_guard, "stop",
                       new=AsyncMock()) as mock_stop, \
         _patch.object(svc, "_idle_detection_loop", new=AsyncMock()), \
         _patch.object(svc, "_schedule_check_loop", new=AsyncMock()):
        await svc.start(monitoring=True)
        await svc.stop()

    mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_baluhost_initiated_suspend_sets_flag_around_backend_call():
    """During the rtcwake -m mem call, the in-progress flag must be True so
    the RTC guard skips its own rtcwake call and doesn't clobber wake_at."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend
    from app.schemas.sleep import SleepTrigger, SleepState
    from unittest.mock import AsyncMock, patch as _patch

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    flag_during_backend = []

    async def fake_suspend_system(wake_at=None):
        flag_during_backend.append(svc.is_baluhost_suspend_in_progress())
        return True

    with _patch.object(svc, "_load_config", return_value=None), \
         _patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         _patch.object(backend, "suspend_system", side_effect=fake_suspend_system), \
         _patch("app.services.power.sleep.SessionLocal"), \
         _patch("app.services.notifications.events.emit_system_suspend",
                new=AsyncMock(return_value=None)):
        svc._current_state = SleepState.SOFT_SLEEP
        assert svc.is_baluhost_suspend_in_progress() is False
        await svc.enter_true_suspend("test", SleepTrigger.MANUAL, wake_at=None)
        # Flag back to False after suspend returns.
        assert svc.is_baluhost_suspend_in_progress() is False

    assert flag_during_backend == [True]
