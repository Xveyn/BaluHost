"""The ws bus must start in EVERY worker — that is the whole point of #685."""

import pytest

from app.core import lifespan as lifespan_module
from app.services.websocket_manager import WebSocketManager


class RecordingBus:
    def __init__(self) -> None:
        self.started_with = "not started"
        self.stopped = False

    async def publish(self, env):
        pass

    async def start(self, deliver):
        self.started_with = deliver

    async def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_bus_starts_bound_to_deliver_local(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    manager = WebSocketManager()

    await lifespan_module._start_ws_bus(manager)

    assert bus.started_with == manager.deliver_local
    assert manager._bus is bus


@pytest.mark.asyncio
async def test_bus_start_is_not_gated_on_primary_worker(monkeypatch):
    """A secondary worker holds connections too; gating this would keep #685 open."""
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", False)

    await lifespan_module._start_ws_bus(WebSocketManager())

    assert bus.started_with != "not started"


@pytest.mark.asyncio
async def test_stop_stops_the_bus(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    await lifespan_module._start_ws_bus(WebSocketManager())

    await lifespan_module._stop_ws_bus()

    assert bus.stopped is True


@pytest.mark.asyncio
async def test_start_failure_does_not_break_startup(monkeypatch):
    class ExplodingBus(RecordingBus):
        async def start(self, deliver):
            raise RuntimeError("no database")

    monkeypatch.setattr(lifespan_module, "build_bus", lambda: ExplodingBus())
    await lifespan_module._start_ws_bus(WebSocketManager())  # must not raise
