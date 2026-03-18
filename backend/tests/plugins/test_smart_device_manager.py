"""Tests for SmartDeviceManager — CRUD, command dispatch, state reads."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.base import PluginMetadata
from app.plugins.smart_device.base import DeviceTypeInfo, SmartDevicePlugin
from app.plugins.smart_device.capabilities import (
    ColorControl,
    ColorState,
    DeviceCapability,
    Dimmer,
    DimmerState,
    Switch,
    SwitchState,
)
from app.plugins.smart_device.manager import SmartDeviceManager, get_smart_device_manager
from app.plugins.smart_device.schemas import SmartDeviceCreate, SmartDeviceUpdate


# =============================================================================
# Mock plugin
# =============================================================================


class MockSmartPlugin(SmartDevicePlugin):
    """A concrete mock SmartDevicePlugin for testing."""

    def __init__(self, name: str = "mock_plugin"):
        self._name = name

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name,
            version="1.0.0",
            display_name="Mock Smart Plugin",
            description="A mock smart device plugin for testing",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="mock_plug",
                display_name="Mock Smart Plug",
                manufacturer="MockCorp",
                capabilities=[DeviceCapability.SWITCH, DeviceCapability.POWER_MONITOR],
                config_schema={"type": "object", "properties": {"ip": {"type": "string"}}},
            ),
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {"switch": SwitchState(is_on=True)}

    # Implement Switch protocol so execute_command works
    async def turn_on(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True, changed_at=datetime.now(timezone.utc))

    async def turn_off(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=False, changed_at=datetime.now(timezone.utc))

    async def get_switch_state(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True)


class MockDimmerPlugin(SmartDevicePlugin):
    """Plugin implementing Dimmer capability."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="mock_dimmer",
            version="1.0.0",
            display_name="Mock Dimmer Plugin",
            description="A mock dimmer plugin",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="mock_dimmer",
                display_name="Mock Dimmer",
                manufacturer="MockCorp",
                capabilities=[DeviceCapability.DIMMER],
            ),
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {}

    async def set_brightness(self, device_id: str, brightness: int) -> DimmerState:
        return DimmerState(brightness=brightness, is_on=True)

    async def get_dimmer_state(self, device_id: str) -> DimmerState:
        return DimmerState(brightness=50, is_on=True)


class MockColorPlugin(SmartDevicePlugin):
    """Plugin implementing ColorControl capability."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="mock_color",
            version="1.0.0",
            display_name="Mock Color Plugin",
            description="A mock color plugin",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="mock_color_bulb",
                display_name="Mock Color Bulb",
                manufacturer="MockCorp",
                capabilities=[DeviceCapability.COLOR],
            ),
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {}

    async def set_color(self, device_id: str, hue: int, saturation: int, brightness: int) -> ColorState:
        return ColorState(hue=hue, saturation=saturation, brightness=brightness, is_on=True)

    async def set_color_temp(self, device_id: str, kelvin: int) -> ColorState:
        return ColorState(hue=0, saturation=0, brightness=100, color_temp_kelvin=kelvin, is_on=True)

    async def get_color_state(self, device_id: str) -> ColorState:
        return ColorState(hue=0, saturation=0, brightness=100, is_on=True)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the SmartDeviceManager singleton between tests."""
    SmartDeviceManager.reset_instance()
    yield
    SmartDeviceManager.reset_instance()


@pytest.fixture
def manager() -> SmartDeviceManager:
    """Return a fresh SmartDeviceManager with no plugins."""
    return SmartDeviceManager()


@pytest.fixture
def manager_with_plugin() -> SmartDeviceManager:
    """Return a SmartDeviceManager with MockSmartPlugin registered."""
    mgr = SmartDeviceManager()
    mgr.register_plugin(MockSmartPlugin())
    return mgr


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
    """Helper to create a SmartDevice directly in DB."""
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


# =============================================================================
# Singleton
# =============================================================================


class TestSingleton:
    def test_get_instance_returns_same_object(self):
        a = SmartDeviceManager.get_instance()
        b = SmartDeviceManager.get_instance()
        assert a is b

    def test_reset_instance_clears(self):
        a = SmartDeviceManager.get_instance()
        SmartDeviceManager.reset_instance()
        b = SmartDeviceManager.get_instance()
        assert a is not b

    def test_get_smart_device_manager_returns_singleton(self):
        mgr = get_smart_device_manager()
        assert mgr is SmartDeviceManager.get_instance()


# =============================================================================
# Plugin registration
# =============================================================================


class TestPluginRegistration:
    def test_register_plugin(self, manager: SmartDeviceManager):
        plugin = MockSmartPlugin()
        manager.register_plugin(plugin)
        assert manager.get_plugin("mock_plugin") is plugin

    def test_get_plugin_returns_none_for_unknown(self, manager: SmartDeviceManager):
        assert manager.get_plugin("nonexistent") is None

    def test_list_plugins(self, manager: SmartDeviceManager):
        p1 = MockSmartPlugin("plugin_a")
        p2 = MockSmartPlugin("plugin_b")
        manager.register_plugin(p1)
        manager.register_plugin(p2)
        plugins = manager.list_plugins()
        assert len(plugins) == 2

    def test_register_overwrites_same_name(self, manager: SmartDeviceManager):
        p1 = MockSmartPlugin("same_name")
        p2 = MockSmartPlugin("same_name")
        manager.register_plugin(p1)
        manager.register_plugin(p2)
        assert manager.get_plugin("same_name") is p2


# =============================================================================
# CRUD: create_device
# =============================================================================


class TestCreateDevice:
    @patch("app.plugins.smart_device.manager.VPNEncryption")
    def test_create_device_success(self, mock_encryption, manager_with_plugin, db_session):
        mock_encryption.encrypt_key.return_value = "encrypted_config_data"

        data = SmartDeviceCreate(
            name="Living Room Plug",
            plugin_name="mock_plugin",
            device_type_id="mock_plug",
            address="192.168.1.100",
            config={"ip": "192.168.1.100", "username": "admin", "password": "secret"},
        )
        device = manager_with_plugin.create_device(db_session, data, created_by_user_id=1)

        assert device.id is not None
        assert device.name == "Living Room Plug"
        assert device.plugin_name == "mock_plugin"
        assert device.device_type_id == "mock_plug"
        assert device.address == "192.168.1.100"
        assert device.is_active is True
        assert device.is_online is False
        assert device.created_by_user_id == 1
        # Capabilities derived from device type
        assert "switch" in device.capabilities
        assert "power_monitor" in device.capabilities

    @patch("app.plugins.smart_device.manager.VPNEncryption")
    def test_create_device_encrypts_config(self, mock_encryption, manager_with_plugin, db_session):
        mock_encryption.encrypt_key.return_value = "encrypted_data"

        data = SmartDeviceCreate(
            name="Test",
            plugin_name="mock_plugin",
            device_type_id="mock_plug",
            address="10.0.0.1",
            config={"password": "secret123"},
        )
        device = manager_with_plugin.create_device(db_session, data, created_by_user_id=1)

        mock_encryption.encrypt_key.assert_called_once()
        assert device.config_secret == "encrypted_data"

    def test_create_device_no_config(self, manager_with_plugin, db_session):
        """Device without config should have no config_secret."""
        data = SmartDeviceCreate(
            name="Simple Device",
            plugin_name="mock_plugin",
            device_type_id="mock_plug",
            address="10.0.0.2",
        )
        device = manager_with_plugin.create_device(db_session, data, created_by_user_id=1)
        assert device.config_secret is None

    def test_create_device_unknown_plugin(self, manager, db_session):
        data = SmartDeviceCreate(
            name="Ghost",
            plugin_name="nonexistent",
            device_type_id="x",
            address="10.0.0.1",
        )
        with pytest.raises(ValueError, match="Unknown plugin"):
            manager.create_device(db_session, data, created_by_user_id=1)

    @patch("app.plugins.smart_device.manager.VPNEncryption")
    def test_create_device_encryption_failure(self, mock_encryption, manager_with_plugin, db_session):
        mock_encryption.encrypt_key.side_effect = RuntimeError("Fernet key missing")

        data = SmartDeviceCreate(
            name="Bad Config",
            plugin_name="mock_plugin",
            device_type_id="mock_plug",
            address="10.0.0.1",
            config={"password": "secret"},
        )
        with pytest.raises(ValueError, match="Failed to encrypt"):
            manager_with_plugin.create_device(db_session, data, created_by_user_id=1)


# =============================================================================
# CRUD: get_device, list_devices
# =============================================================================


class TestGetAndListDevices:
    def test_get_device(self, manager, db_session):
        dev = _create_device_row(db_session)
        result = manager.get_device(db_session, dev.id)
        assert result is not None
        assert result.id == dev.id
        assert result.name == "Test Device"

    def test_get_device_not_found(self, manager, db_session):
        assert manager.get_device(db_session, 9999) is None

    def test_list_devices_empty(self, manager, db_session):
        assert manager.list_devices(db_session) == []

    def test_list_devices_returns_all(self, manager, db_session):
        _create_device_row(db_session, name="A")
        _create_device_row(db_session, name="B")
        devices = manager.list_devices(db_session)
        assert len(devices) == 2

    def test_list_devices_filter_by_plugin(self, manager, db_session):
        _create_device_row(db_session, name="A", plugin_name="alpha")
        _create_device_row(db_session, name="B", plugin_name="beta")
        alpha_devices = manager.list_devices(db_session, plugin_name="alpha")
        assert len(alpha_devices) == 1
        assert alpha_devices[0].name == "A"


# =============================================================================
# CRUD: update_device
# =============================================================================


class TestUpdateDevice:
    def test_update_name(self, manager, db_session):
        dev = _create_device_row(db_session)
        data = SmartDeviceUpdate(name="New Name")
        updated = manager.update_device(db_session, dev, data)
        assert updated.name == "New Name"

    def test_update_address(self, manager, db_session):
        dev = _create_device_row(db_session)
        data = SmartDeviceUpdate(address="10.0.0.99")
        updated = manager.update_device(db_session, dev, data)
        assert updated.address == "10.0.0.99"

    def test_update_is_active(self, manager, db_session):
        dev = _create_device_row(db_session)
        data = SmartDeviceUpdate(is_active=False)
        updated = manager.update_device(db_session, dev, data)
        assert updated.is_active is False

    def test_mass_assignment_prevention(self, manager, db_session):
        """Fields outside the ALLOWED_UPDATE_FIELDS set are ignored."""
        dev = _create_device_row(db_session, plugin_name="original")
        # Even though SmartDeviceUpdate doesn't have plugin_name, verify
        # that only allowed fields are applied
        data = SmartDeviceUpdate(name="Updated")
        updated = manager.update_device(db_session, dev, data)
        assert updated.name == "Updated"
        assert updated.plugin_name == "original"

    @patch("app.plugins.smart_device.manager.VPNEncryption")
    def test_update_config_re_encrypts(self, mock_encryption, manager, db_session):
        mock_encryption.encrypt_key.return_value = "re_encrypted"
        dev = _create_device_row(db_session)
        data = SmartDeviceUpdate(config={"password": "new_secret"})
        updated = manager.update_device(db_session, dev, data)
        mock_encryption.encrypt_key.assert_called_once()
        assert updated.config_secret == "re_encrypted"

    def test_update_sets_updated_at(self, manager, db_session):
        dev = _create_device_row(db_session)
        old_updated = dev.updated_at
        data = SmartDeviceUpdate(name="Changed")
        updated = manager.update_device(db_session, dev, data)
        assert updated.updated_at >= old_updated


# =============================================================================
# CRUD: delete_device
# =============================================================================


class TestDeleteDevice:
    def test_delete_device(self, manager, db_session):
        dev = _create_device_row(db_session)
        device_id = dev.id
        manager.delete_device(db_session, dev)
        assert db_session.query(SmartDevice).filter(SmartDevice.id == device_id).first() is None

    def test_delete_device_with_plugin_disconnect(self, manager_with_plugin, db_session):
        dev = _create_device_row(db_session)
        # Should not raise even though disconnect is called
        manager_with_plugin.delete_device(db_session, dev)
        assert manager_with_plugin.get_device(db_session, dev.id) is None


# =============================================================================
# get_all_device_types
# =============================================================================


class TestGetAllDeviceTypes:
    def test_empty_with_no_plugins(self, manager):
        assert manager.get_all_device_types() == []

    def test_aggregates_across_plugins(self):
        mgr = SmartDeviceManager()
        mgr.register_plugin(MockSmartPlugin())
        mgr.register_plugin(MockDimmerPlugin())
        types = mgr.get_all_device_types()
        assert len(types) == 2
        type_ids = {t["type_id"] for t in types}
        assert "mock_plug" in type_ids
        assert "mock_dimmer" in type_ids

    def test_device_type_has_plugin_name(self, manager_with_plugin):
        types = manager_with_plugin.get_all_device_types()
        assert len(types) == 1
        assert types[0]["plugin_name"] == "mock_plugin"

    def test_device_type_capabilities_are_strings(self, manager_with_plugin):
        types = manager_with_plugin.get_all_device_types()
        for cap in types[0]["capabilities"]:
            assert isinstance(cap, str)


# =============================================================================
# get_device_state
# =============================================================================


class TestGetDeviceState:
    @patch("app.plugins.smart_device.manager.read_shm")
    def test_state_from_shm(self, mock_read_shm, manager, db_session):
        dev = _create_device_row(db_session)
        mock_read_shm.return_value = {
            "devices": {
                str(dev.id): {
                    "state": {"switch": {"is_on": True}},
                }
            }
        }
        state = manager.get_device_state(dev.id, db_session)
        assert state is not None
        assert state["switch"]["is_on"] is True

    @patch("app.plugins.smart_device.manager.read_shm")
    def test_state_fallback_to_db(self, mock_read_shm, manager, db_session):
        """When SHM has no data, falls back to DB samples."""
        mock_read_shm.return_value = None

        dev = _create_device_row(db_session)
        sample = SmartDeviceSample(
            device_id=dev.id,
            capability="switch",
            data_json=json.dumps({"is_on": False}),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(sample)
        db_session.commit()

        state = manager.get_device_state(dev.id, db_session)
        assert state is not None
        assert state["switch"]["is_on"] is False

    @patch("app.plugins.smart_device.manager.read_shm")
    def test_state_none_when_nothing_available(self, mock_read_shm, manager, db_session):
        mock_read_shm.return_value = None
        state = manager.get_device_state(9999, db_session)
        assert state is None

    @patch("app.plugins.smart_device.manager.read_shm")
    def test_state_shm_device_not_in_map(self, mock_read_shm, manager, db_session):
        """SHM data exists but target device not in it."""
        mock_read_shm.return_value = {"devices": {"999": {"state": {"switch": {"is_on": True}}}}}
        dev = _create_device_row(db_session)
        # Device ID won't match 999, so should fall back to DB
        state = manager.get_device_state(dev.id, db_session)
        assert state is None


# =============================================================================
# get_power_summary
# =============================================================================


class TestGetPowerSummary:
    @patch("app.plugins.smart_device.manager.read_shm")
    def test_power_summary_with_data(self, mock_read_shm, manager, db_session):
        dev = _create_device_row(db_session, is_active=True, is_online=True)
        mock_read_shm.return_value = {
            "devices": {
                str(dev.id): {
                    "state": {
                        "power_monitor": {"watts": 42.5},
                    }
                }
            }
        }
        summary = manager.get_power_summary(db_session)
        assert summary["total_watts"] == 42.5
        assert summary["device_count"] == 1
        assert len(summary["devices"]) == 1
        assert summary["devices"][0]["watts"] == 42.5

    @patch("app.plugins.smart_device.manager.read_shm")
    def test_power_summary_empty(self, mock_read_shm, manager, db_session):
        mock_read_shm.return_value = None
        summary = manager.get_power_summary(db_session)
        assert summary["total_watts"] == 0.0
        assert summary["device_count"] == 0
        assert summary["devices"] == []

    @patch("app.plugins.smart_device.manager.read_shm")
    def test_power_summary_skips_inactive_devices(self, mock_read_shm, manager, db_session):
        _create_device_row(db_session, is_active=False, is_online=True)
        mock_read_shm.return_value = {"devices": {}}
        summary = manager.get_power_summary(db_session)
        assert summary["device_count"] == 0

    @patch("app.plugins.smart_device.manager.read_shm")
    def test_power_summary_skips_offline_devices(self, mock_read_shm, manager, db_session):
        _create_device_row(db_session, is_active=True, is_online=False)
        mock_read_shm.return_value = {"devices": {}}
        summary = manager.get_power_summary(db_session)
        assert summary["device_count"] == 0


# =============================================================================
# execute_command
# =============================================================================


@pytest.mark.asyncio
class TestExecuteCommand:
    async def test_switch_turn_on(self, manager_with_plugin, db_session):
        dev = _create_device_row(db_session)
        result = await manager_with_plugin.execute_command(
            device_id=dev.id,
            capability="switch",
            command="turn_on",
            params={},
            db=db_session,
        )
        assert result["success"] is True
        assert result["state"]["is_on"] is True

    async def test_switch_turn_off(self, manager_with_plugin, db_session):
        dev = _create_device_row(db_session)
        result = await manager_with_plugin.execute_command(
            device_id=dev.id,
            capability="switch",
            command="turn_off",
            params={},
            db=db_session,
        )
        assert result["success"] is True
        assert result["state"]["is_on"] is False

    async def test_unknown_switch_command(self, manager_with_plugin, db_session):
        dev = _create_device_row(db_session)
        with pytest.raises(ValueError, match="Unknown switch command"):
            await manager_with_plugin.execute_command(
                device_id=dev.id,
                capability="switch",
                command="toggle",
                params={},
                db=db_session,
            )

    async def test_dimmer_set_brightness(self, db_session):
        mgr = SmartDeviceManager()
        mgr.register_plugin(MockDimmerPlugin())
        dev = _create_device_row(
            db_session,
            plugin_name="mock_dimmer",
            device_type_id="mock_dimmer",
            capabilities=["dimmer"],
        )
        result = await mgr.execute_command(
            device_id=dev.id,
            capability="dimmer",
            command="set_brightness",
            params={"brightness": 75},
            db=db_session,
        )
        assert result["success"] is True
        assert result["state"]["brightness"] == 75

    async def test_color_set_color(self, db_session):
        mgr = SmartDeviceManager()
        mgr.register_plugin(MockColorPlugin())
        dev = _create_device_row(
            db_session,
            plugin_name="mock_color",
            device_type_id="mock_color_bulb",
            capabilities=["color"],
        )
        result = await mgr.execute_command(
            device_id=dev.id,
            capability="color",
            command="set_color",
            params={"hue": 120, "saturation": 80, "brightness": 60},
            db=db_session,
        )
        assert result["success"] is True
        assert result["state"]["hue"] == 120

    async def test_color_set_color_temp(self, db_session):
        mgr = SmartDeviceManager()
        mgr.register_plugin(MockColorPlugin())
        dev = _create_device_row(
            db_session,
            plugin_name="mock_color",
            device_type_id="mock_color_bulb",
            capabilities=["color"],
        )
        result = await mgr.execute_command(
            device_id=dev.id,
            capability="color",
            command="set_color_temp",
            params={"kelvin": 4000},
            db=db_session,
        )
        assert result["success"] is True
        assert result["state"]["color_temp_kelvin"] == 4000

    async def test_unknown_capability(self, manager_with_plugin, db_session):
        dev = _create_device_row(db_session)
        with pytest.raises(ValueError, match="Unknown capability"):
            await manager_with_plugin.execute_command(
                device_id=dev.id,
                capability="thermostat",
                command="set_temp",
                params={},
                db=db_session,
            )

    async def test_device_not_found(self, manager_with_plugin, db_session):
        with pytest.raises(ValueError, match="not found"):
            await manager_with_plugin.execute_command(
                device_id=9999,
                capability="switch",
                command="turn_on",
                params={},
                db=db_session,
            )

    async def test_plugin_not_loaded(self, manager, db_session):
        """Plugin for device exists in DB but is not registered in manager."""
        dev = _create_device_row(db_session, plugin_name="unloaded_plugin")
        with pytest.raises(ValueError, match="not loaded"):
            await manager.execute_command(
                device_id=dev.id,
                capability="switch",
                command="turn_on",
                params={},
                db=db_session,
            )

    async def test_plugin_lacks_capability(self, db_session):
        """Plugin is loaded but doesn't implement the requested capability."""
        mgr = SmartDeviceManager()
        mgr.register_plugin(MockDimmerPlugin())
        dev = _create_device_row(
            db_session,
            plugin_name="mock_dimmer",
            device_type_id="mock_dimmer",
            capabilities=["dimmer"],
        )
        with pytest.raises(ValueError, match="does not implement Switch"):
            await mgr.execute_command(
                device_id=dev.id,
                capability="switch",
                command="turn_on",
                params={},
                db=db_session,
            )


# =============================================================================
# Config decryption
# =============================================================================


class TestDecryptConfig:
    @patch("app.plugins.smart_device.manager.VPNEncryption")
    def test_decrypt_config_success(self, mock_encryption, manager, db_session):
        config_data = {"ip": "192.168.1.1", "password": "secret"}
        mock_encryption.decrypt_key.return_value = json.dumps(config_data)
        dev = _create_device_row(db_session)
        dev.config_secret = "encrypted_blob"
        result = manager._decrypt_config(dev)
        assert result == config_data

    def test_decrypt_config_no_secret(self, manager, db_session):
        dev = _create_device_row(db_session)
        dev.config_secret = None
        result = manager._decrypt_config(dev)
        assert result == {}

    @patch("app.plugins.smart_device.manager.VPNEncryption")
    def test_decrypt_config_failure_returns_empty(self, mock_encryption, manager, db_session):
        mock_encryption.decrypt_key.side_effect = RuntimeError("Bad key")
        dev = _create_device_row(db_session)
        dev.config_secret = "bad_encrypted_data"
        result = manager._decrypt_config(dev)
        assert result == {}
