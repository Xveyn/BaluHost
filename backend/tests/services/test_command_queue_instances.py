"""Die zwei echten Queues tragen, was `DbCommandQueue` voraussetzt (#829).

Die Klasse selbst ist in `test_db_command_queue.py` gegen eine Testtabelle
geprueft. Hier: Die Tabellen `power_commands` und `gpu_power_commands` haben
die Frist-Spalte, die Module reichen das Timeout durch, und die Manager
warten nicht mehr mit einer Session auf dem Event-Loop.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.models.gpu_power import GpuPowerCommand
from app.models.power import PowerCommand
from app.services.power import command_queue as cpu_queue
from app.services.power.gpu import command_queue as gpu_queue

QUEUES = [
    pytest.param(cpu_queue, PowerCommand, id="cpu"),
    pytest.param(gpu_queue, GpuPowerCommand, id="gpu"),
]

_Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def _command_tables():
    for model in (PowerCommand, GpuPowerCommand):
        if not inspect(engine).has_table(model.__tablename__):
            model.__table__.create(bind=engine, checkfirst=True)
    yield
    db = _Session()
    try:
        for model in (PowerCommand, GpuPowerCommand):
            db.query(model).delete()
        db.commit()
    finally:
        db.close()


def _row(model, command_id: int):
    db = _Session()
    try:
        return db.query(model).filter(model.id == command_id).first()
    finally:
        db.close()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@pytest.mark.parametrize("queue, model", QUEUES)
def test_enqueued_command_carries_a_deadline(queue, model):
    before = datetime.now(timezone.utc)

    default_id = queue.enqueue_command("anything")
    long_id = queue.enqueue_command("anything", timeout_s=10.0)

    default_wait = _utc(_row(model, default_id).expires_at) - before
    long_wait = _utc(_row(model, long_id).expires_at) - before
    # Wide upper bounds: a loaded machine may take a while to write the row.
    assert timedelta(seconds=2.9) <= default_wait <= timedelta(seconds=8)
    assert timedelta(seconds=9.9) <= long_wait <= timedelta(seconds=18)


# A command each queue really knows, so that "not executed" is a statement:
# dispatched, each of them calls into the manager.
REAL_COMMANDS = [
    pytest.param(cpu_queue, PowerCommand, "disable_dynamic_mode", None, id="cpu"),
    pytest.param(gpu_queue, GpuPowerCommand, "unregister_demand", {"source": "x"}, id="gpu"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("queue, model, command, payload", REAL_COMMANDS)
async def test_command_in_time_reaches_the_manager(queue, model, command, payload):
    command_id = queue.enqueue_command(command, payload=payload)
    manager = AsyncMock()

    assert await queue.QUEUE.process_one_pending(manager) is True

    assert manager.mock_calls != []
    assert _row(model, command_id).status in ("applied", "failed")


@pytest.mark.asyncio
@pytest.mark.parametrize("queue, model, command, payload", REAL_COMMANDS)
async def test_orphaned_command_is_not_executed(queue, model, command, payload):
    """Der Fall aus #829: eingereiht, Aufrufer weg, Primary kommt spaeter."""
    command_id = queue.enqueue_command(command, payload=payload, timeout_s=0)
    manager = AsyncMock()

    processed = await queue.QUEUE.process_one_pending(manager)

    assert processed is False
    assert manager.mock_calls == []
    row = _row(model, command_id)
    assert row.status == "failed"
    assert "expired" in row.error_message


@pytest.mark.asyncio
@pytest.mark.parametrize("queue, model", QUEUES)
async def test_submit_command_enqueues_off_the_loop_and_reports_the_timeout(
    queue, model, monkeypatch
):
    seen: list[threading.Thread] = []
    original = queue.QUEUE._session_factory

    def recording_factory():
        seen.append(threading.current_thread())
        return original()

    monkeypatch.setattr(queue.QUEUE, "_session_factory", recording_factory)

    success, error = await queue.submit_command("anything", timeout_s=0.2)

    assert success is False
    assert error == "Command timed out after 0.2s"
    assert seen and all(thread is not threading.main_thread() for thread in seen)
    db = _Session()
    try:
        row = db.query(model).one()
        assert row.status == "failed"
        assert row.error_message == "timed out (caller gave up)"
    finally:
        db.close()


# ─── Manager: Follower-Pfade ─────────────────────────────────────────


def _power_follower():
    from app.services.power.manager import PowerManagerService

    follower = PowerManagerService()
    follower._is_running = True
    follower._primary = False
    follower._backend = None
    return follower


def _gpu_follower():
    from app.services.power.gpu.manager import GpuPowerManagerService

    follower = GpuPowerManagerService()
    follower._is_running = True
    follower._primary = False
    follower._backend = None
    return follower


@pytest.mark.asyncio
async def test_backend_switch_stores_its_longer_deadline_on_the_row():
    """`switch_backend` wartet 10 s statt 3 s. Die Zeile muss dieselbe Frist
    tragen -- sonst verfiele sie im Primary, waehrend der Aufrufer noch wartet."""
    import asyncio

    started = datetime.now(timezone.utc)
    call = asyncio.create_task(_power_follower().switch_backend(True))

    seen = None
    for _ in range(200):  # the follower writes its row from a worker thread
        db = _Session()
        try:
            row = db.query(PowerCommand).filter(PowerCommand.status == "pending").first()
            if row is not None:
                seen = (row.command, _utc(row.expires_at))
                row.status = "applied"  # play the primary so the call returns
                db.commit()
                break
        finally:
            db.close()
        await asyncio.sleep(0.02)
    success, _previous, _new = await asyncio.wait_for(call, timeout=5.0)

    assert seen is not None, "the follower never enqueued a command"
    command, deadline = seen
    assert command == "switch_backend"
    wait = deadline - started
    assert timedelta(seconds=cpu_queue.BACKEND_SWITCH_TIMEOUT_S - 0.1) <= wait
    assert wait <= timedelta(seconds=cpu_queue.BACKEND_SWITCH_TIMEOUT_S + 8)
    assert success is True


@pytest.mark.asyncio
async def test_power_follower_hands_over_without_a_session_on_the_event_loop(monkeypatch):
    seen: list[threading.Thread] = []
    original = cpu_queue.QUEUE._session_factory

    def recording_factory():
        seen.append(threading.current_thread())
        return original()

    monkeypatch.setattr(cpu_queue.QUEUE, "_session_factory", recording_factory)
    monkeypatch.setattr(cpu_queue.QUEUE, "_default_timeout_s", 0.2)
    follower = _power_follower()

    assert (await follower.disable_dynamic_mode())[0] is False

    assert seen and all(thread is not threading.main_thread() for thread in seen)


@pytest.mark.asyncio
async def test_gpu_follower_hands_over_without_a_session_on_the_event_loop(monkeypatch):
    seen: list[threading.Thread] = []
    original = gpu_queue.QUEUE._session_factory

    def recording_factory():
        seen.append(threading.current_thread())
        return original()

    monkeypatch.setattr(gpu_queue.QUEUE, "_session_factory", recording_factory)
    monkeypatch.setattr(gpu_queue.QUEUE, "_default_timeout_s", 0.2)
    follower = _gpu_follower()

    assert await follower.unregister_demand("nobody") is False

    assert seen and all(thread is not threading.main_thread() for thread in seen)
