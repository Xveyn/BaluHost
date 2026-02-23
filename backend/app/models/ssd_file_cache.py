"""SSD File Cache Models.

Application-layer file cache that copies hot files from HDD to SSD
for faster read access. Write-through semantics: HDD is always authoritative.
Per-array: each RAID array has its own cache config and entries.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float, BigInteger,
    ForeignKey, Index, UniqueConstraint
)
from app.models.base import Base


class SSDCacheEntry(Base):
    """Individual cached file entry on the SSD."""
    __tablename__ = "ssd_cache_entries"

    id = Column(Integer, primary_key=True, index=True)

    # Array assignment
    array_name = Column(String(64), nullable=False, index=True)

    # Source reference (relative path on HDD, matches FileMetadata.path)
    source_path = Column(Text, nullable=False, index=True)
    file_id = Column(
        Integer,
        ForeignKey("file_metadata.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # SSD cache location (absolute path on SSD)
    cache_path = Column(Text, nullable=False)

    # Size and integrity
    file_size_bytes = Column(BigInteger, nullable=False)
    checksum = Column(String(64), nullable=False)  # SHA256

    # Access tracking for eviction
    access_count = Column(BigInteger, default=0, nullable=False)
    last_accessed = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    first_cached = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )

    # State
    is_valid = Column(Boolean, default=True, nullable=False, index=True)
    # Tracks source file modification time to detect staleness
    source_mtime = Column(Float, nullable=False)

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

    id = Column(Integer, primary_key=True)
    array_name = Column(String(64), unique=True, nullable=False, index=True)

    is_enabled = Column(Boolean, default=False, nullable=False)
    cache_path = Column(Text, nullable=False, default="/mnt/cache-vcl/filecache")
    max_size_bytes = Column(BigInteger, nullable=False, default=500 * 1024**3)
    current_size_bytes = Column(BigInteger, default=0, nullable=False)
    eviction_policy = Column(String(10), default="lfru", nullable=False)
    min_file_size_bytes = Column(BigInteger, default=1024 * 1024, nullable=False)  # 1 MB
    max_file_size_bytes = Column(BigInteger, default=4 * 1024**3, nullable=False)  # 4 GB
    sequential_cutoff_bytes = Column(
        BigInteger, default=64 * 1024 * 1024, nullable=False
    )  # 64 MB

    # Stats
    total_hits = Column(BigInteger, default=0, nullable=False)
    total_misses = Column(BigInteger, default=0, nullable=False)
    total_bytes_served_from_cache = Column(BigInteger, default=0, nullable=False)

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<SSDCacheConfig(array={self.array_name}, enabled={self.is_enabled}, "
            f"size={self.current_size_bytes}/{self.max_size_bytes})>"
        )
