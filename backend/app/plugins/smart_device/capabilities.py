"""Capability protocols and data models for smart device plugins."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable, Optional

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
