"""Health monitor loop: SMART check runs in a worker thread, not on the loop (#872)."""
from __future__ import annotations

import asyncio
import contextlib
import threading

import pytest

from app.services import jobs


@pytest.fixture(autouse=True)
def no_system_info(monkeypatch):
    # The old loop called get_system_info(), whose path ends in `sudo dmidecode`.
    monkeypatch.setattr("app.services.system.get_system_info", lambda: None)


async def test_health_check_runs_off_the_event_loop(monkeypatch):
    loop = asyncio.get_running_loop()
    seen, done = [], asyncio.Event()

    def fake_smart():
        seen.append(threading.get_ident())
        loop.call_soon_threadsafe(done.set)

    monkeypatch.setattr(jobs.smart_service, "get_smart_status", fake_smart)
    task = asyncio.create_task(jobs._health_check_loop(3600))
    await asyncio.wait_for(done.wait(), 5)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert seen and threading.get_ident() not in seen


def test_health_check_does_not_read_system_info(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs.smart_service, "get_smart_status", lambda: None)
    monkeypatch.setattr("app.services.system.get_system_info", lambda: calls.append(1))
    jobs.run_health_checks()
    assert calls == []


async def test_a_failing_check_does_not_end_the_loop(monkeypatch):
    loop = asyncio.get_running_loop()
    calls, second = [], asyncio.Event()

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("smartctl kaputt")
        loop.call_soon_threadsafe(second.set)

    monkeypatch.setattr(jobs.smart_service, "get_smart_status", flaky)
    task = asyncio.create_task(jobs._health_check_loop(0.01))
    await asyncio.wait_for(second.wait(), 5)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
