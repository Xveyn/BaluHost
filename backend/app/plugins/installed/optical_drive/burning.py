"""Burning mixin for the Optical Drive Plugin.

Contains methods for burning ISOs, audio CDs, blanking discs, and media info.
"""
import asyncio
import logging
import re
from typing import TYPE_CHECKING, List, Optional

from .models import (
    BlankMediaInfo,
    BlankMode,
    JobStatus,
    JobType,
    OpticalJob,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class BurningMixin:
    """Mixin providing disc burning and blanking operations."""

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
                    assert proc.stdout is not None

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
                    assert proc.stdout is not None

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
                    assert proc.stdout is not None

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
