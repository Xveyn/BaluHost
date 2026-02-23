"""Tests for storage breakdown (cache/VCL awareness)."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

from app.models.ssd_file_cache import SSDCacheConfig
from app.models.vcl import VCLStats
from app.services.storage_breakdown import compute_storage_breakdown, _get_device_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def cache_config_same_device(db: Session, tmp_path: Path) -> SSDCacheConfig:
    """Cache config whose cache_path is on the same device as tmp_path."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cfg = SSDCacheConfig(
        array_name="md0",
        is_enabled=True,
        cache_path=str(cache_dir),
        max_size_bytes=500 * 1024**3,
        current_size_bytes=300 * 1024**3,  # 300 GB
    )
    db.add(cfg)
    db.commit()
    return cfg


@pytest.fixture
def vcl_stats(db: Session) -> VCLStats:
    """VCL stats row with some compressed bytes."""
    stats = VCLStats(
        total_versions=10,
        total_size_bytes=200 * 1024**3,
        total_compressed_bytes=100 * 1024**3,  # 100 GB
        total_blobs=5,
        unique_blobs=3,
    )
    db.add(stats)
    db.commit()
    return stats


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetDeviceId:
    """Tests for _get_device_id helper."""

    def test_existing_path(self, tmp_path: Path):
        dev_id = _get_device_id(str(tmp_path))
        assert dev_id is not None
        assert isinstance(dev_id, int)

    def test_nonexistent_path_falls_back_to_parent(self, tmp_path: Path):
        """Non-existent child should fall back to the existing parent."""
        nonexistent = tmp_path / "does" / "not" / "exist"
        dev_id = _get_device_id(str(nonexistent))
        assert dev_id == _get_device_id(str(tmp_path))

    def test_completely_invalid_path(self):
        """A path with no valid ancestors returns None (unlikely on real FS)."""
        # Patch os.stat to always fail
        with patch("app.services.storage_breakdown.os.stat", side_effect=OSError):
            assert _get_device_id("/impossible/path") is None


class TestComputeStorageBreakdown:
    """Tests for compute_storage_breakdown."""

    def test_same_device_returns_breakdown(
        self, db: Session, tmp_path: Path, cache_config_same_device: SSDCacheConfig, vcl_stats: VCLStats
    ):
        """When cache and VCL are on the same device, a breakdown is returned."""
        used_bytes = 500 * 1024**3  # 500 GB total used

        # Patch VCL path to be on same device (tmp_path)
        vcl_dir = tmp_path / "vcl"
        vcl_dir.mkdir()
        with patch("app.services.storage_breakdown.settings") as mock_settings:
            mock_settings.vcl_storage_path = str(vcl_dir)
            mock_settings.nas_storage_path = str(tmp_path)

            result = compute_storage_breakdown(str(tmp_path), used_bytes, db)

        assert result is not None
        assert result.cache_bytes == 300 * 1024**3
        assert result.cache_enabled is True
        assert result.vcl_bytes == 100 * 1024**3
        assert result.user_files_bytes == 100 * 1024**3  # 500 - 300 - 100

    def test_different_device_returns_none(self, db: Session, tmp_path: Path, vcl_stats: VCLStats):
        """When cache/VCL are on a different device, None is returned."""
        # No cache config in DB → cache_bytes stays 0
        # Patch VCL path to appear on a different device
        with patch("app.services.storage_breakdown._get_device_id") as mock_dev:
            # mountpoint device = 100, VCL device = 200
            mock_dev.side_effect = lambda p: 100 if p == str(tmp_path) else 200

            with patch("app.services.storage_breakdown.settings") as mock_settings:
                mock_settings.vcl_storage_path = "/other/device/vcl"
                mock_settings.nas_storage_path = str(tmp_path)

                result = compute_storage_breakdown(str(tmp_path), 500 * 1024**3, db)

        assert result is None

    def test_nonexistent_mountpoint_returns_none(self, db: Session):
        """If the mountpoint itself can't be stat'd, return None."""
        with patch("app.services.storage_breakdown.os.stat", side_effect=OSError):
            result = compute_storage_breakdown("/no/such/mount", 1000, db)
        assert result is None

    def test_empty_db_returns_none(self, db: Session, tmp_path: Path):
        """No cache configs and no VCL stats → None."""
        with patch("app.services.storage_breakdown.settings") as mock_settings:
            mock_settings.vcl_storage_path = ""
            mock_settings.nas_storage_path = str(tmp_path)

            result = compute_storage_breakdown(str(tmp_path), 1000, db)

        assert result is None

    def test_user_files_bytes_clamped_to_zero(
        self, db: Session, tmp_path: Path, cache_config_same_device: SSDCacheConfig, vcl_stats: VCLStats
    ):
        """If cache + VCL exceed used_bytes, user_files_bytes should be 0 (not negative)."""
        used_bytes = 50 * 1024**3  # Only 50 GB used but cache=300GB + VCL=100GB

        vcl_dir = tmp_path / "vcl"
        vcl_dir.mkdir()
        with patch("app.services.storage_breakdown.settings") as mock_settings:
            mock_settings.vcl_storage_path = str(vcl_dir)
            mock_settings.nas_storage_path = str(tmp_path)

            result = compute_storage_breakdown(str(tmp_path), used_bytes, db)

        assert result is not None
        assert result.user_files_bytes == 0

    def test_cache_only_no_vcl(self, db: Session, tmp_path: Path, cache_config_same_device: SSDCacheConfig):
        """Only cache on same device, no VCL stats → breakdown with just cache."""
        used_bytes = 400 * 1024**3

        with patch("app.services.storage_breakdown.settings") as mock_settings:
            mock_settings.vcl_storage_path = ""
            mock_settings.nas_storage_path = str(tmp_path)

            result = compute_storage_breakdown(str(tmp_path), used_bytes, db)

        assert result is not None
        assert result.cache_bytes == 300 * 1024**3
        assert result.cache_enabled is True
        assert result.vcl_bytes == 0
        assert result.user_files_bytes == 100 * 1024**3

    def test_vcl_only_no_cache(self, db: Session, tmp_path: Path, vcl_stats: VCLStats):
        """Only VCL on same device, no cache → breakdown with just VCL."""
        used_bytes = 200 * 1024**3
        vcl_dir = tmp_path / "vcl"
        vcl_dir.mkdir()

        with patch("app.services.storage_breakdown.settings") as mock_settings:
            mock_settings.vcl_storage_path = str(vcl_dir)
            mock_settings.nas_storage_path = str(tmp_path)

            result = compute_storage_breakdown(str(tmp_path), used_bytes, db)

        assert result is not None
        assert result.cache_bytes == 0
        assert result.cache_enabled is False
        assert result.vcl_bytes == 100 * 1024**3
        assert result.user_files_bytes == 100 * 1024**3

    def test_vcl_default_path_fallback(self, db: Session, tmp_path: Path, vcl_stats: VCLStats):
        """When vcl_storage_path is empty, falls back to nas_storage_path/.system/versions."""
        used_bytes = 200 * 1024**3

        # Create the default VCL directory under nas_storage_path
        vcl_default = tmp_path / ".system" / "versions"
        vcl_default.mkdir(parents=True)

        with patch("app.services.storage_breakdown.settings") as mock_settings:
            mock_settings.vcl_storage_path = ""
            mock_settings.nas_storage_path = str(tmp_path)

            result = compute_storage_breakdown(str(tmp_path), used_bytes, db)

        assert result is not None
        assert result.vcl_bytes == 100 * 1024**3
