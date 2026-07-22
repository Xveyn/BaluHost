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
