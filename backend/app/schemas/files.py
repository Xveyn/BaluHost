from pydantic import BaseModel, Field
from typing import List

class FilePermissionRule(BaseModel):
    user_id: int
    can_view: bool = True
    can_edit: bool = True
    can_delete: bool = True

class FilePermissions(BaseModel):
    path: str
    owner_id: int
    rules: List[FilePermissionRule]

class FilePermissionsRequest(BaseModel):
    path: str
    owner_id: int = Field(..., gt=0)
    rules: List[FilePermissionRule]
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.sync import SyncDeviceInfo


class FileItem(BaseModel):
    name: str
    path: str
    size: int
    type: Literal["file", "directory"]
    modified_at: datetime
    owner_id: str | None = None
    mime_type: str | None = None
    file_id: int | None = None
    sync_info: list[SyncDeviceInfo] | None = None


class FileListResponse(BaseModel):
    files: list[FileItem]


class FileOperationResponse(BaseModel):
    message: str


class FileUploadResponse(FileOperationResponse):
    uploaded: int
    upload_ids: list[str] | None = None


class FolderCreateRequest(BaseModel):
    path: str | None = ""
    name: str


class RenameRequest(BaseModel):
    old_path: str
    new_name: str


class MoveRequest(BaseModel):
    source_path: str
    target_path: str


# ============================================================================
# Ownership Transfer Schemas
# ============================================================================

class OwnershipTransferRequest(BaseModel):
    """Request to transfer ownership of a file or directory."""
    path: str
    new_owner_id: int = Field(..., gt=0)
    recursive: bool = True
    conflict_strategy: Literal["rename", "skip", "overwrite"] = "rename"


class ConflictInfo(BaseModel):
    """Information about a naming conflict during transfer."""
    original_path: str
    resolved_path: str | None
    action: str  # "renamed", "skipped", "overwritten", "no_conflict"


class OwnershipTransferResponse(BaseModel):
    """Response from an ownership transfer operation."""
    success: bool
    message: str
    transferred_count: int = 0
    skipped_count: int = 0
    new_path: str | None = None
    conflicts: list[ConflictInfo] = []
    error: str | None = None


# ============================================================================
# Residency Enforcement Schemas
# ============================================================================

class ResidencyViolation(BaseModel):
    """Information about a file that violates residency rules."""
    path: str
    current_owner_id: int
    current_owner_username: str
    expected_directory: str
    actual_directory: str


class EnforceResidencyRequest(BaseModel):
    """Request to scan/fix residency violations."""
    dry_run: bool = True
    scope: str | None = None  # None = all users, or specific username


class EnforceResidencyResponse(BaseModel):
    """Response from a residency enforcement operation."""
    violations: list[ResidencyViolation] = []
    fixed_count: int = 0
