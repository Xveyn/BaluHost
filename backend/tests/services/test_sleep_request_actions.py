"""Sleep actions run on the primary only; followers forward them (#823, part 2).

Production runs several API processes; exactly one ("primary") runs the sleep
state machine. `request_soft_sleep()`, `request_wake()` and
`request_suspend()` are what routes and the auto-wake middleware call: the
primary executes directly, a follower hands the action over through the
`sleep_commands` queue and never touches its own (unused) state machine.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.models.sleep import SleepCommand
from app.schemas.sleep import SleepState, SleepTrigger
from app.services.power import sleep_command_queue as scq
from app.services.power.sleep import (
    SleepActionResult,
    SleepActionStatus,
    SleepManagerService,
)
from app.services.power.sleep_backend_dev import DevSleepBackend

_Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _sleep_command_table():
    if not inspect(engine).has_table(SleepCommand.__tablename__):
        SleepCommand.__table__.create(bind=engine, checkfirst=True)
    yield
    db = _Session()
    try:
        db.query(SleepCommand).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_singleton():
    SleepManagerService._instance = None
    yield
    SleepManagerService._instance = None


def _new_service() -> SleepManagerService:
    svc = SleepManagerService(DevSleepBackend())
    inhibitor = MagicMock()
    inhibitor.is_held.return_value = False
    svc._core_uptime_inhibitor = inhibitor
    return svc


def _primary() -> SleepManagerService:
    svc = _new_service()
    svc._is_primary = True
    return svc


def _follower() -> SleepManagerService:
    return _new_service()


def _local_methods(svc: SleepManagerService):
    return (
        patch.object(svc, "enter_soft_sleep", new=AsyncMock(return_value=True)),
        patch.object(svc, "exit_soft_sleep", new=AsyncMock(return_value=True)),
        patch.object(svc, "_exit_soft_sleep", new=AsyncMock(return_value=True)),
        patch.object(svc, "enter_true_suspend", new=AsyncMock(return_value=True)),
    )


# ─── SleepActionResult ───────────────────────────────────────────────


def test_action_result_properties():
    done = SleepActionResult(SleepActionStatus.DONE)
    refused = SleepActionResult(SleepActionStatus.REFUSED)
    unavailable = SleepActionResult(SleepActionStatus.UNAVAILABLE, "timed out")

    assert (done.ok, done.refused, done.unavailable) == (True, False, False)
    assert (refused.ok, refused.refused, refused.unavailable) == (False, True, False)
    assert (unavailable.ok, unavailable.refused, unavailable.unavailable) == (False, False, True)
    assert unavailable.detail == "timed out"
    with pytest.raises(Exception):
        done.status = SleepActionStatus.REFUSED  # frozen


# ─── Primary: executes locally ───────────────────────────────────────


@pytest.mark.asyncio
async def test_primary_soft_sleep_runs_locally_and_never_queues():
    svc = _primary()
    with patch.object(svc, "enter_soft_sleep", new=AsyncMock(return_value=True)) as local, \
         patch.object(scq, "submit_command", new=AsyncMock()) as submit:
        result = await svc.request_soft_sleep("manual by alice")

    assert result.ok
    local.assert_awaited_once_with("manual by alice", SleepTrigger.MANUAL)
    submit.assert_not_called()


@pytest.mark.asyncio
async def test_primary_wake_runs_locally_and_never_queues():
    svc = _primary()
    with patch.object(svc, "exit_soft_sleep", new=AsyncMock(return_value=True)) as local, \
         patch.object(scq, "submit_command", new=AsyncMock()) as submit:
        result = await svc.request_wake("manual wake by alice")

    assert result.ok
    local.assert_awaited_once_with("manual wake by alice")
    submit.assert_not_called()


@pytest.mark.asyncio
async def test_primary_suspend_runs_locally_and_never_queues():
    svc = _primary()
    wake_at = datetime(2026, 11, 13, 6, 0)
    with patch.object(svc, "enter_true_suspend", new=AsyncMock(return_value=True)) as local, \
         patch.object(scq, "submit_command", new=AsyncMock()) as submit:
        result = await svc.request_suspend("manual suspend by alice", wake_at=wake_at)

    assert result.ok
    local.assert_awaited_once_with(
        "manual suspend by alice", SleepTrigger.MANUAL, wake_at=wake_at
    )
    submit.assert_not_called()


@pytest.mark.parametrize(
    "method, local_name, args",
    [
        ("request_soft_sleep", "enter_soft_sleep", ("r",)),
        ("request_wake", "exit_soft_sleep", ("r",)),
        ("request_suspend", "enter_true_suspend", ("r",)),
    ],
)
@pytest.mark.asyncio
async def test_primary_refusal_is_reported_as_refused(method, local_name, args):
    svc = _primary()
    with patch.object(svc, local_name, new=AsyncMock(return_value=False)):
        result = await getattr(svc, method)(*args)

    assert result.refused
    assert result.status is SleepActionStatus.REFUSED


# ─── Follower: forwards, never runs the local state machine ──────────


def _assert_issued_just_now(payload: dict) -> None:
    issued = datetime.fromisoformat(payload["issued_at"])
    assert issued.tzinfo is not None
    assert abs(datetime.now(timezone.utc) - issued) < timedelta(seconds=5)


@pytest.mark.asyncio
async def test_follower_soft_sleep_is_forwarded_and_nothing_runs_locally():
    svc = _follower()
    patches = _local_methods(svc)
    with patches[0] as soft, patches[1] as wake, patches[2] as wake_inner, \
         patches[3] as suspend, \
         patch.object(scq, "submit_command", new=AsyncMock(return_value=(True, None))) as submit:
        result = await svc.request_soft_sleep("manual by alice")

    assert result.ok
    submit.assert_awaited_once()
    command, payload = submit.call_args.args[0], submit.call_args.args[1]
    assert command == "soft"
    assert payload["reason"] == "manual by alice"
    _assert_issued_just_now(payload)
    for local in (soft, wake, wake_inner, suspend):
        local.assert_not_called()
    assert svc._current_state is SleepState.AWAKE


@pytest.mark.asyncio
async def test_follower_wake_is_forwarded_and_nothing_runs_locally():
    svc = _follower()
    patches = _local_methods(svc)
    with patches[0] as soft, patches[1] as wake, patches[2] as wake_inner, \
         patches[3] as suspend, \
         patch.object(scq, "submit_command", new=AsyncMock(return_value=(True, None))) as submit:
        result = await svc.request_wake("manual wake by alice")

    assert result.ok
    command, payload = submit.call_args.args[0], submit.call_args.args[1]
    assert command == "wake"
    assert payload["reason"] == "manual wake by alice"
    _assert_issued_just_now(payload)
    for local in (soft, wake, wake_inner, suspend):
        local.assert_not_called()
    assert svc._current_state is SleepState.AWAKE


@pytest.mark.parametrize(
    "wake_at",
    [None, datetime(2026, 11, 13, 6, 0), datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)],
    ids=["none", "naive", "aware"],
)
@pytest.mark.asyncio
async def test_follower_suspend_is_forwarded_with_wake_at(wake_at):
    svc = _follower()
    patches = _local_methods(svc)
    with patches[0] as soft, patches[1] as wake, patches[2] as wake_inner, \
         patches[3] as suspend, \
         patch.object(scq, "submit_command", new=AsyncMock(return_value=(True, None))) as submit:
        result = await svc.request_suspend("manual suspend by alice", wake_at=wake_at)

    assert result.ok
    command, payload = submit.call_args.args[0], submit.call_args.args[1]
    assert command == "suspend"
    assert payload["reason"] == "manual suspend by alice"
    assert payload["wake_at"] == (wake_at.isoformat() if wake_at else None)
    _assert_issued_just_now(payload)
    for local in (soft, wake, wake_inner, suspend):
        local.assert_not_called()
    assert svc._current_state is SleepState.AWAKE


ALL_REQUESTS = [
    pytest.param("request_soft_sleep", id="soft"),
    pytest.param("request_wake", id="wake"),
    pytest.param("request_suspend", id="suspend"),
]


@pytest.mark.parametrize("method", ALL_REQUESTS)
@pytest.mark.asyncio
async def test_follower_maps_primary_refusal_to_refused(method):
    svc = _follower()
    with patch.object(scq, "submit_command", new=AsyncMock(return_value=(False, scq.REFUSED))):
        result = await getattr(svc, method)("r")

    assert result.refused


@pytest.mark.parametrize("method", ALL_REQUESTS)
@pytest.mark.parametrize(
    "error",
    [
        "Command timed out after 5.0s",
        "expired (not picked up before its deadline)",
        "Command still running after 65.0s; outcome unknown",
        "stale command (issued 30s ago); not executed",
        "Failed to enqueue command",
    ],
)
@pytest.mark.asyncio
async def test_follower_maps_queue_failures_to_unavailable(method, error):
    svc = _follower()
    with patch.object(scq, "submit_command", new=AsyncMock(return_value=(False, error))):
        result = await getattr(svc, method)("r")

    assert result.unavailable
    assert result.detail == error


@pytest.mark.parametrize("method", ALL_REQUESTS)
@pytest.mark.asyncio
async def test_follower_maps_an_exception_to_unavailable(method):
    svc = _follower()
    with patch.object(scq, "submit_command", new=AsyncMock(side_effect=RuntimeError("db down"))):
        result = await getattr(svc, method)("r")

    assert result.unavailable
    assert "db down" in result.detail


# ─── Poll loop lifecycle ─────────────────────────────────────────────


async def _start(svc: SleepManagerService, *, primary: bool, loops) -> None:
    """Start with the real create_task, but stub the coroutines it is given."""
    with patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         patch.object(svc, "_idle_detection_loop", new=loops["idle"]), \
         patch.object(svc, "_schedule_check_loop", new=loops["schedule"]), \
         patch.object(scq, "run_poll_loop", new=loops["poll"]):
        await svc.start(monitoring=primary)


async def _forever(*_args, **_kwargs):
    await asyncio.Event().wait()


def _loop_stubs():
    return {
        "idle": MagicMock(side_effect=lambda: _forever()),
        "schedule": MagicMock(side_effect=lambda: _forever()),
        "poll": MagicMock(side_effect=lambda manager: _forever()),
    }


@pytest.mark.asyncio
async def test_primary_start_runs_the_poll_loop_and_stop_ends_it():
    svc = _new_service()
    loops = _loop_stubs()

    await _start(svc, primary=True, loops=loops)

    loops["poll"].assert_called_once_with(svc)
    task = svc._command_poll_task
    assert task is not None
    await asyncio.sleep(0)
    assert not task.done()

    with patch.object(svc._core_uptime_rtc_guard, "stop", new=AsyncMock()):
        await svc.stop()

    assert task.done()
    assert svc._command_poll_task is None


@pytest.mark.asyncio
async def test_follower_start_does_not_run_the_poll_loop():
    svc = _new_service()
    loops = _loop_stubs()

    await _start(svc, primary=False, loops=loops)

    loops["poll"].assert_not_called()
    assert svc._command_poll_task is None
    with patch.object(svc._core_uptime_rtc_guard, "stop", new=AsyncMock()):
        await svc.stop()


# ─── Two real instances in one process ───────────────────────────────


@pytest.mark.asyncio
async def test_follower_actions_drive_the_primary_state_machine():
    """One primary with its loops running, one follower, one shared DB."""
    primary = _new_service()
    follower = _new_service()
    with patch.object(primary, "_is_gaming_active", return_value=False), \
         patch.object(primary, "_load_config", return_value=None), \
         patch.object(primary, "_load_core_uptime", return_value=(False, [])), \
         patch.object(primary._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         patch.object(primary._core_uptime_rtc_guard, "stop", new=AsyncMock()), \
         patch.object(follower._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         patch.object(follower._core_uptime_rtc_guard, "stop", new=AsyncMock()):
        await primary.start(monitoring=True)
        await follower.start(monitoring=False)
        try:
            assert follower.effective_state()[0] is SleepState.AWAKE  # fills the cache
            slept = await follower.request_soft_sleep("manual by alice")
            primary_state_after_sleep = primary._current_state
            follower_local_after_sleep = follower._current_state
            # No cache reset here: a follower that just changed the primary's
            # state must not keep answering from its 2-s cache.
            follower_view_after_sleep = follower.effective_state()[0]

            woke = await follower.request_wake("manual wake by alice")
            primary_state_after_wake = primary._current_state
            follower_view_after_wake = follower.effective_state()[0]
        finally:
            await follower.stop()
            await primary.stop()

    assert slept.ok
    assert primary_state_after_sleep is SleepState.SOFT_SLEEP
    assert follower_local_after_sleep is SleepState.AWAKE
    assert follower_view_after_sleep is SleepState.SOFT_SLEEP
    assert woke.ok
    assert primary_state_after_wake is SleepState.AWAKE
    assert follower_view_after_wake is SleepState.AWAKE


@pytest.mark.asyncio
async def test_follower_wake_while_primary_is_awake_is_refused_end_to_end():
    primary = _new_service()
    follower = _new_service()
    with patch.object(primary, "_is_gaming_active", return_value=False), \
         patch.object(primary, "_load_config", return_value=None), \
         patch.object(primary, "_load_core_uptime", return_value=(False, [])), \
         patch.object(primary._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         patch.object(primary._core_uptime_rtc_guard, "stop", new=AsyncMock()):
        await primary.start(monitoring=True)
        try:
            result = await follower.request_wake("manual wake by alice")
        finally:
            await primary.stop()

    assert result.refused
    assert primary._current_state is SleepState.AWAKE
