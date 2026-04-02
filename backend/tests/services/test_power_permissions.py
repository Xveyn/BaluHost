"""Tests for power permissions service."""

import pytest
from sqlalchemy.orm import Session

from app.models.power_permissions import UserPowerPermission
from app.models.user import User
from app.schemas.power_permissions import UserPowerPermissionsUpdate
from app.services.power_permissions import (
    get_permissions,
    update_permissions,
    check_permission,
)


@pytest.fixture
def regular_user(db_session: Session) -> User:
    """Create a regular user for testing."""
    from app.services import users as user_service
    from app.schemas.user import UserCreate

    existing = user_service.get_user_by_username("testuser", db=db_session)
    if existing:
        return existing
    return user_service.create_user(
        UserCreate(username="testuser", email="test@test.com", password="Test1234", role="user"),
        db=db_session,
    )


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create an admin user for testing."""
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    from app.core.config import settings

    existing = user_service.get_user_by_username(settings.admin_username, db=db_session)
    if existing:
        return existing
    return user_service.create_user(
        UserCreate(
            username=settings.admin_username,
            email=settings.admin_email,
            password=settings.admin_password,
            role="admin",
        ),
        db=db_session,
    )


class TestGetPermissions:
    def test_returns_defaults_when_no_entry(self, db_session: Session, regular_user: User):
        result = get_permissions(db_session, regular_user.id)
        assert result.user_id == regular_user.id
        assert result.can_soft_sleep is False
        assert result.can_wake is False
        assert result.can_suspend is False
        assert result.can_wol is False
        assert result.granted_by is None

    def test_returns_existing_permissions(self, db_session: Session, regular_user: User):
        perm = UserPowerPermission(
            user_id=regular_user.id,
            can_soft_sleep=True,
            can_wake=True,
            can_suspend=False,
            can_wol=False,
            granted_by=None,
        )
        db_session.add(perm)
        db_session.commit()

        result = get_permissions(db_session, regular_user.id)
        assert result.can_soft_sleep is True
        assert result.can_wake is True
        assert result.can_suspend is False


class TestUpdatePermissions:
    def test_creates_entry_if_none_exists(self, db_session: Session, regular_user: User, admin_user: User):
        update = UserPowerPermissionsUpdate(can_soft_sleep=True)
        result = update_permissions(db_session, regular_user.id, update, granted_by=admin_user.id)

        assert result.can_soft_sleep is True
        assert result.can_wake is True  # implied by soft_sleep
        assert result.granted_by == admin_user.id

    def test_soft_sleep_implies_wake(self, db_session: Session, regular_user: User, admin_user: User):
        update = UserPowerPermissionsUpdate(can_soft_sleep=True, can_wake=False)
        result = update_permissions(db_session, regular_user.id, update, granted_by=admin_user.id)

        assert result.can_soft_sleep is True
        assert result.can_wake is True  # implication overrides explicit False

    def test_suspend_implies_wol(self, db_session: Session, regular_user: User, admin_user: User):
        update = UserPowerPermissionsUpdate(can_suspend=True)
        result = update_permissions(db_session, regular_user.id, update, granted_by=admin_user.id)

        assert result.can_suspend is True
        assert result.can_wol is True  # implied by suspend

    def test_disable_wake_disables_soft_sleep(self, db_session: Session, regular_user: User, admin_user: User):
        # First grant both
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_soft_sleep=True),
            granted_by=admin_user.id,
        )
        # Now disable wake
        result = update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_wake=False),
            granted_by=admin_user.id,
        )
        assert result.can_wake is False
        assert result.can_soft_sleep is False  # reverse implication

    def test_disable_wol_disables_suspend(self, db_session: Session, regular_user: User, admin_user: User):
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_suspend=True),
            granted_by=admin_user.id,
        )
        result = update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_wol=False),
            granted_by=admin_user.id,
        )
        assert result.can_wol is False
        assert result.can_suspend is False

    def test_updates_existing_entry(self, db_session: Session, regular_user: User, admin_user: User):
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_soft_sleep=True),
            granted_by=admin_user.id,
        )
        result = update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_suspend=True),
            granted_by=admin_user.id,
        )
        assert result.can_soft_sleep is True
        assert result.can_suspend is True
        assert result.can_wake is True
        assert result.can_wol is True


class TestCheckPermission:
    def test_returns_false_when_no_entry(self, db_session: Session, regular_user: User):
        assert check_permission(db_session, regular_user.id, "soft_sleep") is False

    def test_returns_true_when_granted(self, db_session: Session, regular_user: User, admin_user: User):
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_soft_sleep=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, regular_user.id, "soft_sleep") is True
        assert check_permission(db_session, regular_user.id, "wake") is True
        assert check_permission(db_session, regular_user.id, "suspend") is False

    def test_returns_false_for_unknown_action(self, db_session: Session, regular_user: User):
        assert check_permission(db_session, regular_user.id, "reboot") is False
