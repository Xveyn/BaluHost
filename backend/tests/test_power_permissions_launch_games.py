"""Das Spielstart-Recht: Standard aus, Admin implizit, keine Implikation."""
from app.schemas.power_permissions import (
    MyPowerPermissionsResponse,
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.power_permissions import _ACTION_FIELD_MAP


class TestWiring:
    def test_the_action_maps_to_the_column(self):
        assert _ACTION_FIELD_MAP["launch_games"] == "can_launch_games"

    def test_the_dependency_exists(self):
        from app.api import deps
        assert hasattr(deps, "require_power_launch_games")

    def test_the_model_has_the_column(self):
        from app.models.power_permissions import UserPowerPermission
        assert hasattr(UserPowerPermission, "can_launch_games")


class TestSchemas:
    def test_it_defaults_to_denied(self):
        assert UserPowerPermissionsResponse(user_id=1).can_launch_games is False
        assert MyPowerPermissionsResponse().can_launch_games is False

    def test_the_update_schema_leaves_it_untouched_by_default(self):
        assert UserPowerPermissionsUpdate().can_launch_games is None


class TestGrantAndRevoke:
    def test_granting_and_revoking_round_trip(self, db_session, test_user, admin_user):
        from app.services.power_permissions import check_permission, update_permissions

        assert check_permission(db_session, test_user.id, "launch_games") is False
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "launch_games") is True
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=False),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "launch_games") is False

    def test_it_implies_neither_unlock_nor_desktop(self, db_session, test_user, admin_user):
        """A launch right must not silently open the physical desktop."""
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=True),
            granted_by=admin_user.id,
        )
        perms = get_permissions(db_session, test_user.id)
        assert perms.can_launch_games is True
        assert perms.can_unlock_session is False
        assert perms.can_toggle_desktop is False

    def test_the_audit_values_carry_the_field(self, db_session, test_user, admin_user, monkeypatch):
        import app.services.power_permissions as svc

        captured: list[dict] = []

        class _Recorder:
            def log_security_event(self, **kwargs):
                captured.append(kwargs)

        monkeypatch.setattr(svc, "get_audit_logger_db", lambda: _Recorder())
        svc.update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=True),
            granted_by=admin_user.id,
        )
        assert captured[0]["details"]["old"]["can_launch_games"] is False
        assert captured[0]["details"]["new"]["can_launch_games"] is True


class TestMyPermissions:
    def test_admins_get_it(self, client, admin_headers):
        resp = client.get("/api/system/sleep/my-permissions", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["can_launch_games"] is True
