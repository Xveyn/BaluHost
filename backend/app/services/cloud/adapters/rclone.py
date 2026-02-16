"""Rclone-based adapter for Google Drive and OneDrive."""
import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from app.services.cloud.adapters.base import CloudAdapter, CloudFile, DownloadResult

logger = logging.getLogger(__name__)


class RcloneAdapter(CloudAdapter):
    """Adapter using rclone CLI for Google Drive and OneDrive.

    Uses asyncio.create_subprocess_exec for safe subprocess invocation
    (no shell injection risk — all arguments are passed as a list).
    """

    def __init__(self, remote_name: str, config_content: str):
        """
        Args:
            remote_name: Name of the rclone remote (e.g. "gdrive_user5")
            config_content: Decrypted rclone config content (INI format)
        """
        self.remote_name = remote_name
        self._config_content = config_content
        self._config_file: Optional[tempfile.NamedTemporaryFile] = None

    def _get_config_path(self) -> str:
        """Write config to a temp file and return its path."""
        if self._config_file is None:
            self._config_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".conf", delete=False, prefix="rclone_"
            )
            self._config_file.write(self._config_content)
            self._config_file.flush()
        return self._config_file.name

    async def _run_rclone(self, *args: str, timeout: int = 300) -> str:
        """Run an rclone command via subprocess_exec (no shell) and return stdout."""
        config_path = self._get_config_path()
        cmd = ["rclone", "--config", config_path, *args]

        logger.debug("Running rclone command with %d args", len(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"rclone command timed out after {timeout}s")

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            raise RuntimeError(f"rclone error (exit {proc.returncode}): {error_msg}")

        return stdout.decode()

    async def list_files(self, path: str = "/") -> list[CloudFile]:
        """List files using rclone lsjson."""
        remote_path = f"{self.remote_name}:{path.lstrip('/')}"
        output = await self._run_rclone(
            "lsjson", remote_path, "--no-modtime=false", timeout=60
        )

        files: list[CloudFile] = []
        if not output.strip():
            return files

        for item in json.loads(output):
            mod_time = None
            if item.get("ModTime"):
                try:
                    mod_time = datetime.fromisoformat(
                        item["ModTime"].replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            full_path = f"{path.rstrip('/')}/{item['Name']}"
            files.append(
                CloudFile(
                    name=item["Name"],
                    path=full_path,
                    is_directory=item.get("IsDir", False),
                    size_bytes=item.get("Size"),
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
        """Download a single file using rclone copyto with streaming progress."""
        remote = f"{self.remote_name}:{remote_path.lstrip('/')}"
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if not progress_callback:
            await self._run_rclone(
                "copyto", remote, str(local_path), timeout=3600
            )
            return

        # Stream stderr for live progress updates.
        # Uses asyncio.create_subprocess_exec (argument list, no shell) —
        # safe against injection by design.
        config_path = self._get_config_path()
        cmd = [
            "rclone", "--config", config_path,
            "copyto", remote, str(local_path),
            "--stats", "1s", "--stats-one-line", "-v",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if proc.stderr:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode().strip()
                if "Transferred:" in text and "/" in text:
                    try:
                        parts = text.split("Transferred:")[1].strip()
                        transferred_part = parts.split("/")[0].strip()
                        bytes_done = self._parse_size(transferred_part)
                        if bytes_done is not None:
                            progress_callback(bytes_done)
                    except (IndexError, ValueError):
                        pass

        await proc.wait()

        if proc.returncode != 0:
            raise RuntimeError(f"rclone copyto failed (exit {proc.returncode})")

        # Final callback with actual file size
        if local_path.exists():
            progress_callback(local_path.stat().st_size)

    async def download_folder(
        self,
        remote_path: str,
        local_path: Path,
        progress_callback: Optional[Callable[[int, Optional[str]], None]] = None,
    ) -> DownloadResult:
        """Download a folder using rclone copy with progress parsing."""
        remote = f"{self.remote_name}:{remote_path.lstrip('/')}"
        local_path.mkdir(parents=True, exist_ok=True)

        config_path = self._get_config_path()
        cmd = [
            "rclone", "--config", config_path,
            "copy", remote, str(local_path),
            "--stats", "2s", "--stats-one-line", "-v",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result = DownloadResult()
        _current_file: Optional[str] = None

        # Parse stderr for progress (rclone outputs stats to stderr)
        if proc.stderr:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode().strip()

                # Track current file from verbose transfer lines
                # rclone -v prints lines like: "* filename: 50% /1.2Mi, ..."
                if text.startswith("* ") and ":" in text:
                    fname = text[2:].split(":")[0].strip()
                    if fname:
                        _current_file = fname

                # Parse transferred bytes (no ETA requirement)
                if "Transferred:" in text and "/" in text:
                    try:
                        parts = text.split("Transferred:")[1].strip()
                        transferred_part = parts.split("/")[0].strip()
                        bytes_done = self._parse_size(transferred_part)
                        if progress_callback and bytes_done is not None:
                            progress_callback(bytes_done, _current_file)
                    except (IndexError, ValueError):
                        pass

        await proc.wait()

        if proc.returncode != 0:
            stderr_text = ""
            if proc.stderr:
                remaining = await proc.stderr.read()
                stderr_text = remaining.decode().strip()
            result.errors.append(f"rclone exit code {proc.returncode}: {stderr_text}")

        # Count transferred files
        for f in local_path.rglob("*"):
            if f.is_file():
                result.files_transferred += 1
                result.bytes_transferred += f.stat().st_size

        return result

    async def get_total_size(self, remote_path: str) -> Optional[int]:
        """Get total size using rclone size."""
        remote = f"{self.remote_name}:{remote_path.lstrip('/')}"
        try:
            output = await self._run_rclone("size", remote, "--json", timeout=120)
            data = json.loads(output)
            return data.get("bytes")
        except Exception:
            logger.warning("Could not get size for %s", remote_path)
            return None

    async def get_file_count(self, remote_path: str) -> Optional[int]:
        """Get total number of files using rclone size --json."""
        remote = f"{self.remote_name}:{remote_path.lstrip('/')}"
        try:
            output = await self._run_rclone("size", remote, "--json", timeout=120)
            data = json.loads(output)
            return data.get("count")
        except Exception:
            logger.warning("Could not get file count for %s", remote_path)
            return None

    @staticmethod
    def _parse_size(size_str: str) -> Optional[int]:
        """Parse a human-readable size string to bytes.

        Supports both binary (KiB, MiB, GiB, TiB) and SI (kB, MB, GB, TB)
        suffixes. Suffixes are matched longest-first so 'GiB' matches before 'B'.
        """
        size_str = size_str.strip()
        # Sorted by suffix length descending so longer suffixes match first
        multipliers: list[tuple[str, int]] = [
            ("TiB", 1024**4),
            ("GiB", 1024**3),
            ("MiB", 1024**2),
            ("KiB", 1024),
            ("TB", 10**12),
            ("GB", 10**9),
            ("MB", 10**6),
            ("kB", 10**3),
            ("B", 1),
        ]
        for suffix, mult in multipliers:
            if size_str.endswith(suffix):
                try:
                    return int(float(size_str[: -len(suffix)].strip()) * mult)
                except ValueError:
                    return None
        return None

    async def close(self) -> None:
        """Clean up temp config file."""
        if self._config_file is not None:
            try:
                Path(self._config_file.name).unlink(missing_ok=True)
            except Exception:
                pass
            self._config_file = None

    @staticmethod
    def generate_config(provider: str, token_json: str) -> tuple[str, str]:
        """
        Generate rclone config content from OAuth token.

        Args:
            provider: "google_drive" or "onedrive"
            token_json: JSON string of the OAuth token

        Returns:
            Tuple of (remote_name, config_content)
        """
        import secrets

        remote_name = f"{provider}_{secrets.token_hex(4)}"

        if provider == "google_drive":
            config = (
                f"[{remote_name}]\n"
                f"type = drive\n"
                f"scope = drive.readonly\n"
                f"token = {token_json}\n"
            )
        elif provider == "onedrive":
            config = (
                f"[{remote_name}]\n"
                f"type = onedrive\n"
                f"token = {token_json}\n"
                f"drive_type = personal\n"
            )
        else:
            raise ValueError(f"Unsupported rclone provider: {provider}")

        return remote_name, config
