"""Die gemeinsame DB-Command-Queue hinter Power- und GPU-Queue (#313).

`power/command_queue.py` und `power/gpu/command_queue.py` waren zeilengleiche
Kopien -- jeder Fix musste zweimal gemacht werden. Die Mechanik (einreihen,
abholen, Ergebnis zurueckschreiben, Zeitueberschreitung) liegt jetzt in
`DbCommandQueue`; die beiden Module liefern nur noch Tabelle und Dispatch.

Die Tests hier laufen gegen eine eigene Tabelle in einer eigenen
In-Memory-Datenbank: Die Klasse darf nichts ueber Power oder GPU wissen.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from sqlalchemy import DateTime, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.services.power.db_command_queue import DbCommandQueue


class _Base(DeclarativeBase):
    pass


class _ThingCommand(_Base):
    __tablename__ = "thing_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class _OtherCommand(_Base):
    __tablename__ = "other_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    command: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


@pytest.fixture
def session_factory():
    # StaticPool + check_same_thread=False: the claim runs in a worker thread
    # and must see the same in-memory database.
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    _Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False)
    engine.dispose()


class _Recorder:
    """Dispatch-Funktion, die aufzeichnet und ein vorgegebenes Ergebnis liefert."""

    def __init__(self, result: Any = (True, None)) -> None:
        self.result = result
        self.calls: list[tuple[Any, str, dict]] = []

    async def __call__(self, manager: Any, command: str, payload: dict):
        self.calls.append((manager, command, payload))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _queue(session_factory, dispatch=None, model=_ThingCommand) -> DbCommandQueue:
    return DbCommandQueue(
        model,
        label="thing",
        dispatch=dispatch or _Recorder(),
        session_factory=session_factory,
        poll_interval_s=0.01,
    )


def _row(session_factory, command_id: int, model=_ThingCommand):
    db = session_factory()
    try:
        return db.query(model).filter(model.id == command_id).first()
    finally:
        db.close()


def _manager(running: bool = True) -> SimpleNamespace:
    return SimpleNamespace(_is_running=running)


async def _drain(queue: DbCommandQueue, manager: Any) -> int:
    count = 0
    while await queue.process_one_pending(manager):
        count += 1
    return count


# ─── einreihen ───────────────────────────────────────────────────────


def test_enqueue_writes_a_pending_row(session_factory):
    queue = _queue(session_factory)

    command_id = queue.enqueue("do_it", payload={"level": 3})

    row = _row(session_factory, command_id)
    assert row.status == "pending"
    assert row.command == "do_it"
    assert json.loads(row.payload_json) == {"level": 3}
    assert row.requested_by == f"pid={os.getpid()}"
    assert row.completed_at is None


def test_enqueue_without_payload_stores_no_json(session_factory):
    queue = _queue(session_factory)

    command_id = queue.enqueue("do_it", requested_by="admin")

    row = _row(session_factory, command_id)
    assert row.payload_json is None
    assert row.requested_by == "admin"


def test_enqueue_reports_a_database_failure_as_none():
    def broken_factory():
        raise RuntimeError("database down")

    queue = _queue(broken_factory)

    assert queue.enqueue("do_it") is None


# ─── abholen und ausfuehren ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_pending_command_is_dispatched_and_marked_applied(session_factory):
    dispatch = _Recorder((True, None))
    queue = _queue(session_factory, dispatch)
    manager = _manager()
    command_id = queue.enqueue("do_it", payload={"level": 3})

    processed = await queue.process_one_pending(manager)

    assert processed is True
    assert dispatch.calls == [(manager, "do_it", {"level": 3})]
    row = _row(session_factory, command_id)
    assert row.status == "applied"
    assert row.error_message is None
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_command_without_payload_is_dispatched_with_an_empty_dict(session_factory):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    queue.enqueue("do_it")

    await queue.process_one_pending(_manager())

    assert dispatch.calls[0][2] == {}


@pytest.mark.asyncio
async def test_empty_queue_processes_nothing(session_factory):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)

    assert await queue.process_one_pending(_manager()) is False
    assert dispatch.calls == []


@pytest.mark.asyncio
async def test_dispatch_failure_is_written_back_with_its_message(session_factory):
    queue = _queue(session_factory, _Recorder((False, "hardware said no")))
    command_id = queue.enqueue("do_it")

    await queue.process_one_pending(_manager())

    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message == "hardware said no"
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_dispatch_failure_without_message_gets_a_placeholder(session_factory):
    queue = _queue(session_factory, _Recorder((False, None)))
    command_id = queue.enqueue("do_it")

    await queue.process_one_pending(_manager())

    assert _row(session_factory, command_id).error_message == "unknown error"


@pytest.mark.asyncio
async def test_raising_dispatch_fails_the_command_and_not_the_loop(session_factory):
    queue = _queue(session_factory, _Recorder(RuntimeError("boom")))
    command_id = queue.enqueue("do_it")

    processed = await queue.process_one_pending(_manager())

    assert processed is True
    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message == "unhandled exception: boom"


@pytest.mark.asyncio
async def test_unparsable_payload_fails_without_reaching_dispatch(session_factory):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    db = session_factory()
    db.add(_ThingCommand(command="do_it", payload_json="{not json", status="pending"))
    db.commit()
    command_id = db.query(_ThingCommand).one().id
    db.close()

    processed = await queue.process_one_pending(_manager())

    assert processed is True
    assert dispatch.calls == []
    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message.startswith("invalid payload_json:")


@pytest.mark.asyncio
async def test_commands_are_processed_oldest_first(session_factory):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    for name in ("first", "second", "third"):
        queue.enqueue(name)

    assert await _drain(queue, _manager()) == 3

    assert [call[1] for call in dispatch.calls] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_finished_commands_are_not_picked_up_again(session_factory):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    queue.enqueue("do_it")

    await _drain(queue, _manager())
    await _drain(queue, _manager())

    assert len(dispatch.calls) == 1


@pytest.mark.asyncio
async def test_queues_on_different_tables_do_not_see_each_other(session_factory):
    thing_dispatch, other_dispatch = _Recorder(), _Recorder()
    things = _queue(session_factory, thing_dispatch)
    others = _queue(session_factory, other_dispatch, model=_OtherCommand)
    things.enqueue("for_things")

    assert await others.process_one_pending(_manager()) is False
    assert await things.process_one_pending(_manager()) is True

    assert other_dispatch.calls == []
    assert [call[1] for call in thing_dispatch.calls] == ["for_things"]


@pytest.mark.asyncio
async def test_claim_runs_off_the_event_loop(session_factory, monkeypatch):
    """Der SELECT oeffnet eine eigene Session (Connect, Pool-Ping) und laeuft
    im Primary alle 0,5 s -- auf dem Event-Loop hielte er jeden Coroutine des
    Workers auf (#797)."""
    queue = _queue(session_factory)
    seen: list[threading.Thread] = []

    def recording_claim():
        seen.append(threading.current_thread())
        return None

    monkeypatch.setattr(queue, "claim_pending", recording_claim)

    assert await queue.process_one_pending(_manager()) is False
    assert len(seen) == 1
    assert seen[0] is not threading.main_thread()


# ─── auf das Ergebnis warten ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_caller_sees_success_once_the_loop_applied_the_command(session_factory):
    queue = _queue(session_factory)
    manager = _manager()
    command_id = queue.enqueue("do_it")
    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    try:
        result = await queue.wait_for_completion(command_id, timeout_s=2.0)
    finally:
        manager._is_running = False
        await asyncio.wait_for(loop_task, timeout=2.0)

    assert result == (True, None)


@pytest.mark.asyncio
async def test_caller_sees_the_error_of_a_failed_command(session_factory):
    queue = _queue(session_factory, _Recorder((False, "hardware said no")))
    command_id = queue.enqueue("do_it")
    await queue.process_one_pending(_manager())

    assert await queue.wait_for_completion(command_id) == (False, "hardware said no")


@pytest.mark.asyncio
async def test_waiting_for_an_unknown_command_reports_not_found(session_factory):
    queue = _queue(session_factory)

    assert await queue.wait_for_completion(4711) == (False, "Command not found")


@pytest.mark.asyncio
async def test_timeout_fails_the_row_so_it_is_never_executed_late(session_factory):
    """Gibt der Aufrufer auf, darf der Befehl nicht spaeter doch noch laufen --
    der Nutzer hat dann laengst eine Fehlermeldung gesehen."""
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    command_id = queue.enqueue("do_it")

    success, error = await queue.wait_for_completion(command_id, timeout_s=0.05)

    assert success is False
    assert error == "Command timed out after 0.1s"
    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message == "timed out (caller gave up)"
    assert await queue.process_one_pending(_manager()) is False
    assert dispatch.calls == []


@pytest.mark.asyncio
async def test_default_timeout_comes_from_the_queue(session_factory):
    queue = DbCommandQueue(
        _ThingCommand,
        label="thing",
        dispatch=_Recorder(),
        session_factory=session_factory,
        poll_interval_s=0.01,
        default_timeout_s=0.05,
    )
    command_id = queue.enqueue("do_it")

    success, error = await queue.wait_for_completion(command_id)

    assert success is False
    assert error == "Command timed out after 0.1s"


# ─── Schleife ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_loop_ends_when_the_manager_stops(session_factory):
    queue = _queue(session_factory)
    manager = _manager()
    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    await asyncio.sleep(0.03)

    manager._is_running = False

    await asyncio.wait_for(loop_task, timeout=2.0)


@pytest.mark.asyncio
async def test_poll_loop_survives_a_failing_iteration(session_factory, monkeypatch):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    manager = _manager()
    original = queue.process_one_pending
    attempts = {"n": 0}

    async def flaky(mgr):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return await original(mgr)

    monkeypatch.setattr(queue, "process_one_pending", flaky)
    command_id = queue.enqueue("do_it")
    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    try:
        result = await queue.wait_for_completion(command_id, timeout_s=2.0)
    finally:
        manager._is_running = False
        await asyncio.wait_for(loop_task, timeout=2.0)

    assert result == (True, None)
    assert attempts["n"] >= 2
