"""Steam session ledger: turn detector observations into persisted sessions.

The open session in the database IS the poller's state - there is no in-process
last_app_id and no initialization flag. That is what makes a restart mid-session
harmless: the gap between `now` and the open session's last_seen_at says what
happened while the process was away (see the gap rules in Task 3).

This module knows the database and nothing about notifications: it returns what
is worth announcing and lets the caller deliver it, after the booking is
committed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from app.models.steam_session import SteamSession

logger = logging.getLogger(__name__)

EVENT_STARTED = "session_started"
EVENT_ENDED = "session_ended"

# Two poll intervals: within this, the poller was there continuously, so `now`
# is a truthful end time and the edge is live news worth announcing.
STALE_AFTER_SECONDS = 60.0
# The same game across a gap this short is one session (a deploy mid-game).
ADOPT_WINDOW_SECONDS = 600.0


@dataclass(frozen=True)
class LedgerEvent:
    """A notification the caller should fire once the booking is committed."""

    event_id: str
    app_id: str
    game: str


def as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes even for DateTime(timezone=True)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _label(session: SteamSession) -> str:
    """Name for a notification; the AppID is the honest fallback."""
    return session.game_name or session.app_id


def _open(
    db: Session,
    app_id: str,
    now: datetime,
    resolve_name: Callable[[str], Optional[str]],
) -> SteamSession:
    """Start a new session. Announcing it is the caller's decision."""
    session = SteamSession(
        app_id=app_id,
        game_name=resolve_name(app_id),
        started_at=now,
        last_seen_at=now,
    )
    db.add(session)
    return session


def _current_session(db: Session) -> Optional[SteamSession]:
    """The newest open session, if any."""
    return (
        db.query(SteamSession)
        .filter(SteamSession.ended_at.is_(None))
        .order_by(SteamSession.started_at.desc())
        .first()
    )


def record(
    db: Session,
    app_id: Optional[str],
    *,
    now: datetime,
    resolve_name: Callable[[str], Optional[str]],
) -> List[LedgerEvent]:
    """Book one detector observation; return the events worth announcing.

    Commits on success. Never raises: a database failure rolls back, logs and
    yields no events, so the next tick simply tries again.

    Args:
        db: SQLAlchemy session, owned by the caller.
        app_id: AppID of the running game, or None when nothing is running.
        now: Current time (injected so tests control the clock).
        resolve_name: AppID -> display name, or None when unresolvable.

    Returns:
        Events to deliver, in order.
    """
    events: List[LedgerEvent] = []
    try:
        current = _current_session(db)

        if current is None:
            if app_id is not None:
                opened = _open(db, app_id, now, resolve_name)
                events.append(LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened)))
        elif app_id == current.app_id:
            current.last_seen_at = now
        else:
            current.ended_at = now
            events.append(LedgerEvent(EVENT_ENDED, current.app_id, _label(current)))
            if app_id is not None:
                opened = _open(db, app_id, now, resolve_name)
                events.append(LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened)))

        db.commit()
    except Exception:  # broad on purpose: a booking failure must not kill the poller
        db.rollback()
        logger.warning("steam ledger: booking failed", exc_info=True)
        return []

    return events
