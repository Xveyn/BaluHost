"""Middleware to track mobile device activity and update last_seen timestamps."""

import asyncio
import time
from collections import OrderedDict
from datetime import datetime, timezone
from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import SessionLocal
from app.models.mobile import MobileDevice


_SYNC_PATH_PREFIXES = (
    "/api/files/upload",
    "/api/files/download",
    "/api/mobile/sync",
)

# How long a device's timestamps may go stale before we write again. The only
# consumer that compares against a threshold is the dashboard's "recently
# active" badge at 5 minutes, so a minute of staleness is invisible there —
# while a syncing device drops from up to 300 commits/min to at most one.
_WRITE_TTL_SECONDS = 60.0

# `X-Device-ID` is unauthenticated input, so the cache must not be a lever for
# unbounded memory growth. A NAS tracks a handful of devices; anything past
# this is flooding and gets evicted least-recently-used first.
_MAX_TRACKED_DEVICES = 512

# device_id -> (last_seen written at, last_sync written at), monotonic seconds.
# Only ever touched from the event loop (see `dispatch`), so it needs no lock.
_WRITE_CACHE: "OrderedDict[str, tuple[float, float | None]]" = OrderedDict()


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def _claim_write(device_id: str, is_sync: bool) -> bool:
    """Decide whether this request must hit the DB, and record that it will.

    Returns True at most once per `_WRITE_TTL_SECONDS` per device — except that
    a sync request also forces a write when `last_sync` itself is stale, so
    sync freshness never rides on unrelated traffic.
    """
    now = _monotonic()
    entry = _WRITE_CACHE.get(device_id)

    if entry is None:
        seen_due = True
        sync_due = is_sync
        prev_sync: float | None = None
    else:
        seen_at, prev_sync = entry
        seen_due = now - seen_at >= _WRITE_TTL_SECONDS
        sync_due = is_sync and (prev_sync is None or now - prev_sync >= _WRITE_TTL_SECONDS)

    if not (seen_due or sync_due):
        return False

    _WRITE_CACHE[device_id] = (now, now if is_sync else prev_sync)
    _WRITE_CACHE.move_to_end(device_id)
    while len(_WRITE_CACHE) > _MAX_TRACKED_DEVICES:
        _WRITE_CACHE.popitem(last=False)
    return True


def _update_device_last_seen(device_id: str, update_last_sync: bool = False) -> None:
    """Synchronous DB update — designed to run in a worker thread."""
    try:
        db: Session = SessionLocal()
        try:
            device = db.query(MobileDevice).filter(
                MobileDevice.id == device_id
            ).first()

            if device:
                now = datetime.now(timezone.utc)
                device.last_seen = now
                if update_last_sync:
                    device.last_sync = now
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass


class DeviceTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that updates the last_seen timestamp for mobile devices.

    This middleware checks for the X-Device-ID header in incoming requests
    and updates the corresponding device's last_seen timestamp in the database.
    For file upload/download/sync requests, it also updates last_sync.

    This allows the web UI to show which devices are currently active/connected.

    Writes are debounced per device (`_WRITE_TTL_SECONDS`): the timestamps are
    coarse activity indicators, not an audit trail, so paying a round-trip on
    every single request buys nothing the UI can show.
    """

    async def dispatch(self, request: Request, call_next):
        # Get device ID from header
        device_id = request.headers.get("X-Device-ID")

        # Update last_seen in a thread so the sync DB call doesn't block the event loop
        # Also update last_sync for file operation paths.
        # The claim runs in the event loop, so concurrent requests from one
        # device cannot both decide to write.
        if device_id:
            path = request.url.path
            is_sync = any(path.startswith(p) for p in _SYNC_PATH_PREFIXES)
            if _claim_write(device_id, is_sync):
                await asyncio.to_thread(_update_device_last_seen, device_id, is_sync)

        # Continue with the request
        response = await call_next(request)
        return response
