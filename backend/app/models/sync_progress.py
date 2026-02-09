"""Progressive sync with chunked uploads for large files."""

from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class ChunkedUpload(Base):
    """Track chunked uploads in progress."""
    
    __tablename__ = "chunked_uploads"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    upload_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)  # UUID
    file_metadata_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_metadata.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Upload info
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, default=5 * 1024 * 1024)  # 5MB chunks
    
    # Progress
    uploaded_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    completed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_token: Mapped[str | None] = mapped_column(String(36), nullable=True)  # For resuming
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # Cleanup old uploads


class SyncBandwidthLimit(Base):
    """Per-user bandwidth limits for sync."""
    
    __tablename__ = "sync_bandwidth_limits"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Limits (bytes/sec)
    upload_speed_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    download_speed_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Throttling window
    throttle_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    throttle_start_hour: Mapped[int] = mapped_column(Integer, default=0)  # 0-23
    throttle_end_hour: Mapped[int] = mapped_column(Integer, default=6)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncSchedule(Base):
    """Scheduled automatic syncs."""
    
    __tablename__ = "sync_schedules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Schedule info
    schedule_type: Mapped[str] = mapped_column(String(20))  # 'daily', 'weekly', 'monthly', 'on_change'
    
    # Timing
    time_of_day: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "02:00"
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=Monday, 6=Sunday
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-31
    
    # Settings
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_deletions: Mapped[bool] = mapped_column(Boolean, default=True)
    resolve_conflicts: Mapped[str] = mapped_column(String(20), default="keep_newest")  # keep_newest, keep_local, keep_server
    
    # Tracking
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SelectiveSync(Base):
    """User's selective sync preferences."""
    
    __tablename__ = "selective_syncs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Folder/file path
    folder_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    include_subfolders: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Status
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # "manual", "storage_limit", etc.
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
