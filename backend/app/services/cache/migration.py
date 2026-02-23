"""VCL data migration service: HDD -> SSD with progress tracking.

Extracts and adapts core logic from scripts/migration/migrate_vcl_to_ssd.py
for use as a background-job service with DB-tracked progress.
"""
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.migration_job import MigrationJob
from app.models.vcl import VersionBlob

logger = logging.getLogger(__name__)

# Class-level cancel flags: job_id -> True means cancel requested
_cancel_flags: dict[int, bool] = {}

# Progress flush interval
_PROGRESS_FLUSH_INTERVAL = 5.0  # seconds
_PROGRESS_FLUSH_FILES = 10  # or every N files


class MigrationService:
    """Manages VCL data migration jobs (copy, verify, cleanup)."""

    def __init__(self, db: Session):
        self.db = db

    # ─── Job Management ──────────────────────────────────────────

    def get_job(self, job_id: int) -> Optional[MigrationJob]:
        """Get a single migration job by ID."""
        return self.db.query(MigrationJob).filter(MigrationJob.id == job_id).first()

    def list_jobs(self, limit: int = 20) -> list[MigrationJob]:
        """List migration jobs, newest first."""
        return (
            self.db.query(MigrationJob)
            .order_by(MigrationJob.created_at.desc())
            .limit(limit)
            .all()
        )

    def cancel_job(self, job_id: int) -> bool:
        """Request cancellation of a running job."""
        job = self.get_job(job_id)
        if not job or job.status not in ("pending", "running"):
            return False
        _cancel_flags[job_id] = True
        # If still pending, mark cancelled immediately
        if job.status == "pending":
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
        return True

    # ─── VCL Migration (Copy + DB Update) ────────────────────────

    def start_vcl_migration(
        self, source: str, dest: str, dry_run: bool, user_id: int
    ) -> MigrationJob:
        """Create a VCL migration job and validate inputs."""
        self._validate_paths(source, dest, check_writable=not dry_run)
        self._check_no_running_jobs("vcl_to_ssd")

        # Space check
        if not dry_run:
            self._check_disk_space(source, dest)

        job = MigrationJob(
            job_type="vcl_to_ssd",
            status="pending",
            source_path=source,
            dest_path=dest,
            dry_run=dry_run,
            created_by=user_id,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_vcl_migration(self, job_id: int) -> None:
        """Background: copy blobs + update DB paths. Uses own DB session."""
        db = SessionLocal()
        try:
            job = db.get(MigrationJob, job_id)
            if not job or job.status == "cancelled":
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            source = Path(job.source_path)
            dest = Path(job.dest_path)
            dry_run = bool(job.dry_run)

            # Step 1: Copy blob files
            source_blobs = source / "blobs"
            dest_blobs = dest / "blobs"

            if not source_blobs.exists():
                self._fail_job(db, job, f"Source blobs directory not found: {source_blobs}")
                return

            if not dry_run:
                dest_blobs.mkdir(parents=True, exist_ok=True)

            blob_files = sorted(source_blobs.glob("*.gz"))
            total = len(blob_files)
            total_bytes = 0
            # Pre-scan total bytes
            for f in blob_files:
                try:
                    total_bytes += f.stat().st_size
                except OSError:
                    pass

            job.total_files = total
            job.total_bytes = total_bytes
            db.commit()

            copied = 0
            skipped = 0
            failed = 0
            processed_bytes = 0
            last_flush = time.monotonic()
            files_since_flush = 0

            for i, src_file in enumerate(blob_files):
                # Check cancel
                if _cancel_flags.get(job_id):
                    job.status = "cancelled"
                    job.completed_at = datetime.now(timezone.utc)
                    job.processed_files = copied + skipped + failed
                    job.skipped_files = skipped
                    job.failed_files = failed
                    job.processed_bytes = processed_bytes
                    db.commit()
                    _cancel_flags.pop(job_id, None)
                    logger.info("Migration job %d cancelled at file %d/%d", job_id, i, total)
                    return

                dst_file = dest_blobs / src_file.name
                try:
                    src_size = src_file.stat().st_size
                except OSError:
                    failed += 1
                    files_since_flush += 1
                    continue

                # Resumable: skip if dest already exists with matching size
                if dst_file.exists():
                    try:
                        if dst_file.stat().st_size == src_size:
                            skipped += 1
                            processed_bytes += src_size
                            files_since_flush += 1
                            self._maybe_flush_progress(
                                db, job, copied + skipped + failed, skipped,
                                failed, processed_bytes, src_file.name,
                                last_flush, files_since_flush,
                            )
                            if files_since_flush >= _PROGRESS_FLUSH_FILES:
                                last_flush = time.monotonic()
                                files_since_flush = 0
                            continue
                    except OSError:
                        pass

                if dry_run:
                    copied += 1
                    processed_bytes += src_size
                else:
                    try:
                        shutil.copy2(str(src_file), str(dst_file))
                        copied += 1
                        processed_bytes += src_size
                    except OSError as e:
                        logger.error("Failed to copy %s: %s", src_file.name, e)
                        failed += 1

                files_since_flush += 1
                now = time.monotonic()
                if files_since_flush >= _PROGRESS_FLUSH_FILES or (now - last_flush) >= _PROGRESS_FLUSH_INTERVAL:
                    job.processed_files = copied + skipped + failed
                    job.skipped_files = skipped
                    job.failed_files = failed
                    job.processed_bytes = processed_bytes
                    job.current_file = src_file.name
                    db.commit()
                    last_flush = now
                    files_since_flush = 0

            # Step 2: Update DB paths (unless dry_run or there were failures)
            db_updated = 0
            if failed == 0:
                db_updated = self._update_db_paths(db, str(source), str(dest), dry_run)

            # Complete
            job.status = "completed"
            job.processed_files = copied + skipped + failed
            job.skipped_files = skipped
            job.failed_files = failed
            job.processed_bytes = processed_bytes
            job.current_file = None
            job.completed_at = datetime.now(timezone.utc)
            if failed > 0:
                job.status = "failed"
                job.error_message = f"{failed} files failed to copy. DB paths not updated."
            db.commit()

            logger.info(
                "VCL migration job %d %s: copied=%d, skipped=%d, failed=%d, db_updated=%d",
                job_id, job.status, copied, skipped, failed, db_updated,
            )

        except Exception as e:
            logger.exception("VCL migration job %d failed: %s", job_id, e)
            try:
                job = db.get(MigrationJob, job_id)
                if job:
                    self._fail_job(db, job, str(e))
            except Exception:
                pass
        finally:
            _cancel_flags.pop(job_id, None)
            db.close()

    # ─── VCL Verify ──────────────────────────────────────────────

    def start_vcl_verify(self, dest: str, user_id: int) -> MigrationJob:
        """Create a VCL verification job."""
        if ".." in dest:
            raise ValueError("Path must not contain '..'")
        self._check_no_running_jobs("vcl_verify")

        job = MigrationJob(
            job_type="vcl_verify",
            status="pending",
            source_path="",
            dest_path=dest,
            dry_run=False,
            created_by=user_id,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_vcl_verify(self, job_id: int) -> None:
        """Background: verify migrated blobs against DB."""
        db = SessionLocal()
        try:
            job = db.get(MigrationJob, job_id)
            if not job or job.status == "cancelled":
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            dest_prefix = job.dest_path
            blobs = (
                db.query(VersionBlob)
                .filter(VersionBlob.storage_path.like(f"{dest_prefix}%"))
                .all()
            )

            total = len(blobs)
            job.total_files = total
            db.commit()

            verified = 0
            missing = 0
            size_mismatch = 0
            last_flush = time.monotonic()
            files_since_flush = 0

            for blob in blobs:
                if _cancel_flags.get(job_id):
                    job.status = "cancelled"
                    job.completed_at = datetime.now(timezone.utc)
                    job.processed_files = verified + missing + size_mismatch
                    job.failed_files = missing + size_mismatch
                    db.commit()
                    _cancel_flags.pop(job_id, None)
                    return

                blob_path = Path(str(blob.storage_path))
                if not blob_path.exists():
                    missing += 1
                elif blob_path.stat().st_size != int(blob.compressed_size):
                    size_mismatch += 1
                else:
                    verified += 1

                files_since_flush += 1
                now = time.monotonic()
                if files_since_flush >= _PROGRESS_FLUSH_FILES or (now - last_flush) >= _PROGRESS_FLUSH_INTERVAL:
                    job.processed_files = verified + missing + size_mismatch
                    job.failed_files = missing + size_mismatch
                    job.current_file = str(blob_path.name)
                    db.commit()
                    last_flush = now
                    files_since_flush = 0

            errors = missing + size_mismatch
            job.processed_files = verified + errors
            job.skipped_files = verified
            job.failed_files = errors
            job.current_file = None
            job.completed_at = datetime.now(timezone.utc)

            if errors > 0:
                job.status = "failed"
                job.error_message = f"Verification failed: {missing} missing, {size_mismatch} size mismatches"
            else:
                job.status = "completed"

            db.commit()
            logger.info(
                "VCL verify job %d: verified=%d, missing=%d, mismatch=%d",
                job_id, verified, missing, size_mismatch,
            )

        except Exception as e:
            logger.exception("VCL verify job %d failed: %s", job_id, e)
            try:
                job = db.get(MigrationJob, job_id)
                if job:
                    self._fail_job(db, job, str(e))
            except Exception:
                pass
        finally:
            _cancel_flags.pop(job_id, None)
            db.close()

    # ─── VCL Cleanup ─────────────────────────────────────────────

    def start_vcl_cleanup(
        self, source: str, dry_run: bool, user_id: int
    ) -> MigrationJob:
        """Create a VCL cleanup job (delete source blobs after migration)."""
        if ".." in source:
            raise ValueError("Path must not contain '..'")
        self._check_no_running_jobs("vcl_cleanup")

        job = MigrationJob(
            job_type="vcl_cleanup",
            status="pending",
            source_path=source,
            dest_path="",
            dry_run=dry_run,
            created_by=user_id,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_vcl_cleanup(self, job_id: int) -> None:
        """Background: remove source blobs that exist at destination."""
        db = SessionLocal()
        try:
            job = db.get(MigrationJob, job_id)
            if not job or job.status == "cancelled":
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.commit()

            source_blobs = Path(job.source_path) / "blobs"
            dry_run = bool(job.dry_run)

            if not source_blobs.exists():
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            # Determine dest from DB: read first blob to find current prefix
            first_blob = db.query(VersionBlob).first()
            if not first_blob:
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return

            dest_blobs = Path(str(first_blob.storage_path)).parent

            blob_files = sorted(source_blobs.glob("*.gz"))
            total = len(blob_files)
            job.total_files = total
            db.commit()

            removed = 0
            kept = 0
            last_flush = time.monotonic()
            files_since_flush = 0

            for src_file in blob_files:
                if _cancel_flags.get(job_id):
                    job.status = "cancelled"
                    job.completed_at = datetime.now(timezone.utc)
                    job.processed_files = removed + kept
                    job.skipped_files = kept
                    db.commit()
                    _cancel_flags.pop(job_id, None)
                    return

                dst_file = dest_blobs / src_file.name
                try:
                    src_size = src_file.stat().st_size
                except OSError:
                    kept += 1
                    files_since_flush += 1
                    continue

                # Only remove if dest exists with matching size
                if dst_file.exists() and dst_file.stat().st_size == src_size:
                    if dry_run:
                        removed += 1
                    else:
                        try:
                            src_file.unlink()
                            removed += 1
                        except OSError as e:
                            logger.error("Failed to remove %s: %s", src_file.name, e)
                            kept += 1
                else:
                    kept += 1

                files_since_flush += 1
                now = time.monotonic()
                if files_since_flush >= _PROGRESS_FLUSH_FILES or (now - last_flush) >= _PROGRESS_FLUSH_INTERVAL:
                    job.processed_files = removed + kept
                    job.skipped_files = kept
                    job.current_file = src_file.name
                    db.commit()
                    last_flush = now
                    files_since_flush = 0

            job.status = "completed"
            job.processed_files = removed + kept
            job.skipped_files = kept
            job.current_file = None
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                "VCL cleanup job %d %s: removed=%d, kept=%d",
                job_id, "dry-run" if dry_run else "complete", removed, kept,
            )

        except Exception as e:
            logger.exception("VCL cleanup job %d failed: %s", job_id, e)
            try:
                job = db.get(MigrationJob, job_id)
                if job:
                    self._fail_job(db, job, str(e))
            except Exception:
                pass
        finally:
            _cancel_flags.pop(job_id, None)
            db.close()

    # ─── Internal Helpers ────────────────────────────────────────

    def _validate_paths(self, source: str, dest: str, check_writable: bool = True) -> None:
        """Validate source/dest paths."""
        if ".." in source or ".." in dest:
            raise ValueError("Paths must not contain '..'")

        source_path = Path(source)
        if not source_path.exists():
            raise ValueError(f"Source path does not exist: {source}")

        if check_writable:
            dest_path = Path(dest)
            try:
                dest_path.mkdir(parents=True, exist_ok=True)
                test_file = dest_path / ".migration_test"
                test_file.write_text("test")
                test_file.unlink()
            except OSError as e:
                raise ValueError(f"Destination path not writable: {e}")

    def _check_disk_space(self, source: str, dest: str) -> None:
        """Verify destination has enough space for source blobs."""
        source_blobs = Path(source) / "blobs"
        if not source_blobs.exists():
            return

        source_size = sum(
            f.stat().st_size for f in source_blobs.glob("*.gz")
            if f.is_file()
        )
        dest_usage = shutil.disk_usage(dest)
        headroom = int(source_size * 1.05)  # 5% headroom

        if dest_usage.free < headroom:
            raise ValueError(
                f"Insufficient space at destination. Need {headroom / (1024**3):.2f} GB, "
                f"have {dest_usage.free / (1024**3):.2f} GB"
            )

    def _check_no_running_jobs(self, job_type: str) -> None:
        """Ensure no other job of same type is currently running."""
        running = (
            self.db.query(MigrationJob)
            .filter(
                MigrationJob.job_type == job_type,
                MigrationJob.status.in_(["pending", "running"]),
            )
            .first()
        )
        if running:
            raise ValueError(
                f"A {job_type} job is already running (id={running.id}). "
                "Cancel it first or wait for completion."
            )

    @staticmethod
    def _update_db_paths(db: Session, source: str, dest: str, dry_run: bool) -> int:
        """Bulk update VersionBlob.storage_path: replace source prefix with dest."""
        blobs = (
            db.query(VersionBlob)
            .filter(VersionBlob.storage_path.like(f"{source}%"))
            .all()
        )

        if dry_run:
            return len(blobs)

        updated = 0
        for blob in blobs:
            old_path = str(blob.storage_path)
            new_path = old_path.replace(source, dest, 1)
            blob.storage_path = new_path
            updated += 1

        db.commit()
        logger.info("Updated %d blob paths in database", updated)
        return updated

    @staticmethod
    def _fail_job(db: Session, job: MigrationJob, error: str) -> None:
        """Mark a job as failed."""
        job.status = "failed"
        job.error_message = error
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    def _maybe_flush_progress(
        self, db: Session, job: MigrationJob,
        processed: int, skipped: int, failed: int,
        processed_bytes: int, current_file: str,
        last_flush: float, files_since_flush: int,
    ) -> None:
        """Flush progress to DB if threshold reached."""
        now = time.monotonic()
        if files_since_flush >= _PROGRESS_FLUSH_FILES or (now - last_flush) >= _PROGRESS_FLUSH_INTERVAL:
            job.processed_files = processed
            job.skipped_files = skipped
            job.failed_files = failed
            job.processed_bytes = processed_bytes
            job.current_file = current_file
            db.commit()
