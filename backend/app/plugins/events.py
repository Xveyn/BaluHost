"""Async Event Manager for loose-coupled plugin communication.

Provides an async-first event system that complements the Pluggy hooks.
Events are non-blocking and support multiple subscribers.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime


logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Represents a system event."""

    name: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: Optional[str] = None  # Plugin name or "system"


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventManager:
    """Async event manager for plugin communication.

    Supports:
    - Async event handlers
    - Multiple subscribers per event
    - Event filtering
    - Non-blocking event dispatch
    """

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._handler_sources: Dict[str, Set[str]] = defaultdict(set)
        self._running = False
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._processor_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the event processor."""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_events())
        logger.info("Event manager started")

    async def stop(self) -> None:
        """Stop the event processor gracefully."""
        if not self._running:
            return
        self._running = False
        # Add sentinel to unblock the queue
        await self._queue.put(Event(name="__shutdown__", data={}))
        if self._processor_task:
            try:
                await asyncio.wait_for(self._processor_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Event processor shutdown timed out")
                self._processor_task.cancel()
        logger.info("Event manager stopped")

    async def _process_events(self) -> None:
        """Process events from the queue."""
        while self._running:
            try:
                event = await self._queue.get()
                if event.name == "__shutdown__":
                    break
                await self._dispatch(event)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error processing event: {e}")

    async def _dispatch(self, event: Event) -> None:
        """Dispatch an event to all registered handlers."""
        handlers = self._handlers.get(event.name, [])
        # Also dispatch to wildcard handlers
        handlers = handlers + self._handlers.get("*", [])

        if not handlers:
            logger.debug(f"No handlers for event: {event.name}")
            return

        logger.debug(f"Dispatching event {event.name} to {len(handlers)} handlers")

        # Run all handlers concurrently
        tasks = [
            asyncio.create_task(self._safe_call(handler, event))
            for handler in handlers
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        """Safely call an event handler, catching exceptions."""
        try:
            await handler(event)
        except Exception as e:
            logger.exception(
                f"Error in event handler for {event.name}: {e}"
            )

    def subscribe(
        self,
        event_name: str,
        handler: EventHandler,
        source: Optional[str] = None,
    ) -> None:
        """Subscribe to an event.

        Args:
            event_name: Name of the event to subscribe to, or "*" for all events
            handler: Async function to call when event occurs
            source: Optional identifier of the subscriber (e.g., plugin name)
        """
        self._handlers[event_name].append(handler)
        if source:
            self._handler_sources[event_name].add(source)
        logger.debug(f"Subscribed to event: {event_name} (source: {source})")

    def unsubscribe(
        self,
        event_name: str,
        handler: EventHandler,
    ) -> bool:
        """Unsubscribe from an event.

        Args:
            event_name: Name of the event
            handler: The handler function to remove

        Returns:
            True if handler was found and removed
        """
        handlers = self._handlers.get(event_name, [])
        try:
            handlers.remove(handler)
            logger.debug(f"Unsubscribed from event: {event_name}")
            return True
        except ValueError:
            return False

    def unsubscribe_all(self, source: str) -> int:
        """Unsubscribe all handlers registered by a source.

        Args:
            source: Source identifier (e.g., plugin name)

        Returns:
            Number of handlers removed
        """
        count = 0
        for event_name in list(self._handlers.keys()):
            if source in self._handler_sources.get(event_name, set()):
                # Note: This removes all handlers for this event from this source
                # For more granular control, handlers should be tracked individually
                self._handler_sources[event_name].discard(source)
                count += 1
        return count

    async def emit(
        self,
        event_name: str,
        data: Dict[str, Any],
        source: Optional[str] = None,
    ) -> None:
        """Emit an event.

        The event is queued for async processing.

        Args:
            event_name: Name of the event
            data: Event data dictionary
            source: Optional source identifier
        """
        event = Event(
            name=event_name,
            data=data,
            source=source,
        )
        await self._queue.put(event)
        logger.debug(f"Emitted event: {event_name}")

    def emit_sync(
        self,
        event_name: str,
        data: Dict[str, Any],
        source: Optional[str] = None,
    ) -> None:
        """Emit an event from synchronous code.

        Creates a new event loop task to emit the event.

        Args:
            event_name: Name of the event
            data: Event data dictionary
            source: Optional source identifier
        """
        try:
            loop = asyncio.get_running_loop()
            event = Event(
                name=event_name,
                data=data,
                source=source,
            )
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._queue.put(event))
            )
        except RuntimeError:
            logger.warning(
                f"Cannot emit event {event_name}: no running event loop"
            )

    def get_subscribers(self, event_name: str) -> int:
        """Get number of subscribers for an event.

        Args:
            event_name: Name of the event

        Returns:
            Number of registered handlers
        """
        return len(self._handlers.get(event_name, []))

    def get_all_event_names(self) -> List[str]:
        """Get list of all event names with subscribers.

        Returns:
            List of event names
        """
        return list(self._handlers.keys())


# Global event manager instance
_event_manager: Optional[EventManager] = None


def get_event_manager() -> EventManager:
    """Get the global event manager instance.

    Returns:
        The singleton EventManager instance
    """
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
    return _event_manager


async def start_event_manager() -> None:
    """Start the global event manager."""
    manager = get_event_manager()
    await manager.start()


async def stop_event_manager() -> None:
    """Stop the global event manager."""
    global _event_manager
    if _event_manager:
        await _event_manager.stop()
        _event_manager = None
