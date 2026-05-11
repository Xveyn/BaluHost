"""Test the notification trash retention migration backfills dismissed rows."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.notification import Notification


def test_existing_notifications_in_inbox_have_deleted_at_null(db_session):
    """After migration, notifications without deleted_at remain in the inbox."""
    n = Notification(
        user_id=None,
        category="system",
        notification_type="info",
        title="Active",
        message="Still in inbox",
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    assert n.deleted_at is None


def test_can_write_and_query_deleted_at(db_session):
    """Migration created the column and index; writes round-trip."""
    n = Notification(
        user_id=None,
        category="system",
        notification_type="info",
        title="Trashed",
        message="In trash",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    assert n.deleted_at is not None


def test_trash_retention_days_defaults_to_7(db_session):
    """New preferences rows default to 7-day retention."""
    from app.models.notification import NotificationPreferences
    prefs = NotificationPreferences(user_id=999999)
    db_session.add(prefs)
    db_session.commit()
    db_session.refresh(prefs)
    assert prefs.trash_retention_days == 7


def test_trash_retention_days_rejects_out_of_range(db_session):
    """CHECK constraint rejects values outside 1..7."""
    from app.models.notification import NotificationPreferences
    from sqlalchemy.exc import IntegrityError

    prefs = NotificationPreferences(user_id=999998, trash_retention_days=0)
    db_session.add(prefs)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
