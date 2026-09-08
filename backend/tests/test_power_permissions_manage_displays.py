"""Das neue Power-Recht: Standard aus, Admin implizit, sauber verdrahtet."""
import pytest

from app.schemas.power_permissions import (
    MyPowerPermissionsResponse,
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.power_permissions import _ACTION_FIELD_MAP


class TestWiring:
    def test_the_action_maps_to_the_column(self):
        assert _ACTION_FIELD_MAP["manage_displays"] == "can_manage_displays"

    def test_the_dependency_exists(self):
        from app.api import deps
        assert hasattr(deps, "require_power_manage_displays")

    def test_the_model_has_the_column(self):
        from app.models.power_permissions import UserPowerPermission
        assert hasattr(UserPowerPermission, "can_manage_displays")


class TestSchemas:
    def test_it_defaults_to_denied(self):
        assert UserPowerPermissionsResponse(user_id=1).can_manage_displays is False
        assert MyPowerPermissionsResponse().can_manage_displays is False

    def test_the_update_schema_leaves_it_untouched_by_default(self):
        # None heisst "nicht angefasst" - nicht "entziehen".
        assert UserPowerPermissionsUpdate().can_manage_displays is None

    def test_the_update_schema_accepts_it(self):
        assert UserPowerPermissionsUpdate(can_manage_displays=True).can_manage_displays is True


class TestGrantAndRevoke:
    def test_granting_and_revoking_round_trip(self, db_session, test_user, admin_user):
        from app.services.power_permissions import check_permission, update_permissions

        assert check_permission(db_session, test_user.id, "manage_displays") is False

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_displays=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_displays") is True

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_displays=False),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_displays") is False

    def test_it_does_not_drag_other_permissions_along(self, db_session, test_user, admin_user):
        # Es steht neben den Sleep-Ketten und ist bewusst nicht in
        # _apply_implications - wie can_control_audio.
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_displays=True),
            granted_by=admin_user.id,
        )
        perms = get_permissions(db_session, test_user.id)
        assert perms.can_manage_displays is True
        assert perms.can_suspend is False
        assert perms.can_toggle_desktop is False
