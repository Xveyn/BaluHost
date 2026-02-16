"""Abstract base class for cloud provider adapters."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


@dataclass
class CloudFile:
    """Represents a file or directory in a cloud provider."""
    name: str
    path: str
    is_directory: bool
    size_bytes: Optional[int] = None
    modified_at: Optional[datetime] = None


@dataclass
class DownloadResult:
    """Result of a folder download operation."""
    files_transferred: int = 0
    bytes_transferred: int = 0
    errors: list[str] = field(default_factory=list)


class CloudAdapter(ABC):
    """Abstract interface for cloud storage providers."""

    @abstractmethod
    async def list_files(self, path: str = "/") -> list[CloudFile]:
        """List files and directories at the given path."""
        ...

    @abstractmethod
    async def download_file(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Download a single file from the cloud to a local path."""
        ...

    @abstractmethod
    async def download_folder(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int, Optional[str]], None]] = None,
    ) -> DownloadResult:
        """Download an entire folder recursively."""
        ...

    @abstractmethod
    async def get_total_size(self, remote_path: str) -> Optional[int]:
        """Get total size in bytes of a file or folder. Returns None if unknown."""
        ...

    async def get_file_count(self, remote_path: str) -> Optional[int]:
        """Get total number of files in a folder. Returns None if unknown."""
        return None

    async def close(self) -> None:
        """Clean up resources. Override if adapter holds state."""
        pass
