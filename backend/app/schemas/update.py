"""Update service request and response schemas."""
from datetime import datetime
from typing import Optional, Literal, Any

from pydantic import BaseModel, Field


# Literal types for validation
UpdateStatusEnum = Literal[
    "pending", "checking", "downloading", "backing_up", "installing",
    "migrating", "restarting", "health_check", "completed", "failed",
    "rolled_back", "cancelled"
]
UpdateChannelEnum = Literal["stable", "beta"]


class VersionInfo(BaseModel):
    """Information about a version."""

    version: str = Field(description="Semantic version string (e.g., '1.5.0')")
    commit: str = Field(description="Git commit hash")
    commit_short: str = Field(description="Short commit hash (7 chars)")
    tag: Optional[str] = Field(default=None, description="Git tag if exists")
    date: Optional[datetime] = Field(default=None, description="Commit/tag date")


class ChangelogEntry(BaseModel):
    """Single changelog entry."""

    version: str = Field(description="Version number")
    date: Optional[datetime] = Field(default=None, description="Release date")
    changes: list[str] = Field(default_factory=list, description="List of changes")
    breaking_changes: list[str] = Field(default_factory=list, description="Breaking changes")
    is_prerelease: bool = Field(default=False, description="Whether this is a prerelease")


class UpdateCheckResponse(BaseModel):
    """Response from checking for updates."""

    update_available: bool = Field(description="Whether an update is available")
    current_version: VersionInfo = Field(description="Current installed version")
    latest_version: Optional[VersionInfo] = Field(
        default=None,
        description="Latest available version (if update available)"
    )
    changelog: list[ChangelogEntry] = Field(
        default_factory=list,
        description="Changelog entries between current and latest"
    )
    channel: UpdateChannelEnum = Field(description="Update channel")
    last_checked: Optional[datetime] = Field(
        default=None,
        description="When last checked for updates"
    )
    # Blockers
    blockers: list[str] = Field(
        default_factory=list,
        description="Issues blocking update (e.g., 'RAID rebuild in progress')"
    )
    can_update: bool = Field(
        default=True,
        description="Whether update can proceed (no blockers)"
    )


class UpdateStartRequest(BaseModel):
    """Request to start an update."""

    target_version: Optional[str] = Field(
        default=None,
        description="Specific version to update to (default: latest)"
    )
    skip_backup: bool = Field(
        default=False,
        description="Skip database backup (not recommended)"
    )
    force: bool = Field(
        default=False,
        description="Force update even with non-critical blockers"
    )


class UpdateStartResponse(BaseModel):
    """Response from starting an update."""

    success: bool = Field(description="Whether update was started")
    update_id: Optional[int] = Field(
        default=None,
        description="ID of the update record"
    )
    message: str = Field(description="Status message")
    blockers: list[str] = Field(
        default_factory=list,
        description="Blocking issues if not started"
    )


class UpdateProgressResponse(BaseModel):
    """Response for update progress."""

    update_id: int = Field(description="Update record ID")
    status: UpdateStatusEnum = Field(description="Current status")
    progress_percent: int = Field(ge=0, le=100, description="Progress percentage")
    current_step: Optional[str] = Field(
        default=None,
        description="Current step description"
    )
    started_at: datetime = Field(description="When update started")
    estimated_remaining: Optional[int] = Field(
        default=None,
        description="Estimated seconds remaining"
    )
    from_version: str = Field(description="Version updating from")
    to_version: str = Field(description="Version updating to")
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if failed"
    )
    can_rollback: bool = Field(
        default=False,
        description="Whether rollback is possible"
    )


class UpdateHistoryEntry(BaseModel):
    """Single entry in update history."""

    id: int
    from_version: str
    to_version: str
    channel: UpdateChannelEnum
    from_commit: str
    to_commit: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    status: UpdateStatusEnum
    error_message: Optional[str] = None
    rollback_commit: Optional[str] = None
    user_id: Optional[int] = None
    can_rollback: bool = Field(
        default=False,
        description="Whether this update can be rolled back to"
    )

    model_config = {"from_attributes": True}


class UpdateHistoryResponse(BaseModel):
    """Paginated update history response."""

    updates: list[UpdateHistoryEntry]
    total: int
    page: int = 1
    page_size: int = 20


class RollbackRequest(BaseModel):
    """Request to rollback to a previous version."""

    target_update_id: Optional[int] = Field(
        default=None,
        description="Update ID to rollback to (default: previous successful update)"
    )
    target_commit: Optional[str] = Field(
        default=None,
        description="Specific commit to rollback to"
    )
    restore_backup: bool = Field(
        default=True,
        description="Restore database backup from that update"
    )


class RollbackResponse(BaseModel):
    """Response from rollback operation."""

    success: bool
    message: str
    update_id: Optional[int] = Field(
        default=None,
        description="ID of the rollback update record"
    )
    rolled_back_to: Optional[str] = Field(
        default=None,
        description="Version rolled back to"
    )


class UpdateConfigBase(BaseModel):
    """Base update configuration schema."""

    auto_check_enabled: bool = Field(
        default=True,
        description="Automatically check for updates"
    )
    check_interval_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Hours between auto-checks (1-168)"
    )
    channel: UpdateChannelEnum = Field(
        default="stable",
        description="Update channel"
    )
    auto_backup_before_update: bool = Field(
        default=True,
        description="Create database backup before updating"
    )
    require_healthy_services: bool = Field(
        default=True,
        description="Require all services healthy before update"
    )
    auto_update_enabled: bool = Field(
        default=False,
        description="Automatically install updates (not recommended)"
    )
    auto_update_window_start: Optional[str] = Field(
        default=None,
        description="Auto-update window start (HH:MM)"
    )
    auto_update_window_end: Optional[str] = Field(
        default=None,
        description="Auto-update window end (HH:MM)"
    )


class UpdateConfigUpdate(BaseModel):
    """Schema for updating configuration (all fields optional)."""

    auto_check_enabled: Optional[bool] = None
    check_interval_hours: Optional[int] = Field(default=None, ge=1, le=168)
    channel: Optional[UpdateChannelEnum] = None
    auto_backup_before_update: Optional[bool] = None
    require_healthy_services: Optional[bool] = None
    auto_update_enabled: Optional[bool] = None
    auto_update_window_start: Optional[str] = None
    auto_update_window_end: Optional[str] = None


class UpdateConfigResponse(UpdateConfigBase):
    """Response for update configuration."""

    id: int
    last_check_at: Optional[datetime] = None
    last_available_version: Optional[str] = None
    updated_at: datetime
    updated_by: Optional[int] = None

    model_config = {"from_attributes": True}


# WebSocket message schemas for real-time updates
class UpdateWebSocketMessage(BaseModel):
    """WebSocket message for update events."""

    type: Literal[
        "update_available", "update_progress", "update_complete",
        "update_failed", "rollback_complete"
    ] = Field(description="Message type")
    payload: Any = Field(description="Message payload")


class UpdateAvailablePayload(BaseModel):
    """Payload for update_available message."""

    version: str
    channel: UpdateChannelEnum
    changelog_summary: str


class UpdateProgressPayload(BaseModel):
    """Payload for update_progress message."""

    update_id: int
    status: UpdateStatusEnum
    progress_percent: int
    current_step: str


class UpdateCompletePayload(BaseModel):
    """Payload for update_complete message."""

    success: bool
    new_version: str
    restart_in_seconds: Optional[int] = Field(
        default=None,
        description="Countdown before service restart"
    )


class UpdateFailedPayload(BaseModel):
    """Payload for update_failed message."""

    update_id: int
    error_message: str
    can_rollback: bool
