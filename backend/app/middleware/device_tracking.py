"""Middleware to track mobile device activity and update last_seen timestamps."""

import asyncio
from datetime import datetime, timezone
from fastapi import Request
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import SessionLocal
from app.models.mobile import MobileDevice


def _update_device_last_seen(device_id: str) -> None:
    """Synchronous DB update — designed to run in a worker thread."""
    try:
        db: Session = SessionLocal()
        try:
            device = db.query(MobileDevice).filter(
                MobileDevice.id == device_id
            ).first()

            if device:
                device.last_seen = datetime.now(timezone.utc)
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

    This allows the web UI to show which devices are currently active/connected.
    """

    async def dispatch(self, request: Request, call_next):
        # Get device ID from header
        device_id = request.headers.get("X-Device-ID")

        # Update last_seen in a thread so the sync DB call doesn't block the event loop
        if device_id:
            await asyncio.to_thread(_update_device_last_seen, device_id)

        # Continue with the request
        response = await call_next(request)
        return response
