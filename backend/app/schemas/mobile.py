"""Pydantic schemas for mobile device management and registration."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    """Device information from mobile app."""
    device_name: str = Field(..., alias="deviceName")
    device_type: str = Field(..., alias="deviceType")
    device_model: str = Field(..., alias="deviceModel")
    os_version: str = Field(..., alias="osVersion")
    app_version: str = Field(..., alias="appVersion")
    
    class Config:
        populate_by_name = True


class MobileDeviceBase(BaseModel):
    """Base schema for mobile device."""
    device_name: str = Field(..., description="User-friendly device name")
    device_type: str = Field(..., description="ios or android")
    device_model: Optional[str] = Field(None, description="Device model (e.g., iPhone 14, Pixel 7)")
    os_version: Optional[str] = Field(None, description="OS version")
    app_version: Optional[str] = Field(None, description="BaluMobile app version")


class MobileDeviceCreate(BaseModel):
    """Schema for creating a new mobile device registration - matches Android app format."""
    token: str = Field(..., description="One-time registration token from QR code")
    device_info: DeviceInfo = Field(..., alias="deviceInfo")
    push_token: Optional[str] = Field(None, alias="pushToken")
    token_validity_days: Optional[int] = Field(None, alias="tokenValidityDays", description="Token validity in days (30-180)")
    
    class Config:
        populate_by_name = True


class MobileDeviceUpdate(BaseModel):
    """Schema for updating mobile device."""
    device_name: Optional[str] = None
    push_token: Optional[str] = None
    is_active: Optional[bool] = None


class MobileDevice(MobileDeviceBase):
    """Schema for mobile device in responses."""
    id: str
    user_id: str
    is_active: bool
    last_sync: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MobileRegistrationToken(BaseModel):
    """Schema for mobile device registration token."""
    token: str = Field(..., description="Registration token")
    server_url: str = Field(..., description="BaluHost server URL")
    expires_at: datetime = Field(..., description="Token expiration time")
    qr_code: str = Field(..., description="Base64 encoded QR code image")
    vpn_config: Optional[str] = Field(None, description="Base64 encoded WireGuard config (optional)")
    device_token_validity_days: int = Field(..., description="Device token validity in days (30-180)")


class MobileRegistrationResponse(BaseModel):
    """Response after successful device registration."""
    access_token: str
    refresh_token: str
    token_type: str
    user: dict
    device: dict


class CameraBackupSettings(BaseModel):
    """Camera backup settings for mobile device."""
    enabled: bool = True
    quality: str = Field("original", description="original, high, or medium")
    wifi_only: bool = True
    delete_after_upload: bool = False
    video_backup: bool = True
    max_video_size_mb: int = Field(500, description="Max video size to backup in MB")


class CameraBackupStatus(BaseModel):
    """Camera backup status."""
    device_id: str
    last_backup: Optional[datetime] = None
    total_photos: int = 0
    total_videos: int = 0
    pending_uploads: int = 0
    failed_uploads: int = 0
    storage_used_bytes: int = 0


class SyncFolderCreate(BaseModel):
    """Schema for creating a sync folder."""
    local_path: str = Field(..., description="Local path on mobile device")
    remote_path: str = Field(..., description="Remote path on server")
    sync_type: str = Field("bidirectional", description="upload, download, or bidirectional")
    auto_sync: bool = True


class SyncFolder(SyncFolderCreate):
    """Schema for sync folder in responses."""
    id: str
    device_id: str
    last_sync: Optional[datetime] = None
    status: str = Field("idle", description="idle, syncing, error")
    created_at: datetime

    class Config:
        from_attributes = True


class UploadProgress(BaseModel):
    """Upload progress for mobile uploads."""
    upload_id: str
    filename: str
    total_bytes: int
    uploaded_bytes: int
    progress_percent: float
    status: str = Field("uploading", description="uploading, completed, failed")
    speed_mbps: Optional[float] = None
    eta_seconds: Optional[int] = None


class ExpirationNotification(BaseModel):
    """Schema for expiration notification history."""
    id: str
    device_id: str
    notification_type: str = Field(..., description="7_days, 3_days, or 1_hour")
    sent_at: datetime
    success: bool
    fcm_message_id: Optional[str] = None
    error_message: Optional[str] = None
    device_expires_at: datetime
    
    class Config:
        from_attributes = True
