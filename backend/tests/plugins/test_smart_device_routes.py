"""Integration tests for /api/smart-devices/ API routes."""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.smart_device.manager import SmartDeviceManager

_PATCH_MGR = "app.api.routes.smart_devices.get_smart_device_manager"
_PATCH_AUDIT = "app.api.routes.smart_devices.AuditLoggerDB"

# =============================================================================
# Helpers
# =============================================================================

API_PREFIX = f"{settings.api_prefix}/smart-devices"


def _create_device_row(
    db: Session,
    name: str = "Test Device",
    plugin_name: str = "mock_plugin",
    device_type_id: str = "mock_plug",
    address: str = "192.168.1.100",
    capabilities: list | None = None,
    is_active: bool = True,
    is_online: bool = False,
) -> SmartDevice:
    """Create a SmartDevice directly in the test DB."""
    device = SmartDevice(
        name=name,
        plugin_name=plugin_name,
        device_type_id=device_type_id,
        address=address,
        capabilities=capabilities or ["switch", "power_monitor"],
        is_active=is_active,
        is_online=is_online,
        created_by_user_id=1,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _create_sample_row(
    db: Session,
    device_id: int,
    capability: str = "switch",
    data: dict | None = None,
    ts: datetime | None = None,
) -> SmartDeviceSample:
    sample = SmartDeviceSample(
        device_id=device_id,
        capability=capability,
        data_json=json.dumps(data or {"is_on": True}),
        timestamp=ts or datetime.now(timezone.utc),
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return sample


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the SmartDeviceManager singleton between tests."""
    SmartDeviceManager.reset_instance()
    yield
    SmartDeviceManager.reset_instance()


# =============================================================================
# Authentication enforcement
# =============================================================================


class TestAuthEnforcement:
    def test_list_devices_requires_auth(self, client: TestClient):
        resp = client.get(f"{API_PREFIX}/")
        assert resp.status_code in (401, 403)

    def test_get_device_requires_auth(self, client: TestClient):
        resp = client.get(f"{API_PREFIX}/1")
        assert resp.status_code in (401, 403)

    def test_create_device_requires_auth(self, client: TestClient):
        resp = client.post(f"{API_PREFIX}/", json={"name": "x", "plugin_name": "y", "device_type_id": "z", "address": "a"})
        assert resp.status_code in (401, 403)

    def test_update_device_requires_auth(self, client: TestClient):
        resp = client.patch(f"{API_PREFIX}/1", json={"name": "new"})
        assert resp.status_code in (401, 403)

    def test_delete_device_requires_auth(self, client: TestClient):
        resp = client.delete(f"{API_PREFIX}/1")
        assert resp.status_code in (401, 403)

    def test_command_requires_auth(self, client: TestClient):
        resp = client.post(f"{API_PREFIX}/1/command", json={"capability": "switch", "command": "turn_on"})
        assert resp.status_code in (401, 403)

    def test_types_requires_auth(self, client: TestClient):
        resp = client.get(f"{API_PREFIX}/types")
        assert resp.status_code in (401, 403)

    def test_power_summary_requires_auth(self, client: TestClient):
        resp = client.get(f"{API_PREFIX}/power/summary")
        assert resp.status_code in (401, 403)

    def test_history_requires_auth(self, client: TestClient):
        resp = client.get(f"{API_PREFIX}/1/history")
        assert resp.status_code in (401, 403)


class TestAdminOnlyEndpoints:
    """Write endpoints should reject non-admin users."""

    def test_create_device_user_forbidden(self, client: TestClient, user_headers: dict):
        resp = client.post(
            f"{API_PREFIX}/",
            json={"name": "x", "plugin_name": "y", "device_type_id": "z", "address": "a"},
            headers=user_headers,
        )
        assert resp.status_code == 403

    def test_update_device_user_forbidden(self, client: TestClient, user_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        resp = client.patch(
            f"{API_PREFIX}/{dev.id}",
            json={"name": "new"},
            headers=user_headers,
        )
        assert resp.status_code == 403

    def test_delete_device_user_forbidden(self, client: TestClient, user_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        resp = client.delete(f"{API_PREFIX}/{dev.id}", headers=user_headers)
        assert resp.status_code == 403

    def test_command_user_forbidden(self, client: TestClient, user_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        resp = client.post(
            f"{API_PREFIX}/{dev.id}/command",
            json={"capability": "switch", "command": "turn_on"},
            headers=user_headers,
        )
        assert resp.status_code == 403


# =============================================================================
# GET /smart-devices/types
# =============================================================================


class TestListDeviceTypes:
    def test_returns_types(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_all_device_types.return_value = [
                {
                    "type_id": "tapo_p115",
                    "display_name": "Tapo P115",
                    "manufacturer": "TP-Link",
                    "capabilities": ["switch", "power_monitor"],
                    "config_schema": None,
                    "icon": "plug",
                    "plugin_name": "tapo_smart_plug",
                }
            ]
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/types", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["type_id"] == "tapo_p115"
            assert data[0]["plugin_name"] == "tapo_smart_plug"

    def test_returns_empty_list(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_all_device_types.return_value = []
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/types", headers=admin_headers)
            assert resp.status_code == 200
            assert resp.json() == []


# =============================================================================
# GET /smart-devices/
# =============================================================================


class TestListDevices:
    def test_list_devices_empty(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.list_devices.return_value = []
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["devices"] == []
            assert data["total"] == 0

    def test_list_devices_with_data(self, client: TestClient, admin_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.list_devices.return_value = [dev]
            mock_mgr.get_device_state.return_value = {"switch": {"is_on": True}}
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["devices"][0]["name"] == "Test Device"
            assert data["devices"][0]["state"]["switch"]["is_on"] is True

    def test_list_devices_accessible_by_regular_user(self, client: TestClient, user_headers: dict):
        """Read endpoint accessible to any authenticated user."""
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.list_devices.return_value = []
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/", headers=user_headers)
            assert resp.status_code == 200


# =============================================================================
# POST /smart-devices/  (Admin only)
# =============================================================================


class TestCreateDevice:
    def test_create_device_success(self, client: TestClient, admin_headers: dict, db_session: Session):
        dev = _create_device_row(db_session, name="New Plug")
        with patch(_PATCH_MGR) as mock_get_mgr, patch(_PATCH_AUDIT):
            mock_mgr = MagicMock()
            mock_mgr.create_device.return_value = dev
            mock_get_mgr.return_value = mock_mgr

            resp = client.post(
                f"{API_PREFIX}/",
                json={
                    "name": "New Plug",
                    "plugin_name": "mock_plugin",
                    "device_type_id": "mock_plug",
                    "address": "192.168.1.50",
                },
                headers=admin_headers,
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["name"] == "New Plug"
            mock_mgr.create_device.assert_called_once()

    def test_create_device_bad_request(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.create_device.side_effect = ValueError("Unknown plugin 'bad'")
            mock_get_mgr.return_value = mock_mgr

            resp = client.post(
                f"{API_PREFIX}/",
                json={
                    "name": "Bad",
                    "plugin_name": "bad",
                    "device_type_id": "x",
                    "address": "10.0.0.1",
                },
                headers=admin_headers,
            )
            assert resp.status_code == 400
            assert "Unknown plugin" in resp.json()["detail"]


# =============================================================================
# GET /smart-devices/{id}
# =============================================================================


class TestGetDevice:
    def test_get_device_success(self, client: TestClient, admin_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = dev
            mock_mgr.get_device_state.return_value = None
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/{dev.id}", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == dev.id
            assert data["name"] == "Test Device"

    def test_get_device_not_found(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = None
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/9999", headers=admin_headers)
            assert resp.status_code == 404

    def test_get_device_accessible_by_regular_user(self, client: TestClient, user_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = dev
            mock_mgr.get_device_state.return_value = None
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/{dev.id}", headers=user_headers)
            assert resp.status_code == 200


# =============================================================================
# PATCH /smart-devices/{id}  (Admin only)
# =============================================================================


class TestUpdateDevice:
    def test_update_device_success(self, client: TestClient, admin_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        dev.name = "Updated Name"
        with patch(_PATCH_MGR) as mock_get_mgr, patch(_PATCH_AUDIT):
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = dev
            mock_mgr.update_device.return_value = dev
            mock_mgr.get_device_state.return_value = None
            mock_get_mgr.return_value = mock_mgr

            resp = client.patch(
                f"{API_PREFIX}/{dev.id}",
                json={"name": "Updated Name"},
                headers=admin_headers,
            )
            assert resp.status_code == 200
            assert resp.json()["name"] == "Updated Name"

    def test_update_device_not_found(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = None
            mock_get_mgr.return_value = mock_mgr

            resp = client.patch(
                f"{API_PREFIX}/9999",
                json={"name": "x"},
                headers=admin_headers,
            )
            assert resp.status_code == 404


# =============================================================================
# DELETE /smart-devices/{id}  (Admin only)
# =============================================================================


class TestDeleteDevice:
    def test_delete_device_success(self, client: TestClient, admin_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        with patch(_PATCH_MGR) as mock_get_mgr, patch(_PATCH_AUDIT):
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = dev
            mock_get_mgr.return_value = mock_mgr

            resp = client.delete(f"{API_PREFIX}/{dev.id}", headers=admin_headers)
            assert resp.status_code == 204

    def test_delete_device_not_found(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = None
            mock_get_mgr.return_value = mock_mgr

            resp = client.delete(f"{API_PREFIX}/9999", headers=admin_headers)
            assert resp.status_code == 404


# =============================================================================
# POST /smart-devices/{id}/command  (Admin only)
# =============================================================================


class TestExecuteCommand:
    def test_command_success(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr, patch(_PATCH_AUDIT):
            mock_mgr = MagicMock()
            mock_mgr.execute_command = AsyncMock(return_value={
                "success": True,
                "state": {"is_on": True},
                "error": None,
            })
            mock_get_mgr.return_value = mock_mgr

            resp = client.post(
                f"{API_PREFIX}/1/command",
                json={"capability": "switch", "command": "turn_on"},
                headers=admin_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["state"]["is_on"] is True

    def test_command_bad_request(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.execute_command = AsyncMock(side_effect=ValueError("Device 1 not found"))
            mock_get_mgr.return_value = mock_mgr

            resp = client.post(
                f"{API_PREFIX}/1/command",
                json={"capability": "switch", "command": "turn_on"},
                headers=admin_headers,
            )
            assert resp.status_code == 400

    def test_command_generic_failure(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr, patch(_PATCH_AUDIT):
            mock_mgr = MagicMock()
            mock_mgr.execute_command = AsyncMock(side_effect=RuntimeError("Connection lost"))
            mock_get_mgr.return_value = mock_mgr

            resp = client.post(
                f"{API_PREFIX}/1/command",
                json={"capability": "switch", "command": "turn_on"},
                headers=admin_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
            assert "Connection lost" in data["error"]


# =============================================================================
# GET /smart-devices/{id}/history
# =============================================================================


class TestDeviceHistory:
    def test_history_success(self, client: TestClient, admin_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        _create_sample_row(db_session, device_id=dev.id, capability="switch", data={"is_on": True})
        _create_sample_row(db_session, device_id=dev.id, capability="switch", data={"is_on": False})
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = dev
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(
                f"{API_PREFIX}/{dev.id}/history?capability=switch&hours=24",
                headers=admin_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["device_id"] == dev.id
            assert data["capability"] == "switch"
            assert len(data["samples"]) == 2

    def test_history_device_not_found(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = None
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/9999/history", headers=admin_headers)
            assert resp.status_code == 404

    def test_history_empty(self, client: TestClient, admin_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = dev
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(
                f"{API_PREFIX}/{dev.id}/history?capability=switch",
                headers=admin_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["samples"] == []

    def test_history_accessible_by_regular_user(self, client: TestClient, user_headers: dict, db_session: Session):
        dev = _create_device_row(db_session)
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_device.return_value = dev
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/{dev.id}/history", headers=user_headers)
            assert resp.status_code == 200


# =============================================================================
# GET /smart-devices/power/summary
# =============================================================================


class TestPowerSummary:
    def test_power_summary(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_power_summary.return_value = {
                "total_watts": 85.3,
                "device_count": 2,
                "devices": [
                    {"device_id": 1, "name": "Plug A", "watts": 42.0},
                    {"device_id": 2, "name": "Plug B", "watts": 43.3},
                ],
            }
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/power/summary", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_watts"] == 85.3
            assert data["device_count"] == 2
            assert len(data["devices"]) == 2

    def test_power_summary_empty(self, client: TestClient, admin_headers: dict):
        with patch(_PATCH_MGR) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.get_power_summary.return_value = {
                "total_watts": 0.0,
                "device_count": 0,
                "devices": [],
            }
            mock_get_mgr.return_value = mock_mgr

            resp = client.get(f"{API_PREFIX}/power/summary", headers=admin_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_watts"] == 0.0
