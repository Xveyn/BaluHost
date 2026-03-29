"""Pydantic schemas for cloud export API."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CloudExportRequest(BaseModel):
    """Request to start a cloud export job."""

    connection_id: int
    source_path: str = Field(min_length=1, description="Relative path on the NAS")
    cloud_folder: str = Field(
        default="BaluHost Shares/", description="Target folder in cloud drive"
    )
    link_type: Literal["view", "edit"] = Field(
        default="view", description="Sharing link permission type"
    )
    expires_at: Optional[datetime] = Field(
        default=None, description="Optional link expiration"
    )


class CloudExportJobResponse(BaseModel):
    """Response schema for an export job."""

    id: int
    user_id: int
    connection_id: int
    source_path: str
    file_name: str
    is_directory: bool
    file_size_bytes: Optional[int] = None
    cloud_folder: str
    cloud_path: Optional[str] = None
    share_link: Optional[str] = None
    link_type: str
    status: str
    progress_bytes: int
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CloudExportStatistics(BaseModel):
    """Statistics for the Cloud Shares tab on SharesPage."""

    total_exports: int
    active_exports: int
    failed_exports: int
    total_upload_bytes: int


class CheckScopeRequest(BaseModel):
    """Request to check if a connection has export-capable scope."""

    connection_id: int


class CheckScopeResponse(BaseModel):
    """Response indicating export scope availability."""

    has_export_scope: bool
    provider: str
