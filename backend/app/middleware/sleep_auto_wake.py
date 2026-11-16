"""
Sleep auto-wake middleware.

Lightweight middleware that:
1. Counts HTTP requests/minute for idle detection
2. Auto-wakes from soft sleep when non-whitelisted requests arrive

The decision uses the state the primary published (`effective_state()`), and
the wake goes through `request_wake()`, which a follower forwards to the
primary (#823). Every worker can therefore wake the box.
"""
import asyncio
import logging
import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Whitelisted paths that do NOT trigger auto-wake during soft sleep.
# These endpoints are safe to call without waking the system.
_WAKE_WHITELIST_PREFIXES = (
    "/api/system/sleep/status",
    "/api/system/sleep/config",
    "/api/system/sleep/history",
    "/api/system/sleep/capabilities",
    "/api/system/sleep/presence",
    "/api/power/status",
    "/api/system/info",
    "/api/monitoring/",
    "/api/admin/services",
    "/api/sync/preflight",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# The presence heartbeat must not count toward the HTTP-RPM idle metric —
# otherwise an open tab would indirectly block soft sleep, which stays
# allowed by design (issue #214: presence only blocks true suspend).
_RPM_EXCLUDED_PATHS = ("/api/system/sleep/presence",)

# Read-only methods that are less likely to need wake
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# After a wake that could not be handed to the primary (dead primary, queue
# down), this process makes no further auto-wake attempt for this long:
# otherwise every request would wait for the queue timeout first.
_AUTO_WAKE_BACKOFF_S = 10.0
_monotonic = time.monotonic
_backoff_until: float = 0.0

# The auto-wake in flight in this process, with the loop it runs on. Requests
# arriving meanwhile await it instead of submitting a wake of their own.
_inflight_wake: Optional[tuple[asyncio.AbstractEventLoop, "asyncio.Task"]] = None


def _reset_auto_wake_state() -> None:
    """Forget back-off and in-flight wake (tests)."""
    global _backoff_until, _inflight_wake
    _backoff_until = 0.0
    _inflight_wake = None


async def _run_wake(manager, reason: str) -> None:
    global _backoff_until
    result = await manager.request_wake(reason)
    if result.unavailable:
        from app.schemas.sleep import SleepState

        if manager.effective_state()[0] != SleepState.SOFT_SLEEP:
            # Another worker's wake got there first: ours waited behind it and
            # was never picked up. The primary is fine — nothing to back off
            # from.
            logger.debug("Auto-wake not needed any more (%s)", result.detail)
            return
        _backoff_until = _monotonic() + _AUTO_WAKE_BACKOFF_S
        logger.warning(
            "Auto-wake could not reach the primary (%s); no auto-wake from this "
            "process for %.0fs", result.detail, _AUTO_WAKE_BACKOFF_S,
        )


def _retrieve_exception(task: "asyncio.Task") -> None:
    # Every waiter may have been cancelled; don't leave an unretrieved error.
    if not task.cancelled():
        task.exception()


async def _auto_wake(manager, method: str, path: str) -> None:
    """Wake the box, sharing a wake already in flight in this process."""
    global _inflight_wake
    loop = asyncio.get_running_loop()
    current = _inflight_wake
    if current is not None and current[0] is loop and not current[1].done():
        task = current[1]
    else:
        logger.info("Auto-wake triggered by %s %s", method, path)
        task = loop.create_task(_run_wake(manager, f"auto_wake: {method} {path}"))
        task.add_done_callback(_retrieve_exception)
        _inflight_wake = (loop, task)
    # Shielded: a client that disconnects must not cancel the wake the other
    # waiting requests share.
    await asyncio.shield(task)


class SleepAutoWakeMiddleware(BaseHTTPMiddleware):
    """Auto-wake from soft sleep on non-whitelisted API requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Count the request for idle detection (except excluded paths)
        if path not in _RPM_EXCLUDED_PATHS:
            try:
                from app.services.power.sleep import record_http_request
                record_http_request()
            except Exception:
                pass

        # Check if we need to auto-wake
        method = request.method

        # Skip whitelisted paths
        is_whitelisted = any(path.startswith(prefix) for prefix in _WAKE_WHITELIST_PREFIXES)

        if not is_whitelisted and _monotonic() >= _backoff_until:
            try:
                from app.services.power.sleep import get_sleep_manager
                from app.schemas.sleep import SleepState

                manager = get_sleep_manager()
                # The primary's state, wherever this request landed: only the
                # primary runs the state machine, and request_wake() hands the
                # wake to it from a follower (#823).
                if manager and manager.effective_state()[0] == SleepState.SOFT_SLEEP:
                    # Check X-Sync-Trigger header for sync paths
                    sync_trigger = request.headers.get("X-Sync-Trigger", "").lower()
                    if sync_trigger in ("auto", "scheduled"):
                        # Automatic sync during sleep — do NOT wake, let guard return 503
                        logger.debug(
                            "Skipping auto-wake for automatic sync: %s %s (trigger=%s)",
                            method, path, sync_trigger,
                        )
                    else:
                        # Non-whitelisted request while in soft sleep -> auto-wake
                        await _auto_wake(manager, method, path)
            except Exception as e:
                logger.debug("Auto-wake check failed: %s", e)

        return await call_next(request)
