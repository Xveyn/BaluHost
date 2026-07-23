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
