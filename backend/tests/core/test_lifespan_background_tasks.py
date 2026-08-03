"""Lifecycle of the lifespan's own background tasks (#320).

Five `asyncio.create_task()` calls in `_startup()` kept no reference to the
task. CPython only holds a *weak* reference in the loop, so such a task may be
garbage-collected mid-flight; and with no reference there is nothing for
`_shutdown()` to cancel, so the loops ran on into interpreter teardown. A
third consequence is quieter but worse: an exception in one of those loops was
never retrieved, so a dead heartbeat writer looked exactly like a healthy one.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from app.core import lifespan


def _clear_registry():
    lifespan._BACKGROUND_TASKS.clear()


async def test_spawned_task_is_kept_referenced_until_it_completes():
    _clear_registry()
    started = asyncio.Event()
    release = asyncio.Event()

    async def _work():
        started.set()
        await release.wait()

    task = lifespan._spawn_background(_work(), "unit-work")
    await started.wait()

    # Referenced by us, not merely by the loop's WeakSet.
    assert task in lifespan._BACKGROUND_TASKS

    release.set()
    await task
    await asyncio.sleep(0)  # let the done-callback run

    assert task not in lifespan._BACKGROUND_TASKS


async def test_a_crashing_background_task_reports_itself(caplog):
    _clear_registry()

    async def _boom():
        raise RuntimeError("loop died")

    with caplog.at_level(logging.ERROR, logger=lifespan.logger.name):
        lifespan._spawn_background(_boom(), "unit-boom")
        await asyncio.sleep(0.05)

    messages = [
        r.getMessage() for r in caplog.records if r.name == lifespan.logger.name
    ]
    assert any("unit-boom" in m for m in messages), messages
    assert any("loop died" in m for m in messages), messages


async def test_cancel_stops_running_loops_and_clears_the_registry():
    _clear_registry()

    async def _forever():
        while True:
            await asyncio.sleep(3600)

    task = lifespan._spawn_background(_forever(), "unit-forever")
    await asyncio.sleep(0)

    await lifespan._cancel_background_tasks()

    assert task.cancelled()
    assert not lifespan._BACKGROUND_TASKS


async def test_heartbeat_writer_survives_a_failing_write(monkeypatch, caplog):
    """One bad write must not end the loop for the rest of the process.

    Nothing restarts it, and its silence is invisible: secondary workers keep
    serving the last heartbeat row that was written.
    """
    calls: list[int] = []

    async def _flaky_write():
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("db hiccup")

    monkeypatch.setattr(lifespan, "_do_heartbeat_write", _flaky_write)
    monkeypatch.setattr(lifespan, "_HEARTBEAT_INTERVAL_SECONDS", 0)

    with caplog.at_level(logging.WARNING, logger=lifespan.logger.name):
        task = asyncio.create_task(lifespan._write_service_heartbeats())
        for _ in range(500):
            await asyncio.sleep(0)
            if len(calls) >= 3:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert len(calls) >= 3, f"the loop stopped after {len(calls)} write(s)"

    messages = [
        r.getMessage() for r in caplog.records if r.name == lifespan.logger.name
    ]
    assert any("db hiccup" in m for m in messages), messages


async def _run_smart_device_bridge_once(monkeypatch, changes, *, is_admin=False):
    """Drive one iteration of the SMART-device bridge against a live manager.

    Returns the frame the mock socket actually received, i.e. the bytes a
    client would parse — not the argument the bridge passed inward.
    """
    from app.services import websocket_manager as wsm
    from app.services.monitoring import shm

    manager = wsm.WebSocketManager()
    ws = MagicMock()
    ws.send_json = AsyncMock()
    await manager.connect(ws, user_id=1, is_admin=is_admin)

    monkeypatch.setattr(lifespan, "_SMART_DEVICE_BRIDGE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(wsm, "get_websocket_manager", lambda: manager)
    monkeypatch.setattr(
        shm, "read_shm", lambda *a, **kw: {"timestamp": 1.0, "changes": changes}
    )

    task = asyncio.create_task(lifespan._smart_device_ws_bridge())
    for _ in range(500):
        await asyncio.sleep(0)
        if ws.send_json.await_count:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert ws.send_json.await_count, "bridge never broadcast the changes"
    return ws.send_json.await_args[0][0]


async def test_smart_device_bridge_sends_one_envelope_not_two(monkeypatch):
    """#511: the frame carries its own type at the top level.

    The bridge used to hand an already-typed message to `broadcast_to_all()`,
    which wrapped it a second time as `{"type": "notification", ...}`. Web
    clients match on the top-level type and saw nothing; the Android client
    trusted the "notification" label, deserialized the inner envelope into a
    NotificationDto whose non-null fields came back null, and crashed.
    """
    changes = [
        {
            "device_id": 9,
            "name": "Sven PC Power Plug",
            "state": {"switch": {"is_on": False}},
            "timestamp": "2026-08-03T11:00:54.393785+00:00",
        }
    ]

    frame = await _run_smart_device_bridge_once(monkeypatch, changes)

    assert frame == {"type": "smart_device_update", "payload": changes}


async def test_smart_device_bridge_still_reaches_non_admins(monkeypatch):
    """Reach must not narrow: these updates always went to every connection."""
    frame = await _run_smart_device_bridge_once(
        monkeypatch, [{"device_id": 1}], is_admin=False
    )
    assert frame["type"] == "smart_device_update"


async def test_shutdown_cancellation_is_not_reported_as_a_crash(caplog):
    """Cancelling at shutdown is normal — it must not look like a failure."""
    _clear_registry()

    async def _forever():
        while True:
            await asyncio.sleep(3600)

    lifespan._spawn_background(_forever(), "unit-quiet")
    await asyncio.sleep(0)

    with caplog.at_level(logging.ERROR, logger=lifespan.logger.name):
        await lifespan._cancel_background_tasks()

    errors = [r for r in caplog.records if r.name == lifespan.logger.name]
    assert errors == [], [r.getMessage() for r in errors]
