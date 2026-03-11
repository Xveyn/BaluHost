"""Pydantic schemas for file activity tracking."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Valid action types
# ---------------------------------------------------------------------------
VALID_ACTION_TYPES = {
    "file.open",
    "file.download",
    "file.upload",
    "file.edit",
    "file.delete",
    "file.move",
    "file.rename",
    "file.share",
    "file.permission",
    "folder.create",
    "sync.triggered",
}

# Actions with short retention (7 days instead of 90)
SHORT_RETENTION_ACTIONS = {"file.list", "file.view"}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class ActivityItem(BaseModel):
    """Single activity entry in API responses."""

    id: int
    action_type: str
    file_path: str
    file_name: str
    is_directory: bool
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    source: str
    device_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityListResponse(BaseModel):
    """Response for GET /api/activity/recent."""

    activities: List[ActivityItem]
    total: int
    has_more: bool


class RecentFileItem(BaseModel):
    """Single file in the recent-files response."""

    file_path: str
    file_name: str
    is_directory: bool
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    last_action: str
    last_action_at: datetime
    action_count: int


class RecentFilesResponse(BaseModel):
    """Response for GET /api/activity/recent-files."""

    files: List[RecentFileItem]


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class ReportedActivity(BaseModel):
    """Single activity reported by a client."""

    action_type: str = Field(..., description="Activity type, e.g. file.open")
    file_path: str = Field(..., description="Server-relative file path")
    file_name: str = Field(..., description="File name for display")
    is_directory: bool = Field(False)
    file_size: Optional[int] = Field(None, ge=0)
    mime_type: Optional[str] = None
    device_id: Optional[str] = None
    occurred_at: Optional[datetime] = Field(
        None,
        description="When the action occurred on the client (ISO timestamp)",
    )


class ReportActivitiesRequest(BaseModel):
    """Request body for POST /api/activity/report."""

    activities: List[ReportedActivity] = Field(
        ..., min_length=1, max_length=100
    )


class ReportActivitiesResponse(BaseModel):
    """Response for POST /api/activity/report."""

    accepted: int
    deduplicated: int
    rejected: int
