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
    DriveInfo,
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

        # Check if media is present
        ret, stdout, _ = await self._run_command(["cd-info", "-q", device], timeout=30)
        if ret == 0:
            is_ready = True

            # Check for audio CD
            if "audio" in stdout.lower():
                media_type = MediaType.CD_AUDIO
                tracks = await self._parse_audio_tracks(stdout)
                total_tracks = len(tracks)
            else:
                # Try isoinfo for data disc
                ret2, iso_stdout, _ = await self._run_command(
                    ["isoinfo", "-d", "-i", device],
                    timeout=30
                )
                if ret2 == 0 and "Volume id:" in iso_stdout:
                    media_type = MediaType.CD_DATA
                    # Parse volume label
                    for line in iso_stdout.split("\n"):
                        if "Volume id:" in line:
                            media_label = line.split(":", 1)[1].strip()
                        elif "Volume size is:" in line:
                            try:
                                blocks = int(line.split(":", 1)[1].strip())
                                total_size_bytes = blocks * 2048
                            except ValueError:
                                pass

                    # Check if DVD
                    if "DVD" in iso_stdout or total_size_bytes and total_size_bytes > 700 * 1024 * 1024:
                        media_type = MediaType.DVD_DATA
                else:
                    # Might be blank media
                    ret3, dvd_stdout, _ = await self._run_command(
                        ["dvd+rw-mediainfo", device],
                        timeout=30
                    )
                    if ret3 == 0:
                        if "blank" in dvd_stdout.lower() or "free blocks" in dvd_stdout.lower():
                            is_blank = True
                            if "DVD" in dvd_stdout:
                                media_type = MediaType.DVD_BLANK
                            else:
                                media_type = MediaType.CD_BLANK
                        if "RW" in dvd_stdout or "rewritable" in dvd_stdout.lower():
                            is_rewritable = True

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
