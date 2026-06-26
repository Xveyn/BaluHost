"""SandboxSupervisor: spawn and supervise one external plugin's worker
subprocess, and proxy requests to it over an RpcChannel.

Phase 2b uses a plain subprocess spawn (the default spawn hook). The
low-privilege OS user + network-namespace isolation is a pluggable spawn hook
deferred to Phase 5 — it slots in at the same boundary without touching this
class. Real plugin loading + capability dispatch (replacing the worker's
echo/health handler) is Phase 3.
"""
import asyncio
import itertools
import logging
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from app.plugins.sandbox.capabilities import CapabilityContext, CapabilityRouter
from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import WorkerListener

logger = logging.getLogger(__name__)

WORKER_MODULE = "app.plugins.sandbox.worker"

# Given argv + working dir, start and return a subprocess. Phase 5 replaces the
# default with a hardened (low-priv user + netns) implementation.
SpawnHook = Callable[[List[str], str], Awaitable[asyncio.subprocess.Process]]


async def _default_spawn(argv: List[str], cwd: str) -> asyncio.subprocess.Process:
    """Plain subprocess spawn (dev/baseline)."""
    return await asyncio.create_subprocess_exec(*argv, cwd=cwd)


class SupervisorError(Exception):
    """Raised when the worker cannot be started, handshaked, or reached."""


class SandboxSupervisor:
    """Owns one external plugin's worker process and the RPC channel to it."""

    def __init__(
        self,
        plugin_name: str,
        plugin_dir: "str | Path",
        *,
        spawn_hook: SpawnHook = _default_spawn,
        handshake_timeout: float = 10.0,
        graceful_timeout: float = 5.0,
        max_restarts: int = 3,
        restart_window: float = 60.0,
        capability_router: Optional[CapabilityRouter] = None,
    ) -> None:
        self.plugin_name = plugin_name
        self._plugin_dir = Path(plugin_dir)
        self._spawn_hook = spawn_hook
        self._handshake_timeout = handshake_timeout
        self._graceful_timeout = graceful_timeout
        self._max_restarts = max_restarts
        self._restart_window = restart_window
        self._capability_router = capability_router

        self._process: Optional[asyncio.subprocess.Process] = None
        self._channel: Optional[RpcChannel] = None
        self._supervise_task: Optional[asyncio.Task] = None
        self._restart_times: List[float] = []
        self._running = False
        self._stopping = False
        self._disabled = False
        self._inflight: dict[int, CapabilityContext] = {}
        self._request_ids = itertools.count(1)

    @property
    def disabled(self) -> bool:
        return self._disabled

    async def start(self) -> None:
        """Spawn the worker, connect, health-handshake, begin supervision."""
        await self._spawn_and_connect()
        self._running = True
        self._stopping = False
        self._supervise_task = asyncio.create_task(self._supervise())

    async def dispatch(
        self, method: str, path: str, body: bytes, context: dict
    ) -> dict:
        """Proxy one HTTP request into the worker and return its response body."""
        if self._disabled:
            raise SupervisorError(f"plugin {self.plugin_name} is disabled")
        channel = self._channel
        if channel is None:
            raise SupervisorError(f"plugin {self.plugin_name} is not running")
        request_id = next(self._request_ids)
        self._inflight[request_id] = CapabilityContext(
            user_id=context.get("user_id", 0),
            username=context.get("username", ""),
            role=context.get("role", "user"),
        )
        try:
            resp = await channel.call(
                MsgType.HTTP_REQUEST,
                {
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "body": body,
                    "context": context,
                },
            )
        finally:
            self._inflight.pop(request_id, None)
        return resp.body

    async def health(self) -> bool:
        """Return True iff the worker answers a health ping."""
        channel = self._channel
        if channel is None or self._disabled:
            return False
        try:
            resp = await channel.call(
                MsgType.LIFECYCLE, {"action": "health"}, timeout=self._handshake_timeout
            )
        except (asyncio.TimeoutError, ConnectionError):
            return False
        return resp.type == MsgType.LIFECYCLE_RESULT and resp.body.get("status") == "ok"

    async def stop(self) -> None:
        """Stop supervision, ask the worker to shut down, then ensure it exits."""
        self._stopping = True
        self._running = False
        if self._supervise_task is not None:
            self._supervise_task.cancel()
            try:
                await self._supervise_task
            except asyncio.CancelledError:
                pass
            self._supervise_task = None
        await self._graceful_channel_close()
        await self._await_exit_or_kill()
        self._process = None

    # --- internals -------------------------------------------------------

    async def _handle_worker_request(self, msg: Message) -> Message:
        """Route inbound requests from the worker to the appropriate handler."""
        if msg.type == MsgType.CAP_CALL:
            return await self._handle_cap_call(msg)
        return Message(id=msg.id, type=MsgType.ERROR, body={"error": "unsupported"})

    async def _handle_cap_call(self, msg: Message) -> Message:
        """Dispatch a cap_call using the host-resolved context from _inflight.

        The user_id is always taken from self._inflight (host-resolved when the
        http_request was dispatched) — never from anything the worker sends.
        Unknown or stale request_id returns {"error": "no_context"} so a plugin
        can never address a foreign user's data.
        """
        if self._capability_router is None:
            return Message(id=msg.id, type=MsgType.CAP_RESULT, body={"error": "unavailable"})
        request_id = msg.body.get("request_id")
        context = self._inflight.get(request_id) if isinstance(request_id, int) else None
        if context is None:
            return Message(id=msg.id, type=MsgType.CAP_RESULT, body={"error": "no_context"})
        result = await self._capability_router.dispatch(
            msg.body.get("capability", ""), msg.body.get("args") or {}, context
        )
        return Message(id=msg.id, type=MsgType.CAP_RESULT, body=result)

    async def _spawn_and_connect(self) -> None:
        listener = WorkerListener(self._plugin_dir)
        address = await listener.start()
        try:
            argv = [sys.executable, "-m", WORKER_MODULE, "--connect", address]
            self._process = await self._spawn_hook(argv, str(self._plugin_dir))
            try:
                reader, writer = await listener.accept(timeout=self._handshake_timeout)
            except asyncio.TimeoutError as exc:
                await self._hard_kill()
                raise SupervisorError(
                    f"worker {self.plugin_name} did not connect back in time"
                ) from exc
        finally:
            await listener.close()

        self._channel = RpcChannel(reader, writer, request_handler=self._handle_worker_request)
        self._channel.start()

        try:
            resp = await self._channel.call(
                MsgType.LIFECYCLE, {"action": "health"}, timeout=self._handshake_timeout
            )
        except (asyncio.TimeoutError, ConnectionError) as exc:
            await self._hard_kill()
            raise SupervisorError(
                f"worker {self.plugin_name} health handshake failed"
            ) from exc
        if resp.type != MsgType.LIFECYCLE_RESULT or resp.body.get("status") != "ok":
            await self._hard_kill()
            raise SupervisorError(
                f"worker {self.plugin_name} reported unhealthy: {resp.body}"
            )

    async def _supervise(self) -> None:
        while self._running:
            process = self._process
            if process is None:
                return
            await process.wait()
            if self._stopping or not self._running:
                return
            logger.warning(
                "plugin %s worker exited unexpectedly (code %s)",
                self.plugin_name,
                process.returncode,
            )
            await self._close_channel()
            if not self._register_restart():
                self._disable("exceeded restart budget")
                return
            try:
                await self._spawn_and_connect()
            except Exception:
                logger.exception("plugin %s restart failed", self.plugin_name)
                self._disable("restart failed")
                return

    def _register_restart(self) -> bool:
        """Record a restart; return False if the budget is now exceeded."""
        now = time.monotonic()
        self._restart_times = [
            t for t in self._restart_times if now - t < self._restart_window
        ]
        self._restart_times.append(now)
        return len(self._restart_times) <= self._max_restarts

    def _disable(self, reason: str) -> None:
        self._disabled = True
        self._running = False
        logger.error("plugin %s auto-disabled: %s", self.plugin_name, reason)

    async def _graceful_channel_close(self) -> None:
        channel = self._channel
        if channel is None:
            return
        try:
            await channel.call(
                MsgType.LIFECYCLE, {"action": "shutdown"}, timeout=self._graceful_timeout
            )
        except (asyncio.TimeoutError, ConnectionError):
            pass
        await self._close_channel()

    async def _close_channel(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None

    async def _await_exit_or_kill(self) -> None:
        process = self._process
        if process is None:
            return
        if await self._wait_exit(self._graceful_timeout):
            return
        self._signal(process.terminate)
        if await self._wait_exit(self._graceful_timeout):
            return
        self._signal(process.kill)
        await process.wait()

    async def _wait_exit(self, timeout: float) -> bool:
        process = self._process
        if process is None:
            return True
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    @staticmethod
    def _signal(fn: Callable[[], None]) -> None:
        try:
            fn()
        except ProcessLookupError:
            pass

    async def _hard_kill(self) -> None:
        await self._close_channel()
        process = self._process
        if process is not None:
            self._signal(process.kill)
            await process.wait()
        self._process = None
