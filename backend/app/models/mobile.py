"""Database models for mobile device management."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base
import uuid


class MobileDevice(Base):
    """Mobile device registration table."""
    __tablename__ = "mobile_devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Device info
    device_name: Mapped[str] = mapped_column(String, nullable=False)
    device_type: Mapped[str] = mapped_column(String, nullable=False)  # ios or android
    device_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Push notifications
    push_token: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Last API request from this device
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Last sync operation (camera/files)

    # Device token expiration (30 days minimum, 6 months maximum)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="mobile_devices")
    camera_backups = relationship("CameraBackup", back_populates="device", cascade="all, delete-orphan")
    sync_folders = relationship("SyncFolder", back_populates="device", cascade="all, delete-orphan")


class MobileRegistrationToken(Base):
    """Temporary tokens for mobile device registration."""
    __tablename__ = "mobile_registration_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")


class CameraBackup(Base):
    """Camera backup settings and status per device."""
    __tablename__ = "camera_backups"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)

    # Settings
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    quality: Mapped[str] = mapped_column(String, default="original", nullable=False)
    wifi_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delete_after_upload: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    video_backup: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_video_size_mb: Mapped[int] = mapped_column(Integer, default=500, nullable=False)

    # Status
    last_backup: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_photos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_videos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_uploads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_uploads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_used_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.utcnow, nullable=True)

    # Relationships
    device = relationship("MobileDevice", back_populates="camera_backups")


class SyncFolder(Base):
    """Folder sync configuration for mobile devices."""
    __tablename__ = "sync_folders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)

    # Paths
    local_path: Mapped[str] = mapped_column(String, nullable=False)
    remote_path: Mapped[str] = mapped_column(String, nullable=False)

    # Settings
    sync_type: Mapped[str] = mapped_column(String, default="bidirectional", nullable=False)  # upload, download, bidirectional
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Status
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="idle", nullable=False)  # idle, syncing, error
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=datetime.utcnow, nullable=True)

    # Relationships
    device = relationship("MobileDevice", back_populates="sync_folders")


class UploadQueue(Base):
    """Queue for background uploads from mobile devices."""
    __tablename__ = "upload_queue"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)

    # File info
    filename: Mapped[str] = mapped_column(String, nullable=False)
    remote_path: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Upload progress
    uploaded_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)  # pending, uploading, completed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retry logic
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ExpirationNotification(Base):
    """Track sent expiration warning notifications to prevent duplicates."""
    __tablename__ = "expiration_notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id: Mapped[str] = mapped_column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)

    # Notification details
    notification_type: Mapped[str] = mapped_column(String, nullable=False)  # "7_days", "3_days", "1_hour"
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # FCM response
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fcm_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Device expiration context (for audit trail)
    device_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    device = relationship("MobileDevice")
