"""Tests for MigrationService (VCL HDD -> SSD migration)."""
import gzip
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

from app.models.migration_job import MigrationJob
from app.models.vcl import VersionBlob
from app.models.user import User
from app.services.cache.migration import MigrationService, _cancel_flags


def _patch_session(db: Session):
    """Patch SessionLocal so background tasks reuse the test session.

    The run_* methods call db.close() in their finally blocks. We must
    prevent that, because in tests the same session is reused across the
    test function.  We return a callable that, when called (i.e.
    ``SessionLocal()``), returns the *same* Session with close() disabled.
    """
    real_close = db.close

    def _factory():
        db.close = lambda: None  # no-op during background task
        return db

    return patch("app.services.cache.migration.SessionLocal", side_effect=_factory)


@pytest.fixture(autouse=True)
def _clear_cancel_flags():
    """Clear module-level cancel flags between tests."""
    _cancel_flags.clear()
    yield
    _cancel_flags.clear()


@pytest.fixture
def admin_id(admin_user: User) -> int:
    """Return admin user ID."""
    return int(admin_user.id)


@pytest.fixture
def migration_service(db: Session) -> MigrationService:
    """Create MigrationService instance."""
    return MigrationService(db)


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a temp source directory with blob files."""
    blobs = tmp_path / "source" / "blobs"
    blobs.mkdir(parents=True)
    for i in range(5):
        blob_file = blobs / f"blob_{i:04d}.gz"
        # Write valid gzip data
        with gzip.open(str(blob_file), "wb") as f:
            f.write(f"content_{i}".encode())
    return tmp_path / "source"


@pytest.fixture
def dest_dir(tmp_path: Path) -> Path:
    """Create a temp destination directory."""
    dest = tmp_path / "dest"
    dest.mkdir(parents=True)
    return dest


@pytest.fixture
def version_blobs(db: Session, source_dir: Path) -> list[VersionBlob]:
    """Create VersionBlob records pointing to source blobs."""
    blobs = []
    for i in range(5):
        blob_path = source_dir / "blobs" / f"blob_{i:04d}.gz"
        compressed_size = blob_path.stat().st_size
        blob = VersionBlob(
            checksum=f"sha256_test_{i:060d}",
            storage_path=str(blob_path),
            original_size=100 + i,
            compressed_size=compressed_size,
            reference_count=1,
        )
        db.add(blob)
        blobs.append(blob)
    db.commit()
    return blobs


# ─── Job Lifecycle ───────────────────────────────────────────────


class TestJobLifecycle:
    """Test job creation, listing, and cancellation."""

    def test_create_migration_job(
        self, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path,
    ):
        job = migration_service.start_vcl_migration(
            source=str(source_dir),
            dest=str(dest_dir),
            dry_run=True,
            user_id=admin_id,
        )
        assert job.id is not None
        assert job.job_type == "vcl_to_ssd"
        assert job.status == "pending"
        assert job.dry_run is True
        assert job.created_by == admin_id

    def test_list_jobs(
        self, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path,
    ):
        # Create multiple jobs
        j1 = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), True, admin_id,
        )
        j2 = migration_service.start_vcl_verify(str(dest_dir), admin_id)

        # Cancel them so we can create more
        migration_service.cancel_job(j1.id)
        migration_service.cancel_job(j2.id)

        jobs = migration_service.list_jobs(limit=10)
        assert len(jobs) >= 2

    def test_cancel_pending_job(
        self, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path,
    ):
        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), True, admin_id,
        )
        assert migration_service.cancel_job(job.id) is True
        refreshed = migration_service.get_job(job.id)
        assert refreshed is not None
        assert refreshed.status == "cancelled"

    def test_cancel_nonexistent_job(self, migration_service: MigrationService):
        assert migration_service.cancel_job(99999) is False

    def test_duplicate_running_job_rejected(
        self, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path,
    ):
        migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), True, admin_id,
        )
        with pytest.raises(ValueError, match="already running"):
            migration_service.start_vcl_migration(
                str(source_dir), str(dest_dir), True, admin_id,
            )


# ─── Path Validation ────────────────────────────────────────────


class TestPathValidation:
    """Test path validation and security checks."""

    def test_reject_path_traversal(
        self, migration_service: MigrationService, admin_id: int,
    ):
        with pytest.raises(ValueError, match="must not contain"):
            migration_service.start_vcl_migration(
                "/mnt/../etc/passwd", "/tmp/dest", False, admin_id,
            )

    def test_reject_nonexistent_source(
        self, migration_service: MigrationService, admin_id: int,
        dest_dir: Path,
    ):
        with pytest.raises(ValueError, match="does not exist"):
            migration_service.start_vcl_migration(
                "/nonexistent/path", str(dest_dir), False, admin_id,
            )

    def test_verify_rejects_traversal(
        self, migration_service: MigrationService, admin_id: int,
    ):
        with pytest.raises(ValueError, match="must not contain"):
            migration_service.start_vcl_verify("../etc", admin_id)

    def test_cleanup_rejects_traversal(
        self, migration_service: MigrationService, admin_id: int,
    ):
        with pytest.raises(ValueError, match="must not contain"):
            migration_service.start_vcl_cleanup("../etc", False, admin_id)


# ─── VCL Migration ──────────────────────────────────────────────


class TestVCLMigration:
    """Test VCL blob migration (copy + DB update)."""

    def test_dry_run_migration(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path, version_blobs: list[VersionBlob],
    ):
        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), dry_run=True, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_migration(job.id)

        refreshed = migration_service.get_job(job.id)
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.total_files == 5
        # Dry run: no actual files copied to dest
        dest_blobs = dest_dir / "blobs"
        if dest_blobs.exists():
            actual_files = list(dest_blobs.glob("*.gz"))
            assert len(actual_files) == 0

    def test_real_migration(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path, version_blobs: list[VersionBlob],
    ):
        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), dry_run=False, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_migration(job.id)

        refreshed = migration_service.get_job(job.id)
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.total_files == 5
        assert refreshed.failed_files == 0

        # Files should exist at destination
        dest_blobs = dest_dir / "blobs"
        actual_files = list(dest_blobs.glob("*.gz"))
        assert len(actual_files) == 5

        # DB paths should be updated
        db.expire_all()
        for blob in version_blobs:
            db.refresh(blob)
            assert str(blob.storage_path).startswith(str(dest_dir))

    def test_resumable_migration(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path, version_blobs: list[VersionBlob],
    ):
        """Pre-copy some files, migration should skip them."""
        # Pre-copy 2 files
        dest_blobs = dest_dir / "blobs"
        dest_blobs.mkdir(parents=True, exist_ok=True)
        import shutil
        source_blobs = source_dir / "blobs"
        for f in sorted(source_blobs.glob("*.gz"))[:2]:
            shutil.copy2(str(f), str(dest_blobs / f.name))

        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), dry_run=False, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_migration(job.id)

        refreshed = migration_service.get_job(job.id)
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.skipped_files == 2

    def test_cancel_migration(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path,
    ):
        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), dry_run=False, user_id=admin_id,
        )
        # Set cancel flag before running
        _cancel_flags[job.id] = True

        with _patch_session(db):
            migration_service.run_vcl_migration(job.id)

        refreshed = migration_service.get_job(job.id)
        assert refreshed is not None
        assert refreshed.status == "cancelled"


# ─── VCL Verify ─────────────────────────────────────────────────


class TestVCLVerify:
    """Test VCL migration verification."""

    def test_verify_success(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path, version_blobs: list[VersionBlob],
    ):
        # First migrate
        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), dry_run=False, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_migration(job.id)

        # Now verify
        verify_job = migration_service.start_vcl_verify(str(dest_dir), admin_id)
        with _patch_session(db):
            migration_service.run_vcl_verify(verify_job.id)

        refreshed = migration_service.get_job(verify_job.id)
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.failed_files == 0

    def test_verify_missing_files(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        dest_dir: Path,
    ):
        """Verify fails when blobs point to nonexistent dest paths."""
        # Create blobs pointing to non-existent dest files
        for i in range(3):
            blob = VersionBlob(
                checksum=f"sha256_verify_{i:058d}",
                storage_path=str(dest_dir / "blobs" / f"missing_{i}.gz"),
                original_size=100,
                compressed_size=50,
                reference_count=1,
            )
            db.add(blob)
        db.commit()

        verify_job = migration_service.start_vcl_verify(str(dest_dir), admin_id)
        with _patch_session(db):
            migration_service.run_vcl_verify(verify_job.id)

        refreshed = migration_service.get_job(verify_job.id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.failed_files == 3
        assert "missing" in (refreshed.error_message or "").lower()


# ─── VCL Cleanup ────────────────────────────────────────────────


class TestVCLCleanup:
    """Test VCL source blob cleanup."""

    def test_cleanup_after_migration(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path, version_blobs: list[VersionBlob],
    ):
        # Migrate first
        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), dry_run=False, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_migration(job.id)

        # Source files should still exist
        source_blobs = source_dir / "blobs"
        assert len(list(source_blobs.glob("*.gz"))) == 5

        # Cleanup
        cleanup_job = migration_service.start_vcl_cleanup(
            str(source_dir), dry_run=False, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_cleanup(cleanup_job.id)

        refreshed = migration_service.get_job(cleanup_job.id)
        assert refreshed is not None
        assert refreshed.status == "completed"

        # Source files should be removed
        remaining = list(source_blobs.glob("*.gz"))
        assert len(remaining) == 0

    def test_cleanup_dry_run(
        self, db: Session, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path, version_blobs: list[VersionBlob],
    ):
        # Migrate first
        job = migration_service.start_vcl_migration(
            str(source_dir), str(dest_dir), dry_run=False, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_migration(job.id)

        # Cleanup dry-run
        cleanup_job = migration_service.start_vcl_cleanup(
            str(source_dir), dry_run=True, user_id=admin_id,
        )
        with _patch_session(db):
            migration_service.run_vcl_cleanup(cleanup_job.id)

        refreshed = migration_service.get_job(cleanup_job.id)
        assert refreshed is not None
        assert refreshed.status == "completed"

        # Source files should NOT be removed (dry run)
        source_blobs = source_dir / "blobs"
        assert len(list(source_blobs.glob("*.gz"))) == 5


# ─── Disk Space Check ───────────────────────────────────────────


class TestDiskSpaceCheck:
    """Test disk space validation."""

    def test_insufficient_space_rejected(
        self, migration_service: MigrationService, admin_id: int,
        source_dir: Path, dest_dir: Path,
    ):
        with patch("app.services.cache.migration.shutil.disk_usage") as mock_usage:
            mock_usage.return_value = MagicMock(free=10)  # 10 bytes free
            with pytest.raises(ValueError, match="Insufficient space"):
                migration_service.start_vcl_migration(
                    str(source_dir), str(dest_dir), dry_run=False, user_id=admin_id,
                )
