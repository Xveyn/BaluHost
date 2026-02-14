"""
Unified Scheduler Service for BaluHost.

Manages all system schedulers with:
- Execution history tracking
- Run-now functionality (fire-and-forget via DB)
- Configuration updates
- Status monitoring (reads scheduler_state table written by worker)
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

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
from app.models.scheduler_state import SchedulerState
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

# Max age (seconds) for a worker heartbeat to be considered healthy
WORKER_HEARTBEAT_MAX_AGE = 60


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


def _is_worker_healthy(state: Optional[SchedulerState]) -> Optional[bool]:
    """Check if the worker heartbeat is recent enough."""
    if state is None or state.last_heartbeat is None:
        return None
    age = (datetime.now(timezone.utc) - state.last_heartbeat).total_seconds()
    return age < WORKER_HEARTBEAT_MAX_AGE


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
        # Read state from scheduler_state table (written by worker process)
        state = (
            self.db.query(SchedulerState)
            .filter(SchedulerState.scheduler_name == name)
            .first()
        )

        worker_healthy = _is_worker_healthy(state)
        is_running = state.is_running if state else False
        is_enabled = self._check_scheduler_enabled(name)
        interval = self._get_scheduler_interval(name, info)

        # next_run_at from worker state (accurate, from APScheduler)
        next_run_at = state.next_run_at if state else None

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

        # Load extra_config from DB
        db_config = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.scheduler_name == name)
            .first()
        )
        extra_config = None
        if db_config and db_config.extra_config:
            try:
                extra_config = json.loads(db_config.extra_config)
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback: estimate next_run_at if worker hasn't written state yet
        if next_run_at is None and is_enabled and last_run_at:
            next_run_at = last_run_at + timedelta(seconds=interval)

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
            extra_config=extra_config,
            worker_healthy=worker_healthy,
        )

    def _check_scheduler_enabled(self, name: str) -> bool:
        """Check if a scheduler is enabled — reads DB config with settings fallback."""
        # Check DB config first (source of truth for toggle)
        config = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.scheduler_name == name)
            .first()
        )
        if config is not None:
            return config.is_enabled

        # Fall back to settings
        if name == "raid_scrub":
            return getattr(settings, "raid_scrub_enabled", False)
        elif name == "smart_scan":
            return getattr(settings, "smart_scan_enabled", False)
        elif name == "backup":
            return getattr(settings, "backup_auto_enabled", False)
        elif name in ("sync_check", "upload_cleanup", "notification_check"):
            return True

        return True

    def _get_scheduler_interval(self, name: str, info: dict[str, Any]) -> int:
        """Get the current interval for a scheduler in seconds."""
        # Check DB config first
        config = (
            self.db.query(SchedulerConfig)
            .filter(SchedulerConfig.scheduler_name == name)
            .first()
        )
        if config and config.interval_seconds:
            return config.interval_seconds

        # Fall back to settings / defaults
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
            return 300
        elif name == "notification_check":
            return 3600
        elif name == "upload_cleanup":
            return 86400

        return info.get("default_interval", 3600)

    async def run_scheduler_now(
        self, name: str, user_id: int, force: bool = False
    ) -> RunNowResponse:
        """
        Trigger a scheduler to run immediately.

        Creates a "requested" execution row in the DB.
        The worker process polls for these and executes them.
        Returns immediately (fire-and-forget).
        """
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

        # Check if already running or requested (unless force)
        if not force:
            active_exec = (
                self.db.query(SchedulerExecution)
                .filter(
                    SchedulerExecution.scheduler_name == name,
                    SchedulerExecution.status.in_([
                        SchedulerStatus.RUNNING.value,
                        SchedulerStatus.REQUESTED.value,
                    ]),
                )
                .first()
            )
            if active_exec:
                return RunNowResponse(
                    success=False,
                    message=f"{info['display_name']} is already {'running' if active_exec.status == SchedulerStatus.RUNNING.value else 'requested'}",
                    execution_id=active_exec.id,
                    scheduler_name=name,
                    status="already_running",
                )

        # Create execution record with status="requested"
        execution = SchedulerExecution(
            scheduler_name=name,
            trigger_type=TriggerType.MANUAL.value,
            user_id=user_id,
            started_at=datetime.now(timezone.utc),
            status=SchedulerStatus.REQUESTED.value,
        )
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)

        logger.info("Scheduler %s run requested (execution_id=%d, user=%d)", name, execution.id, user_id)

        return RunNowResponse(
            success=True,
            message=f"{info['display_name']} run requested — worker will pick it up shortly",
            execution_id=execution.id,
            scheduler_name=name,
            status="requested",
        )

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
        """Enable or disable a scheduler.

        Writes to scheduler_configs in DB. The worker process polls for
        config changes and adjusts its APScheduler jobs accordingly.
        """
        if name not in SCHEDULER_REGISTRY:
            return SchedulerToggleResponse(
                success=False,
                scheduler_name=name,
                is_enabled=False,
                message=f"Unknown scheduler: {name}",
            )

        info = SCHEDULER_REGISTRY[name]

        # Update DB config (worker polls this)
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

        return SchedulerToggleResponse(
            success=True,
            scheduler_name=name,
            is_enabled=enabled,
            message=f"{info['display_name']} {'enabled' if enabled else 'disabled'}",
        )

    def update_scheduler_config(
        self,
        name: str,
        interval_seconds: Optional[int],
        is_enabled: Optional[bool],
        user_id: int,
        extra_config: Optional[dict] = None,
    ) -> bool:
        """Update scheduler configuration.

        Changes are written to DB and the worker picks them up
        on its next config check cycle.
        """
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
            if extra_config is not None:
                config.extra_config = json.dumps(extra_config)
            self.db.add(config)
        else:
            if interval_seconds is not None:
                config.interval_seconds = interval_seconds
            if is_enabled is not None:
                config.is_enabled = is_enabled
            if extra_config is not None:
                config.extra_config = json.dumps(extra_config)
            config.updated_by = user_id

        self.db.commit()
        return True


def recover_stale_executions(db: Session) -> int:
    """Mark any RUNNING scheduler executions as FAILED after a server restart."""
    stale = (
        db.query(SchedulerExecution)
        .filter(SchedulerExecution.status == SchedulerStatus.RUNNING.value)
        .all()
    )
    if not stale:
        return 0
    now = datetime.now(timezone.utc)
    for execution in stale:
        execution.status = SchedulerStatus.FAILED.value
        execution.error_message = "Server restarted during execution"
        execution.completed_at = now
        if execution.started_at:
            delta = now - execution.started_at
            execution.duration_ms = int(delta.total_seconds() * 1000)
    db.commit()
    return len(stale)


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


def is_worker_healthy_global() -> Optional[bool]:
    """Check if the scheduler worker process is healthy (any scheduler has recent heartbeat)."""
    db = SessionLocal()
    try:
        # Check if any scheduler_state has a recent heartbeat
        states = db.query(SchedulerState).all()
        if not states:
            return None  # No state rows = worker never ran

        for state in states:
            healthy = _is_worker_healthy(state)
            if healthy:
                return True

        return False
    finally:
        db.close()
