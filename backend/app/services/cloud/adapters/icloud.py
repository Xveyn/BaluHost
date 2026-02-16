"""iCloud adapter using pyicloud library."""
import asyncio
import logging
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Callable, Optional

from app.services.cloud.adapters.base import CloudAdapter, CloudFile, DownloadResult

logger = logging.getLogger(__name__)


class ICloudAdapter(CloudAdapter):
    """Adapter for iCloud Drive using pyicloud."""

    def __init__(self, apple_id: str, password: str, session_dir: Optional[str] = None):
        """
        Args:
            apple_id: Apple ID email
            password: App-specific password or account password
            session_dir: Directory for pyicloud session cache
        """
        self.apple_id = apple_id
        self._password = password
        self._session_dir = session_dir
        self._api = None

    def _get_api(self):
        """Lazily initialize the pyicloud API."""
        if self._api is None:
            try:
                from pyicloud import PyiCloudService
            except ImportError:
                raise RuntimeError(
                    "pyicloud is not installed. Install with: pip install pyicloud"
                )

            kwargs = {"apple_id": self.apple_id, "password": self._password}
            if self._session_dir:
                kwargs["cookie_directory"] = self._session_dir

            self._api = PyiCloudService(**kwargs)

        return self._api

    @property
    def requires_2fa(self) -> bool:
        """Check if 2FA is required."""
        api = self._get_api()
        return api.requires_2fa or api.requires_2sa

    def validate_2fa(self, code: str) -> bool:
        """Validate a 2FA code."""
        api = self._get_api()
        if api.requires_2fa:
            return api.validate_2fa_code(code)
        elif api.requires_2sa:
            # For 2SA (legacy), use trusted device
            devices = api.trusted_devices
            if devices:
                if api.send_verification_code(devices[0]):
                    return api.validate_verification_code(devices[0], code)
        return False

    def _get_drive_node(self, path: str):
        """Navigate to a drive node by path."""
        api = self._get_api()
        drive = api.drive

        if path in ("/", ""):
            return drive.root

        parts = [p for p in path.strip("/").split("/") if p]
        node = drive.root
        for part in parts:
            node = node[part]
        return node

    async def list_files(self, path: str = "/") -> list[CloudFile]:
        """List files in iCloud Drive at the given path."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._list_files_sync, path))

    def _list_files_sync(self, path: str) -> list[CloudFile]:
        """Synchronous implementation of list_files."""
        node = self._get_drive_node(path)
        files: list[CloudFile] = []

        for child in node.dir():
            child_node = node[child]
            is_dir = child_node.type == "folder"

            mod_time = None
            if hasattr(child_node, "date_modified") and child_node.date_modified:
                mod_time = child_node.date_modified

            size = None
            if not is_dir and hasattr(child_node, "size"):
                size = child_node.size

            child_path = f"{path.rstrip('/')}/{child}"
            files.append(
                CloudFile(
                    name=child,
                    path=child_path,
                    is_directory=is_dir,
                    size_bytes=size,
                    modified_at=mod_time,
                )
            )

        return files

    async def download_file(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Download a single file from iCloud Drive."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, partial(self._download_file_sync, remote_path, local_path, progress_callback)
        )

    def _download_file_sync(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int], None]],
    ) -> None:
        """Synchronous implementation of download_file."""
        node = self._get_drive_node(remote_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        with node.open(stream=True) as response:
            total = 0
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
                        if progress_callback:
                            progress_callback(total)

    async def download_folder(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int, Optional[str]], None]] = None,
    ) -> DownloadResult:
        """Download a folder recursively from iCloud Drive."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            partial(self._download_folder_sync, remote_path, local_path, progress_callback),
        )

    def _download_folder_sync(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int, Optional[str]], None]],
    ) -> DownloadResult:
        """Synchronous recursive folder download."""
        result = DownloadResult()
        local_path.mkdir(parents=True, exist_ok=True)

        node = self._get_drive_node(remote_path)

        for child_name in node.dir():
            child_node = node[child_name]
            child_remote = f"{remote_path.rstrip('/')}/{child_name}"
            child_local = local_path / child_name

            if child_node.type == "folder":
                sub_result = self._download_folder_sync(
                    child_remote, child_local, progress_callback
                )
                result.files_transferred += sub_result.files_transferred
                result.bytes_transferred += sub_result.bytes_transferred
                result.errors.extend(sub_result.errors)
            else:
                try:
                    if progress_callback:
                        progress_callback(result.bytes_transferred, child_name)

                    self._download_file_sync(child_remote, child_local, None)
                    if child_local.exists():
                        result.bytes_transferred += child_local.stat().st_size
                    result.files_transferred += 1
                except Exception as e:
                    logger.error("Failed to download %s: %s", child_remote, e)
                    result.errors.append(f"{child_remote}: {e}")

        return result

    async def get_total_size(self, remote_path: str) -> Optional[int]:
        """Get total size of a path in iCloud Drive."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._get_total_size_sync, remote_path)
        )

    def _get_total_size_sync(self, remote_path: str) -> Optional[int]:
        """Synchronous total size calculation."""
        try:
            node = self._get_drive_node(remote_path)
            if node.type != "folder":
                return node.size if hasattr(node, "size") else None
            return self._calc_folder_size(node)
        except Exception:
            return None

    def _calc_folder_size(self, node) -> int:
        """Recursively calculate folder size."""
        total = 0
        for child_name in node.dir():
            child = node[child_name]
            if child.type == "folder":
                total += self._calc_folder_size(child)
            elif hasattr(child, "size") and child.size:
                total += child.size
        return total

    async def close(self) -> None:
        """Clean up pyicloud session."""
        self._api = None
