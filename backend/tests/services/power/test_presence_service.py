"""Tests for the presence tracker (issue #214)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import SessionLocal
from app.models.sleep import PresenceSession
from app.models.user import User


@pytest.fixture(autouse=True)
def _clean_presence_rows():
    """Each test starts and ends with an empty presence_sessions table.

    Also ensures user id=1 and id=2 exist so FK inserts don't fail.
    """
    db = SessionLocal()
    try:
        db.query(PresenceSession).delete()
        db.commit()
        # Seed minimal users if not present (FK targets for user_id=1 and user_id=2)
        if not db.get(User, 1):
            db.add(User(id=1, username="_test_presence_user", hashed_password="x", role="user"))
            db.commit()
        if not db.get(User, 2):
            db.add(User(id=2, username="_test_presence_user2", hashed_password="x", role="user"))
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


# ---------------------------------------------------------------------------
# Presence tracker service tests (Task 2)
# ---------------------------------------------------------------------------

from app.services.power import presence


def _insert_session(client_id: str, age_minutes: float, user_id: int = 1) -> None:
    db = SessionLocal()
    try:
        db.add(PresenceSession(
            client_id=client_id,
            user_id=user_id,
            client_type="web",
            last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
        ))
        db.commit()
    finally:
        db.close()


class TestRecordHeartbeat:
    def test_creates_row(self):
        presence.record_heartbeat(user_id=1, client_id="tab-1", client_type="web")
        db = SessionLocal()
        try:
            row = db.get(PresenceSession, "tab-1")
            assert row is not None
            assert row.user_id == 1
        finally:
            db.close()

    def test_upserts_existing_row(self):
        presence.record_heartbeat(user_id=1, client_id="tab-1", client_type="web")
        presence.record_heartbeat(user_id=2, client_id="tab-1", client_type="mobile")
        db = SessionLocal()
        try:
            rows = db.query(PresenceSession).all()
            assert len(rows) == 1
            assert rows[0].user_id == 2
            assert rows[0].client_type == "mobile"
        finally:
            db.close()


class TestIsAnyonePresent:
    def test_false_when_no_rows(self):
        assert presence.is_anyone_present(timeout_minutes=3) is False

    def test_true_for_fresh_heartbeat(self):
        _insert_session("tab-fresh", age_minutes=1)
        assert presence.is_anyone_present(timeout_minutes=3) is True

    def test_false_for_expired_heartbeat(self):
        _insert_session("tab-old", age_minutes=10)
        assert presence.is_anyone_present(timeout_minutes=3) is False

    def test_any_single_fresh_session_suffices(self):
        _insert_session("tab-old", age_minutes=10)
        _insert_session("tab-fresh", age_minutes=1, user_id=2)
        assert presence.is_anyone_present(timeout_minutes=3) is True


class TestGetPresentSessions:
    def test_returns_only_fresh_sessions(self):
        _insert_session("tab-old", age_minutes=10)
        _insert_session("tab-fresh", age_minutes=1)
        sessions = presence.get_present_sessions(timeout_minutes=3)
        assert [s.client_id for s in sessions] == ["tab-fresh"]


class TestCleanupExpired:
    def test_deletes_only_stale_rows(self):
        _insert_session("tab-ancient", age_minutes=60 * 25)  # > 24h
        _insert_session("tab-recent", age_minutes=5)
        deleted = presence.cleanup_expired()
        assert deleted == 1
        db = SessionLocal()
        try:
            remaining = [r.client_id for r in db.query(PresenceSession).all()]
        finally:
            db.close()
        assert remaining == ["tab-recent"]


class TestGetPresenceSettings:
    def test_returns_config_values(self):
        from app.models.sleep import SleepConfig
        db = SessionLocal()
        try:
            cfg = db.get(SleepConfig, 1)
            if cfg is None:
                cfg = SleepConfig(id=1)
                db.add(cfg)
            cfg.presence_enabled = True
            cfg.presence_mode = "session"
            cfg.presence_timeout_minutes = 7
            db.commit()
        finally:
            db.close()
        enabled, mode, timeout = presence.get_presence_settings()
        assert enabled is True
        assert mode == "session"
        assert timeout == 7
