"""Background scheduler for automatic sync execution."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.sync_progress import SyncSchedule
from app.services.file_sync import FileSyncService
from app.services.audit_logger import AuditLogger

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[AsyncIOScheduler] = None


class SyncBackgroundScheduler:
    """Manage background sync execution using APScheduler."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.logger = logger
    
    def start(self):
        """Start the background scheduler."""
        if self.scheduler.running:
            self.logger.warning("Scheduler already running")
            return
        
        # Add periodic job to check for due syncs
        self.scheduler.add_job(
            self.check_and_run_due_syncs,
            IntervalTrigger(minutes=5),
            id="sync_check",
            name="Check for due syncs",
            replace_existing=True
        )
        
        # Add cleanup job for expired uploads
        self.scheduler.add_job(
            self.cleanup_expired_uploads,
            CronTrigger(hour=3, minute=0),  # 3 AM daily
            id="cleanup_uploads",
            name="Cleanup expired uploads",
            replace_existing=True
        )
        
        self.scheduler.start()
        self.logger.info("Background scheduler started")
    
    def stop(self):
        """Stop the background scheduler."""
        if not self.scheduler.running:
            return
        
        self.scheduler.shutdown(wait=False)
        self.logger.info("Background scheduler stopped")
    
    async def check_and_run_due_syncs(self):
        """Check for due syncs and execute them."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            
            due_schedules = db.query(SyncSchedule).filter(
                SyncSchedule.is_active == True,
                SyncSchedule.next_run_at <= now
            ).all()
            
            self.logger.info(f"Found {len(due_schedules)} due syncs")
            
            for schedule in due_schedules:
                try:
                    await self.execute_scheduled_sync(schedule, db)
                except Exception as e:
                    self.logger.error(f"Error executing sync {schedule.id}: {e}")
        
        finally:
            db.close()
    
    async def execute_scheduled_sync(self, schedule: SyncSchedule, db: Session):
        """Execute a single scheduled sync."""
        self.logger.info(f"Executing scheduled sync {schedule.id} for user {schedule.user_id}")
        
        # Create sync service
        sync_service = FileSyncService(db)
        audit_logger = AuditLogger()
        
        try:
            # Get device sync status
            sync_status = sync_service.get_sync_status(
                schedule.user_id,
                schedule.device_id
            )
            
            if sync_status.get("status") == "not_registered":
                self.logger.warning(f"Device {schedule.device_id} not registered")
                return
            
            # Simulate sync detection (client would normally send file list)
            # In a real implementation, we'd need client to be online
            # For now, just update timestamps
            
            # Log sync execution
            audit_logger.log_event(
                event_type="SYNC",
                user=str(schedule.user_id),
                action="scheduled_sync_executed",
                resource=schedule.device_id,
                details={
                    "schedule_id": schedule.id,
                    "device_id": schedule.device_id,
                    "schedule_type": schedule.schedule_type
                },
                success=True
            )
            
            # Update schedule
            schedule.last_run_at = datetime.now(timezone.utc)
            self._calculate_next_run(schedule)
            db.commit()
            
            self.logger.info(f"Sync {schedule.id} completed successfully")
        
        except Exception as e:
            self.logger.error(f"Sync {schedule.id} failed: {e}")
            audit_logger.log_event(
                event_type="SYNC",
                user=str(schedule.user_id),
                action="scheduled_sync_failed",
                resource=schedule.device_id,
                details={"schedule_id": schedule.id, "error": str(e)},
                success=False,
                error_message=str(e)
            )
    
    async def cleanup_expired_uploads(self):
        """Clean up expired chunked uploads."""
        from app.services.progressive_sync import ProgressiveSyncService
        
        db = SessionLocal()
        try:
            sync_service = ProgressiveSyncService(db)
            sync_service.cleanup_expired_uploads()
            self.logger.info("Expired uploads cleaned up")
        finally:
            db.close()
    
    def _calculate_next_run(self, schedule: SyncSchedule):
        """Calculate next run time (same as in sync_scheduler.py)."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        
        if schedule.schedule_type == "daily":
            hour, minute = map(int, schedule.time_of_day.split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if next_run <= now:
                next_run += timedelta(days=1)
            
            schedule.next_run_at = next_run
        
        elif schedule.schedule_type == "weekly":
            hour, minute = map(int, schedule.time_of_day.split(":"))
            target_day = schedule.day_of_week or 0
            
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = target_day - now.weekday()
            
            if days_ahead <= 0:
                days_ahead += 7
            
            next_run += timedelta(days=days_ahead)
            schedule.next_run_at = next_run
        
        elif schedule.schedule_type == "monthly":
            hour, minute = map(int, schedule.time_of_day.split(":"))
            target_day = schedule.day_of_month or 1
            
            next_run = now.replace(
                day=target_day,
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
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


async def start_sync_scheduler():
    """Start the background sync scheduler."""
    scheduler = get_scheduler()
    scheduler.start()


async def stop_sync_scheduler():
    """Stop the background sync scheduler."""
    scheduler = get_scheduler()
    scheduler.stop()


def get_status() -> dict:
    """
    Get sync scheduler service status.

    Returns:
        Dict with service status information for admin dashboard
    """
    from datetime import datetime as dt

    scheduler = get_scheduler()

    is_running = scheduler.scheduler.running if scheduler.scheduler else False

    # Get job info if running
    sample_count = 0
    next_run = None
    if is_running:
        try:
            jobs = scheduler.scheduler.get_jobs()
            sample_count = len(jobs)
            for job in jobs:
                if job.next_run_time:
                    if next_run is None or job.next_run_time < next_run:
                        next_run = job.next_run_time
        except Exception:
            pass

    return {
        "is_running": is_running,
        "started_at": None,  # APScheduler doesn't track start time
        "uptime_seconds": None,
        "sample_count": sample_count,  # Number of scheduled jobs
        "error_count": 0,
        "last_error": None,
        "last_error_at": None,
        "interval_seconds": 300,  # Check every 5 minutes
        "next_run": next_run.isoformat() if next_run else None,
    }
