"""Das Bluetooth-Recht: Standard aus, Admin implizit, keine Implikation."""
from app.schemas.power_permissions import (
    MyPowerPermissionsResponse,
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.power_permissions import _ACTION_FIELD_MAP


class TestWiring:
    def test_the_action_maps_to_the_column(self):
        assert _ACTION_FIELD_MAP["manage_bluetooth"] == "can_manage_bluetooth"

    def test_the_dependency_exists(self):
        from app.api import deps
        assert hasattr(deps, "require_power_manage_bluetooth")

    def test_the_model_has_the_column(self):
        from app.models.power_permissions import UserPowerPermission
        assert hasattr(UserPowerPermission, "can_manage_bluetooth")


class TestSchemas:
    def test_it_defaults_to_denied(self):
        assert UserPowerPermissionsResponse(user_id=1).can_manage_bluetooth is False
        assert MyPowerPermissionsResponse().can_manage_bluetooth is False

    def test_the_update_schema_leaves_it_untouched_by_default(self):
        assert UserPowerPermissionsUpdate().can_manage_bluetooth is None


class TestGrantAndRevoke:
    def test_granting_and_revoking_round_trip(self, db_session, test_user, admin_user):
        from app.services.power_permissions import check_permission, update_permissions

        assert check_permission(db_session, test_user.id, "manage_bluetooth") is False
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_bluetooth") is True
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=False),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_bluetooth") is False

    def test_it_does_not_drag_other_permissions_along(self, db_session, test_user, admin_user):
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=True),
            granted_by=admin_user.id,
        )
        perms = get_permissions(db_session, test_user.id)
        assert perms.can_manage_bluetooth is True
        assert perms.can_control_audio is False
        assert perms.can_suspend is False

    def test_the_audit_values_carry_the_field(self, db_session, test_user, admin_user, monkeypatch):
        import app.services.power_permissions as svc

        captured: list[dict] = []

        class _Recorder:
            def log_security_event(self, **kwargs):
                captured.append(kwargs)

        monkeypatch.setattr(svc, "get_audit_logger_db", lambda: _Recorder())
        svc.update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=True),
            granted_by=admin_user.id,
        )
        assert captured[0]["details"]["old"]["can_manage_bluetooth"] is False
        assert captured[0]["details"]["new"]["can_manage_bluetooth"] is True
