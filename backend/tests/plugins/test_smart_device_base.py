"""Tests for smart device base classes, capabilities, and data models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest
from pydantic import ValidationError

from app.plugins.base import PluginBase, PluginMetadata
from app.plugins.smart_device.base import (
    DeviceTypeInfo,
    DiscoveredDevice,
    SmartDevicePlugin,
)
from app.plugins.smart_device.capabilities import (
    ColorControl,
    ColorState,
    DeviceCapability,
    Dimmer,
    DimmerState,
    PowerMonitor,
    PowerReading,
    Sensor,
    SensorReading,
    Switch,
    SwitchState,
)


# =============================================================================
# DeviceCapability enum
# =============================================================================


class TestDeviceCapability:
    def test_enum_values(self):
        assert DeviceCapability.SWITCH == "switch"
        assert DeviceCapability.POWER_MONITOR == "power_monitor"
        assert DeviceCapability.SENSOR == "sensor"
        assert DeviceCapability.DIMMER == "dimmer"
        assert DeviceCapability.COLOR == "color"

    def test_enum_count(self):
        assert len(DeviceCapability) == 5

    def test_enum_is_str(self):
        """Capabilities are string enums for JSON serialization."""
        for cap in DeviceCapability:
            assert isinstance(cap, str)
            assert isinstance(cap.value, str)

    def test_enum_from_value(self):
        assert DeviceCapability("switch") is DeviceCapability.SWITCH
        assert DeviceCapability("dimmer") is DeviceCapability.DIMMER

    def test_invalid_capability_raises(self):
        with pytest.raises(ValueError):
            DeviceCapability("nonexistent")


# =============================================================================
# SwitchState model
# =============================================================================


class TestSwitchState:
    def test_create_minimal(self):
        state = SwitchState(is_on=True)
        assert state.is_on is True
        assert state.changed_at is None

    def test_create_with_timestamp(self):
        now = datetime.now(timezone.utc)
        state = SwitchState(is_on=False, changed_at=now)
        assert state.is_on is False
        assert state.changed_at == now

    def test_serialization(self):
        state = SwitchState(is_on=True)
        data = state.model_dump()
        assert data["is_on"] is True
        assert data["changed_at"] is None

    def test_json_roundtrip(self):
        now = datetime.now(timezone.utc)
        state = SwitchState(is_on=True, changed_at=now)
        json_str = state.model_dump_json()
        restored = SwitchState.model_validate_json(json_str)
        assert restored.is_on is True


# =============================================================================
# PowerReading model
# =============================================================================


class TestPowerReading:
    def test_create_minimal(self):
        now = datetime.now(timezone.utc)
        reading = PowerReading(watts=42.5, timestamp=now)
        assert reading.watts == 42.5
        assert reading.voltage is None
        assert reading.current is None
        assert reading.energy_today_kwh is None

    def test_create_full(self):
        now = datetime.now(timezone.utc)
        reading = PowerReading(
            watts=120.3,
            voltage=230.0,
            current=0.52,
            energy_today_kwh=1.8,
            timestamp=now,
        )
        assert reading.watts == 120.3
        assert reading.voltage == 230.0
        assert reading.current == 0.52
        assert reading.energy_today_kwh == 1.8

    def test_serialization(self):
        now = datetime.now(timezone.utc)
        reading = PowerReading(watts=10.0, timestamp=now)
        data = reading.model_dump()
        assert "watts" in data
        assert "timestamp" in data

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            PowerReading(watts=10.0)  # missing timestamp

    def test_missing_watts(self):
        with pytest.raises(ValidationError):
            PowerReading(timestamp=datetime.now(timezone.utc))  # missing watts


# =============================================================================
# SensorReading model
# =============================================================================


class TestSensorReading:
    def test_create(self):
        now = datetime.now(timezone.utc)
        reading = SensorReading(
            name="temperature",
            value=23.5,
            unit="\u00b0C",
            timestamp=now,
        )
        assert reading.name == "temperature"
        assert reading.value == 23.5
        assert reading.unit == "\u00b0C"
        assert reading.device_class is None

    def test_with_device_class(self):
        now = datetime.now(timezone.utc)
        reading = SensorReading(
            name="humidity",
            value=65.0,
            unit="%",
            device_class="humidity",
            timestamp=now,
        )
        assert reading.device_class == "humidity"

    def test_serialization(self):
        now = datetime.now(timezone.utc)
        reading = SensorReading(name="lux", value=500.0, unit="lux", timestamp=now)
        data = reading.model_dump()
        assert data["name"] == "lux"
        assert data["value"] == 500.0


# =============================================================================
# DimmerState model
# =============================================================================


class TestDimmerState:
    def test_create(self):
        state = DimmerState(brightness=80, is_on=True)
        assert state.brightness == 80
        assert state.is_on is True

    def test_min_brightness(self):
        state = DimmerState(brightness=0, is_on=False)
        assert state.brightness == 0

    def test_max_brightness(self):
        state = DimmerState(brightness=100, is_on=True)
        assert state.brightness == 100

    def test_brightness_out_of_range_high(self):
        with pytest.raises(ValidationError):
            DimmerState(brightness=101, is_on=True)

    def test_brightness_out_of_range_low(self):
        with pytest.raises(ValidationError):
            DimmerState(brightness=-1, is_on=True)

    def test_serialization(self):
        state = DimmerState(brightness=50, is_on=True)
        data = state.model_dump()
        assert data["brightness"] == 50
        assert data["is_on"] is True


# =============================================================================
# ColorState model
# =============================================================================


class TestColorState:
    def test_create_minimal(self):
        state = ColorState(hue=180, saturation=100, brightness=75, is_on=True)
        assert state.hue == 180
        assert state.saturation == 100
        assert state.brightness == 75
        assert state.color_temp_kelvin is None
        assert state.is_on is True

    def test_create_with_color_temp(self):
        state = ColorState(
            hue=0, saturation=0, brightness=100, color_temp_kelvin=4000, is_on=True
        )
        assert state.color_temp_kelvin == 4000

    def test_hue_out_of_range(self):
        with pytest.raises(ValidationError):
            ColorState(hue=361, saturation=50, brightness=50, is_on=True)

    def test_hue_negative(self):
        with pytest.raises(ValidationError):
            ColorState(hue=-1, saturation=50, brightness=50, is_on=True)

    def test_saturation_out_of_range(self):
        with pytest.raises(ValidationError):
            ColorState(hue=0, saturation=101, brightness=50, is_on=True)

    def test_brightness_out_of_range(self):
        with pytest.raises(ValidationError):
            ColorState(hue=0, saturation=50, brightness=101, is_on=True)

    def test_serialization(self):
        state = ColorState(hue=120, saturation=80, brightness=60, is_on=False)
        data = state.model_dump()
        assert data["hue"] == 120
        assert data["is_on"] is False


# =============================================================================
# Protocol runtime_checkable
# =============================================================================


class TestProtocolRuntimeCheckable:
    """Verify that all capability protocols are decorated with @runtime_checkable."""

    def test_switch_is_runtime_checkable(self):
        """Switch protocol can be checked at runtime with isinstance."""
        # A class that implements the Switch protocol methods
        class FakeSwitch:
            async def turn_on(self, device_id: str) -> SwitchState:
                return SwitchState(is_on=True)

            async def turn_off(self, device_id: str) -> SwitchState:
                return SwitchState(is_on=False)

            async def get_switch_state(self, device_id: str) -> SwitchState:
                return SwitchState(is_on=True)

        assert isinstance(FakeSwitch(), Switch)

    def test_power_monitor_is_runtime_checkable(self):
        class FakePowerMonitor:
            async def get_power(self, device_id: str) -> PowerReading:
                return PowerReading(watts=0, timestamp=datetime.now(timezone.utc))

        assert isinstance(FakePowerMonitor(), PowerMonitor)

    def test_sensor_is_runtime_checkable(self):
        class FakeSensor:
            async def get_readings(self, device_id: str) -> list:
                return []

        assert isinstance(FakeSensor(), Sensor)

    def test_dimmer_is_runtime_checkable(self):
        class FakeDimmer:
            async def set_brightness(self, device_id: str, brightness: int) -> DimmerState:
                return DimmerState(brightness=brightness, is_on=True)

            async def get_dimmer_state(self, device_id: str) -> DimmerState:
                return DimmerState(brightness=50, is_on=True)

        assert isinstance(FakeDimmer(), Dimmer)

    def test_color_control_is_runtime_checkable(self):
        class FakeColorControl:
            async def set_color(self, device_id: str, hue: int, saturation: int, brightness: int) -> ColorState:
                return ColorState(hue=hue, saturation=saturation, brightness=brightness, is_on=True)

            async def set_color_temp(self, device_id: str, kelvin: int) -> ColorState:
                return ColorState(hue=0, saturation=0, brightness=100, color_temp_kelvin=kelvin, is_on=True)

            async def get_color_state(self, device_id: str) -> ColorState:
                return ColorState(hue=0, saturation=0, brightness=100, is_on=True)

        assert isinstance(FakeColorControl(), ColorControl)

    def test_non_implementing_class_is_not_switch(self):
        class NotASwitch:
            pass

        assert not isinstance(NotASwitch(), Switch)


# =============================================================================
# DeviceTypeInfo
# =============================================================================


class TestDeviceTypeInfo:
    def test_create(self):
        info = DeviceTypeInfo(
            type_id="tapo_p115",
            display_name="TP-Link Tapo P115",
            manufacturer="TP-Link",
            capabilities=[DeviceCapability.SWITCH, DeviceCapability.POWER_MONITOR],
        )
        assert info.type_id == "tapo_p115"
        assert info.display_name == "TP-Link Tapo P115"
        assert info.manufacturer == "TP-Link"
        assert len(info.capabilities) == 2
        assert info.config_schema is None
        assert info.icon == "plug"  # default

    def test_with_config_schema(self):
        schema = {"type": "object", "properties": {"ip": {"type": "string"}}}
        info = DeviceTypeInfo(
            type_id="test",
            display_name="Test",
            manufacturer="Test",
            capabilities=[DeviceCapability.SWITCH],
            config_schema=schema,
        )
        assert info.config_schema == schema

    def test_custom_icon(self):
        info = DeviceTypeInfo(
            type_id="test",
            display_name="Test",
            manufacturer="Test",
            capabilities=[],
            icon="lightbulb",
        )
        assert info.icon == "lightbulb"

    def test_serialization(self):
        info = DeviceTypeInfo(
            type_id="test_type",
            display_name="Test Type",
            manufacturer="Acme",
            capabilities=[DeviceCapability.SWITCH],
        )
        data = info.model_dump()
        assert data["type_id"] == "test_type"
        assert data["capabilities"] == [DeviceCapability.SWITCH]


# =============================================================================
# DiscoveredDevice
# =============================================================================


class TestDiscoveredDevice:
    def test_create_minimal(self):
        dd = DiscoveredDevice(
            suggested_name="Living Room Plug",
            device_type_id="tapo_p115",
            address="192.168.1.100",
        )
        assert dd.suggested_name == "Living Room Plug"
        assert dd.device_type_id == "tapo_p115"
        assert dd.address == "192.168.1.100"
        assert dd.mac_address is None
        assert dd.extra == {}

    def test_create_full(self):
        dd = DiscoveredDevice(
            suggested_name="Desk Lamp",
            device_type_id="tapo_l530",
            address="192.168.1.101",
            mac_address="AA:BB:CC:DD:EE:FF",
            extra={"firmware": "1.2.3"},
        )
        assert dd.mac_address == "AA:BB:CC:DD:EE:FF"
        assert dd.extra["firmware"] == "1.2.3"

    def test_serialization(self):
        dd = DiscoveredDevice(
            suggested_name="Test",
            device_type_id="test",
            address="10.0.0.1",
        )
        data = dd.model_dump()
        assert data["suggested_name"] == "Test"
        assert data["address"] == "10.0.0.1"


# =============================================================================
# SmartDevicePlugin ABC
# =============================================================================


class TestSmartDevicePluginABC:
    def test_cannot_instantiate_directly(self):
        """SmartDevicePlugin is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            SmartDevicePlugin()

    def test_subclass_must_implement_abstract_methods(self):
        """A subclass missing abstract methods cannot be instantiated."""

        class IncompletePlugin(SmartDevicePlugin):
            @property
            def metadata(self):
                return PluginMetadata(
                    name="incomplete",
                    version="1.0.0",
                    display_name="Incomplete",
                    description="Missing abstract methods",
                    author="Test",
                )

        with pytest.raises(TypeError):
            IncompletePlugin()

    def test_concrete_subclass_instantiates(self):
        """A fully implemented subclass can be instantiated."""

        class ConcretePlugin(SmartDevicePlugin):
            @property
            def metadata(self):
                return PluginMetadata(
                    name="concrete",
                    version="1.0.0",
                    display_name="Concrete",
                    description="Fully implemented",
                    author="Test",
                    category="smart_device",
                )

            def get_device_types(self) -> list:
                return []

            async def connect_device(self, device_id: str, config: dict) -> bool:
                return True

            async def poll_device(self, device_id: str) -> dict:
                return {}

        plugin = ConcretePlugin()
        assert plugin.metadata.name == "concrete"
        assert plugin.get_device_types() == []
        assert plugin.get_poll_interval_seconds() == 5.0

    @pytest.mark.asyncio
    async def test_default_discover_devices_returns_empty(self):
        """Default discover_devices returns empty list."""

        class MinPlugin(SmartDevicePlugin):
            @property
            def metadata(self):
                return PluginMetadata(
                    name="min",
                    version="1.0.0",
                    display_name="Min",
                    description="Minimal",
                    author="Test",
                    category="smart_device",
                )

            def get_device_types(self):
                return []

            async def connect_device(self, device_id, config):
                return True

            async def poll_device(self, device_id):
                return {}

        plugin = MinPlugin()
        result = await plugin.discover_devices()
        assert result == []

    @pytest.mark.asyncio
    async def test_default_poll_device_mock_returns_empty(self):
        """Default poll_device_mock returns empty dict."""

        class MinPlugin(SmartDevicePlugin):
            @property
            def metadata(self):
                return PluginMetadata(
                    name="min2",
                    version="1.0.0",
                    display_name="Min2",
                    description="Minimal",
                    author="Test",
                    category="smart_device",
                )

            def get_device_types(self):
                return []

            async def connect_device(self, device_id, config):
                return True

            async def poll_device(self, device_id):
                return {}

        plugin = MinPlugin()
        result = await plugin.poll_device_mock("1")
        assert result == {}
