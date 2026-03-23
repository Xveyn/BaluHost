"""Tests for capability contract enforcement."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest
from pydantic import BaseModel

from app.plugins.smart_device.capabilities import (
    CAPABILITY_CONTRACTS,
    DeviceCapability,
    PowerMonitor,
    PowerReading,
    Switch,
    SwitchState,
    validate_capability_contracts,
)
from app.plugins.smart_device.base import DeviceTypeInfo, SmartDevicePlugin
from app.plugins.base import PluginMetadata


# --- Helpers ---

class _ValidPowerPlugin(SmartDevicePlugin):
    """Plugin that correctly implements POWER_MONITOR."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="valid_power",
            version="1.0.0",
            display_name="Valid Power",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="test_power",
                display_name="Test Power",
                manufacturer="Test",
                capabilities=[DeviceCapability.POWER_MONITOR],
            )
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {
            "power_monitor": PowerReading(
                watts=42.0, timestamp=datetime.now(timezone.utc)
            )
        }

    async def get_power(self, device_id: str) -> PowerReading:
        return PowerReading(watts=42.0, timestamp=datetime.now(timezone.utc))


class _MissingProtocolPlugin(SmartDevicePlugin):
    """Plugin that declares POWER_MONITOR but does NOT implement get_power()."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="missing_protocol",
            version="1.0.0",
            display_name="Missing Protocol",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="test_broken",
                display_name="Test Broken",
                manufacturer="Test",
                capabilities=[DeviceCapability.POWER_MONITOR],
            )
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {}


class _PartialProtocolPlugin(SmartDevicePlugin):
    """Declares SWITCH + POWER_MONITOR but only implements Switch."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="partial_protocol",
            version="1.0.0",
            display_name="Partial",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="test_partial",
                display_name="Test Partial",
                manufacturer="Test",
                capabilities=[
                    DeviceCapability.SWITCH,
                    DeviceCapability.POWER_MONITOR,
                ],
            )
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {}

    # Implements Switch but NOT PowerMonitor
    async def turn_on(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True)

    async def turn_off(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=False)

    async def get_switch_state(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True)


# --- Tests: CAPABILITY_CONTRACTS completeness ---

def test_all_capabilities_have_contracts():
    """Every DeviceCapability enum value must have an entry in CAPABILITY_CONTRACTS."""
    for cap in DeviceCapability:
        assert cap in CAPABILITY_CONTRACTS, f"Missing contract for {cap.value}"


# --- Tests: validate_capability_contracts ---

def test_valid_plugin_passes_validation():
    plugin = _ValidPowerPlugin()
    errors = validate_capability_contracts(plugin)
    assert errors == []


def test_missing_protocol_fails_validation():
    plugin = _MissingProtocolPlugin()
    errors = validate_capability_contracts(plugin)
    assert len(errors) == 1
    assert "power_monitor" in errors[0].lower()
    assert "PowerMonitor" in errors[0]


def test_partial_protocol_fails_validation():
    plugin = _PartialProtocolPlugin()
    errors = validate_capability_contracts(plugin)
    assert len(errors) == 1
    assert "power_monitor" in errors[0].lower()


from app.plugins.manager import PluginManager, PluginLoadError


@pytest.fixture()
def reset_manager():
    PluginManager.reset_instance()
    yield
    PluginManager.reset_instance()


def test_plugin_manager_rejects_invalid_smart_device_plugin(tmp_path, reset_manager):
    """PluginManager.load_plugin() should reject a SmartDevicePlugin that
    fails capability contract validation."""
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "broken_device"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text('''
from app.plugins.base import PluginMetadata
from app.plugins.smart_device.base import SmartDevicePlugin, DeviceTypeInfo
from app.plugins.smart_device.capabilities import DeviceCapability

class BrokenDevicePlugin(SmartDevicePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="broken_device",
            version="1.0.0",
            display_name="Broken",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self):
        return [DeviceTypeInfo(
            type_id="broken",
            display_name="Broken",
            manufacturer="Test",
            capabilities=[DeviceCapability.POWER_MONITOR],
        )]

    async def connect_device(self, device_id, config):
        return True

    async def poll_device(self, device_id):
        return {}
''')

    manager = PluginManager(plugins_dir=plugins_dir)
    with pytest.raises(PluginLoadError, match="capability contract"):
        manager.load_plugin("broken_device")


def test_plugin_manager_accepts_valid_smart_device_plugin(tmp_path, reset_manager):
    """PluginManager.load_plugin() should accept a SmartDevicePlugin that
    satisfies all capability contracts."""
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "good_device"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text('''
from datetime import datetime, timezone
from app.plugins.base import PluginMetadata
from app.plugins.smart_device.base import SmartDevicePlugin, DeviceTypeInfo
from app.plugins.smart_device.capabilities import (
    DeviceCapability, PowerReading,
)

class GoodDevicePlugin(SmartDevicePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="good_device",
            version="1.0.0",
            display_name="Good",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self):
        return [DeviceTypeInfo(
            type_id="good",
            display_name="Good",
            manufacturer="Test",
            capabilities=[DeviceCapability.POWER_MONITOR],
        )]

    async def connect_device(self, device_id, config):
        return True

    async def poll_device(self, device_id):
        return {"power_monitor": PowerReading(watts=1.0, timestamp=datetime.now(timezone.utc))}

    async def get_power(self, device_id):
        return PowerReading(watts=1.0, timestamp=datetime.now(timezone.utc))
''')

    manager = PluginManager(plugins_dir=plugins_dir)
    plugin = manager.load_plugin("good_device")
    assert plugin is not None
