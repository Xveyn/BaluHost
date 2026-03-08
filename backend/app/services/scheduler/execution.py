"""
Scheduler execution tracking — leaf module (no internal deps).

Provides standalone functions for logging/completing executions,
recovery after crashes, and worker health checks. These are imported
by external services (SMART, RAID scrub, backup, sync, notifications).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.scheduler_history import (
    SchedulerExecution,
    SchedulerStatus,
    TriggerType,
)
from app.models.scheduler_state import SchedulerState

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
    hb = state.last_heartbeat
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - hb).total_seconds()
    return age < WORKER_HEARTBEAT_MAX_AGE


def recover_stale_executions(db: Session) -> int:
    """Mark any RUNNING scheduler executions as CANCELLED after a server restart."""
    stale = (
        db.query(SchedulerExecution)
        .filter(SchedulerExecution.status == SchedulerStatus.RUNNING.value)
        .all()
    )
    if not stale:
        return 0
    now = datetime.now(timezone.utc)
    for execution in stale:
        execution.status = SchedulerStatus.CANCELLED.value
        execution.error_message = "Server restarted during execution"
        execution.completed_at = now
        if execution.started_at:
            started = execution.started_at if execution.started_at.tzinfo else execution.started_at.replace(tzinfo=timezone.utc)
            delta = now - started
            execution.duration_ms = int(delta.total_seconds() * 1000)
    db.commit()
    return len(stale)


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

            started = execution.started_at
            completed = execution.completed_at
            if started and completed:
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                delta = completed - started
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
