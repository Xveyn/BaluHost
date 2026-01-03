"""Database models for file sync state tracking."""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class SyncState(Base):
    """Track sync state for client devices."""
    
    __tablename__ = "sync_states"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(255), nullable=True)
    last_sync: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_change_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    sync_metadata = relationship("SyncMetadata", back_populates="sync_state", cascade="all, delete-orphan")


class SyncMetadata(Base):
    """Track sync metadata for files across devices."""
    
    __tablename__ = "sync_metadata"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_metadata_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_metadata.id"), nullable=False, index=True)
    sync_state_id: Mapped[int] = mapped_column(Integer, ForeignKey("sync_states.id"), nullable=False, index=True)
    
    # Hash for change detection
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Timestamps
    local_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sync_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    server_modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Status tracking
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_resolution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    sync_state = relationship("SyncState", back_populates="sync_metadata")


class SyncFileVersion(Base):
    """Keep historical versions of files for rollback and versioning."""
    
    __tablename__ = "sync_file_versions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_metadata_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_metadata.id"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Storage info
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    change_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
