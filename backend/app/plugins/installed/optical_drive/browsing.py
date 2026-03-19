"""Browsing mixin for the Optical Drive Plugin.

Contains methods for listing disc/ISO files, extracting, and previewing.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from .models import (
    DiscFile,
    DiscFileListResponse,
    DiscFileType,
    DriveInfo,
    FilePreviewResponse,
    JobStatus,
    JobType,
    MediaType,
    OpticalJob,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class BrowsingMixin:
    """Mixin providing disc and ISO file browsing, extraction, and preview."""

    async def list_disc_files(self, device: str, path: str = "/") -> DiscFileListResponse:
        """List files and directories on a data disc.

        For audio CDs, returns tracks as virtual WAV files.

        Args:
            device: Device path (e.g., /dev/sr0)
            path: Path within the disc to list (default: root)

        Returns:
            DiscFileListResponse with file listing
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        # Normalize path
        path = "/" + path.strip("/")

        if self._is_dev_mode:
            return await self._simulate_disc_files(device, path)

        # Get drive info to check media type
        drive_info = await self.get_drive_info(device)

        if not drive_info.is_ready:
            raise ValueError("No disc in drive")

        # Handle audio CDs - show tracks as virtual files
        if drive_info.media_type == MediaType.CD_AUDIO:
            return self._get_audio_cd_files(drive_info)

        # For data discs, use isoinfo to list directory
        return await self._list_iso_directory(device, path)

    async def _simulate_disc_files(self, device: str, path: str) -> DiscFileListResponse:
        """Simulate disc file listing for dev mode."""
        # Simulated file structure
        mock_structure = {
            "/": [
                DiscFile(name="Documents", path="/Documents", type=DiscFileType.DIRECTORY, size=0),
                DiscFile(name="Photos", path="/Photos", type=DiscFileType.DIRECTORY, size=0),
                DiscFile(name="backup.zip", path="/backup.zip", type=DiscFileType.FILE, size=157286400),
                DiscFile(name="README.txt", path="/README.txt", type=DiscFileType.FILE, size=1234),
            ],
            "/Documents": [
                DiscFile(name="Manual.pdf", path="/Documents/Manual.pdf", type=DiscFileType.FILE, size=2621440),
                DiscFile(name="Notes.txt", path="/Documents/Notes.txt", type=DiscFileType.FILE, size=4567),
                DiscFile(name="Spreadsheet.xlsx", path="/Documents/Spreadsheet.xlsx", type=DiscFileType.FILE, size=89012),
            ],
            "/Photos": [
                DiscFile(name="vacation.jpg", path="/Photos/vacation.jpg", type=DiscFileType.FILE, size=3250000),
                DiscFile(name="family.png", path="/Photos/family.png", type=DiscFileType.FILE, size=2800000),
                DiscFile(name="landscape.jpg", path="/Photos/landscape.jpg", type=DiscFileType.FILE, size=4100000),
            ],
        }

        # For audio CD simulation (sr0 has audio in dev mode)
        if device == "/dev/sr0":
            # Return tracks as virtual WAV files
            files = [
                DiscFile(
                    name=f"Track {i:02d}.wav",
                    path=f"/Track {i:02d}.wav",
                    type=DiscFileType.FILE,
                    size=duration * 176400  # CD audio: 44100 Hz * 16 bit * 2 channels
                )
                for i, duration in enumerate([270, 223, 267, 266, 266], 1)
            ]
            return DiscFileListResponse(files=files, total=len(files), current_path="/")

        # Data disc (sr1 in dev mode)
        files = mock_structure.get(path, [])
        return DiscFileListResponse(files=files, total=len(files), current_path=path)

    def _get_audio_cd_files(self, drive_info: DriveInfo) -> DiscFileListResponse:
        """Convert audio CD tracks to virtual WAV files."""
        files = []
        for track in drive_info.tracks:
            # CD audio: 44100 Hz * 16 bit stereo = 176400 bytes/second
            estimated_size = track.duration_seconds * 176400
            files.append(DiscFile(
                name=f"Track {track.number:02d}.wav",
                path=f"/Track {track.number:02d}.wav",
                type=DiscFileType.FILE,
                size=estimated_size,
            ))
        return DiscFileListResponse(files=files, total=len(files), current_path="/")

    async def _list_iso_directory(self, device: str, path: str) -> DiscFileListResponse:
        """List directory contents from a data disc using isoinfo."""
        # Use isoinfo with Rock Ridge extensions
        ret, stdout, stderr = await self._run_command(
            ["isoinfo", "-R", "-l", "-i", device],
            timeout=60
        )

        if ret != 0:
            logger.error(f"isoinfo failed: {stderr}")
            raise RuntimeError(f"Failed to read disc: {stderr}")

        files = self._parse_isoinfo_output(stdout, path)
        return DiscFileListResponse(files=files, total=len(files), current_path=path)

    def _parse_isoinfo_output(self, output: str, target_path: str) -> List[DiscFile]:
        """Parse isoinfo -l output into file list."""
        files = []
        current_dir = None

        # Normalize target path
        target_path = "/" + target_path.strip("/")
        if target_path != "/":
            target_path += "/"

        for line in output.split("\n"):
            # Directory header: "Directory listing of /path"
            if line.startswith("Directory listing of "):
                current_dir = line.split("Directory listing of ")[1].strip()
                if not current_dir.endswith("/"):
                    current_dir += "/"
                continue

            # Skip if not in target directory
            if current_dir != target_path and target_path != "/":
                continue
            if target_path == "/" and current_dir and current_dir != "/":
                continue

            # Parse file entry (format varies, but typically has permissions, size, date, name)
            # Example: "-r-xr-xr-x   1    0    0      1234 Jan 15 2024 filename.txt"
            # Example: "dr-xr-xr-x   1    0    0      2048 Jan 15 2024 dirname"
            parts = line.split()
            if len(parts) < 9:
                continue

            perms = parts[0]
            if not perms.startswith("-") and not perms.startswith("d"):
                continue

            try:
                size = int(parts[4])
                name = " ".join(parts[8:])  # Handle names with spaces

                # Skip . and .. entries
                if name in (".", ".."):
                    continue

                is_dir = perms.startswith("d")
                if current_dir is None:
                    continue
                file_path = current_dir.rstrip("/") + "/" + name

                files.append(DiscFile(
                    name=name,
                    path=file_path,
                    type=DiscFileType.DIRECTORY if is_dir else DiscFileType.FILE,
                    size=0 if is_dir else size,
                ))
            except (ValueError, IndexError):
                continue

        return files

    async def extract_files(
        self,
        device: str,
        paths: List[str],
        destination: str
    ) -> OpticalJob:
        """Extract files from a disc to a destination directory.

        For audio CDs, extracts specified tracks as WAV files.

        Args:
            device: Device path
            paths: List of file/directory paths to extract
            destination: Destination directory

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")
        if not self.validate_path(destination):
            raise ValueError(f"Destination not in allowed storage: {destination}")

        # Ensure destination exists
        Path(destination).mkdir(parents=True, exist_ok=True)

        # Get drive info to determine extraction method
        drive_info = await self.get_drive_info(device)

        if not drive_info.is_ready:
            raise ValueError("No disc in drive")

        # Create job
        job = self._create_job(
            device,
            JobType.RIP_TRACK if drive_info.media_type == MediaType.CD_AUDIO else JobType.READ_ISO,
            output_path=destination
        )

        async def _do_extract():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if drive_info.media_type == MediaType.CD_AUDIO:
                    await self._extract_audio_tracks(job.id, device, paths, destination)
                else:
                    await self._extract_data_files(job.id, device, paths, destination)

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                raise
            except Exception as e:
                logger.error(f"Extraction failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_extract())
        self._job_tasks[job.id] = task
        return job

    async def _extract_audio_tracks(
        self,
        job_id: str,
        device: str,
        paths: List[str],
        destination: str
    ) -> None:
        """Extract audio tracks using cdparanoia."""
        # Parse track numbers from paths (e.g., "/Track 01.wav" -> 1)
        track_numbers = []
        for path in paths:
            match = re.search(r'Track\s*(\d+)', path)
            if match:
                track_numbers.append(int(match.group(1)))

        if not track_numbers:
            raise ValueError("No valid track numbers found in paths")

        self._update_job(job_id, total_tracks=len(track_numbers))

        if self._is_dev_mode:
            for i, track_num in enumerate(track_numbers, 1):
                self._update_job(job_id, current_track=i)
                for p in range(101):
                    await asyncio.sleep(0.02)
                    progress = ((i - 1) * 100 + p) / len(track_numbers)
                    self._update_job(job_id, progress=progress)
                # Create dummy file
                output_path = Path(destination) / f"Track {track_num:02d}.wav"
                output_path.write_bytes(b"RIFF" + b"\x00" * 1000)
            return

        for i, track_num in enumerate(track_numbers, 1):
            self._update_job(job_id, current_track=i)
            output_path = Path(destination) / f"Track {track_num:02d}.wav"

            cmd = ["cdparanoia", str(track_num), str(output_path), "-d", device]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            assert proc.stderr is not None

            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode('utf-8', errors='replace')
                sector_match = re.search(r'(\d+)\s+of\s+(\d+)\s+sectors', text)
                if sector_match:
                    current = int(sector_match.group(1))
                    total = int(sector_match.group(2))
                    track_progress = (current / total) * 100
                    overall = ((i - 1) * 100 + track_progress) / len(track_numbers)
                    self._update_job(job_id, progress=overall)

            await proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"cdparanoia failed for track {track_num}")

    async def _extract_data_files(
        self,
        job_id: str,
        device: str,
        paths: List[str],
        destination: str
    ) -> None:
        """Extract data files from disc using 7z."""
        if self._is_dev_mode:
            # Simulate extraction
            for i, path in enumerate(paths):
                progress = ((i + 1) / len(paths)) * 100
                self._update_job(job_id, progress=progress)
                await asyncio.sleep(0.5)
                # Create dummy file
                name = Path(path).name
                output_path = Path(destination) / name
                output_path.write_bytes(b"SIMULATED FILE DATA" * 10)
            return

        # Build 7z command to extract specific files
        cmd = ["7z", "x", device, f"-o{destination}", "-y"]
        for path in paths:
            # 7z uses paths without leading slash
            cmd.append(path.lstrip("/"))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        assert proc.stdout is not None

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode('utf-8', errors='replace')
            # Parse percentage from 7z output
            match = re.search(r'(\d+)%', text)
            if match:
                self._update_job(job_id, progress=float(match.group(1)))

        await proc.wait()
        if proc.returncode != 0:
            _, stderr = await proc.communicate()
            raise RuntimeError(f"7z extraction failed: {stderr.decode()}")

    async def preview_file(
        self,
        device: str,
        path: str,
        max_size: int = 65536
    ) -> FilePreviewResponse:
        """Get a preview of a file on the disc.

        Args:
            device: Device path
            path: File path on the disc
            max_size: Maximum bytes to read (default: 64KB)

        Returns:
            FilePreviewResponse with content
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        # Normalize path
        path = "/" + path.strip("/")
        name = Path(path).name.lower()

        # Determine content type
        text_extensions = {'.txt', '.md', '.json', '.xml', '.log', '.csv', '.html', '.css', '.js', '.py'}
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

        ext = Path(name).suffix.lower()

        if ext in text_extensions:
            content_type = "text/plain"
        elif ext in image_extensions:
            content_type = f"image/{ext.lstrip('.')}"
            if ext in ('.jpg', '.jpeg'):
                content_type = "image/jpeg"
        else:
            raise ValueError(f"Preview not supported for file type: {ext}")

        if self._is_dev_mode:
            return self._simulate_file_preview(path, content_type, max_size)

        # Use isoinfo to extract file content
        ret, stdout, stderr = await self._run_command(
            ["isoinfo", "-R", "-x", path, "-i", device],
            timeout=30
        )

        if ret != 0:
            raise RuntimeError(f"Failed to read file: {stderr}")

        # Get raw bytes
        content_bytes = stdout.encode('latin-1')  # isoinfo outputs raw bytes
        is_truncated = len(content_bytes) > max_size
        content_bytes = content_bytes[:max_size]

        if content_type.startswith("text/"):
            # Return as plain text
            try:
                content = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                content = content_bytes.decode('latin-1')
        else:
            # Return as base64 for binary files
            import base64
            content = base64.b64encode(content_bytes).decode('ascii')

        return FilePreviewResponse(
            path=path,
            content_type=content_type,
            content=content,
            size=len(content_bytes),
            is_truncated=is_truncated
        )

    def _simulate_file_preview(
        self,
        path: str,
        content_type: str,
        max_size: int
    ) -> FilePreviewResponse:
        """Simulate file preview for dev mode."""
        name = Path(path).name

        if content_type.startswith("text/"):
            if "README" in name or ".txt" in name:
                content = f"""# Sample README

This is a simulated text file from the disc.

Path: {path}

## Contents

Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

- Item 1
- Item 2
- Item 3

Created for development testing purposes.
"""
            elif ".json" in name:
                content = '{\n  "name": "sample",\n  "version": "1.0.0",\n  "simulated": true\n}'
            else:
                content = f"Simulated content for {name}\n" * 10

            return FilePreviewResponse(
                path=path,
                content_type=content_type,
                content=content,
                size=len(content),
                is_truncated=False
            )
        else:
            # For images, return a tiny placeholder (1x1 PNG)
            import base64
            # 1x1 transparent PNG
            png_data = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            )
            return FilePreviewResponse(
                path=path,
                content_type=content_type,
                content=base64.b64encode(png_data).decode('ascii'),
                size=len(png_data),
                is_truncated=False
            )

    # === ISO File Methods ===

    async def list_iso_files(self, iso_path: str, path: str = "/") -> DiscFileListResponse:
        """List files within an ISO file.

        Args:
            iso_path: Path to the ISO file on the filesystem
            path: Path within the ISO to browse

        Returns:
            DiscFileListResponse with file listing
        """
        if not self.validate_source_file(iso_path):
            raise ValueError(f"ISO file not found or not in allowed storage: {iso_path}")

        # Normalize path
        path = "/" + path.strip("/")

        if self._is_dev_mode:
            return self._simulate_iso_files(iso_path, path)

        # Use 7z to list ISO contents
        ret, stdout, stderr = await self._run_command(
            ["7z", "l", iso_path],
            timeout=60
        )

        if ret != 0:
            raise RuntimeError(f"Failed to read ISO: {stderr}")

        files = self._parse_7z_list_output(stdout, path)
        return DiscFileListResponse(files=files, total=len(files), current_path=path)

    def _simulate_iso_files(self, iso_path: str, path: str) -> DiscFileListResponse:
        """Simulate ISO file listing for dev mode."""
        mock_files = {
            "/": [
                DiscFile(name="software", path="/software", type=DiscFileType.DIRECTORY, size=0),
                DiscFile(name="docs", path="/docs", type=DiscFileType.DIRECTORY, size=0),
                DiscFile(name="setup.exe", path="/setup.exe", type=DiscFileType.FILE, size=52428800),
                DiscFile(name="autorun.inf", path="/autorun.inf", type=DiscFileType.FILE, size=123),
            ],
            "/software": [
                DiscFile(name="installer.msi", path="/software/installer.msi", type=DiscFileType.FILE, size=104857600),
                DiscFile(name="readme.txt", path="/software/readme.txt", type=DiscFileType.FILE, size=2048),
            ],
            "/docs": [
                DiscFile(name="manual.pdf", path="/docs/manual.pdf", type=DiscFileType.FILE, size=5242880),
                DiscFile(name="license.txt", path="/docs/license.txt", type=DiscFileType.FILE, size=4096),
            ],
        }
        files = mock_files.get(path, [])
        return DiscFileListResponse(files=files, total=len(files), current_path=path)

    def _parse_7z_list_output(self, output: str, target_path: str) -> List[DiscFile]:
        """Parse 7z list output into file list."""
        files = []
        in_file_list = False

        # Normalize target path for comparison
        target_path = target_path.strip("/")
        if target_path:
            target_path += "/"

        for line in output.split("\n"):
            # 7z output has a header, then file list, then footer
            if "----" in line:
                in_file_list = not in_file_list
                continue

            if not in_file_list:
                continue

            # Parse line: "2024-01-15 10:30:00 D....      0      0  dirname"
            # or:         "2024-01-15 10:30:00 .....  12345  12300  filename"
            parts = line.split()
            if len(parts) < 6:
                continue

            try:
                attrs = parts[2]
                size = int(parts[3])
                name = " ".join(parts[5:])

                # Skip empty names
                if not name:
                    continue

                # Normalize name (remove leading slash if present)
                name = name.lstrip("/")

                # Check if file is in target directory
                if target_path:
                    if not name.startswith(target_path):
                        continue
                    # Get relative name
                    relative = name[len(target_path):]
                    # Skip if it's in a subdirectory
                    if "/" in relative:
                        continue
                    name = relative
                else:
                    # Root level - skip items in subdirectories
                    if "/" in name:
                        continue

                if not name:
                    continue

                is_dir = "D" in attrs
                file_path = "/" + (target_path + name).strip("/")

                files.append(DiscFile(
                    name=name,
                    path=file_path,
                    type=DiscFileType.DIRECTORY if is_dir else DiscFileType.FILE,
                    size=0 if is_dir else size,
                ))

            except (ValueError, IndexError):
                continue

        return files

    async def extract_from_iso(
        self,
        iso_path: str,
        paths: List[str],
        destination: str
    ) -> OpticalJob:
        """Extract files from an ISO file.

        Args:
            iso_path: Path to the ISO file
            paths: Files/directories to extract
            destination: Destination directory

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_source_file(iso_path):
            raise ValueError(f"ISO file not found or not in allowed storage: {iso_path}")
        if not self.validate_path(destination):
            raise ValueError(f"Destination not in allowed storage: {destination}")

        Path(destination).mkdir(parents=True, exist_ok=True)

        job = self._create_job(
            iso_path,  # Use ISO path as "device"
            JobType.READ_ISO,
            input_path=iso_path,
            output_path=destination
        )

        async def _do_extract():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if self._is_dev_mode:
                    for i, path in enumerate(paths):
                        progress = ((i + 1) / len(paths)) * 100
                        self._update_job(job.id, progress=progress)
                        await asyncio.sleep(0.3)
                        # Create dummy file
                        name = Path(path).name
                        output_path = Path(destination) / name
                        output_path.write_bytes(b"SIMULATED ISO EXTRACT" * 10)
                else:
                    # Use 7z to extract
                    cmd = ["7z", "x", iso_path, f"-o{destination}", "-y"]
                    for path in paths:
                        cmd.append(path.lstrip("/"))

                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    assert proc.stdout is not None

                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')
                        match = re.search(r'(\d+)%', text)
                        if match:
                            self._update_job(job.id, progress=float(match.group(1)))

                    await proc.wait()
                    if proc.returncode != 0:
                        _, stderr = await proc.communicate()
                        raise RuntimeError(f"Extraction failed: {stderr.decode()}")

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                raise
            except Exception as e:
                logger.error(f"ISO extraction failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_extract())
        self._job_tasks[job.id] = task
        return job

    async def preview_iso_file(
        self,
        iso_path: str,
        file_path: str,
        max_size: int = 65536
    ) -> FilePreviewResponse:
        """Preview a file from within an ISO.

        Args:
            iso_path: Path to the ISO file
            file_path: Path to the file within the ISO
            max_size: Maximum bytes to read

        Returns:
            FilePreviewResponse with content
        """
        if not self.validate_source_file(iso_path):
            raise ValueError(f"ISO file not found or not in allowed storage: {iso_path}")

        file_path = "/" + file_path.strip("/")
        name = Path(file_path).name.lower()

        # Determine content type
        text_extensions = {'.txt', '.md', '.json', '.xml', '.log', '.csv', '.html', '.css', '.js', '.py'}
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

        ext = Path(name).suffix.lower()

        if ext in text_extensions:
            content_type = "text/plain"
        elif ext in image_extensions:
            content_type = f"image/{ext.lstrip('.')}"
            if ext in ('.jpg', '.jpeg'):
                content_type = "image/jpeg"
        else:
            raise ValueError(f"Preview not supported for file type: {ext}")

        if self._is_dev_mode:
            return self._simulate_file_preview(file_path, content_type, max_size)

        # Use 7z to extract to stdout
        ret, stdout, stderr = await self._run_command(
            ["7z", "e", iso_path, "-so", file_path.lstrip("/")],
            timeout=30
        )

        if ret != 0:
            raise RuntimeError(f"Failed to read file from ISO: {stderr}")

        content_bytes = stdout.encode('latin-1')
        is_truncated = len(content_bytes) > max_size
        content_bytes = content_bytes[:max_size]

        if content_type.startswith("text/"):
            try:
                content = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                content = content_bytes.decode('latin-1')
        else:
            import base64
            content = base64.b64encode(content_bytes).decode('ascii')

        return FilePreviewResponse(
            path=file_path,
            content_type=content_type,
            content=content,
            size=len(content_bytes),
            is_truncated=is_truncated
        )
