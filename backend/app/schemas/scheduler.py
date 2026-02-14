"""Scheduler request and response schemas."""
from datetime import datetime
from typing import Optional, Literal, Any

from pydantic import BaseModel, Field


class SchedulerStatusResponse(BaseModel):
    """Status of a single scheduler."""

    name: str = Field(description="Unique scheduler identifier")
    display_name: str = Field(description="Human-readable scheduler name")
    description: str = Field(description="What this scheduler does")

    # Status
    is_running: bool = Field(description="Whether the scheduler background job is running")
    is_enabled: bool = Field(description="Whether the scheduler is enabled in config")

    # Timing
    interval_seconds: int = Field(description="Interval between executions in seconds")
    interval_display: str = Field(description="Human-readable interval (e.g., 'Every 7 days')")
    last_run_at: Optional[datetime] = Field(
        default=None, description="When the scheduler last ran"
    )
    next_run_at: Optional[datetime] = Field(
        default=None, description="When the scheduler will run next"
    )

    # Last execution result
    last_status: Optional[Literal["requested", "completed", "failed", "running", "cancelled"]] = Field(
        default=None, description="Status of the last execution"
    )

    # Worker health (heartbeat-based)
    worker_healthy: Optional[bool] = Field(
        default=None, description="Whether the scheduler worker process is healthy (heartbeat < 60s)"
    )
    last_error: Optional[str] = Field(
        default=None, description="Error message if last execution failed"
    )
    last_duration_ms: Optional[int] = Field(
        default=None, description="Duration of last execution in milliseconds"
    )

    # Configuration
    config_key: Optional[str] = Field(
        default=None, description="Config key for UI configuration"
    )
    can_run_manually: bool = Field(
        default=True, description="Whether this scheduler can be triggered manually"
    )
    extra_config: Optional[dict[str, Any]] = Field(
        default=None, description="Scheduler-specific configuration (e.g. backup_type)"
    )


class SchedulerListResponse(BaseModel):
    """List of all schedulers with their status."""

    schedulers: list[SchedulerStatusResponse]
    total_running: int = Field(description="Number of running schedulers")
    total_enabled: int = Field(description="Number of enabled schedulers")


class SchedulerExecutionResponse(BaseModel):
    """Single scheduler execution history entry."""

    id: int
    scheduler_name: str
    job_id: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: Literal["requested", "running", "completed", "failed", "cancelled"]
    trigger_type: Literal["scheduled", "manual"]
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    user_id: Optional[int] = None
    duration_ms: Optional[int] = None

    # Computed fields for display
    duration_display: Optional[str] = Field(
        default=None, description="Human-readable duration"
    )

    model_config = {"from_attributes": True}

    @classmethod
    def from_db(cls, execution) -> "SchedulerExecutionResponse":
        """Convert database model to response schema."""
        duration_display = None
        if execution.duration_ms is not None:
            if execution.duration_ms < 1000:
                duration_display = f"{execution.duration_ms}ms"
            elif execution.duration_ms < 60000:
                duration_display = f"{execution.duration_ms / 1000:.1f}s"
            else:
                minutes = execution.duration_ms / 60000
                duration_display = f"{minutes:.1f}min"

        return cls(
            id=execution.id,
            scheduler_name=execution.scheduler_name,
            job_id=execution.job_id,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            status=execution.status,
            trigger_type=execution.trigger_type,
            result_summary=execution.result_summary,
            error_message=execution.error_message,
            user_id=execution.user_id,
            duration_ms=execution.duration_ms,
            duration_display=duration_display,
        )


class SchedulerHistoryResponse(BaseModel):
    """Paginated scheduler execution history."""

    executions: list[SchedulerExecutionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SchedulerConfigUpdate(BaseModel):
    """Request to update scheduler configuration."""

    interval_seconds: Optional[int] = Field(
        default=None,
        ge=60,
        description="New interval in seconds (minimum 60)"
    )
    is_enabled: Optional[bool] = Field(
        default=None,
        description="Enable or disable the scheduler"
    )
    extra_config: Optional[dict[str, Any]] = Field(
        default=None,
        description="Scheduler-specific configuration (e.g. backup_type)"
    )


class RunNowRequest(BaseModel):
    """Request to run a scheduler immediately."""

    force: bool = Field(
        default=False,
        description="Run even if scheduler is currently running"
    )


class RunNowResponse(BaseModel):
    """Response from running a scheduler manually."""

    success: bool
    message: str
    execution_id: Optional[int] = Field(
        default=None, description="ID of the new execution record"
    )
    scheduler_name: str
    status: Literal["requested", "started", "already_running", "disabled", "error"]


class SchedulerToggleRequest(BaseModel):
    """Request to enable/disable a scheduler."""

    enabled: bool


class SchedulerToggleResponse(BaseModel):
    """Response from toggling scheduler enabled state."""

    success: bool
    scheduler_name: str
    is_enabled: bool
    message: str


# Scheduler registry info for frontend
SCHEDULER_REGISTRY: dict[str, dict[str, Any]] = {
    "raid_scrub": {
        "display_name": "RAID Scrub",
        "description": "Performs RAID array scrub to check data integrity and repair errors",
        "config_key": "RAID_SCRUB_INTERVAL_HOURS",
        "default_interval": 604800,  # 7 days
        "can_run_manually": True,
    },
    "smart_scan": {
        "display_name": "SMART Scan",
        "description": "Scans disk health using SMART data to detect potential failures",
        "config_key": "SMART_SCAN_INTERVAL_MINUTES",
        "default_interval": 3600,  # 60 minutes
        "can_run_manually": True,
    },
    "backup": {
        "display_name": "Auto Backup",
        "description": "Creates automated system backups including database and files",
        "config_key": "BACKUP_AUTO_INTERVAL_HOURS",
        "default_interval": 86400,  # 24 hours
        "can_run_manually": True,
    },
    "sync_check": {
        "display_name": "Sync Check",
        "description": "Checks for due sync schedules and triggers synchronization",
        "config_key": None,  # Fixed interval
        "default_interval": 300,  # 5 minutes
        "can_run_manually": True,
    },
    "notification_check": {
        "display_name": "Notification Check",
        "description": "Checks for expiring devices and sends push notification warnings",
        "config_key": None,  # Fixed interval
        "default_interval": 3600,  # 1 hour
        "can_run_manually": True,
    },
    "upload_cleanup": {
        "display_name": "Upload Cleanup",
        "description": "Cleans up expired chunked uploads to free storage space",
        "config_key": None,  # Fixed schedule
        "default_interval": 86400,  # Daily at 3 AM
        "can_run_manually": True,
    },
    "auto_update": {
        "display_name": "Auto Update Check",
        "description": "Automatically checks for available BaluHost updates",
        "config_key": "AUTO_UPDATE_CHECK_ENABLED",
        "default_interval": 86400,  # 24 hours
        "can_run_manually": True,
    },
}
