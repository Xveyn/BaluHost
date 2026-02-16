"""
Scheduler Worker Service for BaluHost.

Runs all APScheduler-based jobs in a separate process to prevent
heavy I/O (backup, RAID scrub, SMART scan) from blocking the web API.

IPC with the web process is done via the PostgreSQL/SQLite database:
- Web API writes "requested" execution rows → Worker picks them up
- Worker writes scheduler_state rows → Web API reads them for status
"""
import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.scheduler_history import (
    SchedulerExecution,
    SchedulerConfig,
    SchedulerStatus,
    TriggerType,
)
from app.models.scheduler_state import SchedulerState
from app.schemas.scheduler import SCHEDULER_REGISTRY

logger = logging.getLogger(__name__)

# Power level mapping per scheduler
SCHEDULER_POWER_LEVELS: dict[str, str] = {
    "backup": "surge",
    "raid_scrub": "surge",
    "smart_scan": "medium",
    "sync_check": "low",
    "notification_check": "idle",
    "upload_cleanup": "low",
    "auto_update": "low",
    "cloud_sync": "medium",
}

# How often to poll for requested executions (seconds)
POLL_INTERVAL = 2

# How often to update heartbeat in scheduler_state (seconds)
HEARTBEAT_INTERVAL = 10

# How often to check for config changes (seconds)
CONFIG_CHECK_INTERVAL = 15

# Max age for a "requested" row before marking it failed (seconds)
STALE_REQUESTED_TIMEOUT = 300  # 5 minutes


class SchedulerWorker:
    """Manages all APScheduler jobs in a dedicated worker process."""

    def __init__(self):
        self.scheduler: Optional[BackgroundScheduler] = None
        self.running = False
        self.pid = os.getpid()
        self._last_heartbeat = 0.0
        self._last_config_check = 0.0
        self._executing_scheduler: Optional[str] = None
        # Track which schedulers are enabled (to detect config changes)
        self._enabled_cache: dict[str, bool] = {}
        self._interval_cache: dict[str, int] = {}

    def start(self) -> None:
        """Initialize the APScheduler and start all configured jobs."""
        logger.info("Scheduler worker starting (PID=%d)", self.pid)

        # Recover stale executions from a previous crash
        self._recover_stale_executions()

        # Initialize APScheduler
        self.scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            }
        )

        # Load config from DB and add jobs
        self._load_and_schedule_jobs()

        self.scheduler.start()
        self.running = True

        # Write initial state
        self._update_all_heartbeats()

        logger.info("Scheduler worker started with %d jobs", len(self.scheduler.get_jobs()))

    def run_loop(self) -> None:
        """Main loop: poll for requested executions and update heartbeats."""
        while self.running:
            now = time.monotonic()

            # Poll for "requested" execution rows
            try:
                self._poll_requested_executions()
            except Exception:
                logger.exception("Error polling requested executions")

            # Update heartbeats periodically
            if now - self._last_heartbeat >= HEARTBEAT_INTERVAL:
                try:
                    self._update_all_heartbeats()
                except Exception:
                    logger.exception("Error updating heartbeats")
                self._last_heartbeat = now

            # Check for config changes periodically
            if now - self._last_config_check >= CONFIG_CHECK_INTERVAL:
                try:
                    self._check_config_changes()
                except Exception:
                    logger.exception("Error checking config changes")
                self._last_config_check = now

            time.sleep(POLL_INTERVAL)

    def shutdown(self) -> None:
        """Graceful shutdown: cancel running jobs, clear state."""
        logger.info("Scheduler worker shutting down...")
        self.running = False

        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        # Mark any currently executing job as cancelled
        if self._executing_scheduler:
            self._cancel_running_executions(self._executing_scheduler)

        # Clear all scheduler_state rows
        self._clear_all_state()

        logger.info("Scheduler worker shutdown complete")

    # ─── Job Dispatching ─────────────────────────────────────────

    def _poll_requested_executions(self) -> None:
        """Check for execution rows with status='requested' and run them."""
        db = SessionLocal()
        try:
            requested = (
                db.query(SchedulerExecution)
                .filter(SchedulerExecution.status == SchedulerStatus.REQUESTED.value)
                .order_by(SchedulerExecution.started_at)
                .all()
            )

            for execution in requested:
                name = execution.scheduler_name
                if name not in SCHEDULER_REGISTRY:
                    execution.status = SchedulerStatus.FAILED.value
                    execution.error_message = f"Unknown scheduler: {name}"
                    execution.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    continue

                # Mark as running
                execution.status = SchedulerStatus.RUNNING.value
                execution.started_at = datetime.now(timezone.utc)
                db.commit()

                # Execute the job
                self._execute_job(execution.id, name)

        finally:
            db.close()

    def _register_power_demand(self, name: str) -> bool:
        """Register a power demand for the given scheduler via the backend API."""
        level = SCHEDULER_POWER_LEVELS.get(name)
        if not level or level == "idle":
            return False  # No demand needed for idle-level jobs

        try:
            import requests as http_requests

            port = settings.port
            url = f"http://127.0.0.1:{port}/api/power/demands"
            payload = {
                "source": f"scheduler:{name}",
                "level": level,
                "timeout_seconds": 3600,  # 1h safety timeout
                "description": f"Scheduler job: {name}",
            }
            headers = {"X-Service-Token": settings.scheduler_service_token}
            resp = http_requests.post(url, json=payload, headers=headers, timeout=5)
            if resp.status_code < 300:
                logger.debug("Registered power demand for %s (level=%s)", name, level)
                return True
            else:
                logger.warning(
                    "Power demand registration failed for %s: %d %s",
                    name, resp.status_code, resp.text[:200],
                )
        except Exception as e:
            logger.warning("Could not register power demand for %s: %s", name, e)
        return False

    def _unregister_power_demand(self, name: str) -> None:
        """Unregister a power demand for the given scheduler via the backend API."""
        level = SCHEDULER_POWER_LEVELS.get(name)
        if not level or level == "idle":
            return

        try:
            import requests as http_requests

            port = settings.port
            url = f"http://127.0.0.1:{port}/api/power/demands"
            payload = {"source": f"scheduler:{name}"}
            headers = {
                "X-Service-Token": settings.scheduler_service_token,
                "Content-Type": "application/json",
            }
            resp = http_requests.delete(url, json=payload, headers=headers, timeout=5)
            if resp.status_code < 300:
                logger.debug("Unregistered power demand for %s", name)
            else:
                logger.debug(
                    "Power demand unregistration returned %d for %s",
                    resp.status_code, name,
                )
        except Exception as e:
            logger.warning("Could not unregister power demand for %s: %s", name, e)

    def _execute_job(self, execution_id: int, name: str) -> None:
        """Run a scheduler job and update the execution record."""
        logger.info("Executing scheduler job: %s (execution_id=%d)", name, execution_id)

        self._executing_scheduler = name
        self._set_executing_state(name, True)
        self._register_power_demand(name)

        try:
            result = self._dispatch_job(name)

            # Mark completed
            db = SessionLocal()
            try:
                execution = db.query(SchedulerExecution).get(execution_id)
                if execution:
                    execution.status = SchedulerStatus.COMPLETED.value
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.result_summary = json.dumps(result) if result else None
                    if execution.started_at:
                        delta = execution.completed_at - execution.started_at
                        execution.duration_ms = int(delta.total_seconds() * 1000)
                    db.commit()
            finally:
                db.close()

            logger.info("Scheduler job completed: %s", name)

        except Exception as e:
            logger.exception("Scheduler job failed: %s", name)

            db = SessionLocal()
            try:
                execution = db.query(SchedulerExecution).get(execution_id)
                if execution:
                    execution.status = SchedulerStatus.FAILED.value
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.error_message = str(e)
                    if execution.started_at:
                        delta = execution.completed_at - execution.started_at
                        execution.duration_ms = int(delta.total_seconds() * 1000)
                    db.commit()
            finally:
                db.close()

        finally:
            self._unregister_power_demand(name)
            self._executing_scheduler = None
            self._set_executing_state(name, False)

    def _dispatch_job(self, name: str) -> Optional[dict]:
        """Dispatch to the appropriate job function. Returns result dict or None."""
        if name == "raid_scrub":
            from app.services.raid import scrub_now
            result = scrub_now(None)
            return {"message": result.message}

        elif name == "smart_scan":
            from app.services.smart import invalidate_smart_cache, get_smart_status
            invalidate_smart_cache()
            status = get_smart_status()
            return {
                "disks_scanned": len(status.devices) if status else 0,
                "overall_status": (
                    "all_passed"
                    if status and all(d.status == "PASSED" for d in status.devices)
                    else "issues_detected"
                )
                if status
                else "unknown",
            }

        elif name == "backup":
            from app.services.backup.scheduler import BackupScheduler
            db = SessionLocal()
            try:
                stats = BackupScheduler.create_automated_backup(db)
                return stats
            finally:
                db.close()

        elif name == "sync_check":
            loop = asyncio.new_event_loop()
            try:
                from app.services.sync_background import get_scheduler
                scheduler = get_scheduler()
                loop.run_until_complete(scheduler.check_and_run_due_syncs())
                return {"checked": True}
            finally:
                loop.close()

        elif name == "notification_check":
            from app.services.notifications.scheduler import NotificationScheduler
            NotificationScheduler.run_periodic_check()
            return {"checked": True}

        elif name == "upload_cleanup":
            loop = asyncio.new_event_loop()
            try:
                from app.services.sync_background import get_scheduler
                scheduler = get_scheduler()
                loop.run_until_complete(scheduler.cleanup_expired_uploads())
                return {"cleaned": True}
            finally:
                loop.close()

        elif name == "auto_update":
            # Auto-update check is on-demand only, not periodic
            return {"checked": True}

        elif name == "cloud_sync":
            from app.services.cloud.scheduler import CloudSyncScheduler
            db = SessionLocal()
            try:
                return CloudSyncScheduler.run_sync(db)
            finally:
                db.close()

        return None

    # ─── APScheduler Job Callbacks ────────────────────────────────

    def _create_scheduled_callback(self, scheduler_name: str):
        """Create a callback for APScheduler periodic jobs."""
        from app.services.scheduler_service import (
            log_scheduler_execution,
            complete_scheduler_execution,
        )

        def callback():
            execution_id = log_scheduler_execution(
                scheduler_name, job_id=f"{scheduler_name}_periodic"
            )
            self._executing_scheduler = scheduler_name
            self._set_executing_state(scheduler_name, True)
            self._register_power_demand(scheduler_name)

            try:
                result = self._dispatch_job(scheduler_name)
                complete_scheduler_execution(
                    execution_id, success=True, result=result
                )
                logger.info("Scheduled job completed: %s", scheduler_name)
            except Exception as e:
                logger.exception("Scheduled job failed: %s", scheduler_name)
                complete_scheduler_execution(
                    execution_id, success=False, error=str(e)
                )
            finally:
                self._unregister_power_demand(scheduler_name)
                self._executing_scheduler = None
                self._set_executing_state(scheduler_name, False)

        return callback

    # ─── Job Loading & Config ─────────────────────────────────────

    def _load_and_schedule_jobs(self) -> None:
        """Load scheduler configs from DB and register APScheduler jobs."""
        db = SessionLocal()
        try:
            for name, info in SCHEDULER_REGISTRY.items():
                is_enabled = self._is_scheduler_enabled(name, db)
                interval = self._get_interval(name, info, db)

                self._enabled_cache[name] = is_enabled
                self._interval_cache[name] = interval

                if not is_enabled:
                    logger.info("Scheduler %s is disabled, skipping", name)
                    continue

                self._add_job(name, interval)

        finally:
            db.close()

    def _add_job(self, name: str, interval_seconds: int) -> None:
        """Add or replace a job in APScheduler."""
        if not self.scheduler:
            return

        callback = self._create_scheduled_callback(name)

        # Convert interval to appropriate trigger kwargs
        if interval_seconds >= 86400:
            trigger_kwargs = {"hours": interval_seconds // 3600}
        elif interval_seconds >= 3600:
            trigger_kwargs = {"hours": interval_seconds // 3600}
        elif interval_seconds >= 60:
            trigger_kwargs = {"minutes": interval_seconds // 60}
        else:
            trigger_kwargs = {"seconds": interval_seconds}

        self.scheduler.add_job(
            func=callback,
            trigger="interval",
            id=name,
            name=f"Scheduled: {name}",
            replace_existing=True,
            **trigger_kwargs,
        )

        logger.info("Scheduled job: %s (every %ds)", name, interval_seconds)

    def _remove_job(self, name: str) -> None:
        """Remove a job from APScheduler."""
        if not self.scheduler:
            return
        try:
            self.scheduler.remove_job(name)
            logger.info("Removed job: %s", name)
        except Exception:
            pass  # Job may not exist

    def _is_scheduler_enabled(self, name: str, db) -> bool:
        """Check if scheduler is enabled via DB config or settings."""
        # Check DB config first
        config = (
            db.query(SchedulerConfig)
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
        elif name == "auto_update":
            return getattr(settings, "auto_update_check_enabled", True)
        elif name == "cloud_sync":
            return getattr(settings, "cloud_import_enabled", True)

        return True

    def _get_interval(self, name: str, info: dict, db) -> int:
        """Get interval for a scheduler from DB config or settings."""
        # Check DB config first
        config = (
            db.query(SchedulerConfig)
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
        elif name == "auto_update":
            return 86400
        elif name == "cloud_sync":
            return 3600

        return info.get("default_interval", 3600)

    def _check_config_changes(self) -> None:
        """Poll DB for config changes and adjust jobs accordingly."""
        if not self.scheduler:
            return

        db = SessionLocal()
        try:
            for name, info in SCHEDULER_REGISTRY.items():
                new_enabled = self._is_scheduler_enabled(name, db)
                new_interval = self._get_interval(name, info, db)

                old_enabled = self._enabled_cache.get(name)
                old_interval = self._interval_cache.get(name)

                if new_enabled != old_enabled:
                    if new_enabled:
                        logger.info("Scheduler %s enabled via config", name)
                        self._add_job(name, new_interval)
                    else:
                        logger.info("Scheduler %s disabled via config", name)
                        self._remove_job(name)
                    self._enabled_cache[name] = new_enabled

                elif new_enabled and new_interval != old_interval:
                    logger.info(
                        "Scheduler %s interval changed: %ds → %ds",
                        name, old_interval or 0, new_interval,
                    )
                    self._add_job(name, new_interval)

                self._interval_cache[name] = new_interval

        finally:
            db.close()

    # ─── State Management ─────────────────────────────────────────

    def _update_all_heartbeats(self) -> None:
        """Write heartbeat and next_run_at for all schedulers to scheduler_state."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)

            for name in SCHEDULER_REGISTRY:
                is_running = self._enabled_cache.get(name, False)
                is_executing = self._executing_scheduler == name

                # Get next_run_at from APScheduler
                next_run_at = None
                if self.scheduler and is_running:
                    try:
                        job = self.scheduler.get_job(name)
                        if job and job.next_run_time:
                            next_run_at = job.next_run_time
                    except Exception:
                        pass

                # Upsert scheduler_state
                state = (
                    db.query(SchedulerState)
                    .filter(SchedulerState.scheduler_name == name)
                    .first()
                )
                if state is None:
                    state = SchedulerState(
                        scheduler_name=name,
                        is_running=is_running,
                        is_executing=is_executing,
                        next_run_at=next_run_at,
                        last_heartbeat=now,
                        worker_pid=self.pid,
                    )
                    db.add(state)
                else:
                    state.is_running = is_running
                    state.is_executing = is_executing
                    state.next_run_at = next_run_at
                    state.last_heartbeat = now
                    state.worker_pid = self.pid

            db.commit()
        finally:
            db.close()

    def _set_executing_state(self, name: str, is_executing: bool) -> None:
        """Update the is_executing flag for a specific scheduler."""
        db = SessionLocal()
        try:
            state = (
                db.query(SchedulerState)
                .filter(SchedulerState.scheduler_name == name)
                .first()
            )
            if state:
                state.is_executing = is_executing
                state.last_heartbeat = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    def _clear_all_state(self) -> None:
        """Clear all scheduler_state rows on shutdown."""
        db = SessionLocal()
        try:
            db.query(SchedulerState).filter(
                SchedulerState.worker_pid == self.pid
            ).update({
                SchedulerState.is_running: False,
                SchedulerState.is_executing: False,
                SchedulerState.last_heartbeat: None,
                SchedulerState.worker_pid: None,
                SchedulerState.next_run_at: None,
            })
            db.commit()
        finally:
            db.close()

    # ─── Recovery ─────────────────────────────────────────────────

    def _recover_stale_executions(self) -> None:
        """Mark stale RUNNING and REQUESTED executions as FAILED after restart."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)

            # Recover RUNNING executions
            stale_running = (
                db.query(SchedulerExecution)
                .filter(SchedulerExecution.status == SchedulerStatus.RUNNING.value)
                .all()
            )
            for execution in stale_running:
                execution.status = SchedulerStatus.FAILED.value
                execution.error_message = "Worker restarted during execution"
                execution.completed_at = now
                if execution.started_at:
                    delta = now - execution.started_at
                    execution.duration_ms = int(delta.total_seconds() * 1000)

            # Recover stale REQUESTED executions (>5 min old)
            cutoff = now - timedelta(seconds=STALE_REQUESTED_TIMEOUT)
            stale_requested = (
                db.query(SchedulerExecution)
                .filter(
                    SchedulerExecution.status == SchedulerStatus.REQUESTED.value,
                    SchedulerExecution.started_at < cutoff,
                )
                .all()
            )
            for execution in stale_requested:
                execution.status = SchedulerStatus.FAILED.value
                execution.error_message = "Request expired (worker was not running)"
                execution.completed_at = now
                if execution.started_at:
                    delta = now - execution.started_at
                    execution.duration_ms = int(delta.total_seconds() * 1000)

            total = len(stale_running) + len(stale_requested)
            if total:
                db.commit()
                logger.info(
                    "Recovered %d stale execution(s) (%d running, %d requested)",
                    total, len(stale_running), len(stale_requested),
                )

            # Clear stale scheduler_state from previous worker
            db.query(SchedulerState).update({
                SchedulerState.is_running: False,
                SchedulerState.is_executing: False,
                SchedulerState.last_heartbeat: None,
                SchedulerState.worker_pid: None,
                SchedulerState.next_run_at: None,
            })
            db.commit()

        finally:
            db.close()

    def _cancel_running_executions(self, scheduler_name: str) -> None:
        """Mark any RUNNING execution for the given scheduler as cancelled."""
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            running = (
                db.query(SchedulerExecution)
                .filter(
                    SchedulerExecution.scheduler_name == scheduler_name,
                    SchedulerExecution.status == SchedulerStatus.RUNNING.value,
                )
                .all()
            )
            for execution in running:
                execution.status = SchedulerStatus.CANCELLED.value
                execution.completed_at = now
                execution.error_message = "Worker shutdown during execution"
                if execution.started_at:
                    delta = now - execution.started_at
                    execution.duration_ms = int(delta.total_seconds() * 1000)
            if running:
                db.commit()
        finally:
            db.close()
