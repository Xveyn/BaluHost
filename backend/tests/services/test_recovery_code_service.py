"""Tests for password recovery codes (column + service)."""
from app.models.user import User


def test_user_has_recovery_codes_column():
    u = User(username="x", hashed_password="h", role="user")
    assert hasattr(u, "password_recovery_codes_encrypted")
    assert u.password_recovery_codes_encrypted is None
