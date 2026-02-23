"""Pydantic schemas for data migration API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


def _reject_path_traversal(v: str) -> str:
    """Reject paths containing '..' components."""
    if ".." in v:
        raise ValueError("Path must not contain '..'")
    return v


class VCLMigrationStartRequest(BaseModel):
    """Start a VCL blob migration from HDD to SSD."""
    source_path: str
    dest_path: str
    dry_run: bool = False

    @field_validator("source_path", "dest_path")
    @classmethod
    def validate_paths(cls, v: str) -> str:
        return _reject_path_traversal(v)


class VCLVerifyRequest(BaseModel):
    """Start integrity verification of migrated VCL blobs."""
    dest_path: str

    @field_validator("dest_path")
    @classmethod
    def validate_dest(cls, v: str) -> str:
        return _reject_path_traversal(v)


class VCLCleanupRequest(BaseModel):
    """Start cleanup of source blobs after verified migration."""
    source_path: str
    dry_run: bool = False

    @field_validator("source_path")
    @classmethod
    def validate_source(cls, v: str) -> str:
        return _reject_path_traversal(v)


class DirectoryEntry(BaseModel):
    """A directory entry returned by the browse endpoint."""
    name: str
    path: str
    is_mountpoint: bool


class MigrationJobResponse(BaseModel):
    """Migration job status and progress."""
    id: int
    job_type: str
    status: str
    source_path: str
    dest_path: str
    total_files: int
    processed_files: int
    skipped_files: int
    failed_files: int
    total_bytes: int
    processed_bytes: int
    current_file: Optional[str]
    progress_percent: float
    error_message: Optional[str]
    dry_run: bool
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
