"""
Power management schemas for CPU frequency scaling.

Defines the power profiles and related data structures for the
CPU power management system.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PowerProfile(str, Enum):
    """
    Power profile levels for CPU frequency scaling.

    Each profile maps to specific CPU governor and frequency settings:
    - IDLE: Minimal power, 400-800 MHz
    - LOW: Light workloads, 800-1200 MHz
    - MEDIUM: File operations, 1500-2500 MHz
    - SURGE: Maximum performance, full boost
    """
    IDLE = "idle"
    LOW = "low"
    MEDIUM = "medium"
    SURGE = "surge"


class ServicePowerProperty(str, Enum):
    """
    Service power property for API endpoints.

    Defines the fixed power intensity of a service/operation:
    - IDLE: 0-10% CPU load (auth, status checks, monitoring reads)
    - LOW: 10-30% CPU load (CRUD, metadata changes, config updates)
    - MEDIUM: 30-60% CPU load (file upload/download, sync, SMART scan)
    - SURGE: 60-100% CPU load (backup, RAID rebuild, restore)

    Used by the @requires_power decorator to register
    power demands when endpoints are called.
    """
    IDLE = "idle"
    LOW = "low"
    MEDIUM = "medium"
    SURGE = "surge"


# Backwards compatibility alias
PowerRating = ServicePowerProperty


class PowerDemandInfo(BaseModel):
    """Information about an active power demand."""
    source: str = Field(..., description="Source identifier (e.g., 'backup_create', 'raid_rebuild')")
    level: PowerProfile = Field(..., description="Required power level")
    power_property: Optional[ServicePowerProperty] = Field(None, description="Service power property (IDLE, LOW, MEDIUM, SURGE)")
    registered_at: datetime = Field(..., description="When demand was registered")
    expires_at: Optional[datetime] = Field(None, description="When demand expires (None = manual unregister)")
    description: Optional[str] = Field(None, description="Human-readable description")


class PowerProfileConfig(BaseModel):
    """Configuration for a power profile."""
    profile: PowerProfile
    governor: str = Field(..., description="CPU governor (powersave/performance)")
    energy_performance_preference: str = Field(..., description="EPP setting")
    min_freq_mhz: Optional[int] = Field(None, description="Minimum frequency in MHz")
    max_freq_mhz: Optional[int] = Field(None, description="Maximum frequency in MHz")
    description: str = Field("", description="Profile description")


class PermissionStatus(BaseModel):
    """Permission status for cpufreq control."""
    user: str = Field(..., description="Current user name")
    groups: list[str] = Field(default_factory=list, description="User's groups")
    in_cpufreq_group: bool = Field(False, description="Whether user is in cpufreq group")
    sudo_available: bool = Field(False, description="Whether passwordless sudo is available")
    files: dict[str, Optional[bool]] = Field(default_factory=dict, description="Write permission per file")
    errors: list[str] = Field(default_factory=list, description="Recent permission errors")
    has_write_access: bool = Field(False, description="Whether we can write to cpufreq (direct or sudo)")


class PowerStatusResponse(BaseModel):
    """Response for power status endpoint."""
    current_profile: PowerProfile = Field(..., description="Currently active power profile")
    current_property: Optional[ServicePowerProperty] = Field(None, description="Current highest service power property")
    current_frequency_mhz: Optional[float] = Field(None, description="Current CPU frequency in MHz")
    target_frequency_range: Optional[str] = Field(None, description="Target frequency range (e.g., '400-800 MHz')")
    active_demands: list[PowerDemandInfo] = Field(default_factory=list, description="Active power demands")
    auto_scaling_enabled: bool = Field(True, description="Whether auto-scaling is enabled")
    is_dev_mode: bool = Field(False, description="Whether running in dev mode (simulated)")
    is_using_linux_backend: bool = Field(False, description="Whether using real Linux cpufreq backend")
    linux_backend_available: bool = Field(False, description="Whether Linux backend is available on this system")
    can_switch_backend: bool = Field(False, description="Whether backend can be switched at runtime")
    permission_status: Optional[PermissionStatus] = Field(None, description="Permission details (only for Linux backend)")
    last_profile_change: Optional[datetime] = Field(None, description="When profile last changed")
    cooldown_remaining_seconds: Optional[int] = Field(None, description="Seconds until next downgrade allowed")
    # Preset info
    active_preset: Optional["PowerPresetSummary"] = Field(None, description="Currently active preset")


class PowerProfilesResponse(BaseModel):
    """Response listing all available power profiles."""
    profiles: list[PowerProfileConfig] = Field(..., description="List of available profiles")
    current_profile: PowerProfile = Field(..., description="Currently active profile")


class SetProfileRequest(BaseModel):
    """Request to manually set a power profile."""
    profile: PowerProfile = Field(..., description="Profile to activate")
    duration_seconds: Optional[int] = Field(
        None,
        description="How long to hold this profile (None = until changed)"
    )
    reason: Optional[str] = Field(None, description="Reason for manual override")


class SetProfileResponse(BaseModel):
    """Response after setting a profile."""
    success: bool
    message: str
    previous_profile: PowerProfile
    new_profile: PowerProfile
    applied_at: datetime


class PowerHistoryEntry(BaseModel):
    """Single entry in power profile history."""
    timestamp: datetime
    profile: PowerProfile
    reason: str = Field(..., description="Why the change occurred")
    source: Optional[str] = Field(None, description="What triggered the change")
    frequency_mhz: Optional[float] = Field(None, description="CPU frequency at time of change")


class PowerHistoryResponse(BaseModel):
    """Response for power history endpoint."""
    entries: list[PowerHistoryEntry] = Field(..., description="Profile change history")
    total_entries: int = Field(..., description="Total entries in history")
    from_timestamp: Optional[datetime] = Field(None, description="Earliest entry timestamp")
    to_timestamp: Optional[datetime] = Field(None, description="Latest entry timestamp")


class RegisterDemandRequest(BaseModel):
    """Request to register a power demand programmatically."""
    source: str = Field(..., description="Unique source identifier")
    level: PowerProfile = Field(..., description="Required power level")
    timeout_seconds: Optional[int] = Field(
        None,
        description="Auto-expire after this many seconds"
    )
    description: Optional[str] = Field(None, description="Human-readable description")


class RegisterDemandResponse(BaseModel):
    """Response after registering a demand."""
    success: bool
    message: str
    demand_id: str = Field(..., description="ID to use for unregistering")
    resulting_profile: PowerProfile = Field(..., description="Profile after demand registered")


class UnregisterDemandRequest(BaseModel):
    """Request to unregister a power demand."""
    source: str = Field(..., description="Source identifier to unregister")


class UnregisterDemandResponse(BaseModel):
    """Response after unregistering a demand."""
    success: bool
    message: str
    resulting_profile: PowerProfile = Field(..., description="Profile after demand removed")


class AutoScalingConfig(BaseModel):
    """Configuration for auto-scaling behavior."""
    enabled: bool = Field(True, description="Whether auto-scaling is enabled")
    cpu_surge_threshold: float = Field(80.0, description="CPU % to trigger SURGE")
    cpu_medium_threshold: float = Field(50.0, description="CPU % to trigger MEDIUM")
    cpu_low_threshold: float = Field(20.0, description="CPU % to trigger LOW")
    cooldown_seconds: int = Field(60, description="Seconds before downgrade allowed")
    use_cpu_monitoring: bool = Field(True, description="Whether to use CPU usage for scaling")


class AutoScalingConfigResponse(BaseModel):
    """Response for auto-scaling configuration."""
    config: AutoScalingConfig
    current_cpu_usage: Optional[float] = Field(None, description="Current CPU usage %")


class SwitchBackendRequest(BaseModel):
    """Request to switch between dev and Linux backends."""
    use_linux_backend: bool = Field(..., description="True to use Linux cpufreq, False for dev simulation")


class SwitchBackendResponse(BaseModel):
    """Response after switching backends."""
    success: bool
    message: str
    is_using_linux_backend: bool = Field(..., description="Whether now using Linux backend")
    previous_backend: str = Field(..., description="Previous backend name")
    new_backend: str = Field(..., description="New backend name")


# Power Preset Schemas

class PowerPresetBase(BaseModel):
    """Base schema for power presets."""
    name: str = Field(..., min_length=1, max_length=100, description="Preset name")
    description: Optional[str] = Field(None, description="Preset description")
    base_clock_mhz: int = Field(1500, ge=100, le=10000, description="Base reference clock in MHz")
    idle_clock_mhz: int = Field(800, ge=100, le=10000, description="Clock for IDLE property in MHz")
    low_clock_mhz: int = Field(1200, ge=100, le=10000, description="Clock for LOW property in MHz")
    medium_clock_mhz: int = Field(2500, ge=100, le=10000, description="Clock for MEDIUM property in MHz")
    surge_clock_mhz: int = Field(4200, ge=100, le=10000, description="Clock for SURGE property in MHz")


class PowerPresetCreate(PowerPresetBase):
    """Schema for creating a new custom preset."""
    pass


class PowerPresetUpdate(BaseModel):
    """Schema for updating an existing preset."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="Preset name")
    description: Optional[str] = Field(None, description="Preset description")
    base_clock_mhz: Optional[int] = Field(None, ge=100, le=10000, description="Base reference clock in MHz")
    idle_clock_mhz: Optional[int] = Field(None, ge=100, le=10000, description="Clock for IDLE property in MHz")
    low_clock_mhz: Optional[int] = Field(None, ge=100, le=10000, description="Clock for LOW property in MHz")
    medium_clock_mhz: Optional[int] = Field(None, ge=100, le=10000, description="Clock for MEDIUM property in MHz")
    surge_clock_mhz: Optional[int] = Field(None, ge=100, le=10000, description="Clock for SURGE property in MHz")


class PowerPresetResponse(PowerPresetBase):
    """Schema for preset response."""
    id: int
    is_system_preset: bool = Field(..., description="Whether this is a system preset (cannot be deleted)")
    is_active: bool = Field(..., description="Whether this preset is currently active")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PowerPresetSummary(BaseModel):
    """Summary of a preset for embedding in other responses."""
    id: int
    name: str
    is_system_preset: bool
    is_active: bool

    class Config:
        from_attributes = True


class PowerPresetListResponse(BaseModel):
    """Response for listing all presets."""
    presets: list[PowerPresetResponse]
    active_preset: Optional[PowerPresetResponse] = None


class ActivatePresetResponse(BaseModel):
    """Response after activating a preset."""
    success: bool
    message: str
    previous_preset: Optional[PowerPresetSummary] = None
    new_preset: PowerPresetSummary
