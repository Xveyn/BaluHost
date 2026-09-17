"""The primary worker reconciles plugin enablement on a timer (#465).

With background tasks gated to the primary worker, a toggle handled by one of
the three secondaries leaves the poller unstarted until the *primary* runs the
reconcile. That used to depend entirely on request traffic: the reconcile is
wired to routes the frontend polls (status strip every 10s), but polling stops
while the tab is hidden, so "enable the plugin, then close the browser" could
leave the task unstarted indefinitely.

This loop makes the catch-up independent of UI traffic and bounded by
``_PLUGIN_RECONCILE_INTERVAL_SECONDS``.
"""

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from app.core import lifespan
from app.services import plugin_enablement

pytestmark = pytest.mark.asyncio


async def _run_until(predicate, task: asyncio.Task, limit: int = 2000) -> None:
    """Yield to the loop until *predicate* holds, then stop *task*."""
    try:
        for _ in range(limit):
            await asyncio.sleep(0)
            if predicate():
                return
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def test_the_loop_reconciles_repeatedly(monkeypatch):
    reconcile = AsyncMock()
    monkeypatch.setattr(plugin_enablement, "reconcile_worker", reconcile)
    monkeypatch.setattr(lifespan, "_PLUGIN_RECONCILE_INTERVAL_SECONDS", 0)

    task = asyncio.create_task(lifespan._reconcile_plugin_enablement())
    await _run_until(lambda: reconcile.await_count >= 3, task)

    assert reconcile.await_count >= 3


async def test_the_loop_survives_a_failing_reconcile(monkeypatch, caplog):
    """``reconcile_worker()`` promises never to raise, but the loop must not
    depend on that promise: nothing restarts it, and its silence would look
    exactly like a healthy worker that simply has nothing to reconcile."""
    calls: list[int] = []

    async def _flaky() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("reconcile blew up")

    monkeypatch.setattr(plugin_enablement, "reconcile_worker", _flaky)
    monkeypatch.setattr(lifespan, "_PLUGIN_RECONCILE_INTERVAL_SECONDS", 0)

    with caplog.at_level(logging.WARNING, logger=lifespan.logger.name):
        task = asyncio.create_task(lifespan._reconcile_plugin_enablement())
        await _run_until(lambda: len(calls) >= 3, task)

    assert len(calls) >= 3
    assert any(
        "reconcile blew up" in r.getMessage() or "reconcile" in r.getMessage()
        for r in caplog.records
        if r.name == lifespan.logger.name
    ), [r.getMessage() for r in caplog.records]
