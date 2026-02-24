"""Factory functions, startup hooks, and service registration for updates."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.update_history import UpdateHistory, UpdateStatus
from app.services.service_status import register_service
from app.services.update.backend import UpdateBackend
from app.services.update.dev_backend import DevUpdateBackend
from app.services.update.prod_backend import ProdUpdateBackend
from app.services.update.service import UpdateService

logger = logging.getLogger(__name__)


# Global singleton for the update service
_update_service: Optional[UpdateService] = None


def get_update_backend() -> UpdateBackend:
    """Get the appropriate backend based on settings."""
    if settings.is_dev_mode:
        return DevUpdateBackend()
    return ProdUpdateBackend()


def finalize_pending_updates(db: Session) -> int:
    """Finalize updates that were in progress when the backend restarted.

    Called during app startup. Reads the status JSON file written by the
    detached update runner script and syncs the final result back to the DB.

    Returns the number of updates finalized.
    """
    status_dir = ProdUpdateBackend._STATUS_DIR
    finalized = 0

    # Find updates that are still in a running state
    running_statuses = [
        UpdateStatus.PENDING.value,
        UpdateStatus.DOWNLOADING.value,
        UpdateStatus.INSTALLING.value,
        UpdateStatus.MIGRATING.value,
        UpdateStatus.RESTARTING.value,
        UpdateStatus.HEALTH_CHECK.value,
        UpdateStatus.BACKING_UP.value,
    ]

    stale_updates = (
        db.query(UpdateHistory)
        .filter(UpdateHistory.status.in_(running_statuses))
        .all()
    )

    for update in stale_updates:
        status_file = status_dir / f"{update.id}.json"

        if not status_file.exists():
            # No status file — the script never ran or was killed before writing
            logger.warning(
                f"Update {update.id} was in '{update.status}' but no status file found. "
                f"Marking as failed."
            )
            update.fail("Update interrupted: no status file found after restart")
            finalized += 1
            continue

        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to read status file for update {update.id}: {e}")
            update.fail(f"Update status file unreadable: {e}")
            finalized += 1
            continue

        file_status = data.get("status", "")
        error_msg = data.get("error_message")
        rollback_commit = data.get("rollback_commit")
        completed_at_str = data.get("completed_at")

        if file_status == "completed":
            update.status = UpdateStatus.COMPLETED.value
            update.progress_percent = 100
            update.current_step = "Update completed successfully"
            if completed_at_str:
                try:
                    update.completed_at = datetime.fromisoformat(completed_at_str)
                except ValueError:
                    update.completed_at = datetime.now(timezone.utc)
            else:
                update.completed_at = datetime.now(timezone.utc)
            if update.started_at and update.completed_at:
                delta = update.completed_at - update.started_at
                update.duration_seconds = int(delta.total_seconds())
            logger.info(f"Update {update.id} finalized as completed")
            finalized += 1

        elif file_status == "failed":
            update.status = UpdateStatus.FAILED.value
            update.error_message = error_msg or "Update failed (see status file)"
            update.current_step = f"Failed: {(error_msg or 'unknown')[:100]}"
            if rollback_commit:
                update.rollback_commit = rollback_commit
            if completed_at_str:
                try:
                    update.completed_at = datetime.fromisoformat(completed_at_str)
                except ValueError:
                    update.completed_at = datetime.now(timezone.utc)
            else:
                update.completed_at = datetime.now(timezone.utc)
            if update.started_at and update.completed_at:
                delta = update.completed_at - update.started_at
                update.duration_seconds = int(delta.total_seconds())
            logger.info(f"Update {update.id} finalized as failed: {error_msg}")
            finalized += 1

        else:
            # Still running (e.g. installing/restarting) — the script may
            # still be active. Update progress from file but don't finalize.
            progress = data.get("progress_percent", update.progress_percent)
            step = data.get("current_step", update.current_step)
            update.set_progress(progress, step)
            update.status = file_status or update.status
            logger.info(
                f"Update {update.id} still in progress (status={file_status}, "
                f"progress={progress}%)"
            )

    if finalized:
        db.commit()
        logger.info(f"Finalized {finalized} pending update(s) from status files")

    return finalized


def get_update_service(db: Session) -> UpdateService:
    """Factory function to get update service instance."""
    return UpdateService(db)


def _get_service_status() -> dict:
    """Get status for service registry."""
    try:
        db = SessionLocal()
        service = UpdateService(db)
        config = service.get_config()

        # Check for running update
        running = (
            db.query(UpdateHistory)
            .filter(UpdateHistory.status.in_([
                UpdateStatus.DOWNLOADING.value,
                UpdateStatus.INSTALLING.value,
                UpdateStatus.MIGRATING.value,
                UpdateStatus.RESTARTING.value,
            ]))
            .first()
        )

        db.close()

        return {
            "state": "running" if running else "idle",
            "auto_check_enabled": config.auto_check_enabled,
            "channel": config.channel,
            "last_check": config.last_check_at.isoformat() if config.last_check_at else None,
            "current_update_id": running.id if running else None,
        }
    except Exception as e:
        return {"state": "error", "error": str(e)}


def register_update_service() -> None:
    """Register update service with service status collector."""
    register_service(
        name="update_service",
        display_name="Update Service",
        get_status_fn=_get_service_status,
    )
