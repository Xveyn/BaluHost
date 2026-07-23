"""Steam session poller: detect play/not-play edges and emit notifications.

Runs as a plugin background task, which thanks to #448 executes primary-only -
so exactly one instance polls, and its last-seen state can live in the object
(no cross-worker sharing). The first tick only establishes a baseline: a game
already running when the backend starts must not be reported as 'started', or
every restart would false-alarm mid-session.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name
from app.services.notifications.plugin_events import emit_plugin_event

_PLUGIN = "steam_gaming"


class SteamSessionPoller:
    def __init__(
        self,
        detect: Callable[[], Optional[str]] = detect_running_app_id,
        resolve: Callable[[str], Optional[str]] = resolve_name,
        emit=emit_plugin_event,
    ) -> None:
        self._detect = detect
        self._resolve = resolve
        self._emit = emit
        self._initialized = False
        self._last_app_id: Optional[str] = None

    async def tick(self) -> None:
        # Blocking /proc + manifest reads off the event loop, same convention
        # as the menu action and the pill collector.
        app_id = await asyncio.to_thread(self._detect)

        if not self._initialized:
            self._last_app_id = app_id
            self._initialized = True
            return

        prev = self._last_app_id
        self._last_app_id = app_id

        if prev is None and app_id is not None:
            await self._fire("session_started", app_id)
        elif prev is not None and app_id is None:
            await self._fire("session_ended", prev)
        # prev == app_id, or a direct X->Y switch: no event; state already moved.

    async def _fire(self, event_id: str, app_id: str) -> None:
        name = await asyncio.to_thread(self._resolve, app_id) or app_id
        await self._emit(_PLUGIN, event_id, entity_id=app_id, game=name)
