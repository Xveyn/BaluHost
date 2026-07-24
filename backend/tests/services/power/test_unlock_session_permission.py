"""The can_unlock_session permission and its action mapping."""
from __future__ import annotations

from app.models.power_permissions import UserPowerPermission
from app.services.power_permissions import _ACTION_FIELD_MAP, check_permission


class TestActionMapping:
    def test_unlock_session_is_mapped(self):
        """check_permission() returns False for unknown actions instead of
        raising, so a missing map entry is invisible: the feature would simply
        never work for delegated users, with no error anywhere."""
        assert _ACTION_FIELD_MAP["unlock_session"] == "can_unlock_session"


class TestCheckPermission:
    def test_granted_user_passes(self, db_session, regular_user):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_unlock_session=True)
        )
        db_session.commit()

        assert check_permission(db_session, regular_user.id, "unlock_session") is True

    def test_user_without_the_permission_is_rejected(self, db_session, regular_user):
        db_session.add(
            UserPowerPermission(user_id=regular_user.id, can_toggle_desktop=True)
        )
        db_session.commit()

        assert check_permission(db_session, regular_user.id, "unlock_session") is False

    def test_default_is_off(self, db_session, regular_user):
        """No row at all must not grant anything."""
        assert check_permission(db_session, regular_user.id, "unlock_session") is False


class TestRoundTrip:
    """Nothing in this repo passes power permissions through generically -
    every read and write lists the fields one by one. A column plus a schema
    field yields a checkbox that saves nothing and reports itself as off."""

    def test_update_then_get_returns_the_granted_permission(
        self, db_session, regular_user, admin_user
    ):
        from app.schemas.power_permissions import UserPowerPermissionsUpdate
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session,
            regular_user.id,
            UserPowerPermissionsUpdate(can_unlock_session=True),
            granted_by=admin_user.id,
        )

        assert get_permissions(db_session, regular_user.id).can_unlock_session is True

    def test_revoking_works_too(self, db_session, regular_user, admin_user):
        from app.schemas.power_permissions import UserPowerPermissionsUpdate
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_unlock_session=True), granted_by=admin_user.id,
        )
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_unlock_session=False), granted_by=admin_user.id,
        )

        assert get_permissions(db_session, regular_user.id).can_unlock_session is False

    def test_the_change_reaches_the_audit_diff(
        self, db_session, regular_user, admin_user
    ):
        """old/new are built from explicit dicts - a missing entry hides the
        grant from the security trail."""
        from unittest.mock import MagicMock, patch

        from app.schemas.power_permissions import UserPowerPermissionsUpdate
        from app.services import power_permissions as svc

        with patch.object(svc, "get_audit_logger_db") as factory:
            logger = MagicMock()
            factory.return_value = logger
            svc.update_permissions(
                db_session, regular_user.id,
                UserPowerPermissionsUpdate(can_unlock_session=True),
                granted_by=admin_user.id,
            )

        details = logger.log_security_event.call_args.kwargs["details"]
        assert details["new"]["can_unlock_session"] is True
