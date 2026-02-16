"""Pydantic schemas for cloud import API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CloudConnectionResponse(BaseModel):
    """Response schema for a cloud connection."""
    id: int
    provider: str
    display_name: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CloudFileResponse(BaseModel):
    """A file or directory in a cloud provider."""
    name: str
    path: str
    is_directory: bool
    size_bytes: Optional[int] = None
    modified_at: Optional[datetime] = None


class CloudImportRequest(BaseModel):
    """Request to start a cloud import job."""
    connection_id: int
    source_path: str = Field(default="/", description="Path in the cloud storage")
    destination_path: str = Field(default="", description="Relative path on the NAS")
    job_type: str = Field(default="import", pattern="^(import|sync)$")


class CloudImportJobResponse(BaseModel):
    """Response schema for an import job."""
    id: int
    connection_id: int
    source_path: str
    destination_path: str
    job_type: str
    status: str
    progress_bytes: int
    total_bytes: Optional[int] = None
    files_transferred: int
    files_total: Optional[int] = None
    current_file: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ICloudConnectRequest(BaseModel):
    """Request to connect an iCloud account."""
    apple_id: str = Field(min_length=1, description="Apple ID email")
    password: str = Field(min_length=1, description="Password or app-specific password")


class ICloud2FARequest(BaseModel):
    """Request to submit a 2FA code for iCloud."""
    connection_id: int
    code: str = Field(min_length=6, max_length=6, description="6-digit 2FA code")


class DevConnectRequest(BaseModel):
    """Request to create a dev-mode mock connection."""
    provider: str = Field(pattern="^(google_drive|onedrive|icloud)$")


class OAuthCallbackRequest(BaseModel):
    """OAuth callback parameters."""
    code: str
    state: str


class CloudOAuthConfigCreate(BaseModel):
    """Request to save OAuth credentials for a provider."""
    provider: str = Field(pattern="^(google_drive|onedrive)$")
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)


class CloudOAuthConfigResponse(BaseModel):
    """Response showing OAuth config status for a provider."""
    provider: str
    is_configured: bool
    client_id_hint: Optional[str] = None  # "1234...5678" or "(env)"
    user_id: Optional[int] = None
    updated_at: Optional[datetime] = None
