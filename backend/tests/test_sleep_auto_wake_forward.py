"""Auto-wake works on every worker and wakes the primary (#823, part 2).

The middleware decides on the state the primary published
(`effective_state()`) and wakes through `request_wake()`, which a follower
forwards to the primary. A dead primary must not slow every request down
(back-off), and concurrent requests in one process share one wake.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import sleep_auto_wake
from app.middleware.sleep_auto_wake import SleepAutoWakeMiddleware
from app.schemas.sleep import SleepState
from app.services.power.sleep import SleepActionResult, SleepActionStatus

DONE = SleepActionResult(SleepActionStatus.DONE)
REFUSED = SleepActionResult(SleepActionStatus.REFUSED)
UNAVAILABLE = SleepActionResult(SleepActionStatus.UNAVAILABLE, "Command timed out after 5.0s")


@pytest.fixture(autouse=True)
def _fresh_middleware_state():
    sleep_auto_wake._reset_auto_wake_state()
    yield
    sleep_auto_wake._reset_auto_wake_state()


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SleepAutoWakeMiddleware)

    @app.post("/api/files/upload")
    async def upload_stub():
        return {"ok": True}

    @app.get("/api/system/sleep/status")
    async def status_stub():
        return {"ok": True}

    @app.post("/api/sync/changes")
    async def sync_stub():
        return {"ok": True}

    return app


def _manager(state: SleepState = SleepState.SOFT_SLEEP, wake=DONE) -> MagicMock:
    manager = MagicMock()
    manager.effective_state.return_value = (state, None)
    if isinstance(wake, BaseException):
        manager.request_wake = AsyncMock(side_effect=wake)
    else:
        manager.request_wake = AsyncMock(return_value=wake)
    return manager


def _post(manager, path="/api/files/upload", headers=None):
    with patch("app.services.power.sleep.record_http_request"), \
         patch("app.services.power.sleep.get_sleep_manager", return_value=manager):
        return TestClient(_app()).post(path, headers=headers or {})


# ─── Deciding and waking ─────────────────────────────────────────────


def test_published_soft_sleep_triggers_a_wake_request():
    manager = _manager()
    # A follower: its own state machine never left AWAKE.
    manager._current_state = SleepState.AWAKE

    response = _post(manager)

    assert response.status_code == 200
    manager.request_wake.assert_awaited_once_with("auto_wake: POST /api/files/upload")


def test_awake_box_does_not_wake():
    manager = _manager(state=SleepState.AWAKE)

    _post(manager)

    manager.request_wake.assert_not_called()


@pytest.mark.parametrize("trigger", ["auto", "scheduled", "AUTO"])
def test_automatic_sync_does_not_wake(trigger):
    manager = _manager()

    _post(manager, path="/api/sync/changes", headers={"X-Sync-Trigger": trigger})

    manager.request_wake.assert_not_called()


def test_manual_sync_wakes():
    manager = _manager()

    _post(manager, path="/api/sync/changes", headers={"X-Sync-Trigger": "manual"})

    manager.request_wake.assert_awaited_once()


def test_whitelisted_path_does_not_wake():
    manager = _manager()
    with patch("app.services.power.sleep.record_http_request"), \
         patch("app.services.power.sleep.get_sleep_manager", return_value=manager):
        TestClient(_app()).get("/api/system/sleep/status")

    manager.request_wake.assert_not_called()
    manager.effective_state.assert_not_called()


# ─── Never failing the request ───────────────────────────────────────


def test_exception_in_the_wake_never_fails_the_request():
    manager = _manager(wake=RuntimeError("queue exploded"))

    response = _post(manager)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_exception_in_effective_state_never_fails_the_request():
    manager = _manager()
    manager.effective_state.side_effect = RuntimeError("db down")

    response = _post(manager)

    assert response.status_code == 200
    manager.request_wake.assert_not_called()


@pytest.mark.parametrize("result", [UNAVAILABLE, REFUSED])
def test_failed_wake_still_serves_the_request(result):
    response = _post(_manager(wake=result))

    assert response.status_code == 200


# ─── Back-off ────────────────────────────────────────────────────────


def test_unavailable_wake_backs_off_for_ten_seconds():
    clock = [1000.0]
    manager = _manager(wake=UNAVAILABLE)
    with patch.object(sleep_auto_wake, "_monotonic", side_effect=lambda: clock[0]):
        _post(manager)
        assert manager.request_wake.await_count == 1

        clock[0] += 9.9
        _post(manager)
        assert manager.request_wake.await_count == 1  # passed straight through

        clock[0] += 0.2
        _post(manager)
        assert manager.request_wake.await_count == 2


def test_wake_someone_else_already_did_is_not_a_dead_primary(caplog):
    """Two workers see soft sleep in the same moment and both forward a wake.
    The primary executes the first; the second waits behind it, is never
    picked up and comes back "unavailable" -- although the box is waking up
    just fine. That must neither warn about an unreachable primary nor stop
    this process from auto-waking for ten seconds."""
    manager = _manager(wake=UNAVAILABLE)
    states = [SleepState.SOFT_SLEEP, SleepState.WAKING]
    manager.effective_state.side_effect = lambda: (states.pop(0) if states else SleepState.SOFT_SLEEP, None)

    with caplog.at_level("WARNING", logger="app.middleware.sleep_auto_wake"):
        _post(manager)   # sees SOFT_SLEEP, wake "unavailable", then sees WAKING
        _post(manager)   # box asleep again later: must try again at once

    assert manager.request_wake.await_count == 2
    first_call_warnings = [r for r in caplog.records if "could not reach" in r.getMessage()]
    assert len(first_call_warnings) == 1  # only the second, genuine failure


def test_back_off_constant_is_ten_seconds():
    assert sleep_auto_wake._AUTO_WAKE_BACKOFF_S == 10.0


def test_refused_wake_does_not_back_off():
    manager = _manager(wake=REFUSED)

    _post(manager)
    _post(manager)

    assert manager.request_wake.await_count == 2


def test_successful_wake_does_not_back_off():
    manager = _manager(wake=DONE)

    _post(manager)
    _post(manager)

    assert manager.request_wake.await_count == 2


# ─── One wake per process at a time ──────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_requests_share_one_wake():
    release = asyncio.Event()
    started = asyncio.Event()

    async def slow_wake(_reason):
        started.set()
        await release.wait()
        return DONE

    manager = _manager()
    manager.request_wake = AsyncMock(side_effect=slow_wake)
    transport = httpx.ASGITransport(app=_app())

    with patch("app.services.power.sleep.record_http_request"), \
         patch("app.services.power.sleep.get_sleep_manager", return_value=manager):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            requests = [
                asyncio.create_task(client.post("/api/files/upload")) for _ in range(5)
            ]
            await asyncio.wait_for(started.wait(), timeout=5)
            # Let the other requests reach the middleware while the wake hangs.
            for _ in range(20):
                await asyncio.sleep(0)
            pending = [r for r in requests if not r.done()]
            release.set()
            responses = await asyncio.wait_for(asyncio.gather(*requests), timeout=5)

    assert len(pending) == 5  # nobody finished before the wake did
    assert [r.status_code for r in responses] == [200] * 5
    assert manager.request_wake.await_count == 1


@pytest.mark.asyncio
async def test_next_wake_after_the_shared_one_finished_is_a_new_one():
    manager = _manager(wake=REFUSED)
    transport = httpx.ASGITransport(app=_app())

    with patch("app.services.power.sleep.record_http_request"), \
         patch("app.services.power.sleep.get_sleep_manager", return_value=manager):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/files/upload")
            await client.post("/api/files/upload")

    assert manager.request_wake.await_count == 2
