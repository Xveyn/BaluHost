"""Schema presence tests for PIN columns and AuthPolicy."""
from app.models.user import User
from app.models.auth_policy import AuthPolicy


def test_user_has_pin_columns():
    cols = set(User.__table__.columns.keys())
    assert {"pin_hash", "pin_grace_until", "pin_failed_attempts", "pin_locked_until"} <= cols


def test_auth_policy_defaults(db_session):
    p = AuthPolicy(id=1)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert p.pin_login_enabled is True
    assert p.pin_grace_window_seconds == 86400
