"""Pydantic schemas for SSD File Cache API."""
from datetime import datetime
from typing import Optional, Literal
import re

from pydantic import BaseModel, Field, field_validator

_ABSOLUTE_PATH = re.compile(r"^(?:[\\/]|[A-Za-z]:[\\/])")


class SSDCacheStats(BaseModel):
    """Cache overview statistics."""
    array_name: str
    is_enabled: bool
    cache_path: str
    max_size_bytes: int
    current_size_bytes: int
    usage_percent: float
    total_entries: int
    valid_entries: int
    total_hits: int
    total_misses: int
    hit_rate_percent: float
    total_bytes_served: int
    ssd_available_bytes: int
    ssd_total_bytes: int


class SSDCacheConfigResponse(BaseModel):
    """Full cache configuration."""
    array_name: str
    is_enabled: bool
    cache_path: str
    max_size_bytes: int
    current_size_bytes: int
    eviction_policy: str
    min_file_size_bytes: int
    max_file_size_bytes: int
    sequential_cutoff_bytes: int
    total_hits: int
    total_misses: int
    total_bytes_served_from_cache: int
    updated_at: Optional[datetime] = None


class SSDCacheConfigUpdate(BaseModel):
    """Partial update for cache configuration."""
    is_enabled: Optional[bool] = None
    cache_path: Optional[str] = None
    max_size_bytes: Optional[int] = Field(None, gt=0)
    eviction_policy: Optional[Literal["lfru", "lru", "lfu"]] = None
    min_file_size_bytes: Optional[int] = Field(None, ge=0)
    max_file_size_bytes: Optional[int] = Field(None, gt=0)
    sequential_cutoff_bytes: Optional[int] = Field(None, gt=0)

    @field_validator("cache_path")
    @classmethod
    def validate_cache_path(cls, value: Optional[str]) -> Optional[str]:
        """Absolute path without ``..``; the backend creates and fills it.

        Separator-agnostic: a dev box stores ``C:\\...``, prod ``/mnt/...``, and
        pathlib on the running OS only knows its own flavour.
        """
        if value is None:
            return value
        if "\x00" in value or not _ABSOLUTE_PATH.match(value):
            raise ValueError("cache_path must be an absolute path")
        if ".." in re.split(r"[\\/]", value):
            raise ValueError("cache_path must not contain '..'")
        return value


class SSDCacheEntryResponse(BaseModel):
    """Single cache entry."""
    id: int
    array_name: str
    source_path: str
    file_size_bytes: int
    access_count: int
    last_accessed: datetime
    first_cached: datetime
    is_valid: bool


class SSDCacheEntriesResponse(BaseModel):
    """Paginated cache entries list."""
    entries: list[SSDCacheEntryResponse]
    total: int


class EvictionResult(BaseModel):
    """Result of an eviction run."""
    freed_bytes: int
    deleted_count: int


class CacheHealthResponse(BaseModel):
    """SSD mount and health status."""
    array_name: str
    is_mounted: bool
    ssd_total_bytes: int
    ssd_available_bytes: int
    ssd_used_percent: float
    cache_dir_exists: bool
