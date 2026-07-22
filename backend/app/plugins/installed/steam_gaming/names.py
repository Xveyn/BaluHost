"""Resolve a Steam AppID to its display name via ``appmanifest_<id>.acf``."""
from __future__ import annotations

import time
from typing import Optional

from app.services.game_libraries import vdf
from app.services.game_libraries.steam import find_steamapps_dirs

# A game's name never changes, so hits are cached for the process lifetime.
_NAME_CACHE: dict[str, str] = {}

# Misses are retried: a manifest appears while a game is still installing,
# and non-Steam shortcuts never get one at all.
_MISS_CACHE: dict[str, float] = {}
_MISS_TTL_SECONDS = 60.0


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def reset_caches() -> None:
    """Drop both caches. Intended for tests."""
    _NAME_CACHE.clear()
    _MISS_CACHE.clear()


def _read_manifest_name(app_id: str) -> Optional[str]:
    for steamapps in find_steamapps_dirs():
        manifest = steamapps / f"appmanifest_{app_id}.acf"
        try:
            data = vdf.parse(manifest.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        except Exception:
            # A corrupt manifest must not break detection for other libraries.
            continue
        state = data.get("AppState")
        if not isinstance(state, dict):
            continue
        name = state.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def resolve_name(app_id: str) -> Optional[str]:
    """Display name for *app_id*, or None when it cannot be resolved."""
    cached = _NAME_CACHE.get(app_id)
    if cached is not None:
        return cached

    missed_at = _MISS_CACHE.get(app_id)
    if missed_at is not None and _monotonic() - missed_at < _MISS_TTL_SECONDS:
        return None

    name = _read_manifest_name(app_id)
    if name is None:
        _MISS_CACHE[app_id] = _monotonic()
        return None

    _NAME_CACHE[app_id] = name
    _MISS_CACHE.pop(app_id, None)
    return name
