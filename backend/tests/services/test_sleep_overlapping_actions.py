"""Sleep actions on the primary never overlap (#833).

The state machine lives in one process, but its three actions are long
coroutines with many awaits: entering soft sleep spins disks down, waking
spins them up, a suspend only returns after resume. A second action arriving
meanwhile — a second request, a forwarded command, one of the loops — used to
run alongside the first. The worst outcome was a second suspend right after
waking up.

Now exactly one action runs at a time and an overlapping one is refused, not
queued: a suspend that waited for its turn would run after the box woke up.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.sleep import SleepConfig
from app.schemas.sleep import SleepState, SleepTrigger
from app.services.power import sleep_command_queue as scq
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend


class _GatedBackend(DevSleepBackend):
    """Dev backend whose slow steps block until the test releases them.

    Only the *first* call of each step blocks. A second one — which is what an
    overlapping action would make — returns at once, so a missing guard shows
    up as a wrong result instead of a hanging test.
    """

    def __init__(self) -> None:
        super().__init__()
        self.suspend_calls = 0
        self.spindown_calls = 0
        self.spinup_calls = 0
        self.suspend_started = asyncio.Event()
        self.spindown_started = asyncio.Event()
        self.spinup_started = asyncio.Event()
        self.release = asyncio.Event()
        self.block: set[str] = set()

    async def _step(self, name: str, calls: int, started: asyncio.Event) -> None:
        started.set()
        if name in self.block and calls == 1:
            await self.release.wait()

    async def spindown_disks(self, devices: list[str]) -> list[str]:
        self.spindown_calls += 1
        await self._step("spindown", self.spindown_calls, self.spindown_started)
        return devices

    async def spinup_disks(self, devices: list[str]) -> list[str]:
        self.spinup_calls += 1
        await self._step("spinup", self.spinup_calls, self.spinup_started)
        return devices

    async def suspend_system(self, wake_at=None) -> bool:
        self.suspend_calls += 1
        await self._step("suspend", self.suspend_calls, self.suspend_started)
        return True


def _config() -> SleepConfig:
    return SleepConfig(
        id=1,
        auto_idle_enabled=False,
        idle_timeout_minutes=1,
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
        disk_spindown_enabled=True,
        core_uptime_enabled=False,
        core_uptime_suspend_on_exit=False,
    )


@pytest.fixture
def resume_push():
    """The resume push, replaceable per test (it is awaited after resume)."""
    return AsyncMock()


@pytest.fixture
def svc(resume_push):
    SleepManagerService._instance = None
    service = SleepManagerService(_GatedBackend())
    inhibitor = MagicMock()
    inhibitor.is_held.return_value = False
    service._core_uptime_inhibitor = inhibitor
    with patch.object(service, "_load_config", return_value=_config()), \
         patch.object(service, "_load_core_uptime", return_value=(False, [])), \
         patch.object(service, "_log_state_change"), \
         patch("app.services.power.manager.get_power_manager", return_value=None), \
         patch("app.services.power.fan_control.get_fan_control_service", return_value=None), \
         patch("app.services.telemetry.stop_telemetry_monitor", new=AsyncMock()), \
         patch("app.services.telemetry.start_telemetry_monitor", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=resume_push), \
         patch(
             "app.services.notifications.scheduler.NotificationScheduler.check_and_send_warnings",
             new=MagicMock(),
         ):
        yield service
    SleepManagerService._instance = None


# ─── One action at a time ────────────────────────────────────────────

# How to get each action running and parked at its slow step:
# (start state, coroutine factory, step it blocks at).
_RUNNING = {
    "soft": (
        SleepState.AWAKE,
        lambda s: s.enter_soft_sleep("first", SleepTrigger.MANUAL),
        "spindown",
    ),
    "wake": (
        SleepState.SOFT_SLEEP,
        lambda s: s.exit_soft_sleep("first"),
        "spinup",
    ),
    "suspend": (
        SleepState.SOFT_SLEEP,
        lambda s: s.enter_true_suspend("first", SleepTrigger.MANUAL),
        "suspend",
    ),
}

_ATTEMPT = {
    "soft": lambda s: s.enter_soft_sleep("second", SleepTrigger.MANUAL),
    "wake": lambda s: s.exit_soft_sleep("second"),
    "suspend": lambda s: s.enter_true_suspend("second", SleepTrigger.MANUAL),
}


async def _park(svc: SleepManagerService, running: str) -> asyncio.Task:
    """Start *running* and wait until it sits at its blocked step."""
    state, start, step = _RUNNING[running]
    backend: _GatedBackend = svc._backend
    backend.block = {step}
    svc._current_state = state
    if running == "wake":
        svc._spun_down_disks = ["/dev/sda"]  # otherwise waking spins nothing up
    task = asyncio.create_task(start(svc))
    await asyncio.wait_for(getattr(backend, f"{step}_started").wait(), timeout=5)
    return task


@pytest.mark.parametrize("attempt", ["soft", "wake", "suspend"])
@pytest.mark.parametrize("running", ["soft", "wake", "suspend"])
@pytest.mark.asyncio
async def test_action_arriving_while_another_runs_is_refused(svc, running, attempt):
    backend: _GatedBackend = svc._backend
    first = await _park(svc, running)
    calls_before = (backend.spindown_calls, backend.spinup_calls, backend.suspend_calls)

    second = await asyncio.wait_for(_ATTEMPT[attempt](svc), timeout=5)

    assert second is False
    # Refused means untouched: no disk moved, no second suspend.
    assert (backend.spindown_calls, backend.spinup_calls, backend.suspend_calls) == calls_before

    backend.release.set()
    assert await asyncio.wait_for(first, timeout=5) is True
    # The first action ends where it would have ended alone.
    expected = SleepState.SOFT_SLEEP if running == "soft" else SleepState.AWAKE
    assert svc._current_state is expected


@pytest.mark.asyncio
async def test_two_suspends_in_a_row_suspend_the_box_once(svc):
    """The case from the issue: a double click, or two clients."""
    backend: _GatedBackend = svc._backend
    backend.block = {"suspend"}
    svc._current_state = SleepState.AWAKE  # the suspend enters soft sleep itself

    first = asyncio.create_task(svc.enter_true_suspend("click 1", SleepTrigger.MANUAL))
    await asyncio.wait_for(backend.suspend_started.wait(), timeout=5)
    second = await asyncio.wait_for(
        svc.enter_true_suspend("click 2", SleepTrigger.MANUAL), timeout=5
    )
    backend.release.set()

    assert second is False
    assert await asyncio.wait_for(first, timeout=5) is True
    assert backend.suspend_calls == 1
    assert svc._current_state is SleepState.AWAKE


@pytest.mark.asyncio
async def test_suspend_arriving_right_after_resume_is_refused(svc, resume_push):
    """After resume the state is SOFT_SLEEP again while the first suspend is
    still finishing (resume push, waking). A suspend arriving in that window
    would put the box straight back to sleep."""
    backend: _GatedBackend = svc._backend
    svc._current_state = SleepState.SOFT_SLEEP
    in_resume = asyncio.Event()
    finish_resume = asyncio.Event()

    async def _slow_resume_push(**_kwargs):
        in_resume.set()
        await finish_resume.wait()

    resume_push.side_effect = _slow_resume_push

    first = asyncio.create_task(svc.enter_true_suspend("first", SleepTrigger.MANUAL))
    await asyncio.wait_for(in_resume.wait(), timeout=5)
    assert svc._current_state is SleepState.SOFT_SLEEP  # the window in question

    second = await asyncio.wait_for(
        svc.enter_true_suspend("second", SleepTrigger.MANUAL), timeout=5
    )
    finish_resume.set()

    assert second is False
    assert await asyncio.wait_for(first, timeout=5) is True
    assert backend.suspend_calls == 1
    assert svc._current_state is SleepState.AWAKE


@pytest.mark.asyncio
async def test_refused_soft_sleep_does_not_clear_always_awake(svc):
    """A refused action changes nothing — not even the override a soft sleep
    normally ends."""
    first = await _park(svc, "wake")
    with patch.object(svc, "_is_always_awake", return_value=True), \
         patch.object(svc, "_clear_always_awake") as clear:
        refused = await svc.enter_soft_sleep("second", SleepTrigger.MANUAL)

    assert refused is False
    clear.assert_not_called()
    svc._backend.release.set()
    await asyncio.wait_for(first, timeout=5)


# ─── The marker never sticks ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_next_action_runs_after_the_previous_one_finished(svc):
    assert await svc.enter_soft_sleep("a", SleepTrigger.MANUAL) is True
    assert await svc.exit_soft_sleep("b") is True
    assert await svc.enter_true_suspend("c", SleepTrigger.MANUAL) is True
    assert await svc.enter_soft_sleep("d", SleepTrigger.MANUAL) is True
    assert svc._current_state is SleepState.SOFT_SLEEP
    assert svc._backend.suspend_calls == 1


@pytest.mark.asyncio
async def test_action_that_raises_does_not_block_the_next_one(svc):
    svc._current_state = SleepState.SOFT_SLEEP
    with patch.object(svc._backend, "suspend_system", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            await svc.enter_true_suspend("a", SleepTrigger.MANUAL)

    svc._current_state = SleepState.SOFT_SLEEP
    assert await svc.exit_soft_sleep("b") is True


@pytest.mark.asyncio
async def test_cancelled_action_does_not_block_the_next_one(svc):
    first = await _park(svc, "soft")
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    # The cancelled entering left ENTERING_SOFT_SLEEP behind; waking from
    # there is what gets the box back.
    assert svc._current_state is SleepState.ENTERING_SOFT_SLEEP
    assert await svc.exit_soft_sleep("recover") is True
    assert svc._current_state is SleepState.AWAKE


# ─── Suspend only starts from a resting state ────────────────────────


@pytest.mark.parametrize(
    "state",
    [
        SleepState.ENTERING_SOFT_SLEEP,
        SleepState.WAKING,
        SleepState.ENTERING_SUSPEND,
        SleepState.TRUE_SUSPEND,
    ],
)
@pytest.mark.asyncio
async def test_suspend_from_a_transitional_state_is_refused(svc, state):
    """No action is running, but the state says one is under way (left behind
    by a cancelled action): a suspend must not start from there."""
    svc._current_state = state
    with patch.object(svc, "_clear_always_awake") as clear:
        result = await svc.enter_true_suspend("x", SleepTrigger.MANUAL)

    assert result is False
    assert svc._backend.suspend_calls == 0
    assert svc._current_state is state
    clear.assert_not_called()


# ─── Every way in is covered ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_on_the_primary_is_refused_while_an_action_runs(svc):
    svc._is_primary = True
    with patch.object(svc, "_publish_state", return_value=True):
        first = await _park(svc, "suspend")
        result = await asyncio.wait_for(svc.request_suspend("second"), timeout=5)
        svc._backend.release.set()
        await asyncio.wait_for(first, timeout=5)

    assert result.refused
    assert svc._backend.suspend_calls == 1


@pytest.mark.asyncio
async def test_forwarded_command_is_refused_while_an_action_runs(svc):
    first = await _park(svc, "suspend")

    outcome = await asyncio.wait_for(
        scq._dispatch(
            svc, scq.COMMAND_SUSPEND,
            {"reason": "from a follower", "wake_at": None, "issued_at": scq.issued_now()},
        ),
        timeout=5,
    )
    svc._backend.release.set()
    await asyncio.wait_for(first, timeout=5)

    assert outcome == (False, scq.REFUSED)
    assert svc._backend.suspend_calls == 1


@pytest.mark.asyncio
async def test_loop_triggered_suspend_is_refused_while_a_wake_runs(svc):
    """A loop calls the state machine directly, with its own trigger."""
    first = await _park(svc, "wake")

    result: Optional[bool] = await asyncio.wait_for(
        svc.enter_true_suspend("auto_escalation", SleepTrigger.AUTO_ESCALATION), timeout=5
    )
    svc._backend.release.set()

    assert result is False
    assert await asyncio.wait_for(first, timeout=5) is True
    assert svc._backend.suspend_calls == 0
    assert svc._current_state is SleepState.AWAKE


@pytest.mark.asyncio
async def test_escalation_suspend_holds_the_action_and_frees_it_afterwards(svc):
    """The real loop path: soft sleep starts the escalation monitor, which
    suspends from its own task and wakes the box after resume — cancelling
    itself on the way. The state machine must be free again afterwards."""
    backend: _GatedBackend = svc._backend
    backend.block = {"suspend"}
    config = _config()
    config.auto_escalation_enabled = True
    config.escalation_after_minutes = 0
    svc._is_running = True

    with patch.object(svc, "_load_config", return_value=config), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=None), \
         patch("app.services.power.sleep.scheduled_reboot.should_defer_suspend",
               return_value=False):
        assert await svc.enter_soft_sleep("idle", SleepTrigger.AUTO_IDLE) is True
        escalation = svc._escalation_task
        assert escalation is not None
        await asyncio.wait_for(backend.suspend_started.wait(), timeout=5)

        # While the escalation's suspend runs, a manual wake is refused ...
        assert await svc.exit_soft_sleep("manual wake") is False

        backend.release.set()
        await asyncio.wait_for(escalation, timeout=5)

        # ... and afterwards the box is awake and takes the next action.
        assert svc._current_state is SleepState.AWAKE
        assert svc._action_in_progress is None
        assert backend.suspend_calls == 1
        assert await svc.enter_soft_sleep("again", SleepTrigger.MANUAL) is True
        svc._escalation_task.cancel()
