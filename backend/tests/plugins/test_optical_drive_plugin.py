"""Unit tests for the Optical Drive Plugin.

Tests drive detection, path validation, job management, and service methods.
"""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from app.plugins.installed.optical_drive.models import (
    AudioTrack,
    BlankMediaInfo,
    BlankMode,
    DriveInfo,
    JobStatus,
    JobType,
    MediaType,
    OpticalDriveConfig,
    OpticalJob,
)
from app.plugins.installed.optical_drive.service import OpticalDriveService


@pytest.fixture
def service():
    """Create a service instance for testing."""
    config = OpticalDriveConfig()
    svc = OpticalDriveService(config)
    svc._is_dev_mode = True
    return svc


@pytest.fixture
def prod_service():
    """Create a service instance with dev mode disabled."""
    config = OpticalDriveConfig()
    svc = OpticalDriveService(config)
    svc._is_dev_mode = False
    return svc


class TestDeviceValidation:
    """Tests for device path validation."""

    def test_valid_device_sr0(self, service):
        assert service.validate_device("/dev/sr0") is True

    def test_valid_device_sr1(self, service):
        assert service.validate_device("/dev/sr1") is True

    def test_valid_device_sr9(self, service):
        assert service.validate_device("/dev/sr9") is True

    def test_invalid_device_sda(self, service):
        """Should reject block devices."""
        assert service.validate_device("/dev/sda") is False

    def test_invalid_device_path_traversal(self, service):
        """Should reject path traversal attempts."""
        assert service.validate_device("/dev/../etc/passwd") is False

    def test_invalid_device_random_path(self, service):
        assert service.validate_device("/tmp/sr0") is False

    def test_invalid_device_empty(self, service):
        assert service.validate_device("") is False

    def test_invalid_device_cdrom_symlink(self, service):
        """Should only accept sr* format, not symlinks."""
        assert service.validate_device("/dev/cdrom") is False


class TestPathValidation:
    """Tests for output path validation."""

    def test_valid_path_dev_storage(self, service):
        """Should accept paths in dev-storage."""
        with patch.object(Path, 'resolve') as mock_resolve:
            mock_resolve.return_value = Path("/home/user/projects/BaluHost/backend/dev-storage/output")
            # In dev mode, dev-storage is allowed
            assert service.validate_path("./dev-storage/output") is True

    def test_invalid_path_outside_storage(self, service):
        """Should reject paths outside allowed directories."""
        assert service.validate_path("/etc/passwd") is False
        assert service.validate_path("/tmp/malicious") is False
        assert service.validate_path("/home/user/desktop") is False

    def test_invalid_path_root(self, service):
        assert service.validate_path("/") is False

    def test_path_traversal_attack(self, service):
        """Should prevent path traversal attacks."""
        assert service.validate_path("./storage/../../../etc/passwd") is False


class TestDriveManagement:
    """Tests for drive listing and info."""

    @pytest.mark.asyncio
    async def test_list_drives_dev_mode(self, service):
        """Should return simulated drives in dev mode."""
        drives = await service.list_drives()
        assert len(drives) == 2
        assert drives[0].device == "/dev/sr0"
        assert drives[1].device == "/dev/sr1"
        assert drives[0].can_write is True
        assert drives[0].media_type == MediaType.CD_AUDIO

    @pytest.mark.asyncio
    async def test_get_drive_info_dev_mode(self, service):
        """Should return drive info in dev mode."""
        info = await service.get_drive_info("/dev/sr0")
        assert info.device == "/dev/sr0"
        assert info.name == "ASUS DRW-24B1ST"
        assert info.is_ready is True
        assert info.total_tracks == 5

    @pytest.mark.asyncio
    async def test_get_drive_info_invalid_device(self, service):
        """Should raise ValueError for invalid device."""
        with pytest.raises(ValueError, match="Invalid device path"):
            await service.get_drive_info("/dev/sda")

    @pytest.mark.asyncio
    async def test_get_drive_info_not_found(self, service):
        """Should raise ValueError for non-existent drive."""
        with pytest.raises(ValueError, match="Drive not found"):
            await service.get_drive_info("/dev/sr9")

    @pytest.mark.asyncio
    async def test_eject_dev_mode(self, service):
        """Should simulate eject in dev mode."""
        result = await service.eject("/dev/sr0")
        assert result is True

    @pytest.mark.asyncio
    async def test_eject_invalid_device(self, service):
        """Should raise ValueError for invalid device."""
        with pytest.raises(ValueError, match="Invalid device path"):
            await service.eject("/dev/sda")

    @pytest.mark.asyncio
    async def test_close_tray_dev_mode(self, service):
        """Should simulate close tray in dev mode."""
        result = await service.close_tray("/dev/sr0")
        assert result is True


class TestJobManagement:
    """Tests for job creation and management."""

    @pytest.mark.asyncio
    async def test_create_job(self, service):
        """Should create a new job with correct attributes."""
        job = service._create_job("/dev/sr0", JobType.READ_ISO, output_path="/storage/test.iso")
        assert job.id is not None
        assert job.device == "/dev/sr0"
        assert job.job_type == JobType.READ_ISO
        assert job.status == JobStatus.PENDING
        assert job.output_path == "/storage/test.iso"

    def test_get_jobs_empty(self, service):
        """Should return empty list when no jobs."""
        jobs = service.get_jobs()
        assert jobs == []

    def test_get_job_not_found(self, service):
        """Should return None for non-existent job."""
        job = service.get_job("non-existent-id")
        assert job is None

    @pytest.mark.asyncio
    async def test_update_job_progress(self, service):
        """Should update job progress."""
        job = service._create_job("/dev/sr0", JobType.READ_ISO)
        service._update_job(job.id, progress=50.0)
        updated = service.get_job(job.id)
        assert updated.progress_percent == 50.0

    @pytest.mark.asyncio
    async def test_update_job_status(self, service):
        """Should update job status."""
        job = service._create_job("/dev/sr0", JobType.READ_ISO)
        service._update_job(job.id, status=JobStatus.RUNNING)
        updated = service.get_job(job.id)
        assert updated.status == JobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_update_job_completion_sets_timestamp(self, service):
        """Should set completed_at when status is completed."""
        job = service._create_job("/dev/sr0", JobType.READ_ISO)
        service._update_job(job.id, status=JobStatus.COMPLETED)
        updated = service.get_job(job.id)
        assert updated.completed_at is not None


class TestReadOperations:
    """Tests for reading/ripping operations."""

    @pytest.mark.asyncio
    async def test_read_iso_creates_job(self, service, tmp_path):
        """Should create a job for ISO reading."""
        output_path = str(tmp_path / "test.iso")
        # Patch validate_path to allow tmp_path
        with patch.object(service, 'validate_path', return_value=True):
            job = await service.read_iso("/dev/sr0", output_path)
        assert job.job_type == JobType.READ_ISO
        assert job.output_path == output_path

    @pytest.mark.asyncio
    async def test_read_iso_invalid_device(self, service, tmp_path):
        """Should raise for invalid device."""
        with pytest.raises(ValueError, match="Invalid device path"):
            await service.read_iso("/dev/sda", str(tmp_path / "test.iso"))

    @pytest.mark.asyncio
    async def test_rip_audio_creates_job(self, service, tmp_path):
        """Should create a job for audio ripping."""
        output_dir = str(tmp_path / "audio")
        with patch.object(service, 'validate_path', return_value=True):
            job = await service.rip_audio_cd("/dev/sr0", output_dir)
        assert job.job_type == JobType.RIP_AUDIO
        assert job.output_path == output_dir

    @pytest.mark.asyncio
    async def test_rip_track_creates_job(self, service, tmp_path):
        """Should create a job for single track ripping."""
        output_path = str(tmp_path / "track01.wav")
        with patch.object(service, 'validate_path', return_value=True):
            job = await service.rip_audio_track("/dev/sr0", 1, output_path)
        assert job.job_type == JobType.RIP_TRACK
        assert job.current_track == 1


class TestBurnOperations:
    """Tests for burning operations."""

    @pytest.mark.asyncio
    async def test_burn_iso_creates_job(self, service, tmp_path):
        """Should create a job for ISO burning."""
        iso_path = tmp_path / "test.iso"
        iso_path.write_bytes(b"ISO DATA")
        with patch.object(service, 'validate_source_file', return_value=True):
            job = await service.burn_iso("/dev/sr0", str(iso_path), speed=8)
        assert job.job_type == JobType.BURN_ISO
        assert job.input_path == str(iso_path)

    @pytest.mark.asyncio
    async def test_burn_iso_file_not_found(self, service):
        """Should raise for non-existent ISO."""
        with pytest.raises(ValueError, match="not found"):
            await service.burn_iso("/dev/sr0", "/nonexistent.iso")

    @pytest.mark.asyncio
    async def test_burn_audio_creates_job(self, service, tmp_path):
        """Should create a job for audio burning."""
        wav1 = tmp_path / "track1.wav"
        wav2 = tmp_path / "track2.wav"
        wav1.write_bytes(b"RIFF WAV DATA")
        wav2.write_bytes(b"RIFF WAV DATA")
        with patch.object(service, 'validate_source_file', return_value=True):
            job = await service.burn_audio_cd("/dev/sr0", [str(wav1), str(wav2)], speed=4)
        assert job.job_type == JobType.BURN_AUDIO
        assert job.total_tracks == 2

    @pytest.mark.asyncio
    async def test_blank_disc_creates_job(self, service):
        """Should create a job for blanking."""
        job = await service.blank_disc("/dev/sr0", BlankMode.FAST)
        assert job.job_type == JobType.BLANK


class TestBlankMediaInfo:
    """Tests for blank media information."""

    @pytest.mark.asyncio
    async def test_get_blank_media_info_dev_mode(self, service):
        """Should return simulated blank media info."""
        info = await service.get_blank_media_info("/dev/sr0")
        assert info is not None
        assert info.media_type == "DVD-R"
        assert info.capacity_bytes == 4700000000
        assert info.is_blank is True

    @pytest.mark.asyncio
    async def test_get_blank_media_info_invalid_device(self, service):
        """Should raise for invalid device."""
        with pytest.raises(ValueError, match="Invalid device path"):
            await service.get_blank_media_info("/dev/sda")


class TestAudioTrackParsing:
    """Tests for audio track parsing."""

    @pytest.mark.asyncio
    async def test_parse_audio_tracks(self, service):
        """Should parse audio tracks from cd-info output."""
        cd_info_output = """
CD-ROM Track List (1 - 3)
  #: MSF       LSN    Type   Green? Copy? Channels Premphasis?
  1: 00:02:00  000150 audio  false  no    2        no
  2: 04:32:25  020275 audio  false  no    2        no
  3: 08:15:50  037175 audio  false  no    2        no
170: 12:00:00  054000 leadout
"""
        tracks = await service._parse_audio_tracks(cd_info_output)
        assert len(tracks) == 3
        assert tracks[0].number == 1
        assert tracks[0].start_sector == 150
        assert tracks[1].number == 2
        assert tracks[2].number == 3


class TestCommandExecution:
    """Tests for command execution."""

    @pytest.mark.asyncio
    async def test_run_command_dev_mode(self, service):
        """Should simulate commands in dev mode."""
        ret, stdout, stderr = await service._run_command(["lsblk"])
        assert ret == 0
        assert "sr0" in stdout

    @pytest.mark.asyncio
    async def test_run_command_eject_simulated(self, service):
        """Should simulate eject command."""
        ret, stdout, stderr = await service._run_command(["eject", "/dev/sr0"])
        assert ret == 0


class TestServiceCleanup:
    """Tests for service cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_cancels_tasks(self, service, tmp_path):
        """Should cancel all running tasks on cleanup."""
        with patch.object(service, 'validate_path', return_value=True):
            job = await service.read_iso("/dev/sr0", str(tmp_path / "test.iso"))

        # Give the task a moment to start
        await asyncio.sleep(0.1)

        await service.cleanup()
        assert len(service._job_tasks) == 0


class TestOpticalDriveConfig:
    """Tests for plugin configuration."""

    def test_default_config(self):
        """Should have sensible defaults."""
        config = OpticalDriveConfig()
        assert config.default_output_dir == "/storage/optical"
        assert config.default_burn_speed == 0
        assert config.auto_eject_after_operation is True
        assert config.scan_interval_seconds == 30
        assert config.max_concurrent_jobs == 2

    def test_config_validation(self):
        """Should validate configuration values."""
        config = OpticalDriveConfig(
            scan_interval_seconds=5,
            max_concurrent_jobs=1
        )
        assert config.scan_interval_seconds == 5
        assert config.max_concurrent_jobs == 1


class TestModels:
    """Tests for Pydantic models."""

    def test_drive_info_model(self):
        """Should create DriveInfo with all fields."""
        drive = DriveInfo(
            device="/dev/sr0",
            name="Test Drive",
            vendor="Test",
            model="Model",
            can_write=True,
            is_ready=True,
            media_type=MediaType.CD_AUDIO,
            total_tracks=5
        )
        assert drive.device == "/dev/sr0"
        assert drive.media_type == MediaType.CD_AUDIO

    def test_optical_job_model(self):
        """Should create OpticalJob with all fields."""
        job = OpticalJob(
            id="test-id",
            device="/dev/sr0",
            job_type=JobType.READ_ISO,
            status=JobStatus.RUNNING,
            progress_percent=50.0
        )
        assert job.id == "test-id"
        assert job.progress_percent == 50.0

    def test_audio_track_model(self):
        """Should create AudioTrack with all fields."""
        track = AudioTrack(
            number=1,
            duration_seconds=180,
            start_sector=150,
            end_sector=13500
        )
        assert track.number == 1
        assert track.duration_seconds == 180

    def test_blank_media_info_model(self):
        """Should create BlankMediaInfo with all fields."""
        info = BlankMediaInfo(
            media_type="DVD-R",
            capacity_bytes=4700000000,
            capacity_mb=4700.0,
            is_rewritable=False,
            is_blank=True,
            write_speeds=[4, 8, 16]
        )
        assert info.media_type == "DVD-R"
        assert len(info.write_speeds) == 3
