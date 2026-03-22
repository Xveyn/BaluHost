"""
Pydantic schemas for Sleep Mode feature.

Defines the state machine, request/response models, and configuration
for the two-stage sleep system (Soft Sleep + True Suspend).
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from app.schemas.validators import validate_mac_address


class SleepState(str, Enum):
    """
    Sleep mode state machine states.

    AWAKE: Normal operation
    ENTERING_SOFT_SLEEP: Transitioning to soft sleep
    SOFT_SLEEP: Server reachable, reduced power (CPU IDLE, services paused)
    ENTERING_SUSPEND: Transitioning to true suspend
    TRUE_SUSPEND: System suspended (~1-2W), wake via WoL/rtcwake
    WAKING: Transitioning back to awake
    """
    AWAKE = "awake"
    ENTERING_SOFT_SLEEP = "entering_soft_sleep"
    SOFT_SLEEP = "soft_sleep"
    ENTERING_SUSPEND = "entering_suspend"
    TRUE_SUSPEND = "true_suspend"
    WAKING = "waking"


class SleepTrigger(str, Enum):
    """What triggered the sleep state change."""
    MANUAL = "manual"
    AUTO_IDLE = "auto_idle"
    SCHEDULE = "schedule"
    AUTO_WAKE = "auto_wake"
    AUTO_ESCALATION = "auto_escalation"
    WOL = "wol"
    RTC_WAKE = "rtc_wake"


class ScheduleMode(str, Enum):
    """Sleep mode to use for scheduled sleep."""
    SOFT = "soft"
    SUSPEND = "suspend"


# ---------------------------------------------------------------------------
# Activity Metrics
# ---------------------------------------------------------------------------

class ActivityMetrics(BaseModel):
    """Current system activity metrics used for idle detection."""
    cpu_usage_avg: float = Field(default=0.0, description="Average CPU usage %")
    disk_io_avg_mbps: float = Field(default=0.0, description="Average disk I/O in MB/s")
    active_uploads: int = Field(default=0, description="Number of active file uploads")
    active_downloads: int = Field(default=0, description="Number of active file downloads")
    http_requests_per_minute: float = Field(default=0.0, description="HTTP requests per minute")


# ---------------------------------------------------------------------------
# Status / Response
# ---------------------------------------------------------------------------

class SleepStatusResponse(BaseModel):
    """Current sleep mode status."""
    current_state: SleepState = Field(..., description="Current sleep state")
    state_since: Optional[datetime] = Field(default=None, description="When current state was entered")
    idle_seconds: float = Field(default=0.0, description="Seconds system has been idle")
    idle_threshold_seconds: float = Field(default=0.0, description="Seconds of idle before auto-sleep")
    activity_metrics: ActivityMetrics = Field(default_factory=ActivityMetrics)
    paused_services: list[str] = Field(default_factory=list, description="Services paused by sleep mode")
    spun_down_disks: list[str] = Field(default_factory=list, description="Disks spun down by sleep mode")
    auto_idle_enabled: bool = Field(default=False, description="Whether auto-idle detection is active")
    schedule_enabled: bool = Field(default=False, description="Whether sleep schedule is active")
    escalation_enabled: bool = Field(default=False, description="Whether auto-escalation to suspend is enabled")


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class EnterSoftSleepRequest(BaseModel):
    """Request to enter soft sleep mode."""
    reason: Optional[str] = Field(default=None, description="Optional reason for entering sleep")


class EnterSuspendRequest(BaseModel):
    """Request to enter true suspend."""
    wake_at: Optional[datetime] = Field(default=None, description="Optional RTC wake time")
    reason: Optional[str] = Field(default=None, description="Optional reason for suspending")


class WolRequest(BaseModel):
    """Request to send a Wake-on-LAN magic packet."""
    mac_address: Optional[str] = Field(default=None, description="Target MAC address (uses configured if omitted)")
    broadcast_address: Optional[str] = Field(default=None, description="Broadcast address (uses configured if omitted)")

    @field_validator("mac_address", mode="before")
    @classmethod
    def _validate_mac(cls, v: Optional[str]) -> Optional[str]:
        return validate_mac_address(v)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class SleepConfigResponse(BaseModel):
    """Full sleep mode configuration."""
    # Auto-idle detection
    auto_idle_enabled: bool = Field(default=False, description="Enable automatic idle detection")
    idle_timeout_minutes: int = Field(default=15, description="Minutes of idle before entering sleep")
    idle_cpu_threshold: float = Field(default=5.0, description="CPU usage % threshold for idle")
    idle_disk_io_threshold: float = Field(default=0.5, description="Disk I/O MB/s threshold for idle")
    idle_http_threshold: float = Field(default=5.0, description="HTTP requests/min threshold for idle")
    # Auto-escalation
    auto_escalation_enabled: bool = Field(default=False, description="Auto-escalate soft sleep to suspend")
    escalation_after_minutes: int = Field(default=60, description="Minutes in soft sleep before escalation")
    # Schedule
    schedule_enabled: bool = Field(default=False, description="Enable sleep schedule")
    schedule_sleep_time: str = Field(default="23:00", description="Time to enter sleep (HH:MM)")
    schedule_wake_time: str = Field(default="06:00", description="Time to wake (HH:MM)")
    schedule_mode: ScheduleMode = Field(default=ScheduleMode.SOFT, description="Sleep mode for schedule")
    # WoL
    wol_mac_address: Optional[str] = Field(default=None, description="MAC address for WoL")
    wol_broadcast_address: Optional[str] = Field(default=None, description="Broadcast address for WoL")
    # Service pausing
    pause_monitoring: bool = Field(default=True, description="Pause monitoring during sleep")
    pause_disk_io: bool = Field(default=True, description="Pause disk I/O monitor during sleep")
    reduced_telemetry_interval: float = Field(default=30.0, description="Telemetry interval during sleep (seconds)")
    # Disk spindown
    disk_spindown_enabled: bool = Field(default=True, description="Spin down data disks during sleep")


class SleepConfigUpdate(BaseModel):
    """Partial update for sleep mode configuration."""
    auto_idle_enabled: Optional[bool] = None
    idle_timeout_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    idle_cpu_threshold: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    idle_disk_io_threshold: Optional[float] = Field(default=None, ge=0.0)
    idle_http_threshold: Optional[float] = Field(default=None, ge=0.0)
    auto_escalation_enabled: Optional[bool] = None
    escalation_after_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    schedule_enabled: Optional[bool] = None
    schedule_sleep_time: Optional[str] = None
    schedule_wake_time: Optional[str] = None
    schedule_mode: Optional[ScheduleMode] = None
    wol_mac_address: Optional[str] = None
    wol_broadcast_address: Optional[str] = None
    pause_monitoring: Optional[bool] = None
    pause_disk_io: Optional[bool] = None
    reduced_telemetry_interval: Optional[float] = Field(default=None, ge=5.0, le=300.0)
    disk_spindown_enabled: Optional[bool] = None

    @field_validator("wol_mac_address", mode="before")
    @classmethod
    def _validate_wol_mac(cls, v: Optional[str]) -> Optional[str]:
        return validate_mac_address(v)


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

class SleepCapabilities(BaseModel):
    """System capabilities for sleep mode features."""
    hdparm_available: bool = Field(default=False, description="hdparm available for disk spindown")
    rtcwake_available: bool = Field(default=False, description="rtcwake available for timed wake")
    systemctl_available: bool = Field(default=False, description="systemctl available for suspend")
    can_suspend: bool = Field(default=False, description="System supports suspend")
    wol_interfaces: list[str] = Field(default_factory=list, description="Network interfaces with WoL support")
    data_disk_devices: list[str] = Field(default_factory=list, description="Data disks (non-OS)")
    own_mac_address: Optional[str] = Field(default=None, description="Detected MAC of primary NIC")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class SleepHistoryEntry(BaseModel):
    """A single sleep state change log entry."""
    id: int
    timestamp: datetime
    previous_state: SleepState
    new_state: SleepState
    reason: str
    triggered_by: SleepTrigger
    details: Optional[dict] = None
    duration_seconds: Optional[float] = None


class SleepHistoryResponse(BaseModel):
    """Paginated sleep state history."""
    entries: list[SleepHistoryEntry] = Field(default_factory=list)
    total: int = Field(default=0)
