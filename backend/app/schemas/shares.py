"""Pydantic schemas for file sharing."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ===========================
# Share Link Schemas
# ===========================

class ShareLinkCreate(BaseModel):
    """Schema for creating a new share link."""
    file_id: int = Field(..., description="ID of the file to share")
    password: Optional[str] = Field(None, description="Optional password protection")
    allow_download: bool = Field(True, description="Allow file downloads")
    allow_preview: bool = Field(True, description="Allow file preview")
    max_downloads: Optional[int] = Field(None, description="Maximum number of downloads (None = unlimited)")
    expires_at: Optional[datetime] = Field(None, description="Expiration date (None = never expires)")
    description: Optional[str] = Field(None, max_length=500, description="Optional description")


class ShareLinkUpdate(BaseModel):
    """Schema for updating a share link."""
    password: Optional[str] = Field(None, description="Update password (empty string to remove)")
    allow_download: Optional[bool] = None
    allow_preview: Optional[bool] = None
    max_downloads: Optional[int] = None
    expires_at: Optional[datetime] = None
    description: Optional[str] = Field(None, max_length=500)


class ShareLinkResponse(BaseModel):
    """Schema for share link response."""
    id: int
    token: str
    file_id: int
    owner_id: int
    has_password: bool = Field(..., description="Whether the link is password protected")
    allow_download: bool
    allow_preview: bool
    max_downloads: Optional[int]
    download_count: int
    expires_at: Optional[datetime]
    description: Optional[str]
    created_at: datetime
    last_accessed_at: Optional[datetime]
    is_expired: bool
    is_accessible: bool
    
    # File information
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    
    model_config = {"from_attributes": True}


class ShareLinkAccessRequest(BaseModel):
    """Schema for accessing a share link with password."""
    password: Optional[str] = Field(None, description="Password if required")


# ===========================
# File Share Schemas
# ===========================

class FileShareCreate(BaseModel):
    """Schema for creating a file share with another user."""
    file_id: int = Field(..., description="ID of the file to share")
    shared_with_user_id: int = Field(..., description="User ID to share with")
    can_read: bool = Field(True, description="Allow read access")
    can_write: bool = Field(False, description="Allow write access")
    can_delete: bool = Field(False, description="Allow delete access")
    can_share: bool = Field(False, description="Allow re-sharing with others")
    expires_at: Optional[datetime] = Field(None, description="Expiration date (None = never expires)")


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
    total_share_links: int
    active_share_links: int
    expired_share_links: int
    total_downloads: int
    total_file_shares: int
    active_file_shares: int
    files_shared_with_me: int
