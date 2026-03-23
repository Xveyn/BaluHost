"""Capability protocols and data models for smart device plugins."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable, Optional

from pydantic import BaseModel, Field


class DeviceCapability(str, Enum):
    SWITCH = "switch"
    POWER_MONITOR = "power_monitor"
    SENSOR = "sensor"
    DIMMER = "dimmer"
    COLOR = "color"


# --- Data Models ---

class SwitchState(BaseModel):
    is_on: bool
    changed_at: Optional[datetime] = None


class PowerReading(BaseModel):
    watts: float
    voltage: Optional[float] = None
    current: Optional[float] = None
    energy_today_kwh: Optional[float] = None
    timestamp: datetime


class SensorReading(BaseModel):
    name: str          # e.g. "temperature", "humidity"
    value: float
    unit: str          # e.g. "°C", "%", "lux"
    device_class: Optional[str] = None  # e.g. "temperature", "humidity"
    timestamp: datetime


class DimmerState(BaseModel):
    brightness: int = Field(..., ge=0, le=100)  # percent
    is_on: bool


class ColorState(BaseModel):
    hue: int = Field(..., ge=0, le=360)
    saturation: int = Field(..., ge=0, le=100)
    brightness: int = Field(..., ge=0, le=100)
    color_temp_kelvin: Optional[int] = None
    is_on: bool


# --- Capability Protocols ---

@runtime_checkable
class Switch(Protocol):
    async def turn_on(self, device_id: str) -> SwitchState: ...
    async def turn_off(self, device_id: str) -> SwitchState: ...
    async def get_switch_state(self, device_id: str) -> SwitchState: ...


@runtime_checkable
class PowerMonitor(Protocol):
    async def get_power(self, device_id: str) -> PowerReading: ...


@runtime_checkable
class Sensor(Protocol):
    async def get_readings(self, device_id: str) -> list[SensorReading]: ...


@runtime_checkable
class Dimmer(Protocol):
    async def set_brightness(self, device_id: str, brightness: int) -> DimmerState: ...
    async def get_dimmer_state(self, device_id: str) -> DimmerState: ...


@runtime_checkable
class ColorControl(Protocol):
    async def set_color(self, device_id: str, hue: int, saturation: int, brightness: int) -> ColorState: ...
    async def set_color_temp(self, device_id: str, kelvin: int) -> ColorState: ...
    async def get_color_state(self, device_id: str) -> ColorState: ...


# --- Capability Contracts ---
# Declaring a capability is a CONTRACT:
# - Your plugin MUST implement the Protocol (checked at startup)
# - poll_device() MUST return the DataModel for this capability key (checked at runtime)
# In return you get: mobile app integration, dashboard panels,
# energy statistics, and cost calculations — for free.

CAPABILITY_CONTRACTS: dict[DeviceCapability, tuple[type, type[BaseModel]]] = {
    DeviceCapability.SWITCH: (Switch, SwitchState),
    DeviceCapability.POWER_MONITOR: (PowerMonitor, PowerReading),
    DeviceCapability.SENSOR: (Sensor, SensorReading),
    DeviceCapability.DIMMER: (Dimmer, DimmerState),
    DeviceCapability.COLOR: (ColorControl, ColorState),
}


def validate_capability_contracts(plugin: object) -> list[str]:
    """Validate that a plugin implements all protocols for its declared capabilities.

    Iterates over every DeviceTypeInfo returned by the plugin's
    ``get_device_types()`` and checks that each declared capability's
    protocol is satisfied (via ``isinstance``).

    Args:
        plugin: A SmartDevicePlugin instance.

    Returns:
        List of human-readable error strings (empty means valid).
    """
    errors: list[str] = []
    seen: set[DeviceCapability] = set()

    # Import here to avoid circular import at module level
    from app.plugins.smart_device.base import SmartDevicePlugin

    if not isinstance(plugin, SmartDevicePlugin):
        return errors

    for device_type in plugin.get_device_types():
        for cap in device_type.capabilities:
            if cap in seen:
                continue
            seen.add(cap)

            contract = CAPABILITY_CONTRACTS.get(cap)
            if contract is None:
                errors.append(
                    f"Capability '{cap.value}' has no contract defined in CAPABILITY_CONTRACTS"
                )
                continue

            protocol_cls, _data_model = contract
            if not isinstance(plugin, protocol_cls):
                errors.append(
                    f"Capability '{cap.value}' requires {protocol_cls.__name__} protocol "
                    f"but plugin '{plugin.metadata.name}' does not implement it"
                )

    return errors
