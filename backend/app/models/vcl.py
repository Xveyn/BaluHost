"""Version Control Light (VCL) Models."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    Integer, String, Text, DateTime, Boolean, Float, BigInteger,
    ForeignKey, UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.file_metadata import FileMetadata
    from app.models.user import User


class VersionBlob(Base):
    """Deduplicated storage blobs for file versions.

    Multiple file versions can reference the same blob via checksum.
    """
    __tablename__ = "version_blobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    checksum: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # SHA256
    storage_path: Mapped[str] = mapped_column(Text)
    original_size: Mapped[int] = mapped_column(BigInteger)
    compressed_size: Mapped[int] = mapped_column(BigInteger)
    reference_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_accessed: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    can_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relationships
    file_versions = relationship("FileVersion", back_populates="blob")
    
    __table_args__ = (
        Index('idx_version_blobs_cleanup', 'can_delete', 'last_accessed'),
    )
    
    def __repr__(self):
        return f"<VersionBlob(id={self.id}, checksum={self.checksum[:8]}..., refs={self.reference_count})>"


class FileVersion(Base):
    """File version metadata and storage information.
    
    Tracks all versions of a file with compression, deduplication, and caching info.
    """
    __tablename__ = "vcl_file_versions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("file_metadata.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Storage Information
    blob_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("version_blobs.id", ondelete="SET NULL"), nullable=True)
    storage_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'stored' or 'reference'
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Original size (uncompressed)
    compressed_size: Mapped[int] = mapped_column(BigInteger, nullable=False)  # Compressed size
    compression_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # file_size / compressed_size

    # Checksums & Integrity
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA256

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    is_high_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    change_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 'create', 'update', 'overwrite', 'batched'
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Caching Info
    was_cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cache_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # seconds in cache
    
    # Relationships
    file = relationship("FileMetadata", back_populates="versions")
    user = relationship("User")
    blob = relationship("VersionBlob", back_populates="file_versions")
    
    __table_args__ = (
        UniqueConstraint('file_id', 'version_number', name='uq_file_versions_file_version'),
    )
    
    def __repr__(self):
        return f"<FileVersion(id={self.id}, file_id={self.file_id}, v{self.version_number}, size={self.file_size})>"


class VCLSettings(Base):
    """Version Control Light settings per user or global.
    
    Controls quota, depth, and feature flags for VCL system.
    """
    __tablename__ = "vcl_settings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=True, index=True)

    # Storage Limits
    max_size_bytes: Mapped[int] = mapped_column(BigInteger, default=10737418240, nullable=False)  # 10 GB
    current_usage_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Versioning Parameters
    depth: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # Max versions per file
    headroom_percent: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # Mode: 'automatic' (version all files, exclude list) or 'manual' (version only tracked files)
    vcl_mode: Mapped[str] = mapped_column(String(20), default="automatic", server_default="automatic", nullable=False)

    # Feature Flags
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    compression_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dedupe_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Caching Parameters
    debounce_window_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_batch_window_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User")
    
    @property
    def usage_percent(self) -> float:
        """Calculate current usage as percentage."""
        if self.max_size_bytes == 0:
            return 0.0
        return (self.current_usage_bytes / self.max_size_bytes) * 100
    
    @property
    def available_bytes(self) -> int:
        """Calculate available storage."""
        return max(0, self.max_size_bytes - self.current_usage_bytes)
    
    @property
    def headroom_bytes(self) -> int:
        """Calculate headroom in bytes."""
        return int(self.max_size_bytes * (self.headroom_percent / 100))
    
    @property
    def is_over_headroom(self) -> bool:
        """Check if usage exceeds max - headroom."""
        threshold = self.max_size_bytes - self.headroom_bytes
        return self.current_usage_bytes >= threshold
    
    def __repr__(self):
        user_str = f"user_id={self.user_id}" if self.user_id else "global"
        return f"<VCLSettings({user_str}, max={self.max_size_bytes}, used={self.current_usage_bytes})>"


class VCLStats(Base):
    """Global VCL statistics.
    
    Singleton table (id=1) tracking system-wide VCL metrics.
    """
    __tablename__ = "vcl_stats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Global Stats
    total_versions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # Uncompressed
    total_compressed_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_blobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_blobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Savings
    deduplication_savings_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    compression_savings_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Priority & Features
    priority_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_versions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Maintenance
    last_cleanup_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_priority_mode_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_deduplication_scan: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    @property
    def compression_ratio(self) -> float:
        """Average compression ratio."""
        if self.total_compressed_bytes == 0:
            return 1.0
        return self.total_size_bytes / self.total_compressed_bytes
    
    @property
    def compression_savings_percent(self) -> float:
        """Compression savings as percentage."""
        if self.total_size_bytes == 0:
            return 0.0
        return (1 - self.total_compressed_bytes / self.total_size_bytes) * 100
    
    @property
    def deduplication_savings_percent(self) -> float:
        """Deduplication savings as percentage."""
        total_without_dedup = self.total_compressed_bytes + self.deduplication_savings_bytes
        if total_without_dedup == 0:
            return 0.0
        return (self.deduplication_savings_bytes / total_without_dedup) * 100
    
    def __repr__(self):
        return f"<VCLStats(versions={self.total_versions}, size={self.total_size_bytes}, ratio={self.compression_ratio:.2f}x)>"


class VCLFileTracking(Base):
    """Per-file/pattern VCL tracking rules.

    In automatic mode: action='exclude' entries skip versioning for matched files.
    In manual mode: action='track' entries enable versioning for matched files.
    """
    __tablename__ = "vcl_file_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("file_metadata.id", ondelete="CASCADE"), nullable=True)
    path_pattern: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # Glob patterns: "*.log", "node_modules/*"
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # 'track' or 'exclude'
    is_directory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User")
    file = relationship("FileMetadata")

    __table_args__ = (
        UniqueConstraint('user_id', 'file_id', name='uq_vcl_tracking_user_file'),
        Index('idx_vcl_tracking_user_action', 'user_id', 'action'),
        CheckConstraint("action IN ('track', 'exclude')", name='ck_vcl_tracking_action'),
    )

    def __repr__(self):
        target = f"file_id={self.file_id}" if self.file_id else f"pattern={self.path_pattern}"
        return f"<VCLFileTracking(user_id={self.user_id}, {target}, action={self.action})>"
