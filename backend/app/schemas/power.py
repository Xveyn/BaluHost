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


class PowerRating(str, Enum):
    """
    Power rating for API endpoints.

    Used by the @requires_power decorator to register
    power demands when endpoints are called.
    """
    IDLE = "idle"
    LOW = "low"
    MEDIUM = "medium"
    SURGE = "surge"


class PowerDemandInfo(BaseModel):
    """Information about an active power demand."""
    source: str = Field(..., description="Source identifier (e.g., 'backup_create', 'raid_rebuild')")
    level: PowerProfile = Field(..., description="Required power level")
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
