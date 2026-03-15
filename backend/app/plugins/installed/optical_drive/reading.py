"""Reading/ripping mixin for the Optical Drive Plugin.

Contains methods for reading ISO images and ripping audio CDs.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .models import JobStatus, JobType, OpticalJob

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ReadingMixin:
    """Mixin providing disc reading and audio ripping operations."""

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
