"""Cloud import job execution service."""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cloud import CloudConnection, CloudImportJob
from app.services.cloud.service import CloudService

logger = logging.getLogger(__name__)


class CloudImportJobService:
    """Manages cloud import/sync jobs."""

    def __init__(self, db: Session):
        self.db = db
        self._cancel_flags: dict[int, bool] = {}

    def start_import(
        self,
        connection_id: int,
        user_id: int,
        source_path: str,
        destination_path: str,
        job_type: str = "import",
    ) -> CloudImportJob:
        """Create a new import job and return it."""
        # Validate connection ownership
        cloud_service = CloudService(self.db)
        cloud_service.get_connection(connection_id, user_id)

        # Sanitize destination path (prevent path traversal)
        dest = destination_path.replace("..", "").strip("/")

        job = CloudImportJob(
            connection_id=connection_id,
            user_id=user_id,
            source_path=source_path,
            destination_path=dest,
            job_type=job_type,
            status="pending",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info(
            "Created cloud import job %d: %s -> %s (user %d)",
            job.id, source_path, dest, user_id,
        )
        return job

    async def execute_import(self, job_id: int) -> None:
        """Execute an import job (download files from cloud to NAS)."""
        job = self.db.query(CloudImportJob).get(job_id)
        if not job:
            logger.error("Import job %d not found", job_id)
            return

        # Mark as running
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()

        cloud_service = CloudService(self.db)
        connection = self.db.query(CloudConnection).get(job.connection_id)
        if not connection:
            job.status = "failed"
            job.error_message = "Cloud connection not found"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return

        adapter = cloud_service.get_adapter_for_connection(connection)

        try:
            # Determine storage root
            storage_root = Path(settings.nas_storage_path).resolve()
            dest_path = storage_root / job.destination_path
            dest_path.mkdir(parents=True, exist_ok=True)

            # Verify destination is within sandbox
            if not str(dest_path.resolve()).startswith(str(storage_root)):
                raise ValueError("Destination path outside storage root")

            # Get total size estimate
            total_size = await adapter.get_total_size(job.source_path)
            if total_size:
                job.total_bytes = total_size
                self.db.commit()

            # Check if source is a file or directory
            parent_path = "/".join(job.source_path.rstrip("/").split("/")[:-1]) or "/"
            source_name = job.source_path.rstrip("/").split("/")[-1]

            files = await adapter.list_files(parent_path)
            source_file = next((f for f in files if f.name == source_name), None)

            if source_file and not source_file.is_directory:
                # Single file download
                job.files_total = 1
                self.db.commit()

                local_file = dest_path / source_file.name

                def file_progress(bytes_done: int) -> None:
                    job.progress_bytes = bytes_done
                    job.current_file = source_file.name
                    self.db.commit()

                await adapter.download_file(
                    job.source_path, local_file, progress_callback=file_progress
                )
                job.files_transferred = 1
                job.progress_bytes = local_file.stat().st_size if local_file.exists() else 0
            else:
                # Folder download — get file count for progress tracking
                file_count = await adapter.get_file_count(job.source_path)
                if file_count is not None:
                    job.files_total = file_count
                    self.db.commit()

                def folder_progress(bytes_done: int, current_file: Optional[str]) -> None:
                    if self._cancel_flags.get(job_id):
                        raise asyncio.CancelledError("Job cancelled by user")
                    job.progress_bytes = bytes_done
                    if current_file:
                        job.current_file = current_file
                    self.db.commit()

                result = await adapter.download_folder(
                    job.source_path, dest_path, progress_callback=folder_progress
                )
                job.files_transferred = result.files_transferred
                job.progress_bytes = result.bytes_transferred

                if result.errors:
                    job.error_message = "; ".join(result.errors[:5])

            # Mark completed
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.current_file = None
            self.db.commit()

            # Update connection last_used_at
            connection.last_used_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(
                "Import job %d completed: %d files, %d bytes",
                job_id, job.files_transferred, job.progress_bytes,
            )

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = "Cancelled by user"
            self.db.commit()
            logger.info("Import job %d cancelled", job_id)

        except Exception as e:
            logger.exception("Import job %d failed", job_id)
            job.status = "failed"
            job.error_message = str(e)[:500]
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()

        finally:
            await adapter.close()
            self._cancel_flags.pop(job_id, None)

    def get_job_status(self, job_id: int, user_id: int) -> Optional[CloudImportJob]:
        """Get a job by ID, ensuring ownership."""
        return (
            self.db.query(CloudImportJob)
            .filter(
                CloudImportJob.id == job_id,
                CloudImportJob.user_id == user_id,
            )
            .first()
        )

    def get_user_jobs(
        self, user_id: int, limit: int = 50
    ) -> list[CloudImportJob]:
        """Get all jobs for a user, newest first."""
        return (
            self.db.query(CloudImportJob)
            .filter(CloudImportJob.user_id == user_id)
            .order_by(CloudImportJob.created_at.desc())
            .limit(limit)
            .all()
        )

    def cancel_job(self, job_id: int, user_id: int) -> bool:
        """Cancel a running job."""
        job = self.get_job_status(job_id, user_id)
        if not job:
            return False

        if job.status == "running":
            self._cancel_flags[job_id] = True
            return True

        if job.status == "pending":
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return True

        return False
