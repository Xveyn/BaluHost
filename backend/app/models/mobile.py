"""Database models for mobile device management."""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.models.base import Base
import uuid


class MobileDevice(Base):
    """Mobile device registration table."""
    __tablename__ = "mobile_devices"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Device info
    device_name = Column(String, nullable=False)
    device_type = Column(String, nullable=False)  # ios or android
    device_model = Column(String, nullable=True)
    os_version = Column(String, nullable=True)
    app_version = Column(String, nullable=True)
    
    # Push notifications
    push_token = Column(String, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    last_sync = Column(DateTime, nullable=True)
    
    # Device token expiration (30 days minimum, 6 months maximum)
    expires_at = Column(DateTime, nullable=True)  # When the device authorization expires
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="mobile_devices")
    camera_backups = relationship("CameraBackup", back_populates="device", cascade="all, delete-orphan")
    sync_folders = relationship("SyncFolder", back_populates="device", cascade="all, delete-orphan")


class MobileRegistrationToken(Base):
    """Temporary tokens for mobile device registration."""
    __tablename__ = "mobile_registration_tokens"

    token = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User")


class CameraBackup(Base):
    """Camera backup settings and status per device."""
    __tablename__ = "camera_backups"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)
    
    # Settings
    enabled = Column(Boolean, default=True, nullable=False)
    quality = Column(String, default="original", nullable=False)
    wifi_only = Column(Boolean, default=True, nullable=False)
    delete_after_upload = Column(Boolean, default=False, nullable=False)
    video_backup = Column(Boolean, default=True, nullable=False)
    max_video_size_mb = Column(Integer, default=500, nullable=False)
    
    # Status
    last_backup = Column(DateTime, nullable=True)
    total_photos = Column(Integer, default=0, nullable=False)
    total_videos = Column(Integer, default=0, nullable=False)
    pending_uploads = Column(Integer, default=0, nullable=False)
    failed_uploads = Column(Integer, default=0, nullable=False)
    storage_used_bytes = Column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow, nullable=True)
    
    # Relationships
    device = relationship("MobileDevice", back_populates="camera_backups")


class SyncFolder(Base):
    """Folder sync configuration for mobile devices."""
    __tablename__ = "sync_folders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)
    
    # Paths
    local_path = Column(String, nullable=False)
    remote_path = Column(String, nullable=False)
    
    # Settings
    sync_type = Column(String, default="bidirectional", nullable=False)  # upload, download, bidirectional
    auto_sync = Column(Boolean, default=True, nullable=False)
    
    # Status
    last_sync = Column(DateTime, nullable=True)
    status = Column(String, default="idle", nullable=False)  # idle, syncing, error
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow, nullable=True)
    
    # Relationships
    device = relationship("MobileDevice", back_populates="sync_folders")


class UploadQueue(Base):
    """Queue for background uploads from mobile devices."""
    __tablename__ = "upload_queue"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)
    
    # File info
    filename = Column(String, nullable=False)
    remote_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=True)
    
    # Upload progress
    uploaded_bytes = Column(Integer, default=0, nullable=False)
    status = Column(String, default="pending", nullable=False)  # pending, uploading, completed, failed
    error_message = Column(Text, nullable=True)
    
    # Retry logic
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class ExpirationNotification(Base):
    """Track sent expiration warning notifications to prevent duplicates."""
    __tablename__ = "expiration_notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String, ForeignKey("mobile_devices.id", ondelete="CASCADE"), nullable=False)
    
    # Notification details
    notification_type = Column(String, nullable=False)  # "7_days", "3_days", "1_hour"
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # FCM response
    success = Column(Boolean, default=True, nullable=False)
    fcm_message_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Device expiration context (for audit trail)
    device_expires_at = Column(DateTime, nullable=False)
    
    # Relationships
    device = relationship("MobileDevice")
