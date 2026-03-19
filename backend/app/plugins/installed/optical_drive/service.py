"""Business logic for the Optical Drive Plugin.

Provides drive detection, disc reading/ripping, burning, and job management.
Uses Linux tools: wodim, readom, cdparanoia, cd-info, eject.
"""
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

from .browsing import BrowsingMixin
from .burning import BurningMixin
from .models import (
    AudioTrack,
    BlankMediaInfo,
    BlankMode,
    DiscFile,
    DiscFileListResponse,
    DiscFileType,
    DriveInfo,
    FilePreviewResponse,
    JobStatus,
    JobType,
    MediaType,
    OpticalJob,
    OpticalDriveConfig,
)
from .reading import ReadingMixin

logger = logging.getLogger(__name__)


class OpticalDriveService(ReadingMixin, BurningMixin, BrowsingMixin):
    """Service for managing optical drives and disc operations."""

    def __init__(self, config: Optional[OpticalDriveConfig] = None):
        self.config = config or OpticalDriveConfig()
        self._jobs: Dict[str, OpticalJob] = {}
        self._job_tasks: Dict[str, asyncio.Task] = {}
        self._is_dev_mode = getattr(settings, 'is_dev_mode', True)

    # === Utility Methods ===

    async def _run_command(
        self,
        cmd: List[str],
        timeout: int = 3600
    ) -> Tuple[int, str, str]:
        """Execute a command asynchronously with timeout.

        Args:
            cmd: Command and arguments as list
            timeout: Timeout in seconds (default: 1 hour)

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        logger.debug(f"Running command: {' '.join(cmd)}")

        if self._is_dev_mode:
            # In dev mode, simulate command output
            return await self._simulate_command(cmd)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            return proc.returncode or 0, stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')
        except asyncio.TimeoutError:
            proc.kill()  # type: ignore[possibly-undefined]
            raise TimeoutError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        except FileNotFoundError:
            return 127, "", f"Command not found: {cmd[0]}"

    async def _simulate_command(self, cmd: List[str]) -> Tuple[int, str, str]:
        """Simulate command output for dev mode."""
        cmd_name = cmd[0] if cmd else ""

        if cmd_name == "lsblk":
            # Simulate two optical drives
            return 0, (
                "sr0 rom  1:0 0 1024M 0 rom  ASUS_DRW-24B1ST\n"
                "sr1 rom  1:1 0 1024M 0 rom  USB_DVD_Drive\n"
            ), ""

        elif "cd-info" in cmd_name or cmd_name == "cd-info":
            # Simulate audio CD info
            return 0, (
                "CD-ROM Track List (1 - 5)\n"
                "  #: MSF       LSN    Type   Green? Copy? Channels Premphasis?\n"
                "  1: 00:02:00  000150 audio  false  no    2        no\n"
                "  2: 04:32:25  020275 audio  false  no    2        no\n"
                "  3: 08:15:50  037175 audio  false  no    2        no\n"
                "  4: 12:42:33  057183 audio  false  no    2        no\n"
                "  5: 17:08:62  077162 audio  false  no    2        no\n"
                "170: 21:35:00  097125 leadout\n"
                "Media Catalog Number (MCN): 0000000000000\n"
                "TRACK  1 ISRC: USRC10000001\n"
            ), ""

        elif "isoinfo" in cmd_name or cmd_name == "isoinfo":
            if "-d" in cmd:
                # Simulate ISO info
                return 0, (
                    "CD-ROM is in ISO 9660 format\n"
                    "Volume id: BACKUP_2024\n"
                    "Volume size is: 2048000\n"
                    "Logical block size is: 2048\n"
                ), ""
            return 0, "", ""

        elif cmd_name == "dvd+rw-mediainfo":
            # Simulate blank DVD info
            return 0, (
                "INQUIRY:                [HL-DT-ST][DVDRAM GH24NSD1][1.00]\n"
                "INQUIRY alignment:      [256]\n"
                "GET [CURRENT] CONFIGURATION:\n"
                " Mounted Media:         13h, DVD-ROM\n"
                "Free Blocks*2KB:        0\n"
                "Disc status:            complete\n"
            ), ""

        elif cmd_name == "udevadm":
            # Simulate udevadm info for optical drive with audio CD
            return 0, (
                "DEVNAME=/dev/sr0\n"
                "ID_CDROM=1\n"
                "ID_CDROM_CD=1\n"
                "ID_CDROM_CD_R=1\n"
                "ID_CDROM_CD_RW=1\n"
                "ID_CDROM_DVD=1\n"
                "ID_CDROM_DVD_R=1\n"
                "ID_CDROM_MEDIA=1\n"
                "ID_CDROM_MEDIA_CD_R=1\n"
                "ID_CDROM_MEDIA_STATE=complete\n"
                "ID_CDROM_MEDIA_SESSION_COUNT=1\n"
                "ID_CDROM_MEDIA_TRACK_COUNT=5\n"
                "ID_CDROM_MEDIA_TRACK_COUNT_AUDIO=5\n"
                "ID_CDROM_MEDIA_TRACK_COUNT_DATA=0\n"
            ), ""

        elif cmd_name == "eject":
            return 0, "", ""

        elif cmd_name == "wodim":
            # Simulate burning
            return 0, "Burning complete.\n", ""

        elif cmd_name == "cdparanoia":
            # Simulate ripping
            return 0, "", "Ripping complete.\n"

        elif cmd_name == "dd":
            # Simulate ISO copy
            return 0, "", "4194304000 bytes copied\n"

        return 0, "", ""

    def validate_device(self, device: str) -> bool:
        """Validate that device path is a valid optical drive.

        Args:
            device: Device path (e.g., /dev/sr0)

        Returns:
            True if valid optical drive path
        """
        return bool(re.match(r'^/dev/sr[0-9]+$', device))

    def validate_path(self, path: str) -> bool:
        """Validate that path is within allowed storage roots.

        Args:
            path: Path to validate

        Returns:
            True if path is within allowed storage directories
        """
        # Get allowed roots from settings
        allowed_roots = [
            Path(settings.nas_storage_path).resolve(),
            Path(settings.nas_backup_path).resolve(),
        ]

        # Add dev-storage if in dev mode
        if self._is_dev_mode:
            allowed_roots.append(Path("./dev-storage").resolve())

        try:
            resolved = Path(path).resolve()
            return any(
                str(resolved).startswith(str(root))
                for root in allowed_roots
            )
        except (ValueError, OSError):
            return False

    def validate_source_file(self, path: str) -> bool:
        """Validate that a source file exists and is within allowed paths.

        Args:
            path: File path to validate

        Returns:
            True if file exists and is within allowed directories
        """
        if not self.validate_path(path):
            return False
        try:
            return Path(path).exists() and Path(path).is_file()
        except (ValueError, OSError):
            return False

    # === Drive Management ===

    async def list_drives(self) -> List[DriveInfo]:
        """List all optical drives on the system.

        Returns:
            List of DriveInfo objects for each optical drive
        """
        if self._is_dev_mode:
            # Return simulated drives in dev mode
            return [
                DriveInfo(
                    device="/dev/sr0",
                    name="ASUS DRW-24B1ST",
                    vendor="ASUS",
                    model="DRW-24B1ST",
                    can_write=True,
                    is_ready=True,
                    media_type=MediaType.CD_AUDIO,
                    total_tracks=5,
                    tracks=[
                        AudioTrack(number=1, duration_seconds=270, start_sector=150, end_sector=20274),
                        AudioTrack(number=2, duration_seconds=223, start_sector=20275, end_sector=37174),
                        AudioTrack(number=3, duration_seconds=267, start_sector=37175, end_sector=57182),
                        AudioTrack(number=4, duration_seconds=266, start_sector=57183, end_sector=77161),
                        AudioTrack(number=5, duration_seconds=266, start_sector=77162, end_sector=97124),
                    ],
                ),
                DriveInfo(
                    device="/dev/sr1",
                    name="USB DVD Drive",
                    vendor="Generic",
                    model="USB DVD Drive",
                    can_write=True,
                    is_ready=True,
                    media_type=MediaType.DVD_BLANK,
                    is_blank=True,
                    is_rewritable=False,
                    total_size_bytes=4700000000,
                ),
            ]

        drives = []

        # Scan /sys/class/block for optical drives
        block_path = Path("/sys/class/block")
        if not block_path.exists():
            logger.warning("/sys/class/block not found")
            return drives

        for entry in block_path.iterdir():
            if not entry.name.startswith("sr"):
                continue

            device = f"/dev/{entry.name}"
            try:
                drive_info = await self.get_drive_info(device)
                drives.append(drive_info)
            except Exception as e:
                logger.error(f"Error getting info for {device}: {e}")

        return drives

    async def get_drive_info(self, device: str) -> DriveInfo:
        """Get detailed information about an optical drive.

        Args:
            device: Device path (e.g., /dev/sr0)

        Returns:
            DriveInfo with drive and media details

        Raises:
            ValueError: If device path is invalid
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        if self._is_dev_mode:
            drives = await self.list_drives()
            for drive in drives:
                if drive.device == device:
                    return drive
            raise ValueError(f"Drive not found: {device}")

        # Get basic drive info from sysfs
        device_name = device.split("/")[-1]
        vendor = ""
        model = ""

        vendor_path = Path(f"/sys/class/block/{device_name}/device/vendor")
        model_path = Path(f"/sys/class/block/{device_name}/device/model")

        if vendor_path.exists():
            vendor = vendor_path.read_text().strip()
        if model_path.exists():
            model = model_path.read_text().strip()

        name = f"{vendor} {model}".strip() or device_name

        # Check if drive can write (has "cdrw" or "dvdrw" capability)
        can_write = False
        cap_path = Path(f"/sys/class/block/{device_name}/device/media")
        if cap_path.exists():
            media = cap_path.read_text().strip()
            can_write = "rw" in media.lower() or "writer" in media.lower()

        # Try to get media info
        is_ready = False
        media_type = None
        media_label = None
        total_tracks = None
        tracks = []
        total_size_bytes = None
        is_blank = None
        is_rewritable = None

        # Use udevadm for fast, reliable media detection (doesn't hang like cd-info)
        ret, udev_stdout, _ = await self._run_command(
            ["udevadm", "info", "--query=property", device],
            timeout=5
        )
        if ret == 0:
            udev_props = {}
            for line in udev_stdout.split("\n"):
                if "=" in line:
                    key, val = line.split("=", 1)
                    udev_props[key] = val

            # Check if media is present
            if udev_props.get("ID_CDROM_MEDIA") == "1":
                is_ready = True

                # Determine media type from udev properties
                audio_tracks = int(udev_props.get("ID_CDROM_MEDIA_TRACK_COUNT_AUDIO", "0"))
                data_tracks = int(udev_props.get("ID_CDROM_MEDIA_TRACK_COUNT_DATA", "0"))
                total_track_count = int(udev_props.get("ID_CDROM_MEDIA_TRACK_COUNT", "0"))
                media_state = udev_props.get("ID_CDROM_MEDIA_STATE", "")

                # Check for audio CD
                if audio_tracks > 0 and data_tracks == 0:
                    media_type = MediaType.CD_AUDIO
                    total_tracks = audio_tracks
                    # Generate basic track list (udevadm doesn't give duration)
                    tracks = [
                        AudioTrack(number=i, duration_seconds=0, start_sector=0, end_sector=0)
                        for i in range(1, audio_tracks + 1)
                    ]
                elif udev_props.get("ID_CDROM_MEDIA_DVD") == "1":
                    # DVD media
                    if media_state == "blank":
                        media_type = MediaType.DVD_BLANK
                        is_blank = True
                    else:
                        media_type = MediaType.DVD_DATA
                elif udev_props.get("ID_CDROM_MEDIA_BD") == "1":
                    # Blu-ray media
                    if media_state == "blank":
                        media_type = MediaType.BD_BLANK
                        is_blank = True
                    else:
                        media_type = MediaType.BD_DATA
                else:
                    # CD media
                    if media_state == "blank":
                        media_type = MediaType.CD_BLANK
                        is_blank = True
                    elif data_tracks > 0:
                        media_type = MediaType.CD_DATA
                    else:
                        media_type = MediaType.UNKNOWN

                # Check if rewritable
                if udev_props.get("ID_CDROM_MEDIA_CD_RW") == "1":
                    is_rewritable = True
                if udev_props.get("ID_CDROM_MEDIA_DVD_RW") == "1":
                    is_rewritable = True

                # Try to get volume label for data discs
                if media_type in (MediaType.CD_DATA, MediaType.DVD_DATA, MediaType.BD_DATA):
                    media_label = udev_props.get("ID_FS_LABEL", None)
                    # Try isoinfo for more details (short timeout)
                    ret2, iso_stdout, _ = await self._run_command(
                        ["isoinfo", "-d", "-i", device],
                        timeout=10
                    )
                    if ret2 == 0:
                        for line in iso_stdout.split("\n"):
                            if "Volume id:" in line:
                                media_label = line.split(":", 1)[1].strip()
                            elif "Volume size is:" in line:
                                try:
                                    blocks = int(line.split(":", 1)[1].strip())
                                    total_size_bytes = blocks * 2048
                                except ValueError:
                                    pass

        return DriveInfo(
            device=device,
            name=name,
            vendor=vendor,
            model=model,
            can_write=can_write,
            is_ready=is_ready,
            media_type=media_type,
            media_label=media_label,
            total_tracks=total_tracks,
            tracks=tracks,
            total_size_bytes=total_size_bytes,
            is_blank=is_blank,
            is_rewritable=is_rewritable,
        )

    async def _parse_audio_tracks(self, cd_info_output: str) -> List[AudioTrack]:
        """Parse audio track information from cd-info output."""
        tracks = []
        track_pattern = re.compile(
            r'^\s*(\d+):\s*(\d{2}):(\d{2}):(\d{2})\s+(\d+)\s+audio'
        )

        lines = cd_info_output.split("\n")
        for i, line in enumerate(lines):
            match = track_pattern.match(line)
            if match:
                track_num = int(match.group(1))
                start_sector = int(match.group(5))

                # Find end sector from next track or leadout
                end_sector = start_sector
                for next_line in lines[i+1:]:
                    next_match = track_pattern.match(next_line)
                    if next_match:
                        end_sector = int(next_match.group(5)) - 1
                        break
                    elif "leadout" in next_line.lower():
                        # Parse leadout sector
                        leadout_match = re.match(r'^\s*\d+:\s*\d+:\d+:\d+\s+(\d+)\s+leadout', next_line)
                        if leadout_match:
                            end_sector = int(leadout_match.group(1)) - 1
                        break

                # Calculate duration (sectors are at 75 per second for audio CD)
                duration_seconds = (end_sector - start_sector + 1) // 75

                tracks.append(AudioTrack(
                    number=track_num,
                    duration_seconds=duration_seconds,
                    start_sector=start_sector,
                    end_sector=end_sector,
                ))

        return tracks

    async def eject(self, device: str) -> bool:
        """Eject/open the drive tray.

        Args:
            device: Device path

        Returns:
            True if successful
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        ret, _, stderr = await self._run_command(["eject", device], timeout=30)
        if ret != 0:
            logger.error(f"Eject failed: {stderr}")
            return False
        return True

    async def close_tray(self, device: str) -> bool:
        """Close the drive tray.

        Args:
            device: Device path

        Returns:
            True if successful
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        ret, _, stderr = await self._run_command(["eject", "-t", device], timeout=30)
        if ret != 0:
            logger.error(f"Close tray failed: {stderr}")
            return False
        return True

    # === Job Management ===

    def get_jobs(self) -> List[OpticalJob]:
        """Get all active and recent jobs."""
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> Optional[OpticalJob]:
        """Get a specific job by ID."""
        return self._jobs.get(job_id)

    def _create_job(
        self,
        device: str,
        job_type: JobType,
        input_path: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> OpticalJob:
        """Create a new job."""
        job = OpticalJob(
            id=str(uuid.uuid4()),
            device=device,
            job_type=job_type,
            status=JobStatus.PENDING,
            input_path=input_path,
            output_path=output_path,
        )
        self._jobs[job.id] = job
        return job

    def _update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[float] = None,
        error: Optional[str] = None,
        current_track: Optional[int] = None,
        total_tracks: Optional[int] = None,
    ) -> None:
        """Update job status and progress."""
        if job_id not in self._jobs:
            return

        job = self._jobs[job_id]
        if status:
            job.status = status
            if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.completed_at = datetime.now(timezone.utc)
        if progress is not None:
            job.progress_percent = min(100.0, max(0.0, progress))
        if error is not None:
            job.error = error
        if current_track is not None:
            job.current_track = current_track
        if total_tracks is not None:
            job.total_tracks = total_tracks

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancelled, False if not found or not running
        """
        if job_id not in self._jobs:
            return False

        job = self._jobs[job_id]
        if job.status != JobStatus.RUNNING:
            return False

        # Cancel the async task
        if job_id in self._job_tasks:
            self._job_tasks[job_id].cancel()
            del self._job_tasks[job_id]

        self._update_job(job_id, status=JobStatus.CANCELLED)
        return True

    # === Read/Rip, Burn, and Browse operations provided by mixins ===
    # See reading.py, burning.py, browsing.py

    # === Cleanup ===

    async def cleanup(self) -> None:
        """Cancel all running jobs and clean up resources."""
        for job_id, task in list(self._job_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._job_tasks.clear()


# Module-level service instance (for singleton pattern)
_service_instance: Optional[OpticalDriveService] = None


def get_optical_drive_service(config: Optional[OpticalDriveConfig] = None) -> OpticalDriveService:
    """Get the optical drive service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = OpticalDriveService(config)
    return _service_instance
