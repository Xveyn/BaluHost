"""Pydantic schemas for GPU power management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class GpuPowerState(str, Enum):
    """Three-state GPU power machine."""
    ACTIVE = "active"
    STANDBY = "standby"
    DEEP_IDLE = "deep_idle"


class AmdProfileMode(str, Enum):
    """Canonical names parsed from `pp_power_profile_mode`. Index resolved at apply time."""
    BOOTUP_DEFAULT = "BOOTUP_DEFAULT"
    POWER_SAVING = "POWER_SAVING"
    VIDEO = "VIDEO"
    VR = "VR"
    COMPUTE = "COMPUTE"
    CUSTOM = "CUSTOM"
    FULL_SCREEN_3D = "3D_FULL_SCREEN"


class AmdStateConfig(BaseModel):
    """Per-state AMD overrides. None = use built-in default for that state."""
    performance_level: Optional[str] = Field(
        default=None,
        description="auto | low | high | manual | profile_standard | profile_min_sclk | profile_min_mclk | profile_peak"
    )
    profile_mode: Optional[AmdProfileMode] = Field(
        default=None,
        description="pp_power_profile_mode name; None = don't touch"
    )


class NvidiaStateConfig(BaseModel):
    """Per-state NVIDIA overrides."""
    min_clock_mhz: Optional[int] = Field(default=None, ge=0)
    max_clock_mhz: Optional[int] = Field(default=None, ge=0)
    power_limit_watts: Optional[int] = Field(default=None, ge=0)


class GpuPowerConfig(BaseModel):
    """Full configuration."""
    enabled: bool = False

    idle_window_seconds: int = Field(default=30, ge=10, le=600)
    deep_idle_extra_seconds: int = Field(default=120, ge=30, le=3600)
    deep_idle_grace_seconds: int = Field(default=5, ge=0, le=30)
    usage_threshold_percent: float = Field(default=5.0, ge=0.0, le=50.0)
    monitor_interval_seconds: int = Field(default=5, ge=1, le=60)

    amd_active: AmdStateConfig = Field(
        default_factory=lambda: AmdStateConfig(performance_level="auto")
    )
    amd_standby: AmdStateConfig = Field(
        default_factory=lambda: AmdStateConfig(
            performance_level="auto",
            profile_mode=AmdProfileMode.POWER_SAVING,
        )
    )
    amd_deep_idle: AmdStateConfig = Field(
        default_factory=lambda: AmdStateConfig(
            performance_level="low",
            profile_mode=AmdProfileMode.POWER_SAVING,
        )
    )

    nvidia_active: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)
    nvidia_standby: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)
    nvidia_deep_idle: NvidiaStateConfig = Field(default_factory=NvidiaStateConfig)


class GpuPowerDemandInfo(BaseModel):
    source: str
    registered_at: datetime
    expires_at: Optional[datetime] = None
    description: Optional[str] = None


class RegisterGpuDemandRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=128)
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    description: Optional[str] = Field(default=None, max_length=500)


class GpuPowerStatus(BaseModel):
    enabled: bool
    detected: bool
    vendor: Optional[str]
    current_state: GpuPowerState
    last_transition: Optional[datetime] = None
    last_reason: Optional[str] = None
    active_demands: List[GpuPowerDemandInfo] = Field(default_factory=list)
    has_write_permission: bool
    estimated_power_watts: Optional[float] = None
    display_count: int = 0
    usage_percent: Optional[float] = None


class GpuPowerCapabilities(BaseModel):
    vendor: Optional[str]
    amd_performance_levels: List[str] = Field(default_factory=list)
    amd_profile_modes: List[str] = Field(default_factory=list)
    nvidia_min_clock_mhz: Optional[int] = None
    nvidia_max_clock_mhz: Optional[int] = None
    nvidia_min_power_watts: Optional[int] = None
    nvidia_max_power_watts: Optional[int] = None
    nvidia_default_power_watts: Optional[int] = None


class GpuPowerHistoryEntry(BaseModel):
    timestamp: datetime
    state: GpuPowerState
    previous_state: Optional[GpuPowerState] = None
    reason: str
    source: Optional[str] = None
    power_watts_at_transition: Optional[float] = None


class GpuPowerHistoryResponse(BaseModel):
    entries: List[GpuPowerHistoryEntry]
    total: int
