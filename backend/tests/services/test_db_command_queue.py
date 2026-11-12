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
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

import pytest
from sqlalchemy import DateTime, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

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
    expires_at: Mapped[Optional[datetime]] = mapped_column(
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
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


@pytest.fixture
def session_factory(tmp_path):
    # A file, not ":memory:" with a StaticPool: the queue does its database
    # work in worker threads, and several of them at once must not share one
    # connection.
    engine = create_engine(
        f"sqlite:///{tmp_path}/queue.db",
        connect_args={"check_same_thread": False, "timeout": 30},
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


def _queue(session_factory, dispatch=None, model=_ThingCommand, **options) -> DbCommandQueue:
    options.setdefault("poll_interval_s", 0.01)
    return DbCommandQueue(
        model,
        label="thing",
        dispatch=dispatch or _Recorder(),
        session_factory=session_factory,
        **options,
    )


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite hands timestamps back without a zone; they are UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _insert(session_factory, model=_ThingCommand, **columns) -> int:
    """Write a row directly, the way an older process or a test setup would."""
    columns.setdefault("command", "do_it")
    columns.setdefault("status", "pending")
    db = session_factory()
    try:
        row = model(**columns)
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _count(session_factory, model=_ThingCommand) -> int:
    db = session_factory()
    try:
        return db.query(model).count()
    finally:
        db.close()


class _Gate:
    """Dispatch-Funktion, die haengt, bis der Test sie freigibt."""

    def __init__(self, result: Any = (True, None)) -> None:
        self.result = result
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, manager: Any, command: str, payload: dict):
        self.entered.set()
        await self.release.wait()
        return self.result


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
    queue = _queue(session_factory, default_timeout_s=0.05)
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


# ─── #829/1: verwaiste Befehle ───────────────────────────────────────
#
# Stirbt der wartende Worker vor seinem Timeout (Deploy: alle Worker starten
# gleichzeitig neu), markiert niemand die Zeile als gescheitert. Sie blieb
# `pending`, und der naechste Primary fuehrte sie nach dem Neustart aus --
# beliebig spaet, fuer niemanden.


def test_enqueue_stores_the_deadline_of_its_caller(session_factory):
    queue = _queue(session_factory, default_timeout_s=3.0)
    before = datetime.now(timezone.utc)

    default_id = queue.enqueue("do_it")
    long_id = queue.enqueue("do_it", timeout_s=10.0)

    default_deadline = _utc(_row(session_factory, default_id).expires_at)
    long_deadline = _utc(_row(session_factory, long_id).expires_at)
    # Wide upper bounds: a loaded machine may take a while to write the row.
    assert timedelta(seconds=2.9) <= default_deadline - before <= timedelta(seconds=8)
    assert timedelta(seconds=9.9) <= long_deadline - before <= timedelta(seconds=18)


@pytest.mark.asyncio
async def test_command_past_its_deadline_is_failed_instead_of_executed(session_factory):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    command_id = queue.enqueue("do_it", timeout_s=0)

    processed = await queue.process_one_pending(_manager())

    assert processed is False
    assert dispatch.calls == []
    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message == "expired (not picked up before its deadline)"
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_expired_commands_do_not_hold_up_the_one_behind_them(session_factory):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    queue.enqueue("orphan_one", timeout_s=0)
    queue.enqueue("orphan_two", timeout_s=0)
    queue.enqueue("alive")

    processed = await queue.process_one_pending(_manager())

    assert processed is True
    assert [call[1] for call in dispatch.calls] == ["alive"]


@pytest.mark.asyncio
async def test_row_without_deadline_expires_by_its_age(session_factory):
    """Zeilen aus der Zeit vor der Spalte -- genau die, die beim ersten Deploy
    dieser Aenderung verwaist herumliegen koennen."""
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch, default_timeout_s=3.0)
    old_id = _insert(
        session_factory,
        command="left_behind",
        requested_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    fresh_id = _insert(
        session_factory,
        command="just_written",
        requested_at=datetime.now(timezone.utc),
    )

    await _drain(queue, _manager())

    assert [call[1] for call in dispatch.calls] == ["just_written"]
    assert _row(session_factory, old_id).status == "failed"
    assert _row(session_factory, fresh_id).status == "applied"


# ─── #829/4: Aufrufer und Primary widersprechen sich ─────────────────
#
# Abholen liess die Zeile `pending`. Lief das Timeout des Aufrufers waehrend
# der Ausfuehrung ab, setzte er sie auf `failed` und meldete einen Fehler;
# der Primary ueberschrieb danach mit `applied`. Der Befehl hatte gewirkt,
# der Nutzer hatte eine Fehlermeldung gesehen.


@pytest.mark.asyncio
async def test_claimed_command_is_marked_running_while_it_executes(session_factory):
    seen: list[str] = []
    queue: DbCommandQueue

    async def dispatch(manager, command, payload):
        seen.append(_row(session_factory, command_id).status)
        return True, None

    queue = _queue(session_factory, dispatch)
    command_id = queue.enqueue("do_it")

    await queue.process_one_pending(_manager())

    assert seen == ["running"]
    assert _row(session_factory, command_id).status == "applied"


@pytest.mark.asyncio
async def test_running_command_is_not_claimed_a_second_time(session_factory):
    gate = _Gate()
    queue = _queue(session_factory, gate)
    queue.enqueue("do_it")
    first = asyncio.create_task(queue.process_one_pending(_manager()))
    await asyncio.wait_for(gate.entered.wait(), timeout=2.0)

    second = await queue.process_one_pending(_manager())

    gate.release.set()
    assert second is False
    assert await asyncio.wait_for(first, timeout=2.0) is True


@pytest.mark.asyncio
async def test_caller_waits_out_a_command_that_is_already_executing(session_factory):
    """Timeout abgelaufen, aber der Primary arbeitet schon daran: der Aufrufer
    bekommt das echte Ergebnis statt einer Fehlermeldung."""
    gate = _Gate((True, None))
    queue = _queue(session_factory, gate, running_grace_s=2.0)
    command_id = queue.enqueue("do_it")
    worker = asyncio.create_task(queue.process_one_pending(_manager()))
    await asyncio.wait_for(gate.entered.wait(), timeout=2.0)

    waiter = asyncio.create_task(queue.wait_for_completion(command_id, timeout_s=0.05))
    await asyncio.sleep(0.2)  # well past the caller's timeout
    assert not waiter.done()
    assert _row(session_factory, command_id).status == "running"
    gate.release.set()

    assert await asyncio.wait_for(waiter, timeout=2.0) == (True, None)
    await worker
    assert _row(session_factory, command_id).status == "applied"


@pytest.mark.asyncio
async def test_caller_giving_up_on_a_running_command_does_not_rewrite_its_result(
    session_factory,
):
    gate = _Gate((True, None))
    queue = _queue(session_factory, gate, running_grace_s=0.05)
    command_id = queue.enqueue("do_it")
    worker = asyncio.create_task(queue.process_one_pending(_manager()))
    await asyncio.wait_for(gate.entered.wait(), timeout=2.0)

    success, error = await queue.wait_for_completion(command_id, timeout_s=0.05)

    assert success is False
    assert error == "Command still running after 0.1s; outcome unknown"
    assert _row(session_factory, command_id).status == "running"
    gate.release.set()
    await asyncio.wait_for(worker, timeout=2.0)
    row = _row(session_factory, command_id)
    assert row.status == "applied"
    assert row.error_message is None


def _flaky_factory(session_factory, failures: int):
    """Session factory whose first *failures* calls raise."""
    state = {"left": failures}

    def factory():
        if state["left"] > 0:
            state["left"] -= 1
            raise RuntimeError("connection refused")
        return session_factory()

    return factory


@pytest.mark.asyncio
async def test_unreadable_status_is_not_reported_as_a_missing_command(session_factory):
    """Ein DB-Fehler beim Statuslesen hiess "Command not found" -- waehrend der
    Befehl weiter in der Queue stand und ausgefuehrt wurde."""
    writer = _queue(session_factory)
    command_id = writer.enqueue("do_it")
    await writer.process_one_pending(_manager())
    reader = _queue(_flaky_factory(session_factory, failures=2))

    result = await reader.wait_for_completion(command_id, timeout_s=2.0)

    assert result == (True, None)


@pytest.mark.asyncio
async def test_status_that_stays_unreadable_is_reported_as_unknown(session_factory):
    """Kann der Follower die Datenbank nicht fragen, weiss er nichts ueber den
    Befehl -- auch nicht, dass er nicht lief. "Timed out" waere eine Aussage."""
    queue = _queue(session_factory)
    command_id = queue.enqueue("do_it")
    reader = _queue(_flaky_factory(session_factory, failures=10_000), running_grace_s=0.05)

    success, error = await reader.wait_for_completion(command_id, timeout_s=0.05)

    assert success is False
    assert error == "Command outcome unknown after 0.1s: its state could not be read"


@pytest.mark.asyncio
async def test_applied_command_is_never_reported_as_timed_out(session_factory):
    """Review-Befund: Der Primary ist gesund und fuehrt aus, nur der Follower
    erreicht die Datenbank nicht. Vorher: "Command timed out" fuer einen
    Befehl, der gewirkt hat."""
    dispatch = _Recorder()
    primary = _queue(session_factory, dispatch)
    command_id = primary.enqueue("do_it")
    await primary.process_one_pending(_manager())
    follower = _queue(_flaky_factory(session_factory, failures=10_000), running_grace_s=0.05)

    success, error = await follower.wait_for_completion(command_id, timeout_s=0.05)

    assert len(dispatch.calls) == 1
    assert success is False
    assert "timed out" not in error
    assert "outcome unknown" in error


# ─── Wettrennen zwischen Abholen und Aufgeben ────────────────────────
#
# Beide Seiten verlassen `pending` mit einem bedingten UPDATE. Genau einer
# gewinnt; der andere muss das merken und darf weder ausfuehren noch das
# Ergebnis ueberschreiben.


@pytest.mark.asyncio
async def test_caller_cancelling_first_keeps_the_primary_from_executing(
    session_factory, monkeypatch
):
    """Der Aufrufer gibt auf, nachdem der Primary die Zeile gelesen, aber
    bevor er sie uebernommen hat."""
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    command_id = queue.enqueue("do_it")
    real_is_expired = queue._is_expired

    def cancel_in_between(row, now):
        assert queue._cancel_pending(command_id) is True
        return real_is_expired(row, now)

    monkeypatch.setattr(queue, "_is_expired", cancel_in_between)

    processed = await queue.process_one_pending(_manager())

    assert processed is False
    assert dispatch.calls == []
    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message == "timed out (caller gave up)"


@pytest.mark.asyncio
async def test_primary_claiming_first_keeps_the_caller_from_cancelling(
    session_factory, monkeypatch
):
    """Der Primary uebernimmt die Zeile, nachdem der Aufrufer `pending` gelesen
    hat, aber bevor er abbricht. Der Abbruch darf nicht greifen, und der
    Aufrufer bekommt das echte Ergebnis."""
    gate = _Gate((True, None))
    queue = _queue(session_factory, gate, running_grace_s=5.0)
    command_id = queue.enqueue("do_it")
    real_read_status = queue._read_status
    worker: list[asyncio.Task] = []
    loop = asyncio.get_running_loop()

    def claim_after_first_read(cid):
        result = real_read_status(cid)
        if not worker:
            # Runs in the wait's worker thread: start the primary and block
            # until it has claimed the row.
            worker.append(
                asyncio.run_coroutine_threadsafe(
                    queue.process_one_pending(_manager()), loop
                )
            )
            asyncio.run_coroutine_threadsafe(gate.entered.wait(), loop).result(timeout=5)
        return result

    monkeypatch.setattr(queue, "_read_status", claim_after_first_read)

    waiter = asyncio.create_task(queue.wait_for_completion(command_id, timeout_s=0))
    await asyncio.wait_for(gate.entered.wait(), timeout=5.0)
    await asyncio.sleep(0.1)  # the caller's cancel attempt happens here
    assert not waiter.done()
    assert _row(session_factory, command_id).status == "running"
    gate.release.set()

    assert await asyncio.wait_for(waiter, timeout=5.0) == (True, None)
    assert worker[0].result(timeout=5) is True
    row = _row(session_factory, command_id)
    assert row.status == "applied"
    assert row.error_message is None


def test_cancel_leaves_a_running_command_alone(session_factory):
    queue = _queue(session_factory)
    command_id = _insert(session_factory, status="running")

    assert queue._cancel_pending(command_id) is False

    row = _row(session_factory, command_id)
    assert row.status == "running"
    assert row.error_message is None


@pytest.mark.asyncio
async def test_deadline_passing_during_the_claim_still_prevents_execution(
    session_factory, monkeypatch
):
    """Review-Befund: Die Frist wurde nur vor dem UPDATE geprueft. Haengt der
    Prozess dazwischen (Suspend, SIGSTOP), wurde eine inzwischen abgelaufene
    Zeile uebernommen und ausgefuehrt."""
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch)
    command_id = queue.enqueue("do_it", timeout_s=0.3)
    real_is_expired = queue._is_expired
    stalled: list[int] = []

    def stall_after_the_check(row, now):
        verdict = real_is_expired(row, now)
        if not stalled:
            stalled.append(1)
            assert verdict is False
            import time

            time.sleep(0.6)  # the deadline passes while the claim is stuck
        return verdict

    monkeypatch.setattr(queue, "_is_expired", stall_after_the_check)

    processed = await queue.process_one_pending(_manager())

    assert processed is False
    assert dispatch.calls == []
    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message == "expired (not picked up before its deadline)"


@pytest.mark.asyncio
async def test_row_without_deadline_is_guarded_by_its_age_during_the_claim(
    session_factory, monkeypatch
):
    dispatch = _Recorder()
    queue = _queue(session_factory, dispatch, default_timeout_s=3.0)
    command_id = _insert(
        session_factory,
        requested_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    real_is_expired = queue._is_expired
    lied: list[int] = []

    def miss_it_once(row, now):
        if not lied:
            lied.append(1)
            return False  # as if the check had run before the deadline
        return real_is_expired(row, now)

    monkeypatch.setattr(queue, "_is_expired", miss_it_once)

    assert await queue.process_one_pending(_manager()) is False
    assert dispatch.calls == []
    assert _row(session_factory, command_id).status == "failed"


@pytest.mark.asyncio
async def test_caller_learns_that_the_primary_let_its_command_expire(session_factory):
    queue = _queue(session_factory)
    command_id = queue.enqueue("do_it", timeout_s=0)
    await queue.process_one_pending(_manager())

    result = await queue.wait_for_completion(command_id, timeout_s=2.0)

    assert result == (False, "expired (not picked up before its deadline)")


# ─── Primary stoppt mitten im Befehl ─────────────────────────────────
#
# `running` darf kein Dauerzustand werden: Wer die Zeile spaeter liest,
# soll sehen, dass niemand mehr daran arbeitet.


@pytest.mark.asyncio
async def test_loop_cancelled_mid_command_marks_the_row_interrupted(session_factory):
    gate = _Gate()
    queue = _queue(session_factory, gate)
    manager = _manager()
    command_id = queue.enqueue("do_it")
    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    await asyncio.wait_for(gate.entered.wait(), timeout=2.0)

    loop_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop_task

    row = _row(session_factory, command_id)
    assert row.status == "failed"
    assert row.error_message == "interrupted (primary stopped mid-command); outcome unknown"
    assert row.completed_at is not None


@pytest.mark.asyncio
async def test_poll_loop_start_fails_commands_a_dead_primary_left_running(session_factory):
    queue = _queue(session_factory)
    left_running = _insert(session_factory, status="running")
    untouched = _insert(session_factory, status="applied")
    manager = _manager()

    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    try:
        result = await queue.submit("do_it", timeout_s=2.0)
    finally:
        manager._is_running = False
        await asyncio.wait_for(loop_task, timeout=2.0)

    assert result == (True, None)
    row = _row(session_factory, left_running)
    assert row.status == "failed"
    assert row.error_message == "interrupted (primary stopped mid-command); outcome unknown"
    assert _row(session_factory, untouched).status == "applied"


def test_fail_interrupted_survives_a_database_failure():
    def broken_factory():
        raise RuntimeError("database down")

    assert _queue(broken_factory).fail_interrupted() == 0


# ─── Fehler sichtbar machen ──────────────────────────────────────────


def test_claim_that_keeps_failing_is_logged_once_and_not_on_every_poll(caplog):
    """Ein dauerhaft scheiternder Claim (fehlende Spalte, DB weg) stand nur im
    DEBUG-Log: die Queue war tot, und niemand sah es."""
    def broken_factory():
        raise RuntimeError("database down")

    queue = _queue(broken_factory)

    with caplog.at_level("WARNING", logger="app.services.power.db_command_queue"):
        for _ in range(5):
            assert queue.claim_pending() is None

    warnings = [r for r in caplog.records if "claim" in r.getMessage()]
    assert len(warnings) == 1
    assert "database down" in warnings[0].getMessage()


def test_claim_failure_is_logged_again_after_a_recovery(session_factory, caplog):
    queue = _queue(_flaky_factory(session_factory, failures=1))

    with caplog.at_level("WARNING", logger="app.services.power.db_command_queue"):
        queue.claim_pending()  # fails
        queue.claim_pending()  # works
        queue._session_factory = _flaky_factory(session_factory, failures=1)
        queue.claim_pending()  # fails again

    assert len([r for r in caplog.records if "claim" in r.getMessage()]) == 2


def test_enqueue_does_not_depend_on_a_read_after_its_commit(tmp_path):
    """Review-Befund: `commit()` gefolgt von `refresh()` -- scheiterte das
    Nachlesen, meldete enqueue "fehlgeschlagen" fuer eine Zeile, die in der
    Queue stand und ausgefuehrt wurde."""
    from sqlalchemy.orm import Session

    class _NoRefresh(Session):
        def refresh(self, *args, **kwargs):
            raise RuntimeError("connection lost after commit")

    engine = create_engine(f"sqlite:///{tmp_path}/norefresh.db")
    _Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=_NoRefresh, autoflush=False, autocommit=False)
    queue = _queue(factory)

    command_id = queue.enqueue("do_it")

    assert command_id is not None
    assert _row(factory, command_id).status == "pending"
    engine.dispose()


# ─── #829/3: Datenbank auf dem Event-Loop ────────────────────────────


def _thread_recording_factory(session_factory, seen: list):
    def factory():
        seen.append(threading.current_thread())
        return session_factory()

    return factory


@pytest.mark.asyncio
async def test_no_session_is_opened_on_the_event_loop(session_factory):
    """Jeder Zugriff oeffnet eine eigene Session (Connect, Pool-Ping). Seit
    #797 lief nur das Abholen in einem Thread; Einreihen, Statuslesen,
    Zurueckschreiben und Aufgeben blockierten weiter den Loop."""
    seen: list[threading.Thread] = []
    queue = _queue(_thread_recording_factory(session_factory, seen))
    manager = _manager()

    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    try:
        applied = await queue.submit("do_it", payload={"level": 3}, timeout_s=2.0)
    finally:
        manager._is_running = False
        await asyncio.wait_for(loop_task, timeout=2.0)
    given_up = await queue.submit("nobody_listens", timeout_s=0.05)

    assert applied == (True, None)
    assert given_up == (False, "Command timed out after 0.1s")
    assert seen, "the queue opened no session at all"
    assert all(thread is not threading.main_thread() for thread in seen)


@pytest.mark.asyncio
async def test_submit_reports_a_failed_enqueue():
    def broken_factory():
        raise RuntimeError("database down")

    queue = _queue(broken_factory)

    assert await queue.submit("do_it") == (False, "Failed to enqueue command")


@pytest.mark.asyncio
async def test_submit_waits_as_long_as_the_deadline_it_stored(session_factory):
    """Ein Timeout fuer Zeile und Wartezeit: sonst gaebe der Aufrufer frueher
    oder spaeter auf, als der Primary die Zeile verfallen laesst."""
    queue = _queue(session_factory, default_timeout_s=30.0)
    started = datetime.now(timezone.utc)

    success, error = await queue.submit("do_it", timeout_s=0.3)

    waited = datetime.now(timezone.utc) - started
    assert (success, error) == (False, "Command timed out after 0.3s")
    assert timedelta(seconds=0.25) <= waited <= timedelta(seconds=10)
    db = session_factory()
    row = db.query(_ThingCommand).one()
    db.close()
    assert _utc(row.expires_at) - started <= timedelta(seconds=10)


# ─── #829/2: Aufraeumen ──────────────────────────────────────────────


def test_purge_removes_finished_commands_past_the_retention(session_factory):
    queue = _queue(session_factory, retention_s=3600.0)
    long_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    recently = datetime.now(timezone.utc) - timedelta(minutes=10)
    for status in ("applied", "failed", "running"):
        _insert(session_factory, status=status, requested_at=long_ago)
    kept_recent = _insert(session_factory, status="applied", requested_at=recently)
    kept_pending = _insert(session_factory, status="pending", requested_at=long_ago)

    removed = queue.purge_finished()

    assert removed == 3
    assert _count(session_factory) == 2
    assert _row(session_factory, kept_recent) is not None
    assert _row(session_factory, kept_pending) is not None


def test_purge_survives_a_database_failure():
    def broken_factory():
        raise RuntimeError("database down")

    assert _queue(broken_factory).purge_finished() == 0


@pytest.mark.asyncio
async def test_poll_loop_purges_when_it_starts_and_not_on_every_poll(
    session_factory, monkeypatch
):
    queue = _queue(session_factory, retention_s=3600.0)
    _insert(
        session_factory,
        status="applied",
        requested_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    purges: list[int] = []
    original = queue.purge_finished

    def counting_purge():
        purges.append(1)
        return original()

    monkeypatch.setattr(queue, "purge_finished", counting_purge)
    manager = _manager()
    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    await asyncio.sleep(0.15)  # a dozen polls at 0.01 s
    manager._is_running = False
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert _count(session_factory) == 0
    assert len(purges) == 1


@pytest.mark.asyncio
async def test_poll_loop_purges_again_after_the_interval(session_factory, monkeypatch):
    queue = _queue(session_factory, purge_interval_s=0.05)
    purges: list[int] = []
    monkeypatch.setattr(queue, "purge_finished", lambda: purges.append(1) or 0)
    manager = _manager()
    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    for _ in range(500):  # up to 5 s on a loaded machine
        if len(purges) >= 2:
            break
        await asyncio.sleep(0.01)
    manager._is_running = False
    await asyncio.wait_for(loop_task, timeout=2.0)

    assert len(purges) >= 2


@pytest.mark.asyncio
async def test_failing_purge_does_not_stop_the_poll_loop(session_factory, monkeypatch):
    queue = _queue(session_factory)

    def broken_purge():
        raise RuntimeError("purge exploded")

    monkeypatch.setattr(queue, "purge_finished", broken_purge)
    manager = _manager()
    loop_task = asyncio.create_task(queue.run_poll_loop(manager))
    try:
        result = await queue.submit("do_it", timeout_s=2.0)
    finally:
        manager._is_running = False
        await asyncio.wait_for(loop_task, timeout=2.0)

    assert result == (True, None)
