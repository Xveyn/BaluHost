"""
Sleep auto-wake middleware.

Lightweight middleware that:
1. Counts HTTP requests/minute for idle detection
2. Auto-wakes from soft sleep when non-whitelisted requests arrive
"""
import logging

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
    "/api/power/status",
    "/api/system/info",
    "/api/monitoring/",
    "/api/admin/services",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# Read-only methods that are less likely to need wake
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class SleepAutoWakeMiddleware(BaseHTTPMiddleware):
    """Auto-wake from soft sleep on non-whitelisted API requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Always count the request for idle detection
        try:
            from app.services.power.sleep import record_http_request
            record_http_request()
        except Exception:
            pass

        # Check if we need to auto-wake
        path = request.url.path
        method = request.method

        # Skip whitelisted paths
        is_whitelisted = any(path.startswith(prefix) for prefix in _WAKE_WHITELIST_PREFIXES)

        if not is_whitelisted:
            try:
                from app.services.power.sleep import get_sleep_manager
                from app.schemas.sleep import SleepState

                manager = get_sleep_manager()
                if manager and manager._current_state == SleepState.SOFT_SLEEP:
                    # Non-whitelisted request while in soft sleep -> auto-wake
                    logger.info(
                        "Auto-wake triggered by %s %s",
                        method, path,
                    )
                    await manager.exit_soft_sleep(f"auto_wake: {method} {path}")
            except Exception as e:
                logger.debug("Auto-wake check failed: %s", e)

        return await call_next(request)
