"""Business logic for the Optical Drive Plugin.

Provides drive detection, disc reading/ripping, burning, and job management.
Uses Linux tools: wodim, readom, cdparanoia, cd-info, eject.
"""
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

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

logger = logging.getLogger(__name__)


class OpticalDriveService:
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
            proc.kill()
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
                        AudioTrack(number=i, duration_seconds=0, title=f"Track {i}", start_sector=0, end_sector=0)
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
                job.completed_at = datetime.utcnow()
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

    # === Read/Rip Operations ===

    async def read_iso(self, device: str, output_path: str) -> OpticalJob:
        """Copy a data disc to an ISO file.

        Args:
            device: Device path
            output_path: Destination ISO file path

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")
        if not self.validate_path(output_path):
            raise ValueError(f"Output path not in allowed storage: {output_path}")

        # Ensure parent directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        job = self._create_job(device, JobType.READ_ISO, output_path=output_path)

        async def _do_read_iso():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if self._is_dev_mode:
                    # Simulate progress in dev mode
                    for i in range(101):
                        await asyncio.sleep(0.05)
                        self._update_job(job.id, progress=float(i))
                    # Create a small dummy file
                    Path(output_path).write_bytes(b"SIMULATED ISO DATA" * 100)
                else:
                    # Use dd to copy the disc
                    # Note: For production, consider using readom for better error handling
                    cmd = ["dd", f"if={device}", f"of={output_path}", "bs=2048", "status=progress"]
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    # Parse progress from stderr
                    while True:
                        line = await proc.stderr.readline()
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')
                        # Parse: "123456789 bytes (...) copied"
                        match = re.search(r'(\d+)\s+bytes', text)
                        if match:
                            # Can't easily get total size from dd, estimate
                            bytes_copied = int(match.group(1))
                            # Assume ~700MB CD as rough progress
                            progress = min(99.0, (bytes_copied / (700 * 1024 * 1024)) * 100)
                            self._update_job(job.id, progress=progress)

                    await proc.wait()
                    if proc.returncode != 0:
                        raise RuntimeError(f"dd failed with code {proc.returncode}")

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

                if self.config.auto_eject_after_operation:
                    await self.eject(device)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                # Clean up partial file
                try:
                    Path(output_path).unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            except Exception as e:
                logger.error(f"ISO read failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_read_iso())
        self._job_tasks[job.id] = task
        return job

    async def rip_audio_cd(self, device: str, output_dir: str) -> OpticalJob:
        """Rip all tracks from an audio CD to WAV files.

        Args:
            device: Device path
            output_dir: Destination directory for WAV files

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")
        if not self.validate_path(output_dir):
            raise ValueError(f"Output path not in allowed storage: {output_dir}")

        # Ensure output directory exists
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        job = self._create_job(device, JobType.RIP_AUDIO, output_path=output_dir)

        async def _do_rip():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if self._is_dev_mode:
                    # Simulate ripping 5 tracks
                    for i in range(1, 6):
                        self._update_job(job.id, current_track=i, total_tracks=5)
                        for p in range(101):
                            await asyncio.sleep(0.02)
                            progress = ((i - 1) * 100 + p) / 5
                            self._update_job(job.id, progress=progress)
                        # Create dummy WAV file
                        wav_path = Path(output_dir) / f"track{i:02d}.wav"
                        wav_path.write_bytes(b"RIFF" + b"\x00" * 1000)
                else:
                    # Use cdparanoia to rip all tracks
                    # -B creates individual track files: track01.cdda.wav, etc.
                    cmd = ["cdparanoia", "-B", "-d", device, "--"]
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        cwd=output_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    # Parse progress from cdparanoia stderr
                    current_track = 0
                    total_tracks = 0
                    while True:
                        line = await proc.stderr.readline()
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')

                        # Parse track info: "Ripping from sector ... (track 1 of 5)"
                        track_match = re.search(r'track\s+(\d+)\s+of\s+(\d+)', text, re.I)
                        if track_match:
                            current_track = int(track_match.group(1))
                            total_tracks = int(track_match.group(2))
                            self._update_job(
                                job.id,
                                current_track=current_track,
                                total_tracks=total_tracks
                            )

                        # Parse sector progress
                        sector_match = re.search(r'(\d+)\s+of\s+(\d+)\s+sectors', text)
                        if sector_match and total_tracks > 0:
                            current_sector = int(sector_match.group(1))
                            total_sectors = int(sector_match.group(2))
                            track_progress = (current_sector / total_sectors) * 100
                            overall = ((current_track - 1) * 100 + track_progress) / total_tracks
                            self._update_job(job.id, progress=overall)

                    await proc.wait()
                    if proc.returncode != 0:
                        raise RuntimeError(f"cdparanoia failed with code {proc.returncode}")

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

                if self.config.auto_eject_after_operation:
                    await self.eject(device)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                raise
            except Exception as e:
                logger.error(f"Audio rip failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_rip())
        self._job_tasks[job.id] = task
        return job

    async def rip_audio_track(
        self,
        device: str,
        track_number: int,
        output_path: str
    ) -> OpticalJob:
        """Rip a single audio track to a WAV file.

        Args:
            device: Device path
            track_number: Track number to rip (1-indexed)
            output_path: Destination WAV file path

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")
        if not self.validate_path(output_path):
            raise ValueError(f"Output path not in allowed storage: {output_path}")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        job = self._create_job(device, JobType.RIP_TRACK, output_path=output_path)
        job.current_track = track_number
        job.total_tracks = 1

        async def _do_rip_track():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if self._is_dev_mode:
                    for p in range(101):
                        await asyncio.sleep(0.02)
                        self._update_job(job.id, progress=float(p))
                    Path(output_path).write_bytes(b"RIFF" + b"\x00" * 1000)
                else:
                    cmd = ["cdparanoia", str(track_number), output_path, "-d", device]
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    while True:
                        line = await proc.stderr.readline()
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')
                        sector_match = re.search(r'(\d+)\s+of\s+(\d+)\s+sectors', text)
                        if sector_match:
                            current = int(sector_match.group(1))
                            total = int(sector_match.group(2))
                            self._update_job(job.id, progress=(current / total) * 100)

                    await proc.wait()
                    if proc.returncode != 0:
                        raise RuntimeError(f"cdparanoia failed with code {proc.returncode}")

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

                if self.config.auto_eject_after_operation:
                    await self.eject(device)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                try:
                    Path(output_path).unlink(missing_ok=True)
                except OSError:
                    pass
                raise
            except Exception as e:
                logger.error(f"Track rip failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_rip_track())
        self._job_tasks[job.id] = task
        return job

    # === Burn Operations ===

    async def burn_iso(self, device: str, iso_path: str, speed: int = 0) -> OpticalJob:
        """Burn an ISO image to disc.

        Args:
            device: Device path
            iso_path: Source ISO file path
            speed: Burn speed (0 = auto)

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")
        if not self.validate_source_file(iso_path):
            raise ValueError(f"Source ISO not found or not in allowed storage: {iso_path}")

        job = self._create_job(device, JobType.BURN_ISO, input_path=iso_path)

        async def _do_burn():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if self._is_dev_mode:
                    for p in range(101):
                        await asyncio.sleep(0.05)
                        self._update_job(job.id, progress=float(p))
                else:
                    cmd = ["wodim", "-v", f"dev={device}"]
                    if speed > 0:
                        cmd.append(f"speed={speed}")
                    cmd.append(iso_path)

                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')
                        # Parse progress: "Track 01:  45 of 128 MB written (fifo 100%)"
                        match = re.search(r'(\d+)\s+of\s+(\d+)\s+MB\s+written', text)
                        if match:
                            current = int(match.group(1))
                            total = int(match.group(2))
                            self._update_job(job.id, progress=(current / total) * 100)

                    await proc.wait()
                    if proc.returncode != 0:
                        _, stderr = await proc.communicate()
                        raise RuntimeError(f"wodim failed: {stderr.decode()}")

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

                if self.config.auto_eject_after_operation:
                    await self.eject(device)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                raise
            except Exception as e:
                logger.error(f"ISO burn failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_burn())
        self._job_tasks[job.id] = task
        return job

    async def burn_audio_cd(
        self,
        device: str,
        wav_files: List[str],
        speed: int = 0
    ) -> OpticalJob:
        """Burn WAV files as an audio CD.

        Args:
            device: Device path
            wav_files: List of WAV file paths
            speed: Burn speed (0 = auto)

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        for wav_file in wav_files:
            if not self.validate_source_file(wav_file):
                raise ValueError(f"WAV file not found or not in allowed storage: {wav_file}")

        job = self._create_job(device, JobType.BURN_AUDIO, input_path=",".join(wav_files))
        job.total_tracks = len(wav_files)

        async def _do_burn_audio():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if self._is_dev_mode:
                    for i, _ in enumerate(wav_files, 1):
                        self._update_job(job.id, current_track=i)
                        for p in range(101):
                            await asyncio.sleep(0.02)
                            progress = ((i - 1) * 100 + p) / len(wav_files)
                            self._update_job(job.id, progress=progress)
                else:
                    cmd = ["wodim", "-v", f"dev={device}", "-audio", "-pad"]
                    if speed > 0:
                        cmd.append(f"speed={speed}")
                    cmd.extend(wav_files)

                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    current_track = 0
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')

                        # Track change: "Track 01:"
                        track_match = re.search(r'Track\s+(\d+):', text)
                        if track_match:
                            current_track = int(track_match.group(1))
                            self._update_job(job.id, current_track=current_track)

                        # Progress within track
                        progress_match = re.search(r'(\d+)\s+of\s+(\d+)\s+MB\s+written', text)
                        if progress_match and len(wav_files) > 0:
                            current_mb = int(progress_match.group(1))
                            total_mb = int(progress_match.group(2))
                            track_progress = (current_mb / total_mb) * 100
                            overall = ((current_track - 1) * 100 + track_progress) / len(wav_files)
                            self._update_job(job.id, progress=overall)

                    await proc.wait()
                    if proc.returncode != 0:
                        _, stderr = await proc.communicate()
                        raise RuntimeError(f"wodim failed: {stderr.decode()}")

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

                if self.config.auto_eject_after_operation:
                    await self.eject(device)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                raise
            except Exception as e:
                logger.error(f"Audio burn failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_burn_audio())
        self._job_tasks[job.id] = task
        return job

    async def blank_disc(self, device: str, mode: BlankMode = BlankMode.FAST) -> OpticalJob:
        """Blank a rewritable disc.

        Args:
            device: Device path
            mode: Blanking mode (fast or all)

        Returns:
            OpticalJob for tracking progress
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        job = self._create_job(device, JobType.BLANK)

        async def _do_blank():
            try:
                self._update_job(job.id, status=JobStatus.RUNNING)

                if self._is_dev_mode:
                    for p in range(101):
                        await asyncio.sleep(0.03)
                        self._update_job(job.id, progress=float(p))
                else:
                    cmd = ["wodim", "-v", f"dev={device}", f"blank={mode.value}"]

                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode('utf-8', errors='replace')
                        # Blanking progress varies, just update periodically
                        if "blanking" in text.lower():
                            # Estimate progress based on time or log messages
                            pass

                    await proc.wait()
                    if proc.returncode != 0:
                        _, stderr = await proc.communicate()
                        raise RuntimeError(f"wodim blank failed: {stderr.decode()}")

                self._update_job(job.id, status=JobStatus.COMPLETED, progress=100.0)

                if self.config.auto_eject_after_operation:
                    await self.eject(device)

            except asyncio.CancelledError:
                self._update_job(job.id, status=JobStatus.CANCELLED)
                raise
            except Exception as e:
                logger.error(f"Blank failed: {e}")
                self._update_job(job.id, status=JobStatus.FAILED, error=str(e))

        task = asyncio.create_task(_do_blank())
        self._job_tasks[job.id] = task
        return job

    # === Media Info ===

    async def get_blank_media_info(self, device: str) -> Optional[BlankMediaInfo]:
        """Get information about blank writable media.

        Args:
            device: Device path

        Returns:
            BlankMediaInfo or None if no blank media
        """
        if not self.validate_device(device):
            raise ValueError(f"Invalid device path: {device}")

        if self._is_dev_mode:
            return BlankMediaInfo(
                media_type="DVD-R",
                capacity_bytes=4700000000,
                capacity_mb=4700.0,
                is_rewritable=False,
                is_blank=True,
                write_speeds=[4, 8, 16],
            )

        ret, stdout, _ = await self._run_command(
            ["dvd+rw-mediainfo", device],
            timeout=30
        )

        if ret != 0:
            return None

        # Parse media info
        media_type = "Unknown"
        capacity_bytes = 0
        is_rewritable = False
        is_blank = False
        write_speeds = []

        for line in stdout.split("\n"):
            line = line.strip()

            if "Mounted Media:" in line:
                # Extract media type
                parts = line.split(",")
                if len(parts) > 1:
                    media_type = parts[1].strip()

            elif "Free Blocks" in line:
                match = re.search(r'Free Blocks\*2KB:\s*(\d+)', line)
                if match:
                    free_blocks = int(match.group(1))
                    if free_blocks > 0:
                        capacity_bytes = free_blocks * 2048
                        is_blank = True

            elif "RW" in line or "rewritable" in line.lower():
                is_rewritable = True

            elif "Write Speed" in line:
                # Parse available speeds
                speed_match = re.findall(r'(\d+)x', line)
                write_speeds = [int(s) for s in speed_match]

        if capacity_bytes == 0:
            return None

        return BlankMediaInfo(
            media_type=media_type,
            capacity_bytes=capacity_bytes,
            capacity_mb=capacity_bytes / (1024 * 1024),
            is_rewritable=is_rewritable,
            is_blank=is_blank,
            write_speeds=write_speeds or [4, 8, 16],
        )

    # === File Explorer Methods ===

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
