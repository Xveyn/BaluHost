"""SSD File Cache Service.

Application-layer read cache that copies hot files from HDD to SSD.
Write-through: HDD is always authoritative. Cache failures never block
file delivery. Per-array: each RAID array has its own config and entries.
"""
import hashlib
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional, List

from cachetools import TTLCache
from sqlalchemy.orm import Session
from sqlalchemy import update as sql_update, func
from sqlalchemy.exc import IntegrityError

from app.models.ssd_file_cache import SSDCacheEntry, SSDCacheConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


def _default_cache_path(array_name: str) -> str:
    """Return the default cache path, dev-mode aware."""
    if settings.is_dev_mode:
        return str(Path(settings.nas_storage_path).resolve() / ".cache" / "filecache" / array_name)
    return f"/mnt/cache-vcl/filecache/{array_name}"

# In-memory hot-path cache to avoid DB hit on every file read
_path_cache: TTLCache = TTLCache(maxsize=10_000, ttl=60)


def _sha256_file(path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class SSDFileCacheService:
    """Core SSD file cache operations, scoped to a specific array."""

    def __init__(self, db: Session, array_name: str = "md0"):
        self.db = db
        self.array_name = array_name

    # ========== Config ==========

    def get_config(self) -> SSDCacheConfig:
        """Get or create the config for this array."""
        config = (
            self.db.query(SSDCacheConfig)
            .filter(SSDCacheConfig.array_name == self.array_name)
            .first()
        )
        if config:
            # Fix stale cache_path from pre-per-array migration or wrong mode
            expected = _default_cache_path(self.array_name)
            if str(config.cache_path) != expected:
                p = Path(str(config.cache_path))
                # Only auto-fix if it's the old default (not user-customized)
                if str(p).startswith("/mnt/cache-vcl/filecache") and settings.is_dev_mode:
                    config.cache_path = expected
                    self.db.flush()
                elif not str(p).endswith(f"/{self.array_name}"):
                    # Old singleton path missing array suffix
                    config.cache_path = f"{config.cache_path}/{self.array_name}"
                    self.db.flush()
        if not config:
            config = SSDCacheConfig(
                array_name=self.array_name,
                is_enabled=False,
                cache_path=_default_cache_path(self.array_name),
            )
            try:
                self.db.add(config)
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                config = (
                    self.db.query(SSDCacheConfig)
                    .filter(SSDCacheConfig.array_name == self.array_name)
                    .first()
                )
                if not config:
                    raise
        return config

    def is_cache_enabled(self) -> bool:
        config = self.get_config()
        return bool(config.is_enabled)

    @classmethod
    def get_all_configs(cls, db: Session) -> List[SSDCacheConfig]:
        """Get configs for all arrays."""
        return db.query(SSDCacheConfig).all()

    # ========== Eligibility ==========

    def should_cache_file(self, file_size: int) -> bool:
        """Check if a file is eligible for caching based on config limits."""
        config = self.get_config()
        if not config.is_enabled:
            return False
        if file_size < int(config.min_file_size_bytes):
            return False
        if file_size > int(config.max_file_size_bytes):
            return False
        # Check if we have capacity
        current = int(config.current_size_bytes)
        max_size = int(config.max_size_bytes)
        if current + file_size > max_size:
            return False
        return True

    # ========== Cache Lookup ==========

    def get_cached_path(
        self, source_path: str, source_mtime: float
    ) -> Optional[Path]:
        """
        Look up a file in the cache.

        Returns SSD path if cache hit (valid + mtime matches).
        Increments access_count on hit. Returns None on miss.
        """
        cache_key = (self.array_name, source_path, source_mtime)
        cached = _path_cache.get(cache_key)
        if cached is not None:
            # Fast path: in-memory hit — still update DB stats asynchronously
            return Path(cached) if cached else None

        entry = (
            self.db.query(SSDCacheEntry)
            .filter(
                SSDCacheEntry.array_name == self.array_name,
                SSDCacheEntry.source_path == source_path,
                SSDCacheEntry.is_valid.is_(True),
            )
            .first()
        )

        if not entry:
            _path_cache[cache_key] = ""
            self._record_miss()
            return None

        # Check staleness
        if float(entry.source_mtime) != source_mtime:
            # Source changed — invalidate
            self.invalidate_entry(source_path)
            _path_cache[cache_key] = ""
            self._record_miss()
            return None

        cached_path = Path(str(entry.cache_path))
        if not cached_path.exists():
            self.invalidate_entry(source_path)
            _path_cache[cache_key] = ""
            self._record_miss()
            return None

        # Cache hit — update access tracking
        now = datetime.now(timezone.utc)
        self.db.execute(
            sql_update(SSDCacheEntry)
            .where(SSDCacheEntry.id == entry.id)
            .values(
                access_count=SSDCacheEntry.access_count + 1,
                last_accessed=now,
            )
        )
        self._record_hit(int(entry.file_size_bytes))
        self.db.flush()

        _path_cache[cache_key] = str(cached_path)
        return cached_path

    # ========== Cache Population ==========

    def cache_file(
        self,
        source_path: str,
        source_abs_path: Path,
        file_id: Optional[int] = None,
    ) -> Optional[Path]:
        """
        Copy a file from HDD to SSD cache.

        Returns SSD cache path on success, None if skipped/failed.
        This method should be called in a background task.
        """
        try:
            if not source_abs_path.exists() or not source_abs_path.is_file():
                return None

            file_size = source_abs_path.stat().st_size
            if not self.should_cache_file(file_size):
                return None

            # Skip if already cached
            existing = (
                self.db.query(SSDCacheEntry)
                .filter(
                    SSDCacheEntry.array_name == self.array_name,
                    SSDCacheEntry.source_path == source_path,
                )
                .first()
            )
            if existing and bool(existing.is_valid):
                return Path(str(existing.cache_path))

            config = self.get_config()
            cache_root = Path(str(config.cache_path))

            # Build cache destination — mirror source path structure
            # Reject path traversal
            rel = PurePosixPath(source_path)
            if ".." in rel.parts:
                logger.warning("Rejected cache path with ..: %s", source_path)
                return None

            cache_dest = cache_root / rel
            cache_dest.parent.mkdir(parents=True, exist_ok=True)

            # Check SSD free space before copying
            try:
                # Walk up to find existing path for disk_usage
                check = cache_root
                while not check.exists() and check.parent != check:
                    check = check.parent
                disk = shutil.disk_usage(str(check))
                if disk.free < file_size * 1.1:
                    logger.debug("SSD space too low to cache %s", source_path)
                    return None
            except OSError:
                return None

            # Copy file
            shutil.copy2(str(source_abs_path), str(cache_dest))

            # Compute checksum
            checksum = _sha256_file(cache_dest)
            source_mtime = source_abs_path.stat().st_mtime
            now = datetime.now(timezone.utc)

            # Upsert entry
            if existing:
                # Subtract old size, add new
                old_size = int(existing.file_size_bytes)
                self.db.execute(
                    sql_update(SSDCacheEntry)
                    .where(SSDCacheEntry.id == existing.id)
                    .values(
                        cache_path=str(cache_dest),
                        file_size_bytes=file_size,
                        checksum=checksum,
                        source_mtime=source_mtime,
                        is_valid=True,
                        access_count=0,
                        last_accessed=now,
                    )
                )
                size_delta = file_size - old_size
            else:
                entry = SSDCacheEntry(
                    array_name=self.array_name,
                    source_path=source_path,
                    file_id=file_id,
                    cache_path=str(cache_dest),
                    file_size_bytes=file_size,
                    checksum=checksum,
                    access_count=0,
                    last_accessed=now,
                    first_cached=now,
                    is_valid=True,
                    source_mtime=source_mtime,
                )
                self.db.add(entry)
                size_delta = file_size

            # Update current size for this array
            self.db.execute(
                sql_update(SSDCacheConfig)
                .where(SSDCacheConfig.array_name == self.array_name)
                .values(current_size_bytes=SSDCacheConfig.current_size_bytes + size_delta)
            )
            self.db.flush()

            logger.debug("Cached %s (%d bytes) for array %s", source_path, file_size, self.array_name)
            return cache_dest

        except Exception:
            logger.exception("Failed to cache file %s", source_path)
            return None

    # ========== Invalidation ==========

    def invalidate_entry(self, source_path: str) -> None:
        """Mark a cache entry as invalid when the source file changes."""
        self.db.execute(
            sql_update(SSDCacheEntry)
            .where(
                SSDCacheEntry.array_name == self.array_name,
                SSDCacheEntry.source_path == source_path,
            )
            .values(is_valid=False)
        )
        self.db.flush()
        # Clear in-memory cache for this path
        keys_to_remove = [k for k in _path_cache if k[1] == source_path]
        for k in keys_to_remove:
            _path_cache.pop(k, None)

    def delete_cache_file(self, entry: SSDCacheEntry) -> int:
        """Delete physical cache file and DB record. Returns freed bytes."""
        freed = int(entry.file_size_bytes)
        cache_path = Path(str(entry.cache_path))
        if cache_path.exists():
            try:
                cache_path.unlink()
            except OSError:
                logger.warning("Could not delete cache file %s", cache_path)

        self.db.delete(entry)

        # Update current size for this array
        self.db.execute(
            sql_update(SSDCacheConfig)
            .where(SSDCacheConfig.array_name == self.array_name)
            .values(
                current_size_bytes=SSDCacheConfig.current_size_bytes - freed
            )
        )
        self.db.flush()

        # Clear in-memory cache
        source = str(entry.source_path)
        keys_to_remove = [k for k in _path_cache if k[1] == source]
        for k in keys_to_remove:
            _path_cache.pop(k, None)

        return freed

    # ========== Stats Helpers ==========

    def _record_hit(self, file_size: int) -> None:
        self.db.execute(
            sql_update(SSDCacheConfig)
            .where(SSDCacheConfig.array_name == self.array_name)
            .values(
                total_hits=SSDCacheConfig.total_hits + 1,
                total_bytes_served_from_cache=(
                    SSDCacheConfig.total_bytes_served_from_cache + file_size
                ),
            )
        )

    def _record_miss(self) -> None:
        self.db.execute(
            sql_update(SSDCacheConfig)
            .where(SSDCacheConfig.array_name == self.array_name)
            .values(total_misses=SSDCacheConfig.total_misses + 1)
        )

    def clear_in_memory_cache(self) -> None:
        """Clear the in-memory TTL cache (for testing)."""
        _path_cache.clear()
