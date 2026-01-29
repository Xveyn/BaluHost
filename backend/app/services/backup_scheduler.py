"""Backup scheduler for automated periodic backups."""

from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.backup import BackupService
from app.schemas.backup import BackupCreate
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Schedule and execute automated periodic backups."""

    @classmethod
    def create_automated_backup(cls, db: Session) -> dict:
        """
        Create an automated backup based on configuration settings.

        This method should be called periodically (e.g., every 24 hours via APScheduler).

        Args:
            db: Database session

        Returns:
            dict: Statistics about backup creation
        """
        settings = get_settings()

        logger.info(f"[BackupScheduler] Starting automated backup at {datetime.now(timezone.utc)}")
        logger.info(f"[BackupScheduler] Backup type: {settings.backup_auto_type}")

        stats = {
            "started_at": datetime.now(timezone.utc),
            "completed_at": None,
            "backup_type": settings.backup_auto_type,
            "status": "in_progress",
            "backup_id": None,
            "filename": None,
            "size_bytes": None,
            "error": None
        }

        try:
            # Initialize backup service
            backup_service = BackupService(db)

            # Determine backup parameters based on type
            backup_type = settings.backup_auto_type
            includes_database = backup_type in ["full", "database_only", "incremental"]
            includes_files = backup_type in ["full", "files_only", "incremental"]

            # Create backup data schema
            backup_data = BackupCreate(
                backup_type=backup_type,
                includes_database=includes_database,
                includes_files=includes_files,
                includes_config=True  # Always include config in automated backups
            )

            # Create backup using system user (ID=1 for admin)
            backup = backup_service.create_backup(
                backup_data=backup_data,
                creator_id=1,  # System/admin user
                creator_username="backup-scheduler"
            )

            # Update stats
            stats["status"] = "completed"
            stats["completed_at"] = datetime.now(timezone.utc)
            stats["backup_id"] = backup.id
            stats["filename"] = backup.filename
            stats["size_bytes"] = backup.size_bytes

            logger.info(f"[BackupScheduler] ✅ Backup created successfully: {backup.filename}")
            logger.info(f"[BackupScheduler] Size: {backup.size_bytes / (1024*1024):.2f} MB")

        except Exception as e:
            stats["status"] = "failed"
            stats["completed_at"] = datetime.now(timezone.utc)
            stats["error"] = str(e)
            logger.error(f"[BackupScheduler] ❌ Backup failed: {e}", exc_info=True)

        return stats

    @classmethod
    def run_periodic_backup(cls):
        """
        Run periodic backup (called by APScheduler).
        Creates its own database session.
        """
        from app.services.scheduler_service import log_scheduler_execution, complete_scheduler_execution

        settings = get_settings()
        execution_id = log_scheduler_execution("backup", job_id="backup_periodic")

        logger.info("="*60)
        logger.info(f"[BackupScheduler] Periodic backup triggered")
        logger.info(f"[BackupScheduler] Interval: {settings.backup_auto_interval_hours}h")
        logger.info("="*60)

        db = SessionLocal()
        try:
            stats = cls.create_automated_backup(db)

            # Log summary
            logger.info("[BackupScheduler] Summary:")
            logger.info(f"  - Backup type: {stats['backup_type']}")
            logger.info(f"  - Status: {stats['status']}")
            logger.info(f"  - Started: {stats['started_at']}")
            logger.info(f"  - Completed: {stats['completed_at']}")

            if stats['status'] == 'completed':
                logger.info(f"  - Backup ID: {stats['backup_id']}")
                logger.info(f"  - Filename: {stats['filename']}")
                logger.info(f"  - Size: {stats['size_bytes'] / (1024*1024):.2f} MB")
                complete_scheduler_execution(
                    execution_id,
                    success=True,
                    result={
                        "backup_id": stats['backup_id'],
                        "filename": stats['filename'],
                        "size_bytes": stats['size_bytes'],
                        "backup_type": stats['backup_type']
                    }
                )
            else:
                logger.error(f"  - Error: {stats['error']}")
                complete_scheduler_execution(execution_id, success=False, error=stats['error'])

        except Exception as e:
            logger.exception(f"[BackupScheduler] Unexpected error: {e}")
            complete_scheduler_execution(execution_id, success=False, error=str(e))
        finally:
            db.close()
