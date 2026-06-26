"""Full-duplex RPC channel over a paired StreamReader/StreamWriter.

Both ends are symmetric: each can issue ``call()`` (outbound request → awaited
response) and each may serve inbound requests via a ``request_handler``. Inbound
requests are dispatched in their own task, so a handler may itself issue a
``call()`` back to the peer while the original request is still in flight
(reentrancy) — required for an http_request handler that needs a cap_call.
"""
import asyncio
import itertools
import logging
from typing import Awaitable, Callable, Optional

from app.plugins.sandbox.protocol import (
    FrameError,
    Message,
    MsgType,
    REQUEST_TYPES,
    RESPONSE_TYPES,
    read_frame,
    write_frame,
)

logger = logging.getLogger(__name__)

RequestHandler = Callable[[Message], Awaitable[Message]]


class RpcChannel:
    """A symmetric, reentrant RPC channel."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        request_handler: Optional[RequestHandler] = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._request_handler = request_handler
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._dispatch_tasks: set[asyncio.Task] = set()
        self._closed = False

    def start(self) -> None:
        """Start the read loop (idempotent)."""
        if self._read_task is None:
            self._read_task = asyncio.create_task(self._read_loop())

    async def call(
        self, type: str, body: dict, *, timeout: Optional[float] = None
    ) -> Message:
        """Send a request and await the correlated response."""
        if self._closed:
            raise ConnectionError("channel closed")
        msg_id = next(self._ids)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        try:
            await write_frame(self._writer, Message(id=msg_id, type=type, body=body))
            if timeout is not None:
                return await asyncio.wait_for(fut, timeout)
            return await fut
        finally:
            self._pending.pop(msg_id, None)

    async def _read_loop(self) -> None:
        try:
            while True:
                try:
                    msg = await read_frame(self._reader)
                except (FrameError, OSError) as exc:
                    logger.warning("rpc: dropping connection: %s", exc)
                    break
                if msg is None:
                    break  # clean EOF
                if msg.type in RESPONSE_TYPES:
                    self._resolve(msg)
                elif msg.type in REQUEST_TYPES:
                    task = asyncio.create_task(self._dispatch(msg))
                    self._dispatch_tasks.add(task)
                    task.add_done_callback(self._dispatch_tasks.discard)
                else:
                    logger.warning("rpc: unknown message type %r", msg.type)
        finally:
            self._closed = True
            self._fail_all(ConnectionError("channel closed"))

    def _resolve(self, msg: Message) -> None:
        fut = self._pending.get(msg.id)
        if fut is None or fut.done():
            logger.warning("rpc: response for unknown/settled id %s", msg.id)
            return
        fut.set_result(msg)

    async def _dispatch(self, msg: Message) -> None:
        if self._request_handler is None:
            await self._safe_write(
                Message(id=msg.id, type=MsgType.ERROR, body={"error": "no_handler"})
            )
            return
        try:
            response = await self._request_handler(msg)
        except Exception:
            logger.exception("rpc: request handler failed")
            await self._safe_write(
                Message(id=msg.id, type=MsgType.ERROR, body={"error": "handler_failed"})
            )
            return
        response.id = msg.id  # always correlate to the request id
        await self._safe_write(response)

    async def _safe_write(self, msg: Message) -> None:
        try:
            await write_frame(self._writer, msg)
        except Exception:
            logger.exception("rpc: failed to write frame")

    def _fail_all(self, exc: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()

    async def close(self) -> None:
        """Cancel the read loop + in-flight dispatch tasks, close the writer,
        fail pending calls."""
        self._closed = True
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass
        # Cancel any in-flight request-dispatch tasks (e.g. a slow handler) so
        # they don't linger past event-loop teardown.
        for task in list(self._dispatch_tasks):
            task.cancel()
        if self._dispatch_tasks:
            await asyncio.gather(*self._dispatch_tasks, return_exceptions=True)
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass
        self._fail_all(ConnectionError("channel closed"))
