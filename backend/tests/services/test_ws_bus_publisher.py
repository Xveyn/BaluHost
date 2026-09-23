"""The standalone workers emit notifications; without this they reach no client."""

import asyncio

import pytest

from app.services import ws_bus_publisher
from app.services.ws_bus import WsEnvelope


@pytest.fixture(autouse=True)
def _restore_process_singletons():
    """These helpers mutate two process-wide singletons on purpose.

    Without restoring them, the manager keeps a RecordingBus and the event
    emitter keeps a loop that this test already closed — harmless today, a
    cross-test failure as soon as the suite runs under xdist or someone adds a
    test that relies on either.
    """
    from app.services.notifications.events import get_event_emitter
    from app.services.websocket_manager import get_websocket_manager

    manager = get_websocket_manager()
    emitter = get_event_emitter()
    saved_bus, saved_loop = manager._bus, emitter._loop
    yield
    manager._bus = saved_bus
    emitter._loop = saved_loop


class RecordingBus:
    def __init__(self) -> None:
        self.started = False
        self.deliver = "unset"
        self.published: list[WsEnvelope] = []

    async def publish(self, env):
        self.published.append(env)

    async def start(self, deliver):
        self.started = True
        self.deliver = deliver

    async def stop(self):
        pass


@pytest.mark.asyncio
async def test_starts_the_bus_publish_only(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)

    result = await ws_bus_publisher.start_publish_only_bus()

    assert result is bus
    assert bus.started is True
    assert bus.deliver is None  # nothing to deliver to in this process


@pytest.mark.asyncio
async def test_binds_the_event_loop_so_emit_sync_can_broadcast(monkeypatch):
    """emit_sync runs on worker threads and needs the loop to schedule the send."""
    from app.services.notifications.events import get_event_emitter

    bus = RecordingBus()
    monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
    get_event_emitter()._loop = None

    await ws_bus_publisher.start_publish_only_bus()

    assert get_event_emitter()._loop is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_manager_publishes_through_the_new_bus(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
    await ws_bus_publisher.start_publish_only_bus()

    from app.services.websocket_manager import get_websocket_manager

    await get_websocket_manager().broadcast_to_admins({"id": 1})

    assert bus.published[0].kind == "admins"


@pytest.mark.asyncio
async def test_failure_returns_none_and_does_not_raise(monkeypatch):
    def boom():
        raise RuntimeError("no database")

    monkeypatch.setattr(ws_bus_publisher, "build_bus", boom)

    assert await ws_bus_publisher.start_publish_only_bus() is None


class TestThreadedVariant:
    """scheduler_worker.main() is fully synchronous — it has no event loop at all."""

    def test_provides_a_running_loop_for_emit_sync(self, monkeypatch):
        from app.services.notifications.events import get_event_emitter

        bus = RecordingBus()
        monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
        get_event_emitter()._loop = None

        handle = ws_bus_publisher.start_publish_only_bus_threaded()
        try:
            assert handle is not None
            loop = get_event_emitter()._loop
            assert loop is not None
            assert loop.is_running()
            assert bus.started is True
            assert bus.deliver is None
        finally:
            handle.stop()

    def test_stop_shuts_the_loop_thread_down(self, monkeypatch):
        bus = RecordingBus()
        monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)

        handle = ws_bus_publisher.start_publish_only_bus_threaded()
        assert handle is not None
        handle.stop()

        assert not handle.thread.is_alive()

    def test_a_broadcast_from_the_sync_thread_reaches_the_bus(self, monkeypatch):
        """The whole point: emit_sync runs here, with no loop of its own."""
        bus = RecordingBus()
        monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
        handle = ws_bus_publisher.start_publish_only_bus_threaded()
        try:
            from app.services.websocket_manager import get_websocket_manager

            manager = get_websocket_manager()
            future = asyncio.run_coroutine_threadsafe(
                manager.broadcast_to_admins({"id": 42}), handle.loop
            )
            future.result(timeout=5)
        finally:
            handle.stop()

        assert bus.published[-1].payload == {"id": 42}

    def test_failure_returns_none(self, monkeypatch):
        def boom():
            raise RuntimeError("no database")

        monkeypatch.setattr(ws_bus_publisher, "build_bus", boom)

        assert ws_bus_publisher.start_publish_only_bus_threaded() is None
