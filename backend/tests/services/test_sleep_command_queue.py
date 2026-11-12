"""Sleep actions travel from a follower to the primary through `sleep_commands` (#823).

Only the primary runs the sleep state machine. A follower hands `soft`,
`wake` and `suspend` over through this queue; `_dispatch` turns a row back
into the primary's method call. Every command carries the caller's wall-clock
time and is dropped when it arrives too late — a suspend executed after a
long freeze between claim and dispatch must never happen.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.models.sleep import SleepCommand
from app.schemas.sleep import SleepTrigger
from app.services.power import sleep_command_queue as scq

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manager(result: bool = True) -> AsyncMock:
    manager = AsyncMock()
    manager.enter_soft_sleep.return_value = result
    manager.exit_soft_sleep.return_value = result
    manager.enter_true_suspend.return_value = result
    return manager


# ─── Configuration ───────────────────────────────────────────────────


def test_queue_waits_five_seconds_for_pickup_and_sixty_for_the_result():
    assert scq.PICKUP_TIMEOUT_S == 5.0
    assert scq.RUNNING_GRACE_S == 60.0
    assert scq.STALE_AFTER_S == 15.0
    assert scq.QUEUE._default_timeout_s == 5.0
    assert scq.QUEUE._running_grace_s == 60.0
    assert scq.QUEUE._model is SleepCommand


# ─── Dispatch ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_soft_reaches_enter_soft_sleep_as_manual():
    manager = _manager()

    result = await scq._dispatch(
        manager, "soft", {"reason": "manual by alice", "issued_at": _now_iso()}
    )

    assert result == (True, None)
    manager.enter_soft_sleep.assert_awaited_once_with("manual by alice", SleepTrigger.MANUAL)
    manager.exit_soft_sleep.assert_not_called()
    manager.enter_true_suspend.assert_not_called()


@pytest.mark.asyncio
async def test_wake_reaches_exit_soft_sleep():
    manager = _manager()

    result = await scq._dispatch(
        manager, "wake", {"reason": "manual wake by alice", "issued_at": _now_iso()}
    )

    assert result == (True, None)
    manager.exit_soft_sleep.assert_awaited_once_with("manual wake by alice")
    manager.enter_soft_sleep.assert_not_called()


@pytest.mark.parametrize(
    "wake_at",
    [
        None,
        datetime(2026, 11, 13, 6, 30),
        datetime(2026, 11, 13, 6, 30, tzinfo=timezone.utc),
        datetime(2026, 11, 13, 6, 30, tzinfo=timezone(timedelta(hours=1))),
    ],
    ids=["none", "naive", "utc", "plus-one"],
)
@pytest.mark.asyncio
async def test_suspend_reaches_enter_true_suspend_with_the_same_wake_at(wake_at):
    manager = _manager()
    payload = {
        "reason": "manual suspend by alice",
        "wake_at": wake_at.isoformat() if wake_at is not None else None,
        "issued_at": _now_iso(),
    }

    result = await scq._dispatch(manager, "suspend", payload)

    assert result == (True, None)
    manager.enter_true_suspend.assert_awaited_once()
    args, kwargs = manager.enter_true_suspend.call_args
    assert args == ("manual suspend by alice", SleepTrigger.MANUAL)
    received = kwargs["wake_at"]
    assert received == wake_at
    if wake_at is not None:
        assert received.tzinfo == wake_at.tzinfo
        assert received.utcoffset() == wake_at.utcoffset()


@pytest.mark.parametrize("command", ["soft", "wake", "suspend"])
@pytest.mark.asyncio
async def test_state_machine_refusal_is_reported_as_refused(command):
    manager = _manager(result=False)

    result = await scq._dispatch(
        manager, command, {"reason": "r", "wake_at": None, "issued_at": _now_iso()}
    )

    assert result == (False, scq.REFUSED)


@pytest.mark.asyncio
async def test_unknown_command_is_reported_and_runs_nothing():
    manager = _manager()

    result = await scq._dispatch(manager, "hibernate", {"reason": "r", "issued_at": _now_iso()})

    assert result == (False, "unknown command: hibernate")
    assert manager.mock_calls == []


@pytest.mark.asyncio
async def test_invalid_wake_at_runs_nothing():
    manager = _manager()

    ok, error = await scq._dispatch(
        manager, "suspend", {"reason": "r", "wake_at": "tomorrow", "issued_at": _now_iso()}
    )

    assert ok is False
    assert "wake_at" in error
    manager.enter_true_suspend.assert_not_called()


# ─── Staleness ───────────────────────────────────────────────────────


STALE_PAYLOADS = [
    pytest.param(
        {"issued_at": (datetime.now(timezone.utc) - timedelta(seconds=16)).isoformat()},
        id="sixteen-seconds-old",
    ),
    pytest.param(
        {"issued_at": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()},
        id="hours-old",
    ),
    pytest.param({}, id="missing"),
    pytest.param({"issued_at": None}, id="null"),
    pytest.param({"issued_at": "not a timestamp"}, id="garbage"),
    pytest.param({"issued_at": 12345}, id="number"),
    pytest.param({"issued_at": datetime.now().isoformat()}, id="naive"),
]


@pytest.mark.parametrize("command", ["soft", "wake", "suspend", "hibernate"])
@pytest.mark.parametrize("extra", STALE_PAYLOADS)
@pytest.mark.asyncio
async def test_stale_or_undated_command_is_not_executed(command, extra):
    manager = _manager()
    payload = {"reason": "r", "wake_at": None, **extra}

    ok, error = await scq._dispatch(manager, command, payload)

    assert ok is False
    assert error.startswith("stale command (")
    assert error.endswith("; not executed")
    assert manager.mock_calls == []


@pytest.mark.asyncio
async def test_stale_error_names_the_age():
    issued = datetime.now(timezone.utc) - timedelta(seconds=120)

    _ok, error = await scq._dispatch(
        _manager(), "suspend", {"reason": "r", "issued_at": issued.isoformat()}
    )

    assert error.startswith("stale command (issued 12")
    assert "s ago)" in error


@pytest.mark.asyncio
async def test_command_just_under_the_limit_is_executed():
    manager = _manager()
    issued = datetime.now(timezone.utc) - timedelta(seconds=10)

    result = await scq._dispatch(manager, "wake", {"reason": "r", "issued_at": issued.isoformat()})

    assert result == (True, None)
    manager.exit_soft_sleep.assert_awaited_once()


# ─── Through the real table ─────────────────────────────────────────


class _StubPrimary:
    """Enough of a `SleepManagerService` for the poll loop."""

    def __init__(self) -> None:
        self._is_running = True
        self.calls: list[tuple] = []

    async def enter_soft_sleep(self, reason, trigger):
        self.calls.append(("soft", reason, trigger))
        return True

    async def exit_soft_sleep(self, reason):
        self.calls.append(("wake", reason))
        return False  # e.g. already awake

    async def enter_true_suspend(self, reason, trigger, wake_at=None):
        self.calls.append(("suspend", reason, trigger, wake_at))
        return True


@pytest.mark.asyncio
async def test_round_trip_through_the_table_and_the_poll_loop():
    primary = _StubPrimary()
    loop_task = asyncio.create_task(scq.QUEUE.run_poll_loop(primary))
    wake_at = datetime(2026, 11, 13, 6, 30)
    try:
        soft = await scq.submit_command("soft", {"reason": "a", "issued_at": _now_iso()})
        wake = await scq.submit_command("wake", {"reason": "b", "issued_at": _now_iso()})
        suspend = await scq.submit_command(
            "suspend",
            {"reason": "c", "wake_at": wake_at.isoformat(), "issued_at": _now_iso()},
        )
    finally:
        primary._is_running = False
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)

    assert soft == (True, None)
    assert wake == (False, scq.REFUSED)
    assert suspend == (True, None)
    assert primary.calls == [
        ("soft", "a", SleepTrigger.MANUAL),
        ("wake", "b"),
        ("suspend", "c", SleepTrigger.MANUAL, wake_at),
    ]

    db = _Session()
    try:
        statuses = [row.status for row in db.query(SleepCommand).order_by(SleepCommand.id)]
    finally:
        db.close()
    assert statuses == ["applied", "failed", "applied"]
