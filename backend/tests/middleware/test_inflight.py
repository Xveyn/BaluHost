"""Tests für die In-Flight-Middleware (S1/#300, PR1)."""
import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.core.concurrency_probe import RequestStats
from app.middleware.inflight import InFlightMiddleware


@pytest.fixture
def stats(monkeypatch) -> RequestStats:
    """Frische Statistik, damit Tests sich nicht über das Singleton beeinflussen."""
    fresh = RequestStats()
    monkeypatch.setattr(
        "app.middleware.inflight.get_request_stats", lambda: fresh
    )
    return fresh


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()

    @application.get("/ok")
    async def ok():
        return {"ok": True}

    @application.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @application.get("/boom")
    async def boom():
        raise RuntimeError("kaputt")

    application.add_middleware(InFlightMiddleware)
    return application


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path)


async def test_counts_a_single_request(stats, app):
    await _get(app, "/ok")

    window = stats.drain()
    assert window.started == 1
    assert window.completed == 1
    assert window.in_flight_now == 0
    assert window.duration_max_ms is not None


async def test_in_flight_max_reflects_real_concurrency(stats, app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        await asyncio.gather(*(client.get("/slow") for _ in range(3)))

    window = stats.drain()
    assert window.started == 3
    assert window.in_flight_max == 3
    assert window.in_flight_now == 0


async def test_counter_is_released_when_the_handler_raises(stats, app):
    with pytest.raises(RuntimeError):
        await _get(app, "/boom")

    window = stats.drain()
    assert window.started == 1
    assert window.completed == 1
    assert window.in_flight_now == 0, "kein Leck bei Exceptions"


async def test_non_http_scopes_are_passed_through_untouched(stats):
    seen = []

    async def inner_app(scope, receive, send):
        seen.append(scope["type"])

    middleware = InFlightMiddleware(inner_app)
    await middleware({"type": "lifespan"}, None, None)

    assert seen == ["lifespan"]
    window = stats.drain()
    assert window.started == 0, "Lifespan ist kein Request"
