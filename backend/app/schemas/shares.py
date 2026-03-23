"""Pydantic schemas for file sharing."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ===========================
# File Share Schemas
# ===========================

class FileShareCreate(BaseModel):
    """Schema for creating a file share with another user."""
    file_id: int = Field(..., description="ID of the file to share")
    shared_with_user_id: int = Field(..., description="User ID to share with")
    can_read: bool = Field(default=True, description="Allow read access")
    can_write: bool = Field(default=False, description="Allow write access")
    can_delete: bool = Field(default=False, description="Allow delete access")
    can_share: bool = Field(default=False, description="Allow re-sharing with others")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration date (None = never expires)")


class FileShareUpdate(BaseModel):
    """Schema for updating a file share."""
    can_read: Optional[bool] = None
    can_write: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_share: Optional[bool] = None
    expires_at: Optional[datetime] = None


class FileShareResponse(BaseModel):
    """Schema for file share response."""
    id: int
    file_id: int
    owner_id: int
    shared_with_user_id: int
    can_read: bool
    can_write: bool
    can_delete: bool
    can_share: bool
    expires_at: Optional[datetime]
    created_at: datetime
    last_accessed_at: Optional[datetime]
    is_expired: bool
    is_accessible: bool
    
    # User information
    owner_username: Optional[str] = None
    shared_with_username: Optional[str] = None
    
    # File information
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    is_directory: bool = False

    model_config = {"from_attributes": True}


class SharedWithMeResponse(BaseModel):
    """Schema for files shared with the current user."""
    share_id: int
    file_id: int
    file_name: str
    file_path: str
    file_size: int
    is_directory: bool
    owner_username: str
    owner_id: int
    can_read: bool
    can_write: bool
    can_delete: bool
    can_share: bool
    shared_at: datetime
    expires_at: Optional[datetime]
    is_expired: bool
    
    model_config = {"from_attributes": True}


class ShareStatistics(BaseModel):
    """Statistics for sharing activity."""
    total_file_shares: int
    active_file_shares: int
    files_shared_with_me: int
