"""Single source of truth for "which plugins are enabled" (#448).

The database is the only state shared by the four production workers.
``PluginManager._enabled`` is process-local and populated at startup, so a
runtime toggle reaches exactly one worker - which made the plugin list report
whatever the answering worker happened to know.

This module caches the database answer for a short window. The read itself
lives in the async ``refresh()`` and runs off the event loop; synchronous
readers consume the warm cache and never open a session of their own, because
the callers that need them (``PluginManager.get_all_plugins()``) have no
session to give.

The cache maps ``name -> granted_permissions`` rather than holding a bare set
of names: ``PluginGateMiddleware`` needs both out of the same read, and a
name-only cache would have forced it to keep a second query.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS: float = 5.0

_cache: Optional[Dict[str, List[str]]] = None
_cached_at: float = 0.0


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def _fetch() -> Dict[str, List[str]]:
    """Blocking DB read - always called through asyncio.to_thread."""
    from app.core.database import SessionLocal
    from app.models.plugin import InstalledPlugin

    db = SessionLocal()
    try:
        rows = (
            db.query(InstalledPlugin)
            .filter(InstalledPlugin.is_enabled == True)  # SQL boolean filter - `is True` would break the query (E712 is globally ignored for this reason)
            .all()
        )
        return {row.name: list(row.granted_permissions or []) for row in rows}
    finally:
        db.close()


async def refresh(force: bool = False) -> None:
    """Reload the cache if the TTL expired. Raises whatever the DB raises.

    Deliberately not swallowing: the display path wants to fall back to the
    last known state, the security gate wants to fail closed. Only the callers
    know which.
    """
    global _cache, _cached_at

    now = _monotonic()
    if not force and _cache is not None and (now - _cached_at) < CACHE_TTL_SECONDS:
        return

    fetched = await asyncio.to_thread(_fetch)
    _cache = fetched
    _cached_at = now


def enabled_plugins() -> Optional[Dict[str, List[str]]]:
    """Warm cache as ``name -> granted_permissions``; None if never loaded."""
    return dict(_cache) if _cache is not None else None


def is_enabled(name: str) -> Optional[bool]:
    """True/False from the cache, or None when there is no data yet."""
    if _cache is None:
        return None
    return name in _cache


def invalidate() -> None:
    """Drop the cache so the next refresh reloads (called after a local toggle)."""
    global _cache, _cached_at
    _cache = None
    _cached_at = 0.0


FAILED_RETRY_SECONDS: float = 60.0

_reconcile_lock = asyncio.Lock()
_failed_until: Dict[str, float] = {}


def _get_manager():
    """Indirection so tests can inject a manager double."""
    from app.plugins.manager import PluginManager

    return PluginManager.get_instance()


async def reconcile_worker() -> None:
    """Align this worker's loaded plugins with the database.

    Single-flight: a second caller returns immediately rather than queueing.
    Two requests arriving together (status-strip poll plus plugin list is the
    realistic pair) would otherwise both see the same diff and run the same
    plugin's on_startup() twice, in parallel. The loser proceeds on the current
    state - the winner's reconcile is a moment away.

    Never raises: a reconcile is best-effort maintenance on a request path.
    """
    if _reconcile_lock.locked():
        return

    async with _reconcile_lock:
        try:
            await refresh()
        except Exception:  # broad on purpose: a DB blip must not fail the request
            logger.warning("plugin enablement refresh failed", exc_info=True)
            return

        desired = enabled_plugins()
        if desired is None:
            return

        # Read as a module attribute: lifespan sets this after the fork, so a
        # from-import would freeze the pre-fork False forever.
        from app.core import lifespan

        manager = _get_manager()
        loaded = set(manager._enabled)
        now = _monotonic()

        for name, permissions in desired.items():
            if name in loaded:
                continue
            if _failed_until.get(name, 0.0) > now:
                continue
            try:
                from app.core.database import SessionLocal

                with SessionLocal() as db:
                    ok = await manager.enable_plugin(
                        name,
                        permissions,
                        db,
                        start_background_tasks=lifespan.IS_PRIMARY_WORKER,
                    )
            except Exception:  # broad on purpose: one bad plugin must not stop the rest
                logger.warning("lazy enable of plugin %s failed", name, exc_info=True)
                ok = False
            if not ok:
                _failed_until[name] = now + FAILED_RETRY_SECONDS

        for name in loaded - set(desired):
            try:
                await manager.disable_plugin(name)
            except Exception:  # broad on purpose: same reasoning as above
                logger.warning("lazy disable of plugin %s failed", name, exc_info=True)
