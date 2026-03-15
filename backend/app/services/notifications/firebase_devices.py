"""Device lookup helpers for Firebase push notification testing."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.mobile import MobileDevice


def get_active_device_by_id(db: Session, device_id: int) -> Optional[MobileDevice]:
    """Get an active mobile device by its ID."""
    return (
        db.query(MobileDevice)
        .filter(MobileDevice.id == device_id, MobileDevice.is_active == True)  # noqa: E712
        .first()
    )


def get_active_devices_for_user(db: Session, user_id: int) -> list[MobileDevice]:
    """Get all active mobile devices for a user."""
    return (
        db.query(MobileDevice)
        .filter(MobileDevice.user_id == user_id, MobileDevice.is_active == True)  # noqa: E712
        .all()
    )
