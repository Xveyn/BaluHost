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

from sqlalchemy.exc import SQLAlchemyError
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


def _claim_current_session(db: Session) -> Optional[SteamSession]:
    """The newest open session; any older open one is an orphan and gets closed.

    The invariant is "at most one open session". A crash at the wrong moment can
    still leave more behind, so every tick cleans up instead of trusting it.
    """
    open_sessions = (
        db.query(SteamSession)
        .filter(SteamSession.ended_at.is_(None))
        .order_by(SteamSession.started_at.desc())
        .all()
    )
    for orphan in open_sessions[1:]:
        orphan.ended_at = as_utc(orphan.last_seen_at)
        logger.warning("steam ledger: closed orphaned session id=%s", orphan.id)
    return open_sessions[0] if open_sessions else None


def _gap_seconds(session: SteamSession, now: datetime) -> float:
    """How long the poller was away, measured from the session's last heartbeat."""
    return (now - as_utc(session.last_seen_at)).total_seconds()


def _safe_rollback(db: Session) -> None:
    """A rollback on a dead connection must not defeat the no-raise contract."""
    try:
        db.rollback()
    except Exception:
        logger.warning("steam ledger: rollback failed", exc_info=True)


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
        current = _claim_current_session(db)

        if current is None:
            if app_id is not None:
                # Nothing open: either nothing was running, or this is the very
                # first tick after deploying the ledger. Both look identical
                # here - see the accepted deviation in the design doc.
                opened = _open(db, app_id, now, resolve_name)
                events.append(LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened)))
        else:
            gap = _gap_seconds(current, now)
            live = gap <= STALE_AFTER_SECONDS

            if app_id == current.app_id:
                if gap <= ADOPT_WINDOW_SECONDS:
                    current.last_seen_at = now
                    if current.game_name is None:
                        # A game started during its own install has no manifest
                        # yet; resolve_name() retries misses after 60s anyway.
                        current.game_name = resolve_name(app_id)
                else:
                    # Same game, but far too long ago to be one session.
                    current.ended_at = as_utc(current.last_seen_at)
                    _open(db, app_id, now, resolve_name)  # after a gap: book, never announce
            else:
                # `now` is only a truthful end time while the poller was there.
                current.ended_at = now if live else as_utc(current.last_seen_at)
                if live:
                    events.append(LedgerEvent(EVENT_ENDED, current.app_id, _label(current)))
                if app_id is not None:
                    opened = _open(db, app_id, now, resolve_name)
                    if live:
                        events.append(
                            LedgerEvent(EVENT_STARTED, opened.app_id, _label(opened))
                        )

        db.commit()
    except SQLAlchemyError:
        _safe_rollback(db)
        logger.warning("steam ledger: booking failed", exc_info=True)
        return []
    except Exception:
        # Not a database problem: a programming error, or an injected
        # resolve_name() that threw. The poller must survive it, but this must
        # not look like a briefly unreachable database in the log - otherwise a
        # permanently silent ledger is indistinguishable from a hiccup.
        _safe_rollback(db)
        logger.exception(
            "steam ledger: unexpected failure (app_id=%s, now=%s)", app_id, now
        )
        return []

    return events


def duration_seconds(session: SteamSession, now: datetime) -> float:
    """Seconds played. An open session counts up to *now*.

    Clamped at 0: an NTP step backwards would otherwise produce a negative
    duration, which is worse in the panel than a flattering zero.
    """
    end = as_utc(session.ended_at) if session.ended_at is not None else now
    return max(0.0, (end - as_utc(session.started_at)).total_seconds())
