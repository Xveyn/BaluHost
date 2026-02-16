"""Cloud sync scheduler — runs periodic syncs for all active sync jobs."""
import asyncio
import logging

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.cloud import CloudImportJob

logger = logging.getLogger(__name__)


class CloudSyncScheduler:
    """Handles periodic cloud sync execution."""

    @staticmethod
    def run_sync(db: Session) -> dict:
        """
        Find all connections with job_type='sync' and re-run them.

        Called by the scheduler worker service.
        """
        # Find the most recent sync job per connection that completed successfully
        sync_jobs = (
            db.query(CloudImportJob)
            .filter(
                CloudImportJob.job_type == "sync",
                CloudImportJob.status == "completed",
            )
            .order_by(CloudImportJob.completed_at.desc())
            .all()
        )

        # Deduplicate by connection_id (keep most recent)
        seen_connections: set[int] = set()
        jobs_to_resync: list[CloudImportJob] = []
        for job in sync_jobs:
            if job.connection_id not in seen_connections:
                seen_connections.add(job.connection_id)
                jobs_to_resync.append(job)

        if not jobs_to_resync:
            logger.info("No cloud sync jobs to execute")
            return {"synced": 0, "errors": 0}

        synced = 0
        errors = 0

        for template_job in jobs_to_resync:
            try:
                from app.services.cloud.import_job import CloudImportJobService
                job_service = CloudImportJobService(db)

                new_job = job_service.start_import(
                    connection_id=template_job.connection_id,
                    user_id=template_job.user_id,
                    source_path=template_job.source_path,
                    destination_path=template_job.destination_path,
                    job_type="sync",
                )

                # Run the import synchronously in a new event loop
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(job_service.execute_import(new_job.id))
                finally:
                    loop.close()

                # Check result
                db.refresh(new_job)
                if new_job.status == "completed":
                    synced += 1
                else:
                    errors += 1

            except Exception as e:
                logger.exception(
                    "Cloud sync failed for connection %d: %s",
                    template_job.connection_id, e,
                )
                errors += 1

        result = {"synced": synced, "errors": errors}
        logger.info("Cloud sync completed: %s", result)
        return result
