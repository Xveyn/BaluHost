"""PIN credential service for the Tauri local-channel login.

PINs are hashed with the same bcrypt context as passwords. SQLite returns
naive datetimes, so timestamps are coerced to UTC before comparison.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.users import pwd_context

PIN_MAX_FAILED = 5
PIN_LOCK_MINUTES = 15


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hash_pin(pin: str) -> str:
    return pwd_context.hash(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    return pwd_context.verify(pin, pin_hash)


def in_grace_window(user: User, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    until = _as_utc(user.pin_grace_until)
    return until is not None and until > now


def is_pin_locked(user: User, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    until = _as_utc(user.pin_locked_until)
    return until is not None and until > now


def register_pin_failure(db: Session, user: User) -> None:
    user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
    if user.pin_failed_attempts >= PIN_MAX_FAILED:
        user.pin_locked_until = datetime.now(timezone.utc) + timedelta(minutes=PIN_LOCK_MINUTES)
        user.pin_failed_attempts = 0
    db.commit()


def reset_pin_failures(db: Session, user: User) -> None:
    if user.pin_failed_attempts or user.pin_locked_until:
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        db.commit()


def set_pin(db: Session, user: User, pin: str) -> None:
    user.pin_hash = hash_pin(pin)
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    db.commit()


def clear_pin(db: Session, user: User) -> None:
    user.pin_hash = None
    user.pin_grace_until = None
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    db.commit()
