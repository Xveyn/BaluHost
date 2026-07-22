"""Steam gaming plugin: shows a status-strip pill while a game is running.

Detection is a /proc scan (see detector.py); the result is cached for a few
seconds so the status strip's poll — once per logged-in user every 10s across
four production workers — does not re-scan for every request. A per-worker
cache is enough: the pill is an activity indicator, not a ledger, and this
avoids sharing state between workers entirely.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.plugins.base import PluginBase, PluginMetadata, StatusPillSpec
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name

_PILL_ID = "session"
_CACHE_TTL_SECONDS = 3.0
_CACHE: Dict[str, object] = {}


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def _current_game() -> Optional[tuple[str, Optional[str]]]:
    """``(app_id, name)`` of the running game, or None. Cached for a few seconds."""
    now = _monotonic()
    checked_at = _CACHE.get("checked_at")
    if isinstance(checked_at, float) and now - checked_at < _CACHE_TTL_SECONDS:
        return _CACHE.get("game")  # type: ignore[return-value]

    app_id = detect_running_app_id()
    game = (app_id, resolve_name(app_id)) if app_id else None
    _CACHE["checked_at"] = now
    _CACHE["game"] = game
    return game


class SteamGamingPlugin(PluginBase):
    """Surfaces a running Steam session in the topbar status strip."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="steam_gaming",
            display_name="Steam Gaming",
            version="1.0.0",
            description="Shows a status-strip pill while a Steam game is running",
            author="BaluHost",
        )

    def get_status_pills(self) -> List[StatusPillSpec]:
        return [StatusPillSpec(
            id=_PILL_ID,
            icon="Gamepad2",
            href="/plugins",
            name_key="pill_name",
            name_text="Gaming Session",
            default_visibility="admin",
            silent_when_ok=True,
        )]

    async def collect_status_pill(self, pill_id: str, db: Session) -> Optional[dict]:
        if pill_id != _PILL_ID:
            return None

        # _current_game() does synchronous filesystem I/O (/proc scan, manifest
        # reads); asyncio.wait_for() can only cancel awaits, not blocking sync
        # code, so a slow/spun-down Steam library mount would otherwise stall
        # the whole worker's event loop instead of being cut off by the
        # PLUGIN_COLLECTOR_TIMEOUT_SECONDS timeout in the status bar service.
        game = await asyncio.to_thread(_current_game)
        if game is None:
            if settings.is_dev_mode:
                # No /proc on a Windows dev box — render something anyway.
                game = ("0", "Dev Mode Game")
            else:
                return None

        _app_id, name = game
        return {
            "kind": "state",
            "tone": "info",
            "label_key": "pill_label",
            "label_text": "Gaming Session",
            "value": name,
            "icon": "Gamepad2",
        }

    def get_translations(self) -> Optional[Dict[str, Dict[str, str]]]:
        return {
            "en": {"pill_name": "Gaming Session", "pill_label": "Gaming Session"},
            "de": {"pill_name": "Gaming-Session", "pill_label": "Gaming-Session"},
        }
