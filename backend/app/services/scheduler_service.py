"""
Unified Scheduler Service for BaluHost.

Manages all system schedulers with:
- Execution history tracking
- Run-now functionality
- Configuration updates
- Status monitoring
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Any

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.scheduler_history import (
    SchedulerExecution,
    SchedulerConfig,
    SchedulerStatus,
    TriggerType,
)
from app.schemas.scheduler import (
    SchedulerStatusResponse,
    SchedulerListResponse,
    SchedulerExecutionResponse,
    SchedulerHistoryResponse,
    RunNowResponse,
    SchedulerToggleResponse,
    SCHEDULER_REGISTRY,
)

logger = logging.getLogger(__name__)


def _format_interval(seconds: int) -> str:
    """Convert seconds to human-readable interval."""
    if seconds < 60:
        return f"Every {seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"Every {minutes} min" if minutes > 1 else "Every minute"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"Every {hours}h" if hours > 1 else "Every hour"
    else:
        days = seconds // 86400
        return f"Every {days} days" if days > 1 else "Daily"


class SchedulerService:
    """Service for managing all system schedulers."""

    def __init__(self, db: Session):
        self.db = db

    def get_all_schedulers(self) -> SchedulerListResponse:
        """Get status of all registered schedulers."""
        schedulers = []

        for name, info in SCHEDULER_REGISTRY.items():
            status = self._get_scheduler_status(name, info)
            schedulers.append(status)

        running = sum(1 for s in schedulers if s.is_running)
        enabled = sum(1 for s in schedulers if s.is_enabled)

        return SchedulerListResponse(
            schedulers=schedulers,
            total_running=running,
            total_enabled=enabled,
        )

    def get_scheduler(self, name: str) -> Optional[SchedulerStatusResponse]:
        """Get status of a specific scheduler."""
        if name not in SCHEDULER_REGISTRY:
            return None

        info = SCHEDULER_REGISTRY[name]
        return self._get_scheduler_status(name, info)

    def _get_scheduler_status(
        self, name: str, info: dict[str, Any]
    ) -> SchedulerStatusResponse:
        """Build status response for a scheduler."""
        # Get runtime status
        is_running = self._check_scheduler_running(name)
        is_enabled = self._check_scheduler_enabled(name)
        interval = self._get_scheduler_interval(name, info)

        # Get last execution from DB
        last_exec = (
            self.db.query(SchedulerExecution)
            .filter(SchedulerExecution.scheduler_name == name)
            .order_by(desc(SchedulerExecution.started_at))
            .first()
        )

        last_run_at = last_exec.started_at if last_exec else None
        last_status = last_exec.status if last_exec else None
        last_error = last_exec.error_message if last_exec else None
        last_duration = last_exec.duration_ms if last_exec else None

        # Calculate next run time
        next_run_at = None
        if is_running and is_enabled and last_run_at:
            next_run_at = last_run_at + timedelta(seconds=interval)
        elif is_running and is_enabled:
            # No last run, estimate from now
            next_run_at = datetime.now(timezone.utc) + timedelta(seconds=interval)

        return SchedulerStatusResponse(
            name=name,
            display_name=info["display_name"],
            description=info["description"],
            is_running=is_running,
            is_enabled=is_enabled,
            interval_seconds=interval,
            interval_display=_format_interval(interval),
            last_run_at=last_run_at,
            next_run_at=next_run_at,
            last_status=last_status,
            last_error=last_error,
            last_duration_ms=last_duration,
            config_key=info.get("config_key"),
            can_run_manually=info.get("can_run_manually", True),
        )

    def _check_scheduler_running(self, name: str) -> bool:
        """Check if a scheduler's background job is currently running."""
        try:
            if name == "raid_scrub":
                from app.services.raid import _scrub_scheduler
                return _scrub_scheduler is not None and _scrub_scheduler.running

            elif name == "smart_scan":
                from app.services.smart import _smart_scheduler
                return _smart_scheduler is not None and _smart_scheduler.running

            elif name == "backup":
                from app.services.backup.scheduler import _backup_scheduler
                return _backup_scheduler is not None and _backup_scheduler.running

            elif name == "sync_check":
                from app.services.sync_background import get_scheduler
                scheduler = get_scheduler()
                return scheduler.scheduler.running if scheduler.scheduler else False

            elif name == "notification_check":
                from app.services.notifications.scheduler import _notification_scheduler
                return _notification_scheduler is not None and _notification_scheduler.running

            elif name == "upload_cleanup":
                # Upload cleanup is part of sync_check scheduler
                from app.services.sync_background import get_scheduler
                scheduler = get_scheduler()
                return scheduler.scheduler.running if scheduler.scheduler else False

        except Exception as e:
            logger.warning(f"Error checking scheduler {name} status: {e}")

        return False

    def _check_scheduler_enabled(self, name: str) -> bool:
        """Check if a scheduler is enabled in configuration."""
        if name == "raid_scrub":
            return getattr(settings, "raid_scrub_enabled", False)
        elif name == "smart_scan":
            return getattr(settings, "smart_scan_enabled", False)
        elif name == "backup":
            return getattr(settings, "backup_auto_enabled", False)
        elif name in ("sync_check", "upload_cleanup", "notification_check"):
            # These are always enabled when running
            return True

        # Check DB config as fallback
        config = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.scheduler_name == name)
            .first()
        )
        return config.is_enabled if config else True

    def _get_scheduler_interval(self, name: str, info: dict[str, Any]) -> int:
        """Get the current interval for a scheduler in seconds."""
        if name == "raid_scrub":
            hours = getattr(settings, "raid_scrub_interval_hours", 168)
            return hours * 3600
        elif name == "smart_scan":
            minutes = getattr(settings, "smart_scan_interval_minutes", 60)
            return minutes * 60
        elif name == "backup":
            hours = getattr(settings, "backup_auto_interval_hours", 24)
            return hours * 3600
        elif name == "sync_check":
            return 300  # 5 minutes
        elif name == "notification_check":
            return 3600  # 1 hour
        elif name == "upload_cleanup":
            return 86400  # Daily

        return info.get("default_interval", 3600)

    def run_scheduler_now(
        self, name: str, user_id: int, force: bool = False
    ) -> RunNowResponse:
        """Trigger a scheduler to run immediately."""
        if name not in SCHEDULER_REGISTRY:
            return RunNowResponse(
                success=False,
                message=f"Unknown scheduler: {name}",
                scheduler_name=name,
                status="error",
            )

        info = SCHEDULER_REGISTRY[name]

        if not info.get("can_run_manually", True):
            return RunNowResponse(
                success=False,
                message=f"Scheduler {info['display_name']} cannot be run manually",
                scheduler_name=name,
                status="error",
            )

        # Check if already running (unless force)
        if not force:
            running_exec = (
                self.db.query(SchedulerExecution)
                .filter(
                    SchedulerExecution.scheduler_name == name,
                    SchedulerExecution.status == SchedulerStatus.RUNNING.value,
                )
                .first()
            )
            if running_exec:
                return RunNowResponse(
                    success=False,
                    message=f"{info['display_name']} is already running",
                    execution_id=running_exec.id,
                    scheduler_name=name,
                    status="already_running",
                )

        # Create execution record
        execution = SchedulerExecution(
            scheduler_name=name,
            trigger_type=TriggerType.MANUAL.value,
            user_id=user_id,
            started_at=datetime.now(timezone.utc),
            status=SchedulerStatus.RUNNING.value,
        )
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)

        # Execute the scheduler job
        try:
            result = self._execute_scheduler(name)
            execution.status = SchedulerStatus.COMPLETED.value
            execution.completed_at = datetime.now(timezone.utc)
            execution.result_summary = json.dumps(result) if result else None

            if execution.started_at:
                delta = execution.completed_at - execution.started_at
                execution.duration_ms = int(delta.total_seconds() * 1000)

            self.db.commit()

            return RunNowResponse(
                success=True,
                message=f"{info['display_name']} completed successfully",
                execution_id=execution.id,
                scheduler_name=name,
                status="started",
            )

        except Exception as e:
            logger.exception(f"Error running scheduler {name}: {e}")
            execution.status = SchedulerStatus.FAILED.value
            execution.completed_at = datetime.now(timezone.utc)
            execution.error_message = str(e)

            if execution.started_at:
                delta = execution.completed_at - execution.started_at
                execution.duration_ms = int(delta.total_seconds() * 1000)

            self.db.commit()

            return RunNowResponse(
                success=False,
                message=f"{info['display_name']} failed: {str(e)}",
                execution_id=execution.id,
                scheduler_name=name,
                status="error",
            )

    def _execute_scheduler(self, name: str) -> Optional[dict]:
        """Execute the actual scheduler job."""
        if name == "raid_scrub":
            from app.services.raid import scrub_now
            result = scrub_now(None)
            return {"message": result.message}

        elif name == "smart_scan":
            from app.services.smart import invalidate_smart_cache, get_smart_status
            invalidate_smart_cache()
            status = get_smart_status()
            return {
                "disks_scanned": len(status.disks) if status else 0,
                "overall_status": status.overall_status if status else "unknown",
            }

        elif name == "backup":
            from app.services.backup.scheduler import BackupScheduler
            stats = BackupScheduler.create_automated_backup(self.db)
            return stats

        elif name == "sync_check":
            from app.services.sync_background import get_scheduler
            scheduler = get_scheduler()
            # Run synchronously for manual trigger
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(scheduler.check_and_run_due_syncs())
            finally:
                loop.close()
            return {"checked": True}

        elif name == "notification_check":
            from app.services.notifications.scheduler import NotificationScheduler
            NotificationScheduler.run_periodic_check()
            return {"checked": True}

        elif name == "upload_cleanup":
            from app.services.sync_background import get_scheduler
            scheduler = get_scheduler()
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(scheduler.cleanup_expired_uploads())
            finally:
                loop.close()
            return {"cleaned": True}

        return None

    def get_scheduler_history(
        self,
        name: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[str] = None,
    ) -> SchedulerHistoryResponse:
        """Get paginated execution history."""
        query = self.db.query(SchedulerExecution)

        if name:
            query = query.filter(SchedulerExecution.scheduler_name == name)

        if status_filter:
            query = query.filter(SchedulerExecution.status == status_filter)

        total = query.count()
        total_pages = (total + page_size - 1) // page_size

        executions = (
            query.order_by(desc(SchedulerExecution.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return SchedulerHistoryResponse(
            executions=[
                SchedulerExecutionResponse.from_db(e) for e in executions
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def toggle_scheduler(
        self, name: str, enabled: bool, user_id: int
    ) -> SchedulerToggleResponse:
        """Enable or disable a scheduler."""
        if name not in SCHEDULER_REGISTRY:
            return SchedulerToggleResponse(
                success=False,
                scheduler_name=name,
                is_enabled=False,
                message=f"Unknown scheduler: {name}",
            )

        info = SCHEDULER_REGISTRY[name]

        # Update DB config
        config = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.scheduler_name == name)
            .first()
        )

        if not config:
            config = SchedulerConfig(
                scheduler_name=name,
                is_enabled=enabled,
                interval_seconds=self._get_scheduler_interval(name, info),
                updated_by=user_id,
            )
            self.db.add(config)
        else:
            config.is_enabled = enabled
            config.updated_by = user_id

        self.db.commit()

        # Try to start/stop the actual scheduler
        try:
            if enabled:
                self._start_scheduler(name)
            else:
                self._stop_scheduler(name)
        except Exception as e:
            logger.warning(f"Could not toggle scheduler {name}: {e}")

        return SchedulerToggleResponse(
            success=True,
            scheduler_name=name,
            is_enabled=enabled,
            message=f"{info['display_name']} {'enabled' if enabled else 'disabled'}",
        )

    def _start_scheduler(self, name: str) -> None:
        """Start a scheduler's background job."""
        if name == "raid_scrub":
            from app.services.raid import start_scrub_scheduler
            start_scrub_scheduler()
        elif name == "smart_scan":
            from app.services.smart import start_smart_scheduler
            start_smart_scheduler()
        elif name == "backup":
            from app.services.backup.scheduler import start_backup_scheduler
            start_backup_scheduler()
        elif name == "sync_check":
            from app.services.sync_background import get_scheduler
            scheduler = get_scheduler()
            scheduler.start()
        elif name == "notification_check":
            from app.services.notifications.scheduler import start_notification_scheduler
            start_notification_scheduler()

    def _stop_scheduler(self, name: str) -> None:
        """Stop a scheduler's background job."""
        if name == "raid_scrub":
            from app.services.raid import stop_scrub_scheduler
            stop_scrub_scheduler()
        elif name == "smart_scan":
            from app.services.smart import stop_smart_scheduler
            stop_smart_scheduler()
        elif name == "backup":
            from app.services.backup.scheduler import stop_backup_scheduler
            stop_backup_scheduler()
        elif name == "sync_check":
            from app.services.sync_background import get_scheduler
            scheduler = get_scheduler()
            scheduler.stop()
        elif name == "notification_check":
            from app.services.notifications.scheduler import stop_notification_scheduler
            stop_notification_scheduler()

    def update_scheduler_config(
        self,
        name: str,
        interval_seconds: Optional[int],
        is_enabled: Optional[bool],
        user_id: int,
    ) -> bool:
        """Update scheduler configuration."""
        if name not in SCHEDULER_REGISTRY:
            return False

        info = SCHEDULER_REGISTRY[name]

        config = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.scheduler_name == name)
            .first()
        )

        if not config:
            config = SchedulerConfig(
                scheduler_name=name,
                is_enabled=is_enabled if is_enabled is not None else True,
                interval_seconds=(
                    interval_seconds
                    if interval_seconds
                    else self._get_scheduler_interval(name, info)
                ),
                updated_by=user_id,
            )
            self.db.add(config)
        else:
            if interval_seconds is not None:
                config.interval_seconds = interval_seconds
            if is_enabled is not None:
                config.is_enabled = is_enabled
            config.updated_by = user_id

        self.db.commit()

        # Note: Changing interval requires scheduler restart
        # which would be handled by stopping and starting the scheduler
        return True


def get_scheduler_service(db: Session) -> SchedulerService:
    """Factory function to get scheduler service instance."""
    return SchedulerService(db)


def log_scheduler_execution(
    scheduler_name: str,
    trigger_type: str = TriggerType.SCHEDULED.value,
    job_id: Optional[str] = None,
) -> int:
    """
    Log the start of a scheduler execution.

    Called by scheduler jobs to track their executions.
    Returns the execution ID for later completion.
    """
    db = SessionLocal()
    try:
        execution = SchedulerExecution(
            scheduler_name=scheduler_name,
            job_id=job_id,
            trigger_type=trigger_type,
            started_at=datetime.now(timezone.utc),
            status=SchedulerStatus.RUNNING.value,
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        return execution.id
    finally:
        db.close()


def complete_scheduler_execution(
    execution_id: int,
    success: bool,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """
    Complete a scheduler execution.

    Called by scheduler jobs when they finish.
    """
    db = SessionLocal()
    try:
        execution = db.query(SchedulerExecution).filter(
            SchedulerExecution.id == execution_id
        ).first()

        if execution:
            execution.completed_at = datetime.now(timezone.utc)

            if success:
                execution.status = SchedulerStatus.COMPLETED.value
                execution.result_summary = json.dumps(result) if result else None
            else:
                execution.status = SchedulerStatus.FAILED.value
                execution.error_message = error

            if execution.started_at and execution.completed_at:
                delta = execution.completed_at - execution.started_at
                execution.duration_ms = int(delta.total_seconds() * 1000)

            db.commit()
    finally:
        db.close()
