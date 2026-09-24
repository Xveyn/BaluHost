"""Bus wiring for the standalone worker processes.

monitoring_worker and scheduler_worker emit notifications (temperature and
disk-space thresholds, scheduler failures) but hold no WebSocket connections.
Two things were missing for those to reach a client at all:

- Nobody called EventEmitter.set_event_loop() outside lifespan, so
  _broadcast_sync() returned early with "No app loop bound" and the whole
  synchronous path was invisible.
- Even with the loop bound, a broadcast would only have reached this process's
  own sockets, of which there are none.

So these processes get the bus in publish-only mode: no listener, no extra
connection, just a way out (#685).

Two limits worth knowing before debugging this:

- In dev (SQLite) build_bus() returns a LocalWsBus, and start(None) leaves it
  without a deliver callback — publish() is a no-op there. Unavoidable: these
  processes hold no sockets, and in dev there is only one process anyway.
- NotificationService._websocket_manager stays None here, so its async
  _send_in_app/_broadcast_to_recipients paths do nothing. That does not matter:
  both workers only ever use emit_*_sync, and EventEmitter._broadcast_sync
  reaches for get_websocket_manager() directly.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Optional

from app.services.ws_bus import WsBus, build_bus

logger = logging.getLogger(__name__)


async def start_publish_only_bus() -> Optional[WsBus]:
    """Wire this process so emit_sync() broadcasts reach the other processes.

    Returns:
        The bus, or None when it could not be started — in which case the
        process keeps working exactly as it did before, minus the broadcasts.
    """
    try:
        from app.services.notifications.events import get_event_emitter
        from app.services.websocket_manager import get_websocket_manager

        bus = build_bus()
        # deliver=None: there is nowhere to deliver in this process, so there is
        # no reason to hold a listener connection either.
        await bus.start(None)
        get_websocket_manager().set_bus(bus)
        get_event_emitter().set_event_loop(asyncio.get_running_loop())
        logger.info("WebSocket bus started (publish-only)")
        return bus
    except Exception as exc:
        logger.warning("WebSocket bus could not start (publish-only): %s", exc)
        return None


@dataclass
class ThreadedBus:
    """A bus plus the background loop it lives on, for processes without one."""

    bus: WsBus
    loop: asyncio.AbstractEventLoop
    thread: threading.Thread

    def stop(self) -> None:
        """Stop the bus, then the loop, then join and close. Safe to call twice.

        Order matters: stopping the loop first would cancel an in-flight publish
        — including the worker's own shutdown notification — and would leave a
        listener connection open if this ever runs with one.
        """
        if not self.thread.is_alive():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.bus.stop(), self.loop).result(timeout=5)
        except Exception as exc:
            logger.warning("WebSocket bus shutdown failed: %s", exc)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        try:
            self.loop.close()
        except Exception:
            pass


def start_publish_only_bus_threaded() -> Optional[ThreadedBus]:
    """Same as start_publish_only_bus(), for a process with no event loop.

    scheduler_worker.main() is synchronous from top to bottom — worker.run_loop()
    blocks the main thread — so there is no loop for
    EventEmitter._broadcast_sync() to schedule into, and it returned early with
    "No app loop bound". Rather than build a second, synchronous broadcast path
    through events.py, this gives the process the one thing it lacks: a loop,
    running in a daemon thread. run_coroutine_threadsafe() then works exactly as
    it does in the web workers.

    Returns:
        A handle to stop the loop with, or None when the bus could not start.
    """
    try:
        from app.services.notifications.events import get_event_emitter
        from app.services.websocket_manager import get_websocket_manager

        bus = build_bus()
        loop = asyncio.new_event_loop()
        started = threading.Event()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.call_soon(started.set)
            loop.run_forever()

        thread = threading.Thread(target=_run, name="ws_bus_loop", daemon=True)
        thread.start()
        if not started.wait(timeout=5):
            raise RuntimeError("bus loop thread did not start")

        asyncio.run_coroutine_threadsafe(bus.start(None), loop).result(timeout=5)
        get_websocket_manager().set_bus(bus)
        get_event_emitter().set_event_loop(loop)
        logger.info("WebSocket bus started (publish-only, background loop)")
        return ThreadedBus(bus=bus, loop=loop, thread=thread)
    except Exception as exc:
        logger.warning("WebSocket bus could not start (threaded): %s", exc)
        return None
