"""Integration tests: SleepManagerService respects foreign block inhibitors (#602).

The regression this covers: on 2026-09-08 steam-bpm-inhibit held a
`block` on `sleep:idle` for the whole game session, and BaluHost suspended
anyway — because `rtcwake -m mem` never goes through logind, so nothing
enforced that inhibitor against us.
"""
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from app.models.sleep import CoreUptimeWindow as CW, SleepConfig
from app.schemas.sleep import SleepState, SleepTrigger
from app.services.power.foreign_inhibitors import Inhibitor
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend

STEAM = Inhibitor(
    what="sleep:idle",
    who="steam-bpm-inhibit",
    why="Steam BPM oder Spiel aktiv",
    mode="block",
    uid=1000,
    pid=102863,
)


def _build_service():
    SleepManagerService._instance = None
    return SleepManagerService(DevSleepBackend())


def _config(auto_escalation_enabled=False, auto_idle_enabled=False):
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
        core_uptime_suspend_on_exit=True,
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


class TestLookupHelper:
    def test_delegates_to_the_foreign_inhibitor_module(self):
        svc = _build_service()
        with patch("app.services.power.foreign_inhibitors.first_blocking",
                   return_value=STEAM) as mock:
            assert svc._foreign_inhibitor("sleep") is STEAM
        mock.assert_called_once_with("sleep")

    def test_none_when_the_lookup_blows_up(self):
        """Fails toward energy saving, like every other suppressor."""
        svc = _build_service()
        with patch("app.services.power.foreign_inhibitors.first_blocking",
                   side_effect=RuntimeError("busctl exploded")):
            assert svc._foreign_inhibitor("sleep") is None


@pytest.mark.asyncio
async def test_suspend_on_exit_blocked_by_a_foreign_inhibitor():
    svc = _build_service()
    cfg = _config()
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append(a)
        return True

    patches = [
        patch.object(svc, "_load_config", return_value=cfg),
        patch.object(svc, "_load_core_uptime", return_value=(True, [_window()])),
        patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
              return_value=(False, None)),
        patch.object(svc, "_is_system_idle", return_value=True),
        patch.object(svc, "_is_user_present", return_value=False),
        patch.object(svc, "_is_always_awake", return_value=False),
        patch.object(svc, "_is_gaming_active", return_value=False),
        patch.object(svc, "_foreign_inhibitor", return_value=STEAM),
        patch.object(svc, "_reconcile_sleep_inhibitor"),
    ]
    with contextlib.ExitStack() as stack:
        for p in patches:
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
    assert svc._core_uptime_exit_pending is True  # a gate, not a disarm


@pytest.mark.asyncio
async def test_escalation_skipped_while_a_foreign_inhibitor_blocks():
    svc = _build_service()
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=STEAM), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()

    mock_suspend.assert_not_called()


@pytest.mark.asyncio
async def test_idle_loop_respects_an_idle_inhibitor():
    """`what` is honoured per segment: idle guards soft sleep, sleep guards suspend."""
    svc = _build_service()
    cfg = _config(auto_idle_enabled=True)
    svc._is_running = True
    svc._current_state = SleepState.AWAKE
    svc._consecutive_idle_checks = 999

    calls = [0]

    async def stop_loop(*_a, **_k):
        # Iteration 1 must run its body in full; stop at the top of iteration 2.
        # Setting _is_running=False on the FIRST sleep breaks out before the
        # body ever executes, which makes the assertions below pass without
        # exercising anything - this test did exactly that when first written.
        calls[0] += 1
        if calls[0] >= 2:
            svc._is_running = False

    seen = []

    def lookup(kind):
        seen.append(kind)
        return STEAM

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc, "_is_system_idle", return_value=True), \
         patch.object(svc, "_foreign_inhibitor", side_effect=lookup), \
         patch.object(svc, "enter_soft_sleep", new=AsyncMock()) as mock_soft, \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_loop):
        await svc._idle_detection_loop()

    mock_soft.assert_not_called()
    assert "idle" in seen


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [
    SleepTrigger.AUTO_IDLE, SleepTrigger.SCHEDULE,
    SleepTrigger.AUTO_ESCALATION, SleepTrigger.CORE_UPTIME_EXIT,
])
async def test_enter_true_suspend_blocks_non_manual(trigger):
    svc = _build_service()
    svc._current_state = SleepState.AWAKE

    with patch.object(svc, "_load_config", return_value=_config()), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=STEAM), \
         patch.object(svc, "enter_soft_sleep", new=AsyncMock()) as mock_soft:
        ok = await svc.enter_true_suspend("test", trigger)

    assert ok is False
    mock_soft.assert_not_called()


@pytest.mark.asyncio
async def test_enter_true_suspend_allows_manual():
    """An admin at the machine may overrule a foreign inhibitor."""
    svc = _build_service()
    svc._current_state = SleepState.SOFT_SLEEP

    with patch.object(svc, "_load_config", return_value=_config()), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=STEAM), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend",
               new=AsyncMock(return_value=None)), \
         patch.object(svc._backend, "suspend_system",
                      new=AsyncMock(return_value=True)) as mock_suspend:
        await svc.enter_true_suspend("manual", SleepTrigger.MANUAL)

    mock_suspend.assert_awaited()


def test_status_names_who_is_holding_the_box_awake():
    svc = _build_service()
    with patch.object(svc, "_load_config", return_value=_config()), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.gaming_presence.game_is_running", return_value=False), \
         patch("app.services.power.gaming_presence.gaming_mode_on_screen", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=STEAM):
        status = svc.get_status()

    assert status.foreign_inhibitor is not None
    assert status.foreign_inhibitor.who == "steam-bpm-inhibit"
    assert status.foreign_inhibitor.why == "Steam BPM oder Spiel aktiv"


def test_status_has_no_inhibitor_when_nothing_blocks():
    svc = _build_service()
    with patch.object(svc, "_load_config", return_value=_config()), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.gaming_presence.game_is_running", return_value=False), \
         patch("app.services.power.gaming_presence.gaming_mode_on_screen", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=None):
        status = svc.get_status()

    assert status.foreign_inhibitor is None
