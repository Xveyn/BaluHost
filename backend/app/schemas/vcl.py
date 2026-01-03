"""VCL Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ========== Version Blob Schemas ==========

class VersionBlobBase(BaseModel):
    """Base schema for version blob."""
    checksum: str = Field(..., min_length=64, max_length=64, description="SHA256 checksum")
    storage_path: str
    original_size: int = Field(..., gt=0)
    compressed_size: int = Field(..., gt=0)


class VersionBlobCreate(VersionBlobBase):
    """Schema for creating a new version blob."""
    pass


class VersionBlobInDB(VersionBlobBase):
    """Schema for version blob from database."""
    id: int
    reference_count: int
    created_at: datetime
    last_accessed: Optional[datetime] = None
    can_delete: bool
    
    model_config = ConfigDict(from_attributes=True)


# ========== File Version Schemas ==========

class FileVersionBase(BaseModel):
    """Base schema for file version."""
    file_id: int
    user_id: int
    version_number: int = Field(..., ge=1)
    storage_type: str = Field(..., pattern="^(stored|reference)$")
    file_size: int = Field(..., gt=0)
    compressed_size: int = Field(..., gt=0)
    checksum: str = Field(..., min_length=64, max_length=64)
    is_high_priority: bool = False
    change_type: Optional[str] = Field(None, pattern="^(create|update|overwrite|batched)$")
    comment: Optional[str] = None


class FileVersionCreate(FileVersionBase):
    """Schema for creating a new file version."""
    blob_id: Optional[int] = None
    was_cached: bool = False
    cache_duration: Optional[int] = None


class FileVersionInDB(FileVersionBase):
    """Schema for file version from database."""
    id: int
    blob_id: Optional[int] = None
    compression_ratio: Optional[float] = None
    created_at: datetime
    was_cached: bool
    cache_duration: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class FileVersionResponse(FileVersionInDB):
    """Extended response with additional computed fields."""
    file_name: Optional[str] = None
    user_name: Optional[str] = None
    size_saved: Optional[int] = None  # Bytes saved via compression


# ========== VCL Settings Schemas ==========

class VCLSettingsBase(BaseModel):
    """Base schema for VCL settings."""
    max_size_bytes: int = Field(..., gt=0)
    depth: int = Field(..., ge=1, le=100)
    headroom_percent: int = Field(..., ge=0, le=100)
    is_enabled: bool = True
    compression_enabled: bool = True
    dedupe_enabled: bool = True
    debounce_window_seconds: int = Field(..., ge=0, le=300)
    max_batch_window_seconds: int = Field(..., ge=0, le=3600)


class VCLSettingsUpdate(BaseModel):
    """Schema for updating VCL settings (all optional)."""
    max_size_bytes: Optional[int] = Field(None, gt=0)
    depth: Optional[int] = Field(None, ge=1, le=100)
    headroom_percent: Optional[int] = Field(None, ge=0, le=100)
    is_enabled: Optional[bool] = None
    compression_enabled: Optional[bool] = None
    dedupe_enabled: Optional[bool] = None
    debounce_window_seconds: Optional[int] = Field(None, ge=0, le=300)
    max_batch_window_seconds: Optional[int] = Field(None, ge=0, le=3600)


class VCLSettingsInDB(VCLSettingsBase):
    """Schema for VCL settings from database."""
    id: int
    user_id: Optional[int] = None
    current_usage_bytes: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class VCLSettingsResponse(BaseModel):
    """Response schema for VCL settings."""
    user_id: Optional[int] = None
    max_size_bytes: int
    current_usage_bytes: int
    depth: int
    headroom_percent: int
    is_enabled: bool
    compression_enabled: bool
    dedupe_enabled: bool
    debounce_window_seconds: int
    max_batch_window_seconds: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# ========== VCL Stats Schemas ==========

class VCLStatsBase(BaseModel):
    """Base schema for VCL stats."""
    total_versions: int = 0
    total_size_bytes: int = 0
    total_compressed_bytes: int = 0
    total_blobs: int = 0
    unique_blobs: int = 0
    deduplication_savings_bytes: int = 0
    compression_savings_bytes: int = 0
    priority_count: int = 0
    cached_versions_count: int = 0


class VCLStatsInDB(VCLStatsBase):
    """Schema for VCL stats from database."""
    id: int
    last_cleanup_at: Optional[datetime] = None
    last_priority_mode_at: Optional[datetime] = None
    last_deduplication_scan: Optional[datetime] = None
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class VCLStatsResponse(VCLStatsInDB):
    """Extended response with computed ratios."""
    compression_ratio: float
    compression_savings_percent: float
    deduplication_savings_percent: float


# ========== API Response Schemas ==========

class VersionDetail(BaseModel):
    """Detailed version information for API responses."""
    id: int
    version_number: int
    file_size: int
    compressed_size: int
    compression_ratio: float
    checksum: str
    created_at: datetime
    is_high_priority: bool
    change_type: Optional[str] = None
    comment: Optional[str] = None
    was_cached: bool
    storage_type: str
    
    model_config = ConfigDict(from_attributes=True)


class VersionListResponse(BaseModel):
    """Response for listing file versions."""
    file_id: int
    file_path: str
    total_versions: int
    versions: list[VersionDetail]


class RestoreRequest(BaseModel):
    """Request to restore a file version."""
    version_id: int


class RestoreResponse(BaseModel):
    """Response after restoring a version."""
    success: bool
    message: str
    file_id: int
    file_path: str
    restored_version: int
    file_size: int


class QuotaInfo(BaseModel):
    """User quota information."""
    max_size_bytes: int
    current_usage_bytes: int
    available_bytes: int
    usage_percent: float
    is_enabled: bool
    depth: int
    compression_enabled: bool
    dedupe_enabled: bool
    cleanup_needed: bool


class AdminVCLOverview(BaseModel):
    """Admin overview of VCL system."""
    total_versions: int
    total_size_bytes: int
    total_compressed_bytes: int
    total_blobs: int
    unique_blobs: int
    deduplication_savings_bytes: int
    compression_savings_bytes: int
    total_savings_bytes: int
    compression_ratio: float
    priority_count: int
    cached_versions_count: int
    total_users: int
    last_cleanup_at: Optional[datetime] = None
    last_priority_mode_at: Optional[datetime] = None
    updated_at: datetime


class AdminUserQuota(BaseModel):
    """User quota info for admin."""
    user_id: int
    username: str
    max_size_bytes: int
    current_usage_bytes: int
    usage_percent: float
    total_versions: int
    is_enabled: bool
    cleanup_needed: bool


class CleanupRequest(BaseModel):
    """Request for manual cleanup."""
    user_id: Optional[int] = None  # None = all users
    dry_run: bool = False  # If True, only simulate cleanup


class CleanupResponse(BaseModel):
    """Response after cleanup operation."""
    success: bool
    message: str
    deleted_versions: int
    freed_bytes: int
    affected_users: int


class AdminStatsResponse(BaseModel):
    """Detailed stats for admin."""
    total_versions: int
    total_size_bytes: int
    total_compressed_bytes: int
    total_blobs: int
    unique_blobs: int
    deduplication_savings_bytes: int
    compression_savings_bytes: int
    deduplication_ratio_percent: float
    compression_ratio_percent: float
    total_savings_ratio_percent: float
    priority_count: int
    cached_versions_count: int
    last_cleanup_at: Optional[datetime] = None
    last_priority_mode_at: Optional[datetime] = None
    last_deduplication_scan: Optional[datetime] = None
    updated_at: datetime


# ========== File Version List Schemas ==========

class FileVersionListItem(BaseModel):
    """Compact schema for version list."""
    id: int
    version_number: int
    file_size: int
    compressed_size: int
    compression_ratio: Optional[float] = None
    created_at: datetime
    is_high_priority: bool
    change_type: Optional[str] = None
    comment: Optional[str] = None
    user_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class FileVersionListResponse(BaseModel):
    """Response for paginated version list."""
    versions: list[FileVersionListItem]
    total: int
    file_name: str
    current_version: int


# ========== Version Restore Schemas ==========

class VersionRestoreRequest(BaseModel):
    """Request to restore a specific version."""
    version_id: int
    create_backup: bool = True
    comment: Optional[str] = None


class VersionRestoreResponse(BaseModel):
    """Response after version restore."""
    success: bool
    restored_version: int
    backup_version: Optional[int] = None
    message: str


# ========== User Quota Info ==========

class UserQuotaInfo(BaseModel):
    """User's VCL quota and usage information."""
    max_size_bytes: int
    current_usage_bytes: int
    usage_percent: float
    available_bytes: int
    is_over_headroom: bool
    depth: int
    is_enabled: bool
    versioned_files_count: int
    total_versions: int


# ========== Admin Schemas (moved from old duplicate) ==========
