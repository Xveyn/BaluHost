"""Tests for SSD file cache service, eviction, and API routes."""
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

from app.models.ssd_file_cache import SSDCacheEntry, SSDCacheConfig
from app.services.cache.ssd_file_cache import SSDFileCacheService
from app.services.cache.eviction import EvictionManager

ARRAY_NAME = "md0"


@pytest.fixture
def cache_config(db: Session) -> SSDCacheConfig:
    """Create SSD cache config for test array."""
    config = SSDCacheConfig(
        array_name=ARRAY_NAME,
        is_enabled=True,
        cache_path="/tmp/test-cache",
        max_size_bytes=1024 * 1024 * 100,  # 100MB
        current_size_bytes=0,
        eviction_policy="lfru",
        min_file_size_bytes=1024,  # 1KB
        max_file_size_bytes=1024 * 1024 * 50,  # 50MB
        sequential_cutoff_bytes=64 * 1024 * 1024,
        total_hits=0,
        total_misses=0,
        total_bytes_served_from_cache=0,
    )
    db.add(config)
    db.commit()
    return config


@pytest.fixture
def disabled_config(db: Session) -> SSDCacheConfig:
    """Create disabled SSD cache config."""
    config = SSDCacheConfig(
        array_name=ARRAY_NAME,
        is_enabled=False,
        cache_path="/tmp/test-cache",
        max_size_bytes=1024 * 1024 * 100,
        current_size_bytes=0,
    )
    db.add(config)
    db.commit()
    return config


@pytest.fixture
def cache_service(db: Session, cache_config: SSDCacheConfig) -> SSDFileCacheService:
    """Create SSD file cache service."""
    svc = SSDFileCacheService(db, ARRAY_NAME)
    svc.clear_in_memory_cache()
    return svc


@pytest.fixture
def sample_entries(db: Session, cache_config: SSDCacheConfig) -> list[SSDCacheEntry]:
    """Create sample cache entries."""
    now = datetime.now(timezone.utc)
    entries = []
    for i in range(5):
        entry = SSDCacheEntry(
            array_name=ARRAY_NAME,
            source_path=f"user1/files/doc{i}.pdf",
            cache_path=f"/tmp/test-cache/user1/files/doc{i}.pdf",
            file_size_bytes=1024 * 1024 * (i + 1),  # 1MB to 5MB
            checksum=f"sha256_{i:064d}",
            access_count=i * 3,
            last_accessed=now - timedelta(hours=i * 2),
            first_cached=now - timedelta(days=i),
            is_valid=True,
            source_mtime=1000000.0 + i,
        )
        entries.append(entry)
        db.add(entry)

    # Update current_size
    total = sum(e.file_size_bytes for e in entries)
    cache_config.current_size_bytes = total
    db.commit()
    return entries


class TestSSDFileCacheService:
    """Test SSD file cache service core operations."""

    def test_get_config_creates_default(self, db: Session):
        """get_config creates config for array if not exists."""
        svc = SSDFileCacheService(db, ARRAY_NAME)
        config = svc.get_config()
        assert config.array_name == ARRAY_NAME
        assert config.is_enabled is False

    def test_get_config_returns_existing(self, db: Session, cache_config: SSDCacheConfig):
        """get_config returns existing config."""
        svc = SSDFileCacheService(db, ARRAY_NAME)
        config = svc.get_config()
        assert config.array_name == ARRAY_NAME
        assert config.is_enabled is True

    def test_get_all_configs(self, db: Session, cache_config: SSDCacheConfig):
        """get_all_configs returns all array configs."""
        configs = SSDFileCacheService.get_all_configs(db)
        assert len(configs) >= 1
        assert any(c.array_name == ARRAY_NAME for c in configs)

    def test_is_cache_enabled(self, cache_service: SSDFileCacheService):
        """is_cache_enabled reflects config state."""
        assert cache_service.is_cache_enabled() is True

    def test_is_cache_disabled(self, db: Session, disabled_config: SSDCacheConfig):
        """is_cache_enabled returns False when disabled."""
        svc = SSDFileCacheService(db, ARRAY_NAME)
        assert svc.is_cache_enabled() is False

    def test_should_cache_file_eligible(self, cache_service: SSDFileCacheService):
        """Eligible file size returns True."""
        assert cache_service.should_cache_file(1024 * 1024 * 5) is True  # 5MB

    def test_should_cache_file_too_small(self, cache_service: SSDFileCacheService):
        """File smaller than min_file_size_bytes is rejected."""
        assert cache_service.should_cache_file(512) is False  # 512B < 1KB min

    def test_should_cache_file_too_large(self, cache_service: SSDFileCacheService):
        """File larger than max_file_size_bytes is rejected."""
        assert cache_service.should_cache_file(1024 * 1024 * 60) is False  # 60MB > 50MB max

    def test_should_cache_file_no_capacity(self, db: Session, cache_config: SSDCacheConfig):
        """File rejected when cache is near full."""
        cache_config.current_size_bytes = 1024 * 1024 * 99  # 99MB of 100MB
        db.commit()
        svc = SSDFileCacheService(db, ARRAY_NAME)
        assert svc.should_cache_file(1024 * 1024 * 5) is False  # 5MB would exceed

    def test_should_cache_file_disabled(self, db: Session, disabled_config: SSDCacheConfig):
        """Disabled cache rejects all files."""
        svc = SSDFileCacheService(db, ARRAY_NAME)
        assert svc.should_cache_file(1024 * 1024) is False

    def test_get_cached_path_miss(self, cache_service: SSDFileCacheService, db: Session):
        """Cache miss returns None and increments miss counter."""
        result = cache_service.get_cached_path("nonexistent/file.txt", 123.0)
        assert result is None
        db.flush()
        config = cache_service.get_config()
        assert int(config.total_misses) >= 1

    def test_get_cached_path_stale_mtime(
        self, cache_service: SSDFileCacheService, sample_entries: list, db: Session
    ):
        """Stale entry (mtime mismatch) returns None."""
        entry = sample_entries[0]
        result = cache_service.get_cached_path(
            str(entry.source_path), 999999.0  # wrong mtime
        )
        assert result is None
        # Entry should be invalidated
        db.refresh(entry)
        assert entry.is_valid is False

    def test_get_cached_path_hit(
        self, cache_service: SSDFileCacheService, sample_entries: list, db: Session, tmp_path: Path
    ):
        """Cache hit with valid file returns path."""
        entry = sample_entries[0]
        # Create actual file at cache_path
        cache_file = tmp_path / "cached.pdf"
        cache_file.write_bytes(b"cached content")
        entry.cache_path = str(cache_file)
        db.commit()

        result = cache_service.get_cached_path(
            str(entry.source_path), float(entry.source_mtime)
        )
        assert result == cache_file
        db.refresh(entry)
        assert int(entry.access_count) > 0

    def test_get_cached_path_missing_file(
        self, cache_service: SSDFileCacheService, sample_entries: list, db: Session
    ):
        """Cache entry pointing to missing file returns None."""
        entry = sample_entries[0]
        entry.cache_path = "/tmp/nonexistent/file.pdf"
        db.commit()

        result = cache_service.get_cached_path(
            str(entry.source_path), float(entry.source_mtime)
        )
        assert result is None

    def test_cache_file_success(
        self, cache_service: SSDFileCacheService, db: Session, tmp_path: Path
    ):
        """Successfully cache a file from source to SSD."""
        # Set cache path to tmp_path
        config = cache_service.get_config()
        config.cache_path = str(tmp_path / "cache")
        db.commit()

        # Create source file
        source = tmp_path / "source" / "test.txt"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"x" * 2048)  # 2KB

        with patch("app.services.cache.ssd_file_cache.shutil") as mock_shutil:
            mock_shutil.disk_usage.return_value = MagicMock(free=1024 * 1024 * 100)
            mock_shutil.copy2 = lambda src, dst: Path(dst).parent.mkdir(parents=True, exist_ok=True) or Path(dst).write_bytes(source.read_bytes())

            result = cache_service.cache_file("user1/test.txt", source, file_id=1)

        assert result is not None
        db.flush()
        config = cache_service.get_config()
        assert int(config.current_size_bytes) > 0

    def test_cache_file_rejects_path_traversal(
        self, cache_service: SSDFileCacheService, tmp_path: Path
    ):
        """Files with .. in path are rejected."""
        source = tmp_path / "evil.txt"
        source.write_bytes(b"data")

        result = cache_service.cache_file("../../etc/passwd", source)
        assert result is None

    def test_cache_file_nonexistent_source(
        self, cache_service: SSDFileCacheService, tmp_path: Path
    ):
        """Nonexistent source file returns None."""
        result = cache_service.cache_file("user1/missing.txt", tmp_path / "nope.txt")
        assert result is None

    def test_invalidate_entry(
        self, cache_service: SSDFileCacheService, sample_entries: list, db: Session
    ):
        """Invalidating an entry marks it as invalid."""
        entry = sample_entries[0]
        assert entry.is_valid is True

        cache_service.invalidate_entry(str(entry.source_path))
        db.refresh(entry)
        assert entry.is_valid is False

    def test_delete_cache_file(
        self, cache_service: SSDFileCacheService, sample_entries: list, db: Session, tmp_path: Path
    ):
        """Deleting a cache file removes it from DB and disk."""
        entry = sample_entries[0]
        cache_file = tmp_path / "to_delete.pdf"
        cache_file.write_bytes(b"delete me")
        entry.cache_path = str(cache_file)
        db.commit()

        freed = cache_service.delete_cache_file(entry)
        db.flush()

        assert freed == int(entry.file_size_bytes)
        assert not cache_file.exists()
        # Entry should be deleted from DB
        remaining = db.query(SSDCacheEntry).filter(SSDCacheEntry.id == entry.id).first()
        assert remaining is None


class TestEvictionManager:
    """Test cache eviction logic."""

    def test_needs_eviction_false_when_low(self, db: Session, cache_config: SSDCacheConfig):
        """No eviction needed when usage is low."""
        cache_config.current_size_bytes = 1024 * 1024 * 50  # 50% of 100MB
        db.commit()
        em = EvictionManager(db, ARRAY_NAME)
        assert em.needs_eviction() is False

    def test_needs_eviction_true_when_high(self, db: Session, cache_config: SSDCacheConfig):
        """Eviction needed when usage exceeds 95%."""
        cache_config.current_size_bytes = 1024 * 1024 * 97  # 97% of 100MB
        db.commit()
        em = EvictionManager(db, ARRAY_NAME)
        assert em.needs_eviction() is True

    def test_needs_eviction_no_config(self, db: Session):
        """No eviction if config doesn't exist."""
        em = EvictionManager(db, "nonexistent")
        assert em.needs_eviction() is False

    def test_get_eviction_candidates_lru(
        self, db: Session, cache_config: SSDCacheConfig, sample_entries: list
    ):
        """LRU eviction orders by last_accessed ascending."""
        needed = 1024 * 1024 * 3  # need to free 3MB
        em = EvictionManager(db, ARRAY_NAME)
        candidates = em.get_eviction_candidates("lru", needed)
        assert len(candidates) > 0
        # Oldest accessed should be first
        for i in range(len(candidates) - 1):
            if candidates[i].is_valid and candidates[i + 1].is_valid:
                assert candidates[i].last_accessed <= candidates[i + 1].last_accessed

    def test_get_eviction_candidates_lfu(
        self, db: Session, cache_config: SSDCacheConfig, sample_entries: list
    ):
        """LFU eviction orders by access_count ascending."""
        needed = 1024 * 1024 * 3
        em = EvictionManager(db, ARRAY_NAME)
        candidates = em.get_eviction_candidates("lfu", needed)
        assert len(candidates) > 0

    def test_get_eviction_candidates_lfru(
        self, db: Session, cache_config: SSDCacheConfig, sample_entries: list
    ):
        """LFRU eviction uses hybrid scoring."""
        needed = 1024 * 1024 * 3
        em = EvictionManager(db, ARRAY_NAME)
        candidates = em.get_eviction_candidates("lfru", needed)
        assert len(candidates) > 0

    def test_eviction_prefers_invalid_entries(
        self, db: Session, cache_config: SSDCacheConfig, sample_entries: list
    ):
        """Invalid entries are evicted first regardless of policy."""
        # Mark some entries as invalid
        sample_entries[0].is_valid = False
        sample_entries[1].is_valid = False
        db.commit()

        em = EvictionManager(db, ARRAY_NAME)
        candidates = em.get_eviction_candidates(
            "lru", int(sample_entries[0].file_size_bytes)
        )
        # Invalid entries should come first
        assert candidates[0].is_valid is False

    def test_run_eviction_frees_space(
        self, db: Session, cache_config: SSDCacheConfig, sample_entries: list
    ):
        """run_eviction frees space down to low watermark."""
        # Set current size to 97% of max
        cache_config.current_size_bytes = int(cache_config.max_size_bytes * 0.97)
        db.commit()

        em = EvictionManager(db, ARRAY_NAME)
        svc = SSDFileCacheService(db, ARRAY_NAME)

        # Mock delete_cache_file to just return size
        def mock_delete(entry):
            freed = int(entry.file_size_bytes)
            db.delete(entry)
            db.execute(
                __import__("sqlalchemy").update(SSDCacheConfig)
                .where(SSDCacheConfig.array_name == ARRAY_NAME)
                .values(current_size_bytes=SSDCacheConfig.current_size_bytes - freed)
            )
            db.flush()
            return freed

        svc.delete_cache_file = mock_delete
        result = em.run_eviction(svc)

        assert result["freed_bytes"] > 0
        assert result["deleted_count"] > 0

    def test_run_eviction_no_config(self, db: Session):
        """run_eviction with no config returns zeros."""
        em = EvictionManager(db, "nonexistent")
        svc = SSDFileCacheService(db, "nonexistent")
        result = em.run_eviction(svc)
        assert result == {"freed_bytes": 0, "deleted_count": 0}

    def test_run_eviction_not_needed(
        self, db: Session, cache_config: SSDCacheConfig
    ):
        """run_eviction returns zeros when below watermark."""
        cache_config.current_size_bytes = 1024 * 1024 * 50  # 50%
        db.commit()

        em = EvictionManager(db, ARRAY_NAME)
        svc = SSDFileCacheService(db, ARRAY_NAME)
        result = em.run_eviction(svc)
        assert result == {"freed_bytes": 0, "deleted_count": 0}


class TestInvalidationHelper:
    """Test the _invalidate_ssd_cache helper from operations.py."""

    def test_invalidate_ssd_cache_with_disabled_cache(self, db: Session, disabled_config):
        """Invalidation is a no-op when cache is disabled."""
        from app.services.files.operations import _invalidate_ssd_cache
        # Should not raise
        _invalidate_ssd_cache("any/path.txt", db=db)

    def test_invalidate_ssd_cache_without_db(self):
        """Invalidation is a no-op without db session."""
        from app.services.files.operations import _invalidate_ssd_cache
        _invalidate_ssd_cache("any/path.txt", db=None)

    def test_invalidate_ssd_cache_with_entry(
        self, db: Session, cache_config: SSDCacheConfig, sample_entries: list
    ):
        """Invalidation marks matching entry as invalid."""
        from app.services.files.operations import _invalidate_ssd_cache
        entry = sample_entries[0]
        assert entry.is_valid is True

        _invalidate_ssd_cache(str(entry.source_path), db=db)
        db.refresh(entry)
        assert entry.is_valid is False
