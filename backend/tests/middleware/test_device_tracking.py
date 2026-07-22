"""Tests for DeviceTrackingMiddleware's write debouncing (#322).

Every request carrying `X-Device-ID` used to trigger SELECT + UPDATE + COMMIT
before the handler even ran. With `mobile_sync` allowing 300 requests/min that
is 300 commits per minute per device, purely to move a `last_seen` timestamp
the UI only reads with a 5-minute "recently active" threshold.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import device_tracking
from app.middleware.device_tracking import DeviceTrackingMiddleware

DEVICE = "device-abc"


@pytest.fixture(autouse=True)
def _clear_cache():
    """The debounce cache is module state — never leak it between tests."""
    device_tracking._WRITE_CACHE.clear()
    yield
    device_tracking._WRITE_CACHE.clear()


@pytest.fixture
def writes(monkeypatch):
    """Record calls to the DB writer instead of touching a database."""
    recorded = []

    def _record(device_id, update_last_sync=False):
        recorded.append((device_id, update_last_sync))

    monkeypatch.setattr(device_tracking, "_update_device_last_seen", _record)
    return recorded


@pytest.fixture
def clock(monkeypatch):
    """Controllable monotonic clock."""

    class _Clock:
        now = 1000.0

        def advance(self, seconds):
            self.now += seconds

    c = _Clock()
    monkeypatch.setattr(device_tracking, "_monotonic", lambda: c.now)
    return c


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(DeviceTrackingMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/api/mobile/sync/items")
    async def sync_items():
        return {"ok": True}

    return TestClient(app)


def test_first_request_from_a_device_is_written(client, writes, clock):
    client.get("/ping", headers={"X-Device-ID": DEVICE})

    assert writes == [(DEVICE, False)]


def test_repeated_requests_within_the_ttl_are_debounced(client, writes, clock):
    for _ in range(50):
        clock.advance(1)
        client.get("/ping", headers={"X-Device-ID": DEVICE})

    assert len(writes) == 1, f"50 requests inside the TTL caused {len(writes)} writes"


def test_the_device_is_written_again_after_the_ttl(client, writes, clock):
    client.get("/ping", headers={"X-Device-ID": DEVICE})
    clock.advance(device_tracking._WRITE_TTL_SECONDS + 1)
    client.get("/ping", headers={"X-Device-ID": DEVICE})

    assert len(writes) == 2


def test_a_sync_request_still_refreshes_last_sync_within_the_ttl(client, writes, clock):
    """last_seen was just written, but last_sync has its own freshness."""
    client.get("/ping", headers={"X-Device-ID": DEVICE})
    clock.advance(1)
    client.get("/api/mobile/sync/items", headers={"X-Device-ID": DEVICE})

    assert writes == [(DEVICE, False), (DEVICE, True)]

    # ...but a second sync inside the TTL is debounced like everything else.
    clock.advance(1)
    client.get("/api/mobile/sync/items", headers={"X-Device-ID": DEVICE})
    assert len(writes) == 2


def test_requests_without_the_header_never_write(client, writes, clock):
    client.get("/ping")
    client.get("/api/mobile/sync/items")

    assert writes == []


def test_unknown_device_ids_cannot_grow_the_cache_without_bound(client, writes, clock):
    """The header is unauthenticated input — it must not be a memory lever."""
    for i in range(device_tracking._MAX_TRACKED_DEVICES * 2):
        client.get("/ping", headers={"X-Device-ID": f"flood-{i}"})

    assert len(device_tracking._WRITE_CACHE) <= device_tracking._MAX_TRACKED_DEVICES
