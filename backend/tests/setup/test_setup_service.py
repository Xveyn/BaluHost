"""Tests for setup wizard service.

TDD: Tests written first, then implementation.
Covers is_setup_required, get_completed_steps, complete_setup, is_setup_complete.
"""

from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import users as user_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_admin(db: Session) -> User:
    """Create an admin user in the test DB."""
    return user_service.create_user(
        UserCreate(
            username="setupadmin",
            email="setupadmin@example.com",
            password="AdminPass123",
            role="admin",
        ),
        db=db,
    )


def _create_regular_user(db: Session) -> User:
    """Create a regular user in the test DB."""
    return user_service.create_user(
        UserCreate(
            username="regularuser",
            email="regular@example.com",
            password="UserPass1234",
            role="user",
        ),
        db=db,
    )


# ============================================================================
# is_setup_required
# ============================================================================

class TestIsSetupRequired:
    """Tests for is_setup_required(db)."""

    def test_required_when_no_users(self, db_session: Session):
        """Setup is required when the users table is empty."""
        from app.services.setup.service import is_setup_required, _reset_setup_complete

        _reset_setup_complete()
        assert is_setup_required(db_session) is True

    def test_not_required_when_user_exists(self, db_session: Session):
        """Setup is NOT required when at least one user exists."""
        from app.services.setup.service import is_setup_required, _reset_setup_complete

        _reset_setup_complete()
        _create_admin(db_session)
        assert is_setup_required(db_session) is False

    def test_not_required_when_skip_setup_true(self, db_session: Session):
        """Setup is NOT required when settings.skip_setup is True."""
        from app.services.setup.service import is_setup_required, _reset_setup_complete

        _reset_setup_complete()
        original = settings.skip_setup
        try:
            settings.skip_setup = True  # type: ignore[misc]
            assert is_setup_required(db_session) is False
        finally:
            settings.skip_setup = original  # type: ignore[misc]

    def test_not_required_when_setup_complete_flag_set(self, db_session: Session):
        """Setup is NOT required when complete_setup() was called."""
        from app.services.setup.service import (
            is_setup_required,
            complete_setup,
            _reset_setup_complete,
        )

        _reset_setup_complete()
        # No users, but flag is set
        complete_setup(db_session)
        assert is_setup_required(db_session) is False

    def test_skip_setup_takes_priority_over_no_users(self, db_session: Session):
        """skip_setup=True makes setup not required even without users."""
        from app.services.setup.service import is_setup_required, _reset_setup_complete

        _reset_setup_complete()
        original = settings.skip_setup
        try:
            settings.skip_setup = True  # type: ignore[misc]
            # No users in DB
            assert is_setup_required(db_session) is False
        finally:
            settings.skip_setup = original  # type: ignore[misc]


# ============================================================================
# complete_setup / is_setup_complete
# ============================================================================

class TestCompleteSetup:
    """Tests for complete_setup and is_setup_complete."""

    def test_initially_not_complete(self, db_session: Session):
        """is_setup_complete returns False before complete_setup is called."""
        from app.services.setup.service import is_setup_complete, _reset_setup_complete

        _reset_setup_complete()
        assert is_setup_complete(db_session) is False

    def test_complete_setup_sets_flag(self, db_session: Session):
        """complete_setup sets the in-memory flag to True."""
        from app.services.setup.service import (
            complete_setup,
            is_setup_complete,
            _reset_setup_complete,
        )

        _reset_setup_complete()
        complete_setup(db_session)
        assert is_setup_complete(db_session) is True

    def test_flag_persists_across_calls(self, db_session: Session):
        """Once set, is_setup_complete stays True."""
        from app.services.setup.service import (
            complete_setup,
            is_setup_complete,
            _reset_setup_complete,
        )

        _reset_setup_complete()
        complete_setup(db_session)
        assert is_setup_complete(db_session) is True
        # Call again — still True
        assert is_setup_complete(db_session) is True


# ============================================================================
# get_completed_steps
# ============================================================================

class TestGetCompletedSteps:
    """Tests for get_completed_steps(db)."""

    def test_no_steps_when_empty(self, db_session: Session):
        """Returns empty list when no users, no RAID, no file access."""
        from app.services.setup.service import get_completed_steps

        steps = get_completed_steps(db_session)
        # No admin, no regular user -> "admin" and "users" should not be present
        assert "admin" not in steps
        assert "users" not in steps

    def test_admin_step_when_admin_exists(self, db_session: Session):
        """'admin' step is completed when an admin user exists."""
        from app.services.setup.service import get_completed_steps

        _create_admin(db_session)
        steps = get_completed_steps(db_session)
        assert "admin" in steps

    def test_admin_step_not_present_with_only_regular_user(self, db_session: Session):
        """'admin' step is NOT completed when only regular users exist."""
        from app.services.setup.service import get_completed_steps

        _create_regular_user(db_session)
        steps = get_completed_steps(db_session)
        assert "admin" not in steps

    def test_users_step_when_regular_user_exists(self, db_session: Session):
        """'users' step is completed when a non-admin user exists."""
        from app.services.setup.service import get_completed_steps

        _create_regular_user(db_session)
        steps = get_completed_steps(db_session)
        assert "users" in steps

    def test_users_step_not_present_with_only_admin(self, db_session: Session):
        """'users' step is NOT completed when only admin users exist."""
        from app.services.setup.service import get_completed_steps

        _create_admin(db_session)
        steps = get_completed_steps(db_session)
        assert "users" not in steps

    def test_both_admin_and_users_steps(self, db_session: Session):
        """Both 'admin' and 'users' steps present when both roles exist."""
        from app.services.setup.service import get_completed_steps

        _create_admin(db_session)
        _create_regular_user(db_session)
        steps = get_completed_steps(db_session)
        assert "admin" in steps
        assert "users" in steps

    def test_raid_step_with_arrays(self, db_session: Session):
        """'raid' step is completed when RAID arrays exist."""
        from app.services.setup.service import get_completed_steps

        mock_status = MagicMock()
        mock_status.arrays = [MagicMock()]  # At least one array

        with patch(
            "app.services.setup.service.raid_api.get_status",
            return_value=mock_status,
        ):
            steps = get_completed_steps(db_session)
            assert "raid" in steps

    def test_raid_step_without_arrays(self, db_session: Session):
        """'raid' step is NOT completed when no RAID arrays exist."""
        from app.services.setup.service import get_completed_steps

        mock_status = MagicMock()
        mock_status.arrays = []

        with patch(
            "app.services.setup.service.raid_api.get_status",
            return_value=mock_status,
        ):
            steps = get_completed_steps(db_session)
            assert "raid" not in steps

    def test_raid_step_handles_exception(self, db_session: Session):
        """'raid' step is absent (no crash) when raid_api raises an error."""
        from app.services.setup.service import get_completed_steps

        with patch(
            "app.services.setup.service.raid_api.get_status",
            side_effect=Exception("RAID unavailable"),
        ):
            steps = get_completed_steps(db_session)
            assert "raid" not in steps

    def test_file_access_step_with_webdav_running(self, db_session: Session):
        """'file_access' step is completed when WebDAV is running."""
        from app.services.setup.service import get_completed_steps
        from app.models.webdav_state import WebdavState

        # Insert a WebDAV state row showing is_running=True
        state = WebdavState(id=1, is_running=True, port=8080, ssl_enabled=False)
        db_session.add(state)
        db_session.commit()

        with patch(
            "app.services.setup.service.samba_service.get_samba_status",
            return_value={"is_running": False},
        ):
            steps = get_completed_steps(db_session)
            assert "file_access" in steps

    def test_file_access_step_with_samba_running(self, db_session: Session):
        """'file_access' step is completed when Samba is running."""
        from app.services.setup.service import get_completed_steps

        with patch(
            "app.services.setup.service.samba_service.get_samba_status",
            return_value={"is_running": True},
        ):
            steps = get_completed_steps(db_session)
            assert "file_access" in steps

    def test_file_access_step_when_nothing_running(self, db_session: Session):
        """'file_access' step is absent when neither Samba nor WebDAV is running."""
        from app.services.setup.service import get_completed_steps

        with patch(
            "app.services.setup.service.samba_service.get_samba_status",
            return_value={"is_running": False},
        ):
            steps = get_completed_steps(db_session)
            assert "file_access" not in steps

    def test_file_access_handles_samba_exception(self, db_session: Session):
        """'file_access' step doesn't crash when samba_service raises an error."""
        from app.services.setup.service import get_completed_steps

        with patch(
            "app.services.setup.service.samba_service.get_samba_status",
            side_effect=Exception("Samba unavailable"),
        ):
            # Should not raise
            steps = get_completed_steps(db_session)
            assert "file_access" not in steps

    def test_returns_list_of_strings(self, db_session: Session):
        """get_completed_steps always returns a list of strings."""
        from app.services.setup.service import get_completed_steps

        steps = get_completed_steps(db_session)
        assert isinstance(steps, list)
        for step in steps:
            assert isinstance(step, str)
