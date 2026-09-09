"""Integration tests: SleepManagerService does not suspend while gaming.

Regression cover for 2026-09-08, when the box suspended sixteen minutes after
the core-uptime window ended while DiRT Rally 2.0 was running: the suspend-on-
exit gate asks `_is_system_idle()`, which measures NAS load (CPU percent, disk
I/O, HTTP requests) and cannot see a game.

Mirrors test_sleep_presence_integration.py — gaming is the fourth suppressor
next to core uptime, always-awake and presence.
"""
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from app.models.sleep import CoreUptimeWindow as CW, SleepConfig
from app.schemas.sleep import SleepState, SleepTrigger
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend


def _build_service():
    SleepManagerService._instance = None  # reset singleton
    return SleepManagerService(DevSleepBackend())


def _config(suspend_on_exit=True, auto_escalation_enabled=False, auto_idle_enabled=False):
    return SleepConfig(
        id=1,
        auto_idle_enabled=auto_idle_enabled,
        idle_timeout_minutes=1,
        idle_cpu_threshold=8.0,
        idle_disk_io_threshold=1.0,
        idle_http_threshold=5.0,
        auto_escalation_enabled=auto_escalation_enabled,
        escalation_after_minutes=1,
        schedule_enabled=False,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode="suspend",
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=True,
        core_uptime_suspend_on_exit=suspend_on_exit,
        always_awake_enabled=False,
        always_awake_until=None,
        block_suspend_in_gaming_mode=True,
        presence_enabled=False,
        presence_mode="active",
        presence_timeout_minutes=3,
    )


def _window() -> CW:
    return CW(id=1, enabled=True, label="Werktags",
              start_time="19:00", end_time="23:30", weekdays="0,1,2,3,4")


def _drive_schedule_loop(svc, cfg, *, gaming, ticks=2):
    """Run _schedule_check_loop for `ticks` ticks with the window just ended."""
    return [
        patch.object(svc, "_load_config", return_value=cfg),
        patch.object(svc, "_load_core_uptime", return_value=(True, [_window()])),
        patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
              return_value=(False, None)),
        patch.object(svc, "_is_system_idle", return_value=True),
        patch.object(svc, "_is_user_present", return_value=False),
        patch.object(svc, "_is_always_awake", return_value=False),
        patch.object(svc, "_is_gaming_active", return_value=gaming),
        patch.object(svc, "_reconcile_sleep_inhibitor"),
    ]


class TestIsGamingActive:
    def test_delegates_to_the_gaming_presence_module(self):
        svc = _build_service()
        cfg = _config()
        with patch("app.services.power.gaming_presence.blocks_suspend",
                   return_value=True) as mock:
            assert svc._is_gaming_active(cfg) is True
        mock.assert_called_once_with(cfg)

    def test_false_when_the_detector_blows_up(self):
        """Fails toward energy saving, like the presence check."""
        svc = _build_service()
        with patch("app.services.power.gaming_presence.blocks_suspend",
                   side_effect=RuntimeError("boom")):
            assert svc._is_gaming_active(_config()) is False


@pytest.mark.asyncio
async def test_suspend_on_exit_blocked_while_gaming():
    """The 2026-09-08 regression: window ended, game running, box must stay up."""
    svc = _build_service()
    cfg = _config()
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append(a)
        return True

    with contextlib.ExitStack() as stack:
        for p in _drive_schedule_loop(svc, cfg, gaming=True):
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        calls = [0]

        async def stop_after_two(*_a, **_k):
            calls[0] += 1
            if calls[0] >= 2:
                svc._is_running = False

        stack.enter_context(
            patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_two)
        )
        await svc._schedule_check_loop()

    assert suspend_calls == []
    # Gaming is a gate, not a disarm: the suspend must still happen once the
    # game ends, exactly as presence behaves.
    assert svc._core_uptime_exit_pending is True


@pytest.mark.asyncio
async def test_suspend_on_exit_still_fires_when_no_game_runs():
    """Control: without gaming the existing behaviour is untouched."""
    svc = _build_service()
    cfg = _config()
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append(a)
        return True

    with contextlib.ExitStack() as stack:
        for p in _drive_schedule_loop(svc, cfg, gaming=False):
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        calls = [0]

        async def stop_after_two(*_a, **_k):
            calls[0] += 1
            if calls[0] >= 2:
                svc._is_running = False

        stack.enter_context(
            patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_two)
        )
        await svc._schedule_check_loop()

    assert len(suspend_calls) == 1


@pytest.mark.asyncio
async def test_escalation_skipped_while_gaming():
    svc = _build_service()
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=True), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()

    mock_suspend.assert_not_called()


@pytest.mark.asyncio
async def test_idle_loop_does_not_soft_sleep_while_gaming():
    """Soft sleep locks the CPU to the IDLE profile — not during a game."""
    svc = _build_service()
    cfg = _config(auto_idle_enabled=True)
    svc._is_running = True
    svc._current_state = SleepState.AWAKE
    svc._consecutive_idle_checks = 999  # threshold long since exceeded

    async def stop_loop(*_a, **_k):
        svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_system_idle", return_value=True), \
         patch.object(svc, "_is_gaming_active", return_value=True), \
         patch.object(svc, "enter_soft_sleep", new=AsyncMock()) as mock_soft, \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_loop):
        await svc._idle_detection_loop()

    mock_soft.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [
    SleepTrigger.AUTO_IDLE, SleepTrigger.SCHEDULE,
    SleepTrigger.AUTO_ESCALATION, SleepTrigger.CORE_UPTIME_EXIT,
])
async def test_enter_true_suspend_blocks_non_manual_while_gaming(trigger):
    svc = _build_service()
    cfg = _config()
    svc._current_state = SleepState.AWAKE

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=True), \
         patch.object(svc, "enter_soft_sleep", new=AsyncMock()) as mock_soft:
        ok = await svc.enter_true_suspend("test", trigger)

    assert ok is False
    mock_soft.assert_not_called()


@pytest.mark.asyncio
async def test_enter_true_suspend_allows_manual_while_gaming():
    """An admin pressing suspend always wins over the automatic guards."""
    svc = _build_service()
    cfg = _config()
    svc._current_state = SleepState.SOFT_SLEEP

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=True), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend",
               new=AsyncMock(return_value=None)), \
         patch.object(svc._backend, "suspend_system",
                      new=AsyncMock(return_value=True)) as mock_suspend:
        await svc.enter_true_suspend("manual", SleepTrigger.MANUAL)

    mock_suspend.assert_awaited()


def test_inhibitor_is_held_while_gaming():
    """Holding the logind lock is what stops KDE PowerDevil from suspending.

    A gamepad in Big Picture does not reset the Wayland idle timer, so the
    desktop's own idle-suspend is a real path to losing the session — and
    BaluHost's per-loop guards do not cover it.
    """
    svc = _build_service()
    cfg = _config()

    with patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=True), \
         patch.object(svc._core_uptime_inhibitor, "is_held", return_value=False), \
         patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire:
        svc._reconcile_sleep_inhibitor(cfg, in_core=False)

    mock_acquire.assert_called_once()
    assert "gaming" in mock_acquire.call_args.args[0]
