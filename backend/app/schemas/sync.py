"""Pydantic schemas for file sync."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class RegisterDeviceRequest(BaseModel):
    """Register a device for synchronization."""
    device_id: str = Field(..., description="Unique device identifier")
    device_name: Optional[str] = Field(None, description="Human-readable device name")
    registration_token: Optional[str] = Field(None, description="One-time registration token (required for registration)")


class SyncFileInfo(BaseModel):
    """File information from client for sync."""
    path: str = Field(..., description="File path")
    hash: str = Field(..., description="SHA256 content hash")
    size: int = Field(..., description="File size in bytes")
    modified_at: str = Field(..., description="ISO 8601 modified timestamp")


class SyncChangesRequest(BaseModel):
    """Request to detect changes."""
    device_id: str = Field(..., description="Device identifier")
    file_list: list[SyncFileInfo] = Field(..., description="List of files on client")


class ChangeItem(BaseModel):
    """Single change item."""
    path: str
    action: str  # 'add', 'update', 'delete', 'mkdir'
    size: Optional[int] = None
    modified_at: Optional[str] = None


class ConflictItem(BaseModel):
    """Conflict item."""
    path: str
    client_hash: str
    server_hash: str
    server_modified_at: str


class SyncChangesResponse(BaseModel):
    """Response with detected changes."""
    to_download: list[ChangeItem] = Field(..., description="Files to download")
    to_delete: list[dict] = Field(..., description="Files to delete")
    conflicts: list[ConflictItem] = Field(..., description="Conflicting files")
    change_token: str = Field(..., description="Change token for next sync")


class SyncStatusResponse(BaseModel):
    """Sync status for a device."""
    status: str
    device_id: str
    device_name: str
    last_sync: str
    pending_changes: int
    conflicts: int
    change_token: Optional[str] = None


class ResolveConflictRequest(BaseModel):
    """Resolve a file conflict."""
    file_path: str = Field(..., description="File path")
    resolution: str = Field(..., description="Resolution method: keep_local, keep_server, create_version")


class ResolveConflictResponse(BaseModel):
    """Response after resolving conflict."""
    file_path: str
    resolution: str
    resolved: bool


class FileVersionInfo(BaseModel):
    """Information about a file version."""
    version_number: int
    size: int
    hash: str
    created_at: str
    reason: Optional[str] = None


class FileHistoryResponse(BaseModel):
    """File version history."""
    file_path: str
    versions: list[FileVersionInfo]


# ============================================================================
# PROGRESSIVE SYNC SCHEMAS
# ============================================================================

class StartChunkedUploadRequest(BaseModel):
    """Start a chunked upload session."""
    file_path: str
    file_name: str
    total_size: int
    chunk_size: int = 5 * 1024 * 1024  # 5MB default


class UploadChunkResponse(BaseModel):
    """Response after uploading a chunk."""
    chunk_number: int
    uploaded_size: int
    total_size: int
    complete: bool


class UploadProgressResponse(BaseModel):
    """Progress of a chunked upload."""
    upload_id: str
    file_name: str
    file_path: str
    total_size: int
    uploaded_size: int
    chunk_size: int
    chunks_uploaded: list[int]
    is_completed: bool
    created_at: str
    last_updated: str


class SetBandwidthLimitRequest(BaseModel):
    """Set bandwidth limits for sync operations."""
    upload_speed_limit: Optional[int] = None  # bytes/sec
    download_speed_limit: Optional[int] = None  # bytes/sec


class BandwidthLimitResponse(BaseModel):
    """Current bandwidth limits."""
    upload_speed_limit: Optional[int]
    download_speed_limit: Optional[int]


class CreateSyncScheduleRequest(BaseModel):
    """Create a sync schedule."""
    device_id: str
    schedule_type: str = Field(..., description="daily, weekly, monthly, on_change")
    time_of_day: Optional[str] = Field(None, description="HH:MM format")
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    sync_deletions: bool = True
    resolve_conflicts: str = "keep_newest"


class UpdateSyncScheduleRequest(BaseModel):
    """Update an existing sync schedule."""
    schedule_type: Optional[str] = Field(None, description="daily, weekly, monthly, on_change")
    time_of_day: Optional[str] = Field(None, description="HH:MM format")
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    sync_deletions: Optional[bool] = None
    resolve_conflicts: Optional[str] = None
    is_active: Optional[bool] = None


class SyncScheduleResponse(BaseModel):
    """Sync schedule information."""
    schedule_id: int
    device_id: str
    schedule_type: str
    time_of_day: str
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    next_run_at: Optional[str]
    last_run_at: Optional[str]
    enabled: bool
    sync_deletions: bool = True
    resolve_conflicts: str = "keep_newest"


class SelectiveSyncFolder(BaseModel):
    """Selective sync folder configuration."""
    path: str
    enabled: bool = True
    include_subfolders: bool = True


class SelectiveSyncRequest(BaseModel):
    """Configure selective sync."""
    device_id: str
    folders: list[dict]  # Using dict for flexibility with legacy code


class SelectiveSyncResponse(BaseModel):
    """Selective sync configuration."""
    device_id: str
    sync_paths: list[str]


# ============================================================================
# DESKTOP SYNC FOLDER TRACKING
# ============================================================================

class SyncFolderReport(BaseModel):
    """Single folder report from BaluDesk client."""
    remote_path: str = Field(..., description="Remote path on BaluHost being synced")
    sync_direction: str = Field("bidirectional", description="bidirectional, push, or pull")


class ReportSyncFoldersRequest(BaseModel):
    """BaluDesk reports its active sync folders."""
    device_id: str = Field(..., description="Unique device identifier")
    device_name: str = Field(..., description="Human-readable device name")
    platform: str = Field(..., description="windows, mac, or linux")
    folders: list[SyncFolderReport] = Field(..., description="Currently active sync folders")


class ReportSyncFoldersResponse(BaseModel):
    """Response after processing sync folder report."""
    accepted: int = Field(..., description="Number of folders accepted")
    deactivated: int = Field(..., description="Number of previously active folders now deactivated")


class SyncDeviceInfo(BaseModel):
    """Info about a device syncing a specific folder."""
    device_name: str
    platform: str
    sync_direction: str
    last_reported_at: str


class SyncedFolderInfo(BaseModel):
    """Full info about a synced folder."""
    remote_path: str
    device_id: str
    device_name: str
    platform: str
    sync_direction: str
    is_active: bool
    last_reported_at: str
    username: str | None = None


class SyncedFoldersResponse(BaseModel):
    """List of synced folders."""
    folders: list[SyncedFolderInfo]
