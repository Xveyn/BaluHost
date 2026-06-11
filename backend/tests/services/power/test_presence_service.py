"""Tests for the presence tracker (issue #214)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import SessionLocal
from app.models.sleep import PresenceSession
from app.models.user import User


@pytest.fixture(autouse=True)
def _clean_presence_rows():
    """Each test starts and ends with an empty presence_sessions table.

    Also ensures user id=1 exists so FK inserts don't fail.
    """
    db = SessionLocal()
    try:
        db.query(PresenceSession).delete()
        db.commit()
        # Seed a minimal user if not present (FK target for user_id=1)
        if not db.get(User, 1):
            db.add(User(id=1, username="_test_presence_user", hashed_password="x", role="user"))
            db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.query(PresenceSession).delete()
        db.commit()
    finally:
        db.close()


def test_presence_session_model_roundtrip():
    db = SessionLocal()
    try:
        row = PresenceSession(
            client_id="tab-abc-123",
            user_id=1,
            client_type="web",
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        loaded = db.get(PresenceSession, "tab-abc-123")
        assert loaded is not None
        assert loaded.user_id == 1
        assert loaded.client_type == "web"
    finally:
        db.close()
