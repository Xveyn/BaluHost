"""
Presence tracking for sleep mode (issue #214).

Heartbeats arrive on any Uvicorn worker via POST /api/system/sleep/presence
and are upserted into the presence_sessions table; the primary worker's
sleep loops read it (same any-worker-writes / primary-reads pattern as
power_demands). Each function opens its own short-lived session.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.sleep import PresenceSession, SleepConfig

logger = logging.getLogger(__name__)

# Served to clients in the heartbeat response; clients self-configure.
HEARTBEAT_INTERVAL_SECONDS = 45

# Rows older than this are garbage-collected by cleanup_expired().
_CLEANUP_MAX_AGE = timedelta(hours=24)


def record_heartbeat(user_id: int, client_id: str, client_type: str) -> None:
    """Upsert the heartbeat row for *client_id*."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        row = db.get(PresenceSession, client_id)
        if row is None:
            row = PresenceSession(
                client_id=client_id,
                user_id=user_id,
                client_type=client_type,
                last_heartbeat_at=now,
            )
            db.add(row)
        else:
            row.user_id = user_id
            row.client_type = client_type
            row.last_heartbeat_at = now
        db.commit()
    finally:
        db.close()


def is_anyone_present(timeout_minutes: int) -> bool:
    """True if any session sent a heartbeat within the timeout window."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    db = SessionLocal()
    try:
        row = db.execute(
            select(PresenceSession.client_id)
            .where(PresenceSession.last_heartbeat_at > cutoff)
            .limit(1)
        ).first()
        return row is not None
    finally:
        db.close()


def get_present_sessions(timeout_minutes: int) -> list[PresenceSession]:
    """All sessions with a heartbeat within the timeout window (for status)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    db = SessionLocal()
    try:
        rows = db.execute(
            select(PresenceSession).where(PresenceSession.last_heartbeat_at > cutoff)
        ).scalars().all()
        db.expunge_all()
        return list(rows)
    finally:
        db.close()


def cleanup_expired() -> int:
    """Delete sessions whose last heartbeat is older than 24h. Returns count."""
    cutoff = datetime.now(timezone.utc) - _CLEANUP_MAX_AGE
    db = SessionLocal()
    try:
        deleted = (
            db.query(PresenceSession)
            .filter(PresenceSession.last_heartbeat_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted)
    finally:
        db.close()


def get_presence_settings() -> tuple[bool, str, int]:
    """Return (presence_enabled, presence_mode, presence_timeout_minutes).

    Falls back to model defaults when no config row exists yet.
    """
    db = SessionLocal()
    try:
        cfg = db.get(SleepConfig, 1)
        if cfg is None:
            return True, "active", 3
        return (
            bool(cfg.presence_enabled),
            str(cfg.presence_mode),
            int(cfg.presence_timeout_minutes),
        )
    finally:
        db.close()
