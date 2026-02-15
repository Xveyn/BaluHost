"""Pydantic schemas for SSD cache (bcache) management."""

from enum import Enum

from pydantic import BaseModel


class CacheMode(str, Enum):
    WRITETHROUGH = "writethrough"  # Safe: no data loss on SSD failure
    WRITEBACK = "writeback"        # Fast: writes cached on SSD
    WRITEAROUND = "writearound"    # Only reads cached
    NONE = "none"


class CacheStatus(BaseModel):
    """Status of an SSD cache attached to a RAID array."""
    array_name: str                          # e.g. "md0"
    cache_device: str                        # e.g. "nvme1n1p1"
    bcache_device: str | None = None         # e.g. "bcache0"
    mode: CacheMode
    state: str                               # running, detaching, error, idle
    hit_rate_percent: float | None = None
    dirty_data_bytes: int = 0                # Only relevant in writeback mode
    cache_size_bytes: int = 0
    cache_used_bytes: int = 0
    sequential_cutoff_bytes: int = 4 * 1024 * 1024  # 4 MiB default


class CacheAttachRequest(BaseModel):
    """Request to attach an SSD cache to a RAID array."""
    array: str
    cache_device: str
    mode: CacheMode = CacheMode.WRITETHROUGH


class CacheDetachRequest(BaseModel):
    """Request to detach an SSD cache from a RAID array."""
    array: str
    force: bool = False


class CacheConfigureRequest(BaseModel):
    """Request to change cache parameters."""
    array: str
    mode: CacheMode | None = None
    sequential_cutoff_bytes: int | None = None


class ExternalBitmapRequest(BaseModel):
    """Request to move RAID bitmap to SSD."""
    array: str
    ssd_partition: str
