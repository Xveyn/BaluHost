"""SMART scan scheduler (APScheduler integration).

Depends on: cache, utils. Lazy-depends on api (circular avoidance).
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from app.core.config import settings

from app.services.hardware.smart.cache import invalidate_smart_cache
from app.services.hardware.smart.utils import _get_smartctl_path

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

try:
    from apscheduler.schedulers.background import BackgroundScheduler as _APScheduler
except Exception:
    _APScheduler = None

logger = logging.getLogger(__name__)

# Scheduler for periodic SMART scans
_smart_scheduler: Optional["BackgroundScheduler"] = None


def _perform_smart_scan_job() -> None:
    from app.services.scheduler import log_scheduler_execution, complete_scheduler_execution

    execution_id = log_scheduler_execution("smart_scan", job_id="smart_scan")
    try:
        logger.info("SMART scan job: invalidating cache and performing scan")
        invalidate_smart_cache()
        # Warm the cache by calling get_smart_status (will populate from mock or real)
        # Lazy import to avoid circular dependency
        from app.services.hardware.smart.api import get_smart_status
        status = get_smart_status()
        logger.info("SMART scan job: completed")
        complete_scheduler_execution(
            execution_id,
            success=True,
            result={
                "disks_scanned": len(status.devices) if status else 0,
                "overall_status": (
                    "all_passed" if status and all(d.status == 'PASSED' for d in status.devices)
                    else "issues_detected"
                ) if status else "unknown"
            }
        )
    except Exception as exc:
        logger.exception("SMART scan job failed: %s", exc)
        complete_scheduler_execution(execution_id, success=False, error=str(exc))


def run_smart_self_test(device: str, test_type: str = "short") -> str:
    """Trigger a SMART self-test on the specified device.

    In dev-mode this is simulated. In production, calls `smartctl -t`.
    Returns a textual status message.
    """
    test_type = test_type.lower()
    if test_type not in {"short", "long"}:
        raise ValueError("Invalid test type; expected 'short' or 'long'")

    if settings.is_dev_mode or _get_smartctl_path() is None:
        logger.info("Dev-mode or smartctl missing: simulating SMART %s test on %s", test_type, device)
        # Invalidate cache so subsequent reads reflect new state
        invalidate_smart_cache()
        return f"Simulated {test_type} SMART test started for {device}"

    smartctl = _get_smartctl_path()
    import subprocess
    try:
        result = subprocess.run(["sudo", "-n", smartctl, "-t", test_type, device], check=False, capture_output=True, text=True, timeout=10)
        # Bits 0-1: command-line parse error / device open failed → fatal
        if result.returncode & 0b11:
            logger.error("smartctl -t failed (code %d): %s", result.returncode, result.stderr or result.stdout)
            raise RuntimeError(f"Failed to start SMART test for {device}: exit code {result.returncode}")
        # Bit 2+: informational (SMART command issue, disk failing, etc.) → test was still sent
        if result.returncode:
            logger.warning("smartctl -t returned code %d for %s (non-fatal)", result.returncode, device)
        invalidate_smart_cache()
        return f"SMART {test_type} test started for {device}"
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"SMART test command timed out for {device}") from exc


def start_smart_scheduler() -> None:
    global _smart_scheduler
    if not getattr(settings, "smart_scan_enabled", False):
        logger.debug("SMART scheduler disabled by settings")
        return
    if _APScheduler is None:
        logger.warning("APScheduler not available; SMART scheduler skipped")
        return
    if _smart_scheduler is not None:
        logger.debug("SMART scheduler already running")
        return

    scheduler: "BackgroundScheduler" = _APScheduler()
    _smart_scheduler = scheduler
    interval_minutes = max(1, int(getattr(settings, "smart_scan_interval_minutes", 60)))
    scheduler.add_job(
        func=_perform_smart_scan_job,
        trigger="interval",
        minutes=interval_minutes,
        id="smart_scan",
        name="Periodic SMART scan",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("SMART scheduler started (every %d minutes)", interval_minutes)


def stop_smart_scheduler() -> None:
    global _smart_scheduler
    if _smart_scheduler is None:
        return
    try:
        _smart_scheduler.shutdown(wait=False)
    except Exception:
        logger.debug("Error while shutting down SMART scheduler")
    _smart_scheduler = None


def get_smart_scheduler_status() -> dict:
    """
    Get SMART scan scheduler status for service status monitoring.

    Returns:
        Dict with service status information for admin dashboard
    """
    is_running = _smart_scheduler is not None and _smart_scheduler.running
    interval_minutes = max(1, int(getattr(settings, "smart_scan_interval_minutes", 60)))

    # Get next run time if scheduler is running
    next_run = None
    if is_running:
        try:
            job = _smart_scheduler.get_job("smart_scan")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except Exception:
            pass

    return {
        "is_running": is_running,
        "interval_seconds": interval_minutes * 60,
        "config_enabled": getattr(settings, "smart_scan_enabled", False),
        "next_run": next_run,
    }
