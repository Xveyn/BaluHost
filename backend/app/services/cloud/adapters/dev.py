"""Mock cloud adapter for development mode."""
import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable, Optional

from app.services.cloud.adapters.base import CloudAdapter, CloudFile, DownloadResult

logger = logging.getLogger(__name__)

# Simulated cloud filesystem
_MOCK_FS: dict[str, list[CloudFile]] = {
    "/": [
        CloudFile(name="Documents", path="/Documents", is_directory=True),
        CloudFile(name="Photos", path="/Photos", is_directory=True),
        CloudFile(name="Music", path="/Music", is_directory=True),
        CloudFile(
            name="readme.txt", path="/readme.txt", is_directory=False,
            size_bytes=1024, modified_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        ),
        CloudFile(
            name="budget.xlsx", path="/budget.xlsx", is_directory=False,
            size_bytes=245_760, modified_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        ),
    ],
    "/Documents": [
        CloudFile(
            name="report.pdf", path="/Documents/report.pdf", is_directory=False,
            size_bytes=2_500_000, modified_at=datetime(2026, 1, 20, tzinfo=timezone.utc),
        ),
        CloudFile(
            name="notes.md", path="/Documents/notes.md", is_directory=False,
            size_bytes=8_192, modified_at=datetime(2026, 2, 10, tzinfo=timezone.utc),
        ),
        CloudFile(name="Projects", path="/Documents/Projects", is_directory=True),
    ],
    "/Documents/Projects": [
        CloudFile(
            name="plan.docx", path="/Documents/Projects/plan.docx", is_directory=False,
            size_bytes=150_000, modified_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        ),
        CloudFile(
            name="data.csv", path="/Documents/Projects/data.csv", is_directory=False,
            size_bytes=50_000, modified_at=datetime(2026, 2, 14, tzinfo=timezone.utc),
        ),
    ],
    "/Photos": [
        CloudFile(
            name="vacation_001.jpg", path="/Photos/vacation_001.jpg", is_directory=False,
            size_bytes=4_500_000, modified_at=datetime(2025, 8, 15, tzinfo=timezone.utc),
        ),
        CloudFile(
            name="vacation_002.jpg", path="/Photos/vacation_002.jpg", is_directory=False,
            size_bytes=3_800_000, modified_at=datetime(2025, 8, 15, tzinfo=timezone.utc),
        ),
        CloudFile(
            name="screenshot.png", path="/Photos/screenshot.png", is_directory=False,
            size_bytes=1_200_000, modified_at=datetime(2026, 2, 5, tzinfo=timezone.utc),
        ),
    ],
    "/Music": [
        CloudFile(
            name="playlist.m3u", path="/Music/playlist.m3u", is_directory=False,
            size_bytes=2_048, modified_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
        ),
        CloudFile(
            name="song01.mp3", path="/Music/song01.mp3", is_directory=False,
            size_bytes=8_000_000, modified_at=datetime(2025, 11, 20, tzinfo=timezone.utc),
        ),
    ],
}


class DevCloudAdapter(CloudAdapter):
    """Mock adapter for development without real cloud credentials."""

    def __init__(self, provider: str = "google_drive"):
        self.provider = provider

    async def list_files(self, path: str = "/") -> list[CloudFile]:
        """Return mock files for the given path."""
        await asyncio.sleep(0.3)  # Simulate network latency
        normalized = path.rstrip("/") or "/"
        return list(_MOCK_FS.get(normalized, []))

    async def download_file(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Simulate downloading a file by creating a local placeholder."""
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Find file info for realistic size
        size = 1024
        for files in _MOCK_FS.values():
            for f in files:
                if f.path == remote_path and f.size_bytes:
                    size = f.size_bytes
                    break

        # Simulate download with progress
        chunk_size = max(size // 10, 1024)
        downloaded = 0
        with open(local_path, "wb") as fh:
            while downloaded < size:
                write_size = min(chunk_size, size - downloaded)
                fh.write(b"\x00" * write_size)
                downloaded += write_size
                if progress_callback:
                    progress_callback(downloaded)
                await asyncio.sleep(0.05)

    async def download_folder(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int, Optional[str]], None]] = None,
    ) -> DownloadResult:
        """Simulate downloading a folder."""
        result = DownloadResult()
        local_path.mkdir(parents=True, exist_ok=True)

        normalized = remote_path.rstrip("/") or "/"
        files = _MOCK_FS.get(normalized, [])

        for f in files:
            if f.is_directory:
                sub_result = await self.download_folder(
                    f.path, local_path / f.name, progress_callback
                )
                result.files_transferred += sub_result.files_transferred
                result.bytes_transferred += sub_result.bytes_transferred
            else:
                if progress_callback:
                    progress_callback(result.bytes_transferred, f.name)

                file_path = local_path / f.name
                await self.download_file(f.path, file_path)
                result.files_transferred += 1
                result.bytes_transferred += f.size_bytes or 1024

        return result

    async def get_file_count(self, remote_path: str) -> Optional[int]:
        """Count files in mock filesystem recursively."""
        await asyncio.sleep(0.1)
        normalized = remote_path.rstrip("/") or "/"
        return self._count_files(normalized)

    def _count_files(self, path: str) -> int:
        """Recursively count mock files (non-directory entries)."""
        total = 0
        files = _MOCK_FS.get(path, [])
        for f in files:
            if f.is_directory:
                total += self._count_files(f.path)
            else:
                total += 1
        return total

    async def get_total_size(self, remote_path: str) -> Optional[int]:
        """Calculate total size of mock files."""
        await asyncio.sleep(0.1)
        normalized = remote_path.rstrip("/") or "/"
        return self._calc_size(normalized)

    def _calc_size(self, path: str) -> int:
        """Recursively calculate mock folder size."""
        total = 0
        files = _MOCK_FS.get(path, [])
        for f in files:
            if f.is_directory:
                total += self._calc_size(f.path)
            elif f.size_bytes:
                total += f.size_bytes
        return total
