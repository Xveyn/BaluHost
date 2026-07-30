"""Tests für die In-Flight-Middleware (S1/#300, PR1)."""
import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

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

    @application.get("/stream")
    async def stream():
        """Steht für `/api/admin/backend-logs/stream`: Response-Header sofort,
        Body über die gesamte Sitzung."""

        async def body():
            for _ in range(3):
                await asyncio.sleep(0.06)
                yield b"x"

        return StreamingResponse(body(), media_type="text/plain")

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
    assert window.duration_max_ms is not None, (
        "ohne Response-Start muss auf die Gesamtdauer zurückgefallen werden, "
        "sonst geht die Messung verloren"
    )


async def test_duration_stops_at_the_response_start_not_at_the_stream_end(stats, app):
    """C2: gemessen wird Bedienzeit, nicht Verbindungslebensdauer.

    Ein SSE-Stream, den ein Admin zehn Minuten offen lässt, würde sonst EINEN
    Messwert von 600 000 ms liefern — und in einem ruhigen Fenster ist genau
    der das p95. Die Auslegung des Connection-Pools in PR2 liest diese Zahl.
    """
    started = time.perf_counter()
    response = await _get(app, "/stream")
    total_ms = (time.perf_counter() - started) * 1000.0

    assert response.status_code == 200
    assert total_ms > 150, "Der Stream lief nicht wirklich lange genug"

    window = stats.drain()
    assert window.completed == 1
    assert window.duration_max_ms is not None
    assert window.duration_max_ms < 100, (
        f"Streaming-Phase floss in die Dauer ein: {window.duration_max_ms} ms "
        f"bei {total_ms} ms Gesamtdauer"
    )


async def test_in_flight_still_spans_the_whole_streaming_request(stats, app):
    """Die Gegenprobe: die Dauer schrumpft, der In-Flight-Zähler nicht — ein
    laufender Stream IST in flight, und `req_in_flight_*` soll das sagen."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        task = asyncio.create_task(client.get("/stream"))
        await asyncio.sleep(0.08)  # mitten im Body-Transfer
        during = stats.drain()
        await task

    assert during.in_flight_now == 1, (
        "Stream muss während des Transfers als in flight gelten"
    )
    assert during.completed == 0, "abgeschlossen ist er da noch nicht"
    assert stats.drain().completed == 1
    assert stats.drain().in_flight_now == 0


async def test_non_http_scopes_are_passed_through_untouched(stats):
    seen = []

    async def inner_app(scope, receive, send):
        seen.append(scope["type"])

    middleware = InFlightMiddleware(inner_app)
    await middleware({"type": "lifespan"}, None, None)

    assert seen == ["lifespan"]
    window = stats.drain()
    assert window.started == 0, "Lifespan ist kein Request"
