"""Sync execution helpers invoked by the central scheduler worker.

Historically this module ran its own APScheduler (``SyncBackgroundScheduler``)
that duplicated the jobs dispatched by ``app.services.scheduler.worker``. That
caused two ``sync_check`` executions per tick and nested history rows because
the inner coroutine also called ``log_scheduler_execution``. The central
scheduler worker is now the sole driver — this module only exposes the plain
coroutines it invokes via ``_dispatch_job``.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.sync_progress import SyncSchedule
from app.services.sync.file_sync import FileSyncService
from app.services.audit.logger import AuditLogger

logger = logging.getLogger(__name__)

# Global instance (kept so callers that already imported ``get_scheduler`` and
# called methods on it continue to work — there is no APScheduler behind it).
_scheduler: Optional["SyncBackgroundScheduler"] = None


class SyncBackgroundScheduler:
    """Stateless container for sync-related coroutines.

    The central scheduler worker calls :meth:`check_and_run_due_syncs` and
    :meth:`cleanup_expired_uploads` via ``_dispatch_job``. Both methods now
    return a result dict and do NOT touch ``scheduler_executions`` themselves
    — the worker wraps them with ``log_scheduler_execution`` /
    ``complete_scheduler_execution``.
    """

    def __init__(self) -> None:
        self.logger = logger

    async def check_and_run_due_syncs(self) -> dict:
        """Check for due syncs and execute them. Returns a result dict."""
        db = SessionLocal()
        executed_count = 0
        error_count = 0
        try:
            now = datetime.now(timezone.utc)

            due_schedules = db.query(SyncSchedule).filter(
                SyncSchedule.is_active == True,  # noqa: E712
                SyncSchedule.next_run_at <= now,
            ).all()

            self.logger.info("Found %d due syncs", len(due_schedules))

            for schedule in due_schedules:
                try:
                    await self.execute_scheduled_sync(schedule, db)
                    executed_count += 1
                except Exception as e:
                    self.logger.error("Error executing sync %s: %s", schedule.id, e)
                    error_count += 1

            return {
                "due_syncs": len(due_schedules),
                "executed": executed_count,
                "errors": error_count,
            }
        finally:
            db.close()

    async def execute_scheduled_sync(self, schedule: SyncSchedule, db: Session) -> None:
        """Execute a single scheduled sync."""
        self.logger.info(
            "Executing scheduled sync %s for user %s", schedule.id, schedule.user_id
        )

        sync_service = FileSyncService(db)
        audit_logger = AuditLogger()

        try:
            sync_status = sync_service.get_sync_status(
                schedule.user_id,
                schedule.device_id,
            )

            if sync_status.get("status") == "not_registered":
                self.logger.warning("Device %s not registered", schedule.device_id)
                return

            audit_logger.log_event(
                event_type="SYNC",
                user=str(schedule.user_id),
                action="scheduled_sync_executed",
                resource=schedule.device_id,
                details={
                    "schedule_id": schedule.id,
                    "device_id": schedule.device_id,
                    "schedule_type": schedule.schedule_type,
                },
                success=True,
            )

            schedule.last_run_at = datetime.now(timezone.utc)
            self._calculate_next_run(schedule)
            db.commit()

            self.logger.info("Sync %s completed successfully", schedule.id)

        except Exception as e:
            self.logger.error("Sync %s failed: %s", schedule.id, e)
            audit_logger.log_event(
                event_type="SYNC",
                user=str(schedule.user_id),
                action="scheduled_sync_failed",
                resource=schedule.device_id,
                details={"schedule_id": schedule.id, "error": str(e)},
                success=False,
                error_message=str(e),
            )
            raise

    async def cleanup_expired_uploads(self) -> dict:
        """Clean up expired chunked uploads. Returns a result dict."""
        from app.services.sync.progressive import ProgressiveSyncService

        db = SessionLocal()
        try:
            sync_service = ProgressiveSyncService(db)
            cleaned = sync_service.cleanup_expired_uploads()
            self.logger.info("Expired uploads cleaned up")
            return {"cleaned": cleaned if isinstance(cleaned, int) else 0}
        finally:
            db.close()

    def _calculate_next_run(self, schedule: SyncSchedule) -> None:
        """Calculate next run time (same as in sync_scheduler.py)."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)

        if schedule.schedule_type == "daily":
            hour, minute = map(int, (schedule.time_of_day or "00:00").split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if next_run <= now:
                next_run += timedelta(days=1)

            schedule.next_run_at = next_run

        elif schedule.schedule_type == "weekly":
            hour, minute = map(int, (schedule.time_of_day or "00:00").split(":"))
            target_day = schedule.day_of_week or 0

            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = target_day - now.weekday()

            if days_ahead <= 0:
                days_ahead += 7

            next_run += timedelta(days=days_ahead)
            schedule.next_run_at = next_run

        elif schedule.schedule_type == "monthly":
            hour, minute = map(int, (schedule.time_of_day or "00:00").split(":"))
            target_day = schedule.day_of_month or 1

            next_run = now.replace(
                day=target_day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )

            if next_run <= now:
                next_run = (next_run + timedelta(days=32)).replace(day=target_day)

            schedule.next_run_at = next_run


def get_scheduler() -> SyncBackgroundScheduler:
    """Get the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = SyncBackgroundScheduler()
    return _scheduler


def get_status() -> dict:
    """Admin dashboard status stub — the real scheduler status lives in the
    central scheduler worker's service registry now."""
    return {
        "is_running": True,
        "started_at": None,
        "uptime_seconds": None,
        "sample_count": 0,
        "error_count": 0,
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": 300,
        "next_run": None,
    }
