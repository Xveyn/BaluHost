"""SSD File Cache Models.

Application-layer file cache that copies hot files from HDD to SSD
for faster read access. Write-through semantics: HDD is always authoritative.
Per-array: each RAID array has its own cache config and entries.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class SSDCacheEntry(Base):
    """Individual cached file entry on the SSD."""
    __tablename__ = "ssd_cache_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Array assignment
    array_name: Mapped[str] = mapped_column(String(64), index=True)

    # Source reference (relative path on HDD, matches FileMetadata.path)
    source_path: Mapped[str] = mapped_column(Text, index=True)
    file_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("file_metadata.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # SSD cache location (absolute path on SSD)
    cache_path: Mapped[str] = mapped_column(Text)

    # Size and integrity
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))  # SHA256

    # Access tracking for eviction
    access_count: Mapped[int] = mapped_column(BigInteger, default=0)
    last_accessed: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    first_cached: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )

    # State
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Tracks source file modification time to detect staleness
    source_mtime: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("array_name", "source_path", name="uq_ssd_cache_array_source"),
        Index(
            "idx_ssd_cache_eviction",
            "array_name",
            "is_valid",
            "access_count",
            "last_accessed",
        ),
    )

    def __repr__(self):
        return (
            f"<SSDCacheEntry(id={self.id}, array={self.array_name}, "
            f"source={self.source_path}, size={self.file_size_bytes}, hits={self.access_count})>"
        )


class SSDCacheConfig(Base):
    """Per-array configuration for the SSD file cache."""
    __tablename__ = "ssd_cache_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    array_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_path: Mapped[str] = mapped_column(Text, default="/mnt/cache-vcl/filecache")
    max_size_bytes: Mapped[int] = mapped_column(BigInteger, default=500 * 1024**3)
    current_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    eviction_policy: Mapped[str] = mapped_column(String(10), default="lfru")
    min_file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=1024 * 1024)  # 1 MB
    max_file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=4 * 1024**3)  # 4 GB
    sequential_cutoff_bytes: Mapped[int] = mapped_column(
        BigInteger, default=64 * 1024 * 1024
    )  # 64 MB

    # Stats
    total_hits: Mapped[int] = mapped_column(BigInteger, default=0)
    total_misses: Mapped[int] = mapped_column(BigInteger, default=0)
    total_bytes_served_from_cache: Mapped[int] = mapped_column(BigInteger, default=0)

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    def __repr__(self):
        return (
            f"<SSDCacheConfig(array={self.array_name}, enabled={self.is_enabled}, "
            f"size={self.current_size_bytes}/{self.max_size_bytes})>"
        )
