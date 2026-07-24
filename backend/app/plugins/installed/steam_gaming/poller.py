"""Steam session poller: detect, book, announce (Teilprojekt 3+4/4).

Runs as a plugin background task, which thanks to #448 executes primary-only -
so exactly one instance polls. It keeps no state of its own: the open session
in the database is the state (see ledger.py), which is what makes a restart
mid-session harmless.

Order matters: book and commit first, announce afterwards. A failed push must
never roll back a booking.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.plugins.installed.steam_gaming import ledger
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name
from app.services.notifications.plugin_events import emit_plugin_event

logger = logging.getLogger(__name__)

_PLUGIN = "steam_gaming"
_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60.0


def _utc_now() -> datetime:
    """Indirection so tests can control the clock."""
    return datetime.now(timezone.utc)


class SteamSessionPoller:
    """Books what the detector sees and announces the edges worth announcing."""

    def __init__(
        self,
        detect: Callable[[], Optional[str]] = detect_running_app_id,
        resolve: Callable[[str], Optional[str]] = resolve_name,
        emit=emit_plugin_event,
        session_factory: Callable[[], Session] = SessionLocal,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._detect = detect
        self._resolve = resolve
        self._emit = emit
        self._session_factory = session_factory
        self._clock = clock
        self._last_cleanup: Optional[datetime] = None

    async def tick(self) -> None:
        """One poll: detect, book, then deliver whatever the ledger returned."""
        # Blocking /proc + manifest + DB work stays off the event loop.
        app_id = await asyncio.to_thread(self._detect)
        now = self._clock()
        events = await asyncio.to_thread(self._book, app_id, now)

        for event in events:
            await self._emit(
                _PLUGIN, event.event_id, entity_id=event.app_id, game=event.game
            )

    def _book(self, app_id: Optional[str], now: datetime) -> List[ledger.LedgerEvent]:
        """Blocking: owns the database session for this tick."""
        db = self._session_factory()
        try:
            events = ledger.record(db, app_id, now=now, resolve_name=self._resolve)
            if self._due_for_cleanup(now):
                ledger.cleanup_old_sessions(db, now=now)
                self._last_cleanup = now
            return events
        finally:
            db.close()

    def _due_for_cleanup(self, now: datetime) -> bool:
        """Once a day. The marker lives in the process - a restart costs at most
        one extra DELETE that finds nothing."""
        if self._last_cleanup is None:
            return True
        return (now - self._last_cleanup).total_seconds() >= _CLEANUP_INTERVAL_SECONDS
