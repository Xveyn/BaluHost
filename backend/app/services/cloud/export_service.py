"""Cloud export service — upload NAS files to cloud and create sharing links."""
import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cloud import CloudConnection
from app.models.cloud_export import CloudExportJob
from app.schemas.cloud_export import CloudExportStatistics
from app.services.cloud.service import CloudService

logger = logging.getLogger(__name__)


class CloudExportService:
    """Manages cloud export jobs — upload + share link creation."""

    def __init__(self, db: Session):
        self.db = db

    # ─── Start Export ─────────────────────────────────────────────

    def start_export(
        self,
        connection_id: int,
        user_id: int,
        source_path: str,
        cloud_folder: str,
        link_type: str,
        expires_at: Optional[datetime],
    ) -> CloudExportJob:
        """Create a new export job. Validates inputs."""
        # Reject path traversal
        if ".." in source_path:
            raise ValueError("Invalid source_path: path traversal not allowed")

        # Validate connection ownership
        cloud_service = CloudService(self.db)
        cloud_service.get_connection(connection_id, user_id)

        # Derive file name and detect directory
        clean_path = source_path.strip("/")
        parts = PurePosixPath(clean_path)
        file_name = parts.name or clean_path
        is_directory = clean_path.endswith("/") or not PurePosixPath(file_name).suffix

        # Try to get file size from filesystem
        file_size_bytes: Optional[int] = None
        try:
            storage_root = Path(settings.nas_storage_path).resolve()
            full_path = storage_root / clean_path
            if full_path.exists():
                if full_path.is_file():
                    file_size_bytes = full_path.stat().st_size
                    is_directory = False
                elif full_path.is_dir():
                    is_directory = True
                    file_size_bytes = sum(
                        f.stat().st_size for f in full_path.rglob("*") if f.is_file()
                    )
        except Exception:
            pass  # Size is optional, continue without it

        job = CloudExportJob(
            user_id=user_id,
            connection_id=connection_id,
            source_path=clean_path,
            is_directory=is_directory,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            cloud_folder=cloud_folder.strip("/") + "/" if cloud_folder else "BaluHost Shares/",
            link_type=link_type,
            status="pending",
            progress_bytes=0,
            expires_at=expires_at,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info(
            "Created cloud export job %d: %s -> %s (user %d)",
            job.id, source_path, cloud_folder, user_id,
        )
        return job

    # ─── Execute Export ───────────────────────────────────────────

    async def execute_export(self, job_id: int) -> None:
        """Background task: upload file/folder, then create share link."""
        job = self.db.query(CloudExportJob).get(job_id)
        if not job:
            logger.error("Export job %d not found", job_id)
            return

        connection = self.db.query(CloudConnection).get(job.connection_id)
        if not connection:
            job.status = "failed"
            job.error_message = "Cloud connection not found"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return

        cloud_service = CloudService(self.db)
        adapter = cloud_service.get_adapter_for_connection(connection)

        try:
            # Phase 1: Upload
            job.status = "uploading"
            self.db.commit()

            storage_root = Path(settings.nas_storage_path).resolve()
            local_path = storage_root / job.source_path

            if not local_path.exists():
                raise FileNotFoundError(f"Source path does not exist: {job.source_path}")

            cloud_dest = f"{job.cloud_folder}{job.file_name}"

            def progress_callback(bytes_done: int, *_args) -> None:
                job.progress_bytes = bytes_done
                self.db.commit()

            if job.is_directory:
                result = await adapter.upload_folder(
                    local_path, cloud_dest, progress_callback=progress_callback
                )
                job.progress_bytes = result.bytes_transferred
                if result.errors:
                    job.error_message = "; ".join(result.errors[:5])
            else:
                await adapter.upload_file(
                    local_path, cloud_dest, progress_callback=lambda b: progress_callback(b)
                )
                if local_path.exists():
                    job.progress_bytes = local_path.stat().st_size

            job.cloud_path = cloud_dest
            self.db.commit()

            # Phase 2: Create share link
            job.status = "creating_link"
            self.db.commit()

            share_link = await adapter.create_share_link(cloud_dest, job.link_type)
            job.share_link = share_link
            job.status = "ready"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            # Update connection last_used_at
            connection.last_used_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(
                "Export job %d completed: %s -> %s",
                job_id, job.source_path, share_link,
            )

        except Exception as e:
            logger.exception("Export job %d failed", job_id)
            job.status = "failed"
            job.error_message = str(e)[:500]
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()

        finally:
            await adapter.close()

    # ─── Revoke ───────────────────────────────────────────────────

    def revoke_export(self, job_id: int, user_id: int) -> bool:
        """Revoke an export — sets status to revoked. Cloud deletion is best-effort."""
        job = self.get_export_status(job_id, user_id)
        if not job or job.status not in ("ready", "creating_link"):
            return False

        job.status = "revoked"
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()

        logger.info("Revoked export job %d", job_id)
        return True

    async def _delete_cloud_file(self, job: CloudExportJob) -> None:
        """Best-effort deletion of uploaded cloud file."""
        if not job.cloud_path:
            return
        try:
            connection = self.db.query(CloudConnection).get(job.connection_id)
            if not connection:
                return
            cloud_service = CloudService(self.db)
            adapter = cloud_service.get_adapter_for_connection(connection)
            try:
                remote = f"{adapter.remote_name}:{job.cloud_path.lstrip('/')}"
                await adapter._run_rclone("delete", remote, timeout=60)
            finally:
                await adapter.close()
        except Exception:
            logger.warning("Failed to delete cloud file for job %d", job.id)

    # ─── Retry ────────────────────────────────────────────────────

    def retry_export(self, job_id: int, user_id: int) -> Optional[CloudExportJob]:
        """Retry a failed export by resetting it to pending."""
        job = self.get_export_status(job_id, user_id)
        if not job or job.status != "failed":
            return None

        job.status = "pending"
        job.progress_bytes = 0
        job.error_message = None
        job.share_link = None
        job.cloud_path = None
        job.completed_at = None
        self.db.commit()
        self.db.refresh(job)
        return job

    # ─── Queries ──────────────────────────────────────────────────

    def get_user_exports(self, user_id: int, limit: int = 50) -> list[CloudExportJob]:
        """Get all export jobs for a user, newest first."""
        return (
            self.db.query(CloudExportJob)
            .filter(CloudExportJob.user_id == user_id)
            .order_by(CloudExportJob.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_export_status(self, job_id: int, user_id: int) -> Optional[CloudExportJob]:
        """Get a single job, ensuring ownership."""
        return (
            self.db.query(CloudExportJob)
            .filter(
                CloudExportJob.id == job_id,
                CloudExportJob.user_id == user_id,
            )
            .first()
        )

    def get_export_statistics(self, user_id: int) -> CloudExportStatistics:
        """Get export statistics for the SharesPage."""
        now = datetime.now(timezone.utc)

        total = self.db.query(func.count(CloudExportJob.id)).filter(
            CloudExportJob.user_id == user_id
        ).scalar() or 0

        active = self.db.query(func.count(CloudExportJob.id)).filter(
            CloudExportJob.user_id == user_id,
            CloudExportJob.status == "ready",
            or_(
                CloudExportJob.expires_at.is_(None),
                CloudExportJob.expires_at > now,
            ),
        ).scalar() or 0

        failed = self.db.query(func.count(CloudExportJob.id)).filter(
            CloudExportJob.user_id == user_id,
            CloudExportJob.status == "failed",
        ).scalar() or 0

        total_bytes = self.db.query(func.coalesce(func.sum(CloudExportJob.progress_bytes), 0)).filter(
            CloudExportJob.user_id == user_id,
            CloudExportJob.status == "ready",
        ).scalar() or 0

        return CloudExportStatistics(
            total_exports=total,
            active_exports=active,
            failed_exports=failed,
            total_upload_bytes=total_bytes,
        )
