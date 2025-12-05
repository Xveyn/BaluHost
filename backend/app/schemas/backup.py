"""Backup request and response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BackupBase(BaseModel):
    """Base backup schema."""
    backup_type: str = Field(default="full", pattern="^(full|incremental|database_only|files_only)$")
    includes_database: bool = True
    includes_files: bool = True
    includes_config: bool = False


class BackupCreate(BackupBase):
    """Schema for creating a new backup."""
    backup_path: Optional[str] = None


class BackupInDB(BackupBase):
    """Schema for backup stored in database."""
    id: int
    filename: str
    filepath: str
    size_bytes: int
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    creator_id: int
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class BackupResponse(BackupInDB):
    """Schema for backup response to client."""
    size_mb: float = Field(description="Size in megabytes for display")

    @classmethod
    def from_db(cls, backup: BackupInDB) -> "BackupResponse":
        """Convert database model to response schema."""
        return cls(
            **backup.model_dump(),
            size_mb=round(backup.size_bytes / (1024 * 1024), 2)
        )


class BackupListResponse(BaseModel):
    """Schema for listing backups."""
    backups: list[BackupResponse]
    total_size_bytes: int
    total_size_mb: float


class BackupRestoreRequest(BaseModel):
    """Schema for restore request."""
    backup_id: int
    restore_database: bool = True
    restore_files: bool = True
    restore_config: bool = False
    confirm: bool = Field(description="User must confirm restore operation")


class BackupRestoreResponse(BaseModel):
    """Schema for restore response."""
    success: bool
    message: str
    backup_id: int
    restored_at: datetime
