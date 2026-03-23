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
