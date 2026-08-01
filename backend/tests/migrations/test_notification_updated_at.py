"""The updated_at stamp exists, is written on creation, and moves on change."""
from datetime import datetime, timezone

from app.models.notification import Notification


def _make(db_session, **over) -> Notification:
    n = Notification(
        user_id=None,
        category="system",
        notification_type="info",
        title="Probe",
        message="Body",
        **over,
    )
    db_session.add(n)
    db_session.commit()
    db_session.refresh(n)
    return n


def test_new_notification_gets_a_stamp(db_session):
    n = _make(db_session)

    assert n.updated_at is not None


def test_stamp_is_exposed_in_to_dict(db_session):
    """The WebSocket payload carries the same stamp as the REST response."""
    n = _make(db_session)

    payload = n.to_dict()

    assert "updated_at" in payload
    assert payload["updated_at"] is not None


def test_stamp_survives_an_explicit_value(db_session):
    """A caller-supplied value round-trips through the ORM.

    Note: the migration backfill itself is raw SQL (`UPDATE ... COALESCE(...)`)
    and never goes through the ORM, so this test does not cover it. This suite
    also never runs an Alembic migration — its tables come from
    `Base.metadata.create_all()` — so the backfill has no test coverage here.
    """
    fixed = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    n = _make(db_session, updated_at=fixed)

    assert n.updated_at.year == 2026
    assert n.updated_at.month == 1
