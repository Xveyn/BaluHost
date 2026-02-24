from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from app.core.config import settings
from app.schemas.system import (
    RaidActionResponse,
    RaidOptionsRequest,
)

logger = logging.getLogger(__name__)

# Type-only import for annotations; runtime import uses `_APScheduler`.
if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

try:
    from apscheduler.schedulers.background import BackgroundScheduler as _APScheduler
except Exception:  # pragma: no cover - scheduler optional
    _APScheduler = None


# Scheduler for periodic RAID scrubs
_scrub_scheduler: Optional["BackgroundScheduler"] = None


def _perform_scrub_job() -> None:
    from app.services.scheduler_service import log_scheduler_execution, complete_scheduler_execution

    execution_id = log_scheduler_execution("raid_scrub", job_id="raid_scrub")
    try:
        logger.info("RAID scrub job: starting automatic scrub")
        result = scrub_now(None)
        logger.info("RAID scrub job: completed")
        complete_scheduler_execution(
            execution_id,
            success=True,
            result={"message": result.message if result else "Scrub completed"}
        )
        try:
            from app.services.notifications.events import emit_raid_scrub_complete_sync
            emit_raid_scrub_complete_sync("all", details=result.message if result else "")
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.exception("RAID scrub job failed: %s", exc)
        complete_scheduler_execution(execution_id, success=False, error=str(exc))


def scrub_now(array: str | None = None) -> RaidActionResponse:
    """Trigger an immediate scrub/check on a specific array or all arrays.

    When `array` is None, all known arrays will be triggered.
    """
    from app.services.hardware.raid.api import _backend

    # Build payload(s) using RaidOptionsRequest
    if array:
        payload = RaidOptionsRequest(array=array, trigger_scrub=True)
        return _backend.configure(payload)

    # Trigger scrub for all arrays
    status = None
    try:
        status = _backend.get_status()
    except Exception:
        # If get_status fails (e.g., no arrays), raise a clear error
        raise RuntimeError("Unable to determine RAID arrays for scrubbing")

    messages: list[str] = []
    for arr in status.arrays:
        try:
            payload = RaidOptionsRequest(array=arr.name, trigger_scrub=True)
            resp = _backend.configure(payload)
            messages.append(resp.message)
        except Exception as exc:
            logger.warning("Failed to trigger scrub on %s: %s", arr.name, exc)
            messages.append(f"{arr.name}: error: {exc}")

    return RaidActionResponse(message="; ".join(messages))


def start_scrub_scheduler() -> None:
    global _scrub_scheduler
    if not getattr(settings, "raid_scrub_enabled", False):
        logger.debug("RAID scrub scheduler disabled by settings")
        return
    if _APScheduler is None:
        logger.warning("APScheduler not available; RAID scrub scheduler skipped")
        return
    if _scrub_scheduler is not None:
        logger.debug("RAID scrub scheduler already running")
        return

    # Create scheduler (narrow type for the static analyzer)
    scheduler: "BackgroundScheduler" = _APScheduler()
    _scrub_scheduler = scheduler
    interval_hours = max(1, int(getattr(settings, "raid_scrub_interval_hours", 168)))
    scheduler.add_job(
        func=_perform_scrub_job,
        trigger="interval",
        hours=interval_hours,
        id="raid_scrub",
        name="Periodic RAID scrub",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("RAID scrub scheduler started (every %d hours)", interval_hours)


def stop_scrub_scheduler() -> None:
    global _scrub_scheduler
    if _scrub_scheduler is None:
        return
    try:
        _scrub_scheduler.shutdown(wait=False)
    except Exception:
        logger.debug("Error while shutting down RAID scrub scheduler")
    _scrub_scheduler = None


def get_scrub_scheduler_status() -> dict:
    """
    Get RAID scrub scheduler status for service status monitoring.

    Returns:
        Dict with service status information for admin dashboard
    """
    is_running = _scrub_scheduler is not None and _scrub_scheduler.running
    interval_hours = max(1, int(getattr(settings, "raid_scrub_interval_hours", 168)))

    # Get next run time if scheduler is running
    next_run = None
    if is_running:
        try:
            job = _scrub_scheduler.get_job("raid_scrub")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except Exception:
            pass

    return {
        "is_running": is_running,
        "interval_seconds": interval_hours * 3600,
        "config_enabled": getattr(settings, "raid_scrub_enabled", False),
        "next_run": next_run,
    }
