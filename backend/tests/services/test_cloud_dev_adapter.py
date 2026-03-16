"""Tests for services/cloud/adapters/dev.py — DevCloudAdapter (async, no external deps)."""

import tempfile
from pathlib import Path

import pytest

from app.services.cloud.adapters.dev import DevCloudAdapter, _MOCK_FS


@pytest.fixture
def adapter() -> DevCloudAdapter:
    return DevCloudAdapter(provider="google_drive")


@pytest.mark.asyncio
class TestListFiles:
    async def test_root_returns_files(self, adapter: DevCloudAdapter):
        files = await adapter.list_files("/")
        assert len(files) > 0
        names = {f.name for f in files}
        assert "Documents" in names
        assert "readme.txt" in names

    async def test_subdirectory(self, adapter: DevCloudAdapter):
        files = await adapter.list_files("/Documents")
        names = {f.name for f in files}
        assert "report.pdf" in names
        assert "Projects" in names

    async def test_nonexistent_path_returns_empty(self, adapter: DevCloudAdapter):
        files = await adapter.list_files("/nonexistent")
        assert files == []

    async def test_trailing_slash_normalized(self, adapter: DevCloudAdapter):
        files = await adapter.list_files("/Documents/")
        assert len(files) > 0

    async def test_returns_copies_not_references(self, adapter: DevCloudAdapter):
        """Modifying returned list should not affect mock filesystem."""
        files = await adapter.list_files("/")
        original_len = len(_MOCK_FS["/"])
        files.clear()
        assert len(_MOCK_FS["/"]) == original_len


@pytest.mark.asyncio
class TestDownloadFile:
    async def test_creates_local_file(self, adapter: DevCloudAdapter, tmp_path: Path):
        dest = tmp_path / "readme.txt"
        await adapter.download_file("/readme.txt", dest)
        assert dest.exists()
        assert dest.stat().st_size > 0

    async def test_creates_parent_dirs(self, adapter: DevCloudAdapter, tmp_path: Path):
        dest = tmp_path / "sub" / "dir" / "file.txt"
        await adapter.download_file("/readme.txt", dest)
        assert dest.exists()

    async def test_progress_callback_called(self, adapter: DevCloudAdapter, tmp_path: Path):
        calls = []
        dest = tmp_path / "report.pdf"
        await adapter.download_file("/Documents/report.pdf", dest, progress_callback=calls.append)
        assert len(calls) > 0
        # Last call should equal total size
        assert calls[-1] >= 1024


@pytest.mark.asyncio
class TestDownloadFolder:
    async def test_downloads_folder_files(self, adapter: DevCloudAdapter, tmp_path: Path):
        result = await adapter.download_folder("/Music", tmp_path / "Music")
        assert result.files_transferred >= 2
        assert result.bytes_transferred > 0
        assert (tmp_path / "Music" / "playlist.m3u").exists()

    async def test_recursive_download(self, adapter: DevCloudAdapter, tmp_path: Path):
        result = await adapter.download_folder("/Documents", tmp_path / "Documents")
        # Should include files from /Documents and /Documents/Projects
        assert result.files_transferred >= 4


@pytest.mark.asyncio
class TestGetFileCount:
    async def test_root_count(self, adapter: DevCloudAdapter):
        count = await adapter.get_file_count("/")
        # All non-directory files across entire mock FS
        assert count is not None
        assert count >= 10

    async def test_leaf_directory(self, adapter: DevCloudAdapter):
        count = await adapter.get_file_count("/Music")
        assert count == 2

    async def test_empty_path(self, adapter: DevCloudAdapter):
        count = await adapter.get_file_count("/nonexistent")
        assert count == 0


@pytest.mark.asyncio
class TestGetTotalSize:
    async def test_root_size(self, adapter: DevCloudAdapter):
        size = await adapter.get_total_size("/")
        assert size is not None
        assert size > 0

    async def test_music_folder_size(self, adapter: DevCloudAdapter):
        size = await adapter.get_total_size("/Music")
        # playlist.m3u (2048) + song01.mp3 (8000000)
        assert size == 2048 + 8_000_000

    async def test_empty_path_returns_zero(self, adapter: DevCloudAdapter):
        size = await adapter.get_total_size("/nonexistent")
        assert size == 0
