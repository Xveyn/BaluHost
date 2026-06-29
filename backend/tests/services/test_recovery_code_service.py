"""Tests for password recovery codes (column + service)."""
import pytest
from app.models.user import User


def test_user_has_recovery_codes_column():
    u = User(username="x", hashed_password="h", role="user")
    assert hasattr(u, "password_recovery_codes_encrypted")
    assert u.password_recovery_codes_encrypted is None


from app.services import recovery_code_service as rcs


@pytest.fixture
def a_user(db_session):
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    return user_service.create_user(
        UserCreate(username="recov", email="r@example.com", password="StrongPass9x", role="user"),
        db=db_session,
    )


def test_generate_returns_ten_codes(db_session, a_user):
    codes = rcs.generate_recovery_codes(db_session, a_user.id)
    assert len(codes) == rcs.RECOVERY_CODE_COUNT
    assert rcs.has_recovery_codes(db_session, a_user.id) is True
    assert rcs.get_recovery_codes_remaining(db_session, a_user.id) == 10


def test_code_is_single_use(db_session, a_user):
    codes = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, codes[0]) is True
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, codes[0]) is False
    assert rcs.get_recovery_codes_remaining(db_session, a_user.id) == 9


def test_regenerate_invalidates_old(db_session, a_user):
    old = rcs.generate_recovery_codes(db_session, a_user.id)
    new = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, old[0]) is False
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, new[0]) is True


def test_verify_for_username_success_and_misses(db_session, a_user):
    codes = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_for_username(db_session, "recov", codes[0]) is not None
    # consumed
    assert rcs.verify_and_consume_for_username(db_session, "recov", codes[0]) is None
    # unknown user → None (no raise)
    assert rcs.verify_and_consume_for_username(db_session, "ghost", "AAAA111122") is None


def test_verify_for_username_disabled_user(db_session, a_user):
    rcs.generate_recovery_codes(db_session, a_user.id)
    a_user.is_active = False
    db_session.commit()
    codes = rcs.generate_recovery_codes(db_session, a_user.id)  # still generatable directly
    assert rcs.verify_and_consume_for_username(db_session, "recov", codes[0]) is None
