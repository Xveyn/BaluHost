"""SSD Cache Eviction Manager.

Supports LFRU (default), LRU, and LFU eviction policies.
Per-array: each array has independent eviction.

LFRU scoring: score = access_count * recency_weight
  recency_weight = 1.0 / (1 + hours_since_last_access)
  Lowest score = evict first.
"""
import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import asc

from app.models.ssd_file_cache import SSDCacheEntry, SSDCacheConfig

logger = logging.getLogger(__name__)


class EvictionManager:
    """Manages cache eviction based on configurable policies, scoped to an array."""

    # Trigger eviction when usage > 95%, target: reduce to 80%
    HIGH_WATERMARK = 0.95
    LOW_WATERMARK = 0.80

    def __init__(self, db: Session, array_name: str = "md0"):
        self.db = db
        self.array_name = array_name

    def needs_eviction(self) -> bool:
        """Check if cache usage exceeds high watermark."""
        config = (
            self.db.query(SSDCacheConfig)
            .filter(SSDCacheConfig.array_name == self.array_name)
            .first()
        )
        if not config:
            return False
        current = int(config.current_size_bytes)
        max_size = int(config.max_size_bytes)
        if max_size <= 0:
            return False
        return current > max_size * self.HIGH_WATERMARK

    def get_eviction_candidates(
        self, policy: str, needed_bytes: int
    ) -> List[SSDCacheEntry]:
        """
        Get ordered list of entries to evict until needed_bytes is freed.

        Args:
            policy: 'lfru' | 'lru' | 'lfu'
            needed_bytes: Minimum bytes to free
        """
        # First: always evict invalid entries
        invalid = (
            self.db.query(SSDCacheEntry)
            .filter(
                SSDCacheEntry.array_name == self.array_name,
                SSDCacheEntry.is_valid.is_(False),
            )
            .all()
        )

        accumulated = sum(int(e.file_size_bytes) for e in invalid)
        if accumulated >= needed_bytes:
            return invalid

        # Then: get valid entries ordered by eviction priority
        base_filter = [
            SSDCacheEntry.array_name == self.array_name,
            SSDCacheEntry.is_valid.is_(True),
        ]

        if policy == "lru":
            query = (
                self.db.query(SSDCacheEntry)
                .filter(*base_filter)
                .order_by(asc(SSDCacheEntry.last_accessed))
            )
        elif policy == "lfu":
            query = (
                self.db.query(SSDCacheEntry)
                .filter(*base_filter)
                .order_by(asc(SSDCacheEntry.access_count))
            )
        else:
            # LFRU: we need to score in Python since the formula is complex
            query = (
                self.db.query(SSDCacheEntry)
                .filter(*base_filter)
            )

        valid_entries = query.all()

        if policy == "lfru":
            now = datetime.now(timezone.utc)
            scored = []
            for e in valid_entries:
                last = e.last_accessed
                if last and last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                hours_ago = (now - last).total_seconds() / 3600 if last else 999
                recency_weight = 1.0 / (1 + hours_ago)
                score = int(e.access_count) * recency_weight
                scored.append((score, e))
            scored.sort(key=lambda x: x[0])
            valid_entries = [e for _, e in scored]

        # Collect enough entries to free needed_bytes
        candidates = list(invalid)
        for entry in valid_entries:
            if accumulated >= needed_bytes:
                break
            candidates.append(entry)
            accumulated += int(entry.file_size_bytes)

        return candidates

    def run_eviction(self, cache_service) -> dict:
        """
        Run one eviction cycle.

        Triggered when current_size > max_size * 0.95.
        Target: reduce to max_size * 0.80.

        Returns summary dict with freed_bytes, deleted_count.
        """
        config = (
            self.db.query(SSDCacheConfig)
            .filter(SSDCacheConfig.array_name == self.array_name)
            .first()
        )
        if not config:
            return {"freed_bytes": 0, "deleted_count": 0}

        current = int(config.current_size_bytes)
        max_size = int(config.max_size_bytes)
        target = int(max_size * self.LOW_WATERMARK)
        needed = current - target

        if needed <= 0:
            return {"freed_bytes": 0, "deleted_count": 0}

        policy = str(config.eviction_policy) or "lfru"
        candidates = self.get_eviction_candidates(policy, needed)

        freed_bytes = 0
        deleted_count = 0

        for entry in candidates:
            freed = cache_service.delete_cache_file(entry)
            freed_bytes += freed
            deleted_count += 1

        logger.info(
            "Eviction complete for array %s: freed=%d bytes, deleted=%d entries (policy=%s)",
            self.array_name, freed_bytes, deleted_count, policy,
        )
        return {"freed_bytes": freed_bytes, "deleted_count": deleted_count}
