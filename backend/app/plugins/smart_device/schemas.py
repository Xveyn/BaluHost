"""Pydantic schemas for the Smart Device plugin API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class SmartDeviceCreate(BaseModel):
    """Schema for creating a new smart device."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable device name")
    plugin_name: str = Field(..., description="Name of the plugin that handles this device")
    device_type_id: str = Field(..., description="Device type identifier from plugin's get_device_types()")
    address: str = Field(..., description="Device address (IP, hostname, or identifier)")
    mac_address: Optional[str] = Field(default=None, description="Optional MAC address for discovery")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Plugin-specific config (credentials etc.) — encrypted before storage",
    )


class SmartDeviceUpdate(BaseModel):
    """Schema for updating a smart device (partial updates supported)."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    address: Optional[str] = Field(default=None)
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="If provided, re-encrypted and stored",
    )
    is_active: Optional[bool] = Field(default=None)


class DeviceCommandRequest(BaseModel):
    """Schema for executing a command on a smart device."""

    capability: str = Field(
        ...,
        description="Capability to use: 'switch', 'dimmer', 'color'",
    )
    command: str = Field(
        ...,
        description="Command to execute: 'turn_on', 'turn_off', 'set_brightness', 'set_color', 'set_color_temp'",
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Command parameters, e.g. {'brightness': 80}",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SmartDeviceResponse(BaseModel):
    """Full smart device response (no credentials)."""

    id: int
    name: str
    plugin_name: str
    device_type_id: str
    address: str
    mac_address: Optional[str]
    capabilities: List[str]
    is_active: bool
    is_online: bool
    last_seen: Optional[datetime]
    last_error: Optional[str]
    state: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Current state from SHM / latest DB sample",
    )
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SmartDeviceListResponse(BaseModel):
    """Paginated list of smart devices."""

    devices: List[SmartDeviceResponse]
    total: int


class DeviceTypeResponse(BaseModel):
    """Describes a device type provided by a smart device plugin."""

    type_id: str
    display_name: str
    manufacturer: str
    capabilities: List[str]
    config_schema: Optional[Dict[str, Any]]
    icon: str
    plugin_name: str


class DeviceCommandResponse(BaseModel):
    """Result of executing a device command."""

    success: bool
    state: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class PowerSummaryResponse(BaseModel):
    """Aggregated power consumption across all smart devices."""

    total_watts: float
    device_count: int
    devices: List[Dict[str, Any]] = Field(
        description="Per-device breakdown: [{device_id, name, watts}]",
    )


class SmartDeviceHistoryResponse(BaseModel):
    """Historical state samples for a single device capability."""

    device_id: int
    capability: str
    samples: List[Dict[str, Any]]
    period_start: datetime
    period_end: datetime
