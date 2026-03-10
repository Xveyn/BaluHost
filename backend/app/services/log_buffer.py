"""In-memory ring buffer for backend application logs with SSE subscriber support."""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Regex to redact sensitive values in log messages
_SENSITIVE_PATTERN = re.compile(
    r'(password|passwd|secret|token|api_key|private_key|authorization)'
    r'\s*[=:]\s*\S+',
    re.IGNORECASE,
)


def _redact(message: str) -> str:
    """Replace sensitive key=value patterns with redacted placeholders."""
    return _SENSITIVE_PATTERN.sub(r'\1=***REDACTED***', message)


class LogBufferHandler(logging.Handler):
    """
    Logging handler that stores entries in a ring buffer and notifies SSE subscribers.

    Thread-safe via the built-in Handler lock.  Subscriber queues are asyncio-based,
    so ``emit()`` uses ``loop.call_soon_threadsafe`` to bridge from the logging thread
    to the event loop.
    """

    def __init__(self, maxlen: int = 1000) -> None:
        super().__init__()
        self._buffer: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self._counter: int = 0
        self._subscribers: set[asyncio.Queue] = set()
        self._lock_sub = threading.Lock()  # protects _subscribers
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the asyncio event loop for thread→async bridging."""
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        """Process a log record: store in buffer and fan out to subscribers."""
        try:
            self._counter += 1
            entry = self._format_entry(record)

            self._buffer.append(entry)

            # Fan out to SSE subscribers
            with self._lock_sub:
                dead: list[asyncio.Queue] = []
                for queue in self._subscribers:
                    try:
                        if self._loop and self._loop.is_running():
                            self._loop.call_soon_threadsafe(queue.put_nowait, entry)
                        else:
                            queue.put_nowait(entry)
                    except asyncio.QueueFull:
                        pass  # Drop log for slow consumers
                    except Exception:
                        dead.append(queue)
                for q in dead:
                    self._subscribers.discard(q)
        except Exception:
            self.handleError(record)

    def _format_entry(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Convert a LogRecord to a serializable dictionary."""
        exc_info: Optional[str] = None
        if record.exc_info and record.exc_info[1] is not None:
            exc_info = self.format(record) if self.formatter else logging.Formatter().formatException(record.exc_info)
            # Only keep the traceback part
            msg_line = _redact(record.getMessage())
            if exc_info.startswith(msg_line):
                exc_info = exc_info[len(msg_line):].strip()

        return {
            "id": self._counter,
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger_name": record.name,
            "message": _redact(record.getMessage()),
            "exc_info": exc_info,
        }

    # -- Subscriber management --

    def subscribe(self) -> asyncio.Queue:
        """Create and register a new subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        with self._lock_sub:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue."""
        with self._lock_sub:
            self._subscribers.discard(queue)

    # -- Query API --

    def get_logs(
        self,
        since_id: int = 0,
        level: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Return buffered log entries matching the given filters.

        Args:
            since_id: Only return entries with id > since_id.
            level: Minimum log level filter (DEBUG/INFO/WARNING/ERROR/CRITICAL).
            search: Case-insensitive substring search in message and logger_name.
            limit: Maximum number of entries to return.
        """
        level_num = getattr(logging, level.upper(), 0) if level else 0
        results: List[Dict[str, Any]] = []

        for entry in self._buffer:
            if entry["id"] <= since_id:
                continue
            if level_num and getattr(logging, entry["level"], 0) < level_num:
                continue
            if search:
                needle = search.lower()
                if needle not in entry["message"].lower() and needle not in entry["logger_name"].lower():
                    continue
            results.append(entry)
            if len(results) >= limit:
                break

        return results

    def get_latest_id(self) -> int:
        """Return the id of the most recent buffered entry, or 0 if empty."""
        if self._buffer:
            return self._buffer[-1]["id"]
        return 0

    def get_total_buffered(self) -> int:
        """Return the number of entries currently in the buffer."""
        return len(self._buffer)

    def clear(self) -> None:
        """Clear the buffer and reset the counter."""
        self._buffer.clear()
        self._counter = 0


# -- Global singleton --

_handler: Optional[LogBufferHandler] = None


def get_log_buffer_handler() -> LogBufferHandler:
    """Get or create the global LogBufferHandler singleton."""
    global _handler
    if _handler is None:
        _handler = LogBufferHandler(maxlen=1000)
    return _handler
