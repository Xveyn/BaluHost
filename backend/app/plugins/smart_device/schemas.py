"""Pydantic schemas for the Smart Device plugin API."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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


# ---------------------------------------------------------------------------
# History Import (Task 3 — Tapo energy backfill)
# ---------------------------------------------------------------------------


class ImportHistoryInterval(str, Enum):
    """Bucket granularity for history import."""

    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class ImportHistoryConflictStrategy(str, Enum):
    """How to resolve overlap between imported buckets and existing live samples."""

    LIVE_WINS = "live_wins"      # Skip imported bucket if any live sample exists in its time range.
    IMPORT_WINS = "import_wins"  # Delete live samples in the bucket's range, then write import.


class ImportHistoryRequest(BaseModel):
    """Admin-triggered request to import historical energy data from the device."""

    interval: ImportHistoryInterval
    start_date: date
    end_date: date
    conflict_strategy: ImportHistoryConflictStrategy

    @field_validator("end_date")
    @classmethod
    def _end_after_start(cls, v: date, info) -> date:
        start = info.data.get("start_date")
        if start is not None and v < start:
            raise ValueError("end_date must be >= start_date")
        return v

    @model_validator(mode="after")
    def _check_interval_constraints(self) -> "ImportHistoryRequest":
        if self.interval == ImportHistoryInterval.DAILY:
            # Tapo requires start_date == first day of a quarter (Jan/Apr/Jul/Oct, day=1)
            if self.start_date.day != 1 or self.start_date.month not in (1, 4, 7, 10):
                raise ValueError(
                    "Daily interval requires start_date to be the first day of a quarter "
                    "(Jan 1, Apr 1, Jul 1, or Oct 1)"
                )
        elif self.interval == ImportHistoryInterval.MONTHLY:
            # Tapo requires start_date == Jan 1 of some year
            if self.start_date.day != 1 or self.start_date.month != 1:
                raise ValueError(
                    "Monthly interval requires start_date to be January 1 of some year"
                )
        return self


class ImportHistoryResponse(BaseModel):
    """Result of a history import operation."""

    device_id: int
    interval: ImportHistoryInterval
    buckets_fetched: int                  # how many buckets the device returned
    samples_inserted: int                 # how many SmartDeviceSamples were created
    samples_skipped_idempotent: int       # already imported (Task 2B)
    samples_skipped_live: int             # blocked by LIVE_WINS strategy
    live_samples_deleted: int             # cleared by IMPORT_WINS strategy
    started_at: datetime
    completed_at: datetime
