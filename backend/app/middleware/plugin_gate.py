"""Middleware to enforce plugin enabled-status and permissions at runtime.

Validates every request to ``/api/plugins/{name}/...`` against the database
(the only shared state across Uvicorn workers) with a short TTL cache so
that disabling a plugin on one worker takes effect on all workers within
a few seconds.

Management routes (toggle, config, details, ui assets) are excluded so
admins can still manage plugins that are currently disabled.
"""

import asyncio
import logging
import time
from typing import Dict, List, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# TTL-based in-memory cache: {plugin_name: (is_enabled, granted_perms, timestamp)}
_plugin_cache: Dict[str, Tuple[bool, List[str], float]] = {}
CACHE_TTL_SECONDS = 5.0

# Path suffixes for management routes that should NOT be gated.
# These are the admin endpoints defined in api/routes/plugins.py.
_MANAGEMENT_SUFFIXES = ("/toggle", "/config")
_MANAGEMENT_PREFIXES = ("/ui/",)


def _is_management_route(sub_path: str) -> bool:
    """Return True if *sub_path* (the part after ``/api/plugins/{name}``)
    is a management route that must remain accessible regardless of
    plugin enabled-state."""
    if not sub_path or sub_path == "/":
        # Exact match = plugin details (GET) or uninstall (DELETE)
        return True
    for suffix in _MANAGEMENT_SUFFIXES:
        if sub_path == suffix:
            return True
    for prefix in _MANAGEMENT_PREFIXES:
        if sub_path.startswith(prefix):
            return True
    return False


def _fetch_plugin_status(name: str) -> Tuple[bool, List[str]]:
    """Synchronous DB lookup -- designed to run in a worker thread via
    ``asyncio.to_thread()``.

    Returns ``(is_enabled, granted_permissions)``."""
    from app.core.database import SessionLocal
    from app.models.plugin import InstalledPlugin

    db = SessionLocal()
    try:
        record = (
            db.query(InstalledPlugin)
            .filter(InstalledPlugin.name == name)
            .first()
        )
        if record and record.is_enabled:
            return (True, record.granted_permissions or [])
        return (False, [])
    finally:
        db.close()


def invalidate_plugin_cache(name: str) -> None:
    """Drop the cached entry for *name* so the next request triggers a
    fresh DB lookup.  Call this from the local worker after toggling a
    plugin."""
    _plugin_cache.pop(name, None)


class PluginGateMiddleware(BaseHTTPMiddleware):
    """Block requests to disabled plugin routes with a 403 response.

    Only intercepts paths matching ``/api/plugins/{name}/...`` where
    ``{name}`` is a concrete plugin name (not the list/permissions
    endpoints).  Management sub-routes (toggle, config, ui assets,
    details, uninstall) are always allowed through.
    """

    # Paths under /api/plugins/ that are NOT plugin-name segments
    _LIST_PATHS = {"", "permissions", "ui"}

    async def dispatch(self, request: Request, call_next):  # noqa: ANN201
        path = request.url.path

        # Only intercept /api/plugins/... requests
        if not path.startswith("/api/plugins/"):
            return await call_next(request)

        # Strip prefix to get the remainder: "{name}" or "{name}/..."
        remainder = path[len("/api/plugins/"):]

        # Exact "/api/plugins" or "/api/plugins/" -- plugin list endpoint
        if not remainder or remainder == "/":
            return await call_next(request)

        # Split into plugin name and sub-path
        if "/" in remainder:
            name, sub_path = remainder.split("/", 1)
            sub_path = "/" + sub_path
        else:
            name = remainder
            sub_path = ""

        # Skip non-plugin-name top-level paths (permissions, ui/manifest)
        if name in self._LIST_PATHS:
            return await call_next(request)

        # Skip management routes (toggle, config, ui assets, details, uninstall)
        if _is_management_route(sub_path):
            return await call_next(request)

        # --- Gate: check plugin status ---
        now = time.monotonic()
        cached = _plugin_cache.get(name)

        if cached is not None:
            is_enabled, granted_perms, ts = cached
            if (now - ts) >= CACHE_TTL_SECONDS:
                cached = None  # expired

        if cached is None:
            try:
                is_enabled, granted_perms = await asyncio.to_thread(
                    _fetch_plugin_status, name
                )
            except Exception:
                logger.exception("Failed to fetch plugin status for %s", name)
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Internal error checking plugin status"},
                )
            _plugin_cache[name] = (is_enabled, granted_perms, now)
        else:
            is_enabled, granted_perms, _ = cached

        if not is_enabled:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Plugin '{name}' is disabled"},
            )

        # Check permissions: granted must be a superset of required
        try:
            from app.plugins.manager import PluginManager

            manager = PluginManager.get_instance()
            required = manager.get_required_permissions(name)
        except Exception:
            # Plugin not loaded in this worker -- allow through
            # (the route handler will 404 if the plugin is truly gone)
            required = []

        if required:
            granted_set = set(granted_perms)
            missing = [p for p in required if p not in granted_set]
            if missing:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Plugin '{name}' missing permissions: {missing}"
                    },
                )

        return await call_next(request)
