"""Main update service coordinating update operations."""
import asyncio
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.database import SessionLocal
from app.models.update_history import UpdateHistory, UpdateConfig, UpdateStatus, UpdateChannel
from app.schemas.update import (
    UpdateCheckResponse,
    UpdateStartResponse,
    UpdateProgressResponse,
    UpdateHistoryEntry,
    UpdateHistoryResponse,
    RollbackRequest,
    RollbackResponse,
    UpdateConfigResponse,
    UpdateConfigUpdate,
    ReleaseNotesResponse,
)
from app.services.update.backend import UpdateBackend
from app.services.update.prod_backend import ProdUpdateBackend
from app.services.update.utils import ProgressCallback

logger = logging.getLogger(__name__)


class UpdateService:
    """Main update service coordinating update operations."""

    def __init__(self, db: Session, backend: Optional[UpdateBackend] = None):
        self.db = db
        if backend is None:
            from app.services.update.api import get_update_backend
            backend = get_update_backend()
        self.backend = backend
        self._current_update: Optional[UpdateHistory] = None
        self._progress_callbacks: list[ProgressCallback] = []

    def add_progress_callback(self, callback: ProgressCallback) -> None:
        """Register a callback to receive progress updates."""
        self._progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: ProgressCallback) -> None:
        """Unregister a progress callback."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)

    def _notify_progress(self, percent: int, step: str) -> None:
        """Notify all registered callbacks of progress."""
        for callback in self._progress_callbacks:
            try:
                callback(percent, step)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

        # Also update the current update record if we have one
        if self._current_update:
            self._current_update.set_progress(percent, step)
            self.db.commit()

    def get_config(self) -> UpdateConfigResponse:
        """Get current update configuration."""
        config = self.db.query(UpdateConfig).first()
        if not config:
            # Create default config
            config = UpdateConfig(
                auto_check_enabled=True,
                check_interval_hours=24,
                channel=UpdateChannel.STABLE.value,
                auto_backup_before_update=True,
                require_healthy_services=True,
                auto_update_enabled=False,
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)

        return UpdateConfigResponse.model_validate(config)

    def update_config(self, updates: UpdateConfigUpdate, user_id: int) -> UpdateConfigResponse:
        """Update configuration."""
        config = self.db.query(UpdateConfig).first()
        if not config:
            config = UpdateConfig()
            self.db.add(config)

        update_data = updates.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(config, key, value)

        config.updated_by = user_id
        self.db.commit()
        self.db.refresh(config)

        return UpdateConfigResponse.model_validate(config)

    async def check_for_updates(self) -> UpdateCheckResponse:
        """Check if updates are available."""
        config = self.get_config()

        # Get current version
        current = await self.backend.get_current_version()

        # Check for blockers
        blockers = await self._check_blockers()

        # Check for updates
        available, latest, changelog = await self.backend.check_for_updates(config.channel)

        # Check dev branch for unreleased commits
        dev_available, dev_version, dev_commits_ahead, dev_commits = await self.backend.check_dev_branch()

        # Update last check time
        db_config = self.db.query(UpdateConfig).first()
        if db_config:
            db_config.last_check_at = datetime.now(timezone.utc)
            if latest:
                db_config.last_available_version = latest.version
            self.db.commit()

        return UpdateCheckResponse(
            update_available=available,
            current_version=current,
            latest_version=latest,
            changelog=changelog,
            channel=config.channel,
            last_checked=datetime.now(timezone.utc),
            blockers=blockers,
            can_update=available and len(blockers) == 0,
            dev_version_available=dev_available,
            dev_version=dev_version,
            dev_commits_ahead=dev_commits_ahead,
            dev_commits=dev_commits,
        )

    async def get_release_notes(self) -> ReleaseNotesResponse:
        """Get release notes for the current version."""
        return await self.backend.get_release_notes()

    async def _check_blockers(self) -> list[str]:
        """Check for conditions that block updates."""
        blockers = []

        # Check for running update in DB
        running = (
            self.db.query(UpdateHistory)
            .filter(UpdateHistory.status.in_([
                UpdateStatus.DOWNLOADING.value,
                UpdateStatus.INSTALLING.value,
                UpdateStatus.MIGRATING.value,
                UpdateStatus.RESTARTING.value,
            ]))
            .first()
        )
        if running:
            blockers.append(f"Update already in progress (ID: {running.id})")

        # In prod, also check if the systemd-run unit is still active
        if isinstance(self.backend, ProdUpdateBackend) and not running:
            try:
                result = subprocess.run(
                    ["sudo", "systemctl", "is-active", "baluhost-update.service"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip() == "active":
                    blockers.append("Update script is still running (baluhost-update.service)")
            except Exception:
                pass

        return blockers

    async def start_update(
        self,
        user_id: int,
        target_version: Optional[str] = None,
        skip_backup: bool = False,
        force: bool = False,
    ) -> UpdateStartResponse:
        """Start the update process."""
        # Check for blockers
        blockers = await self._check_blockers()
        if blockers and not force:
            return UpdateStartResponse(
                success=False,
                message="Update blocked",
                blockers=blockers,
            )

        # Get current and target versions
        current = await self.backend.get_current_version()
        check_result = await self.check_for_updates()

        if not check_result.update_available:
            return UpdateStartResponse(
                success=False,
                message="No update available",
            )

        target = check_result.latest_version
        if target_version:
            # User specified a version - we'd need to look it up
            # For now, use latest
            pass

        # Create update record
        update = UpdateHistory(
            from_version=current.version,
            to_version=target.version,
            channel=check_result.channel,
            from_commit=current.commit,
            to_commit=target.commit,
            user_id=user_id,
            status=UpdateStatus.PENDING.value,
            changelog="\n".join(
                f"- {change}" for entry in check_result.changelog for change in entry.changes
            ),
        )
        self.db.add(update)
        self.db.commit()
        self.db.refresh(update)

        self._current_update = update

        # Production: launch detached shell script via systemd-run
        # Dev mode: run in-process simulation via asyncio task
        if isinstance(self.backend, ProdUpdateBackend):
            update.status = UpdateStatus.DOWNLOADING.value
            update.set_progress(5, "Launching update runner...")
            self.db.commit()

            success, error = self.backend.launch_update_script(
                update_id=update.id,
                from_commit=current.commit,
                to_commit=target.commit,
                from_version=current.version,
                to_version=target.version,
            )
            if not success:
                update.fail(f"Failed to launch update: {error}")
                self.db.commit()
                return UpdateStartResponse(
                    success=False,
                    message=f"Failed to launch update: {error}",
                )
        else:
            asyncio.create_task(self._run_dev_update(update.id, skip_backup))

        return UpdateStartResponse(
            success=True,
            update_id=update.id,
            message=f"Update to {target.version} started",
        )

    async def _run_dev_update(self, update_id: int, skip_backup: bool) -> None:
        """Run the update process in-process (dev mode only).

        In production, the detached run-update.sh script handles everything.
        This method simulates the update for development/testing.
        """
        db = SessionLocal()
        try:
            update = db.query(UpdateHistory).filter(UpdateHistory.id == update_id).first()
            if not update:
                return

            config = db.query(UpdateConfig).first()

            def progress(percent: int, step: str):
                update.set_progress(percent, step)
                db.commit()
                self._notify_progress(percent, step)

            try:
                # Step 1: Backup (if enabled)
                if config and config.auto_backup_before_update and not skip_backup:
                    update.status = UpdateStatus.BACKING_UP.value
                    progress(5, "Creating backup...")

                    try:
                        from app.services.backup import BackupService
                        from app.schemas.backup import BackupCreate

                        backup_service = BackupService(db)
                        backup_data = BackupCreate(
                            backup_type="full",
                            includes_database=True,
                            includes_files=False,
                            includes_config=True,
                        )
                        backup = backup_service.create_backup(
                            backup_data,
                            update.user_id or 0,
                            "update_service",
                        )
                        update.backup_id = backup.id
                        db.commit()
                        progress(10, "Backup complete")
                    except Exception as e:
                        logger.warning(f"Backup failed during update: {e}")
                        progress(10, f"Backup skipped: {e}")

                # Step 2: Fetch
                update.status = UpdateStatus.DOWNLOADING.value
                progress(15, "Fetching updates...")

                success = await self.backend.fetch_updates(
                    lambda p, s: progress(15 + int(p * 0.15), s)
                )
                if not success:
                    raise Exception("Failed to fetch updates")

                # Step 3: Apply
                update.status = UpdateStatus.INSTALLING.value
                progress(30, "Applying updates...")

                success, error = await self.backend.apply_updates(
                    update.to_commit,
                    lambda p, s: progress(30 + int(p * 0.20), s),
                )
                if not success:
                    raise Exception(f"Failed to apply updates: {error}")

                # Step 4: Dependencies
                progress(50, "Installing dependencies...")

                success, error = await self.backend.install_dependencies(
                    lambda p, s: progress(50 + int(p * 0.20), s),
                )
                if not success:
                    raise Exception(f"Failed to install dependencies: {error}")

                # Step 5: Migrations
                update.status = UpdateStatus.MIGRATING.value
                progress(70, "Running migrations...")

                success, error = await self.backend.run_migrations(
                    lambda p, s: progress(70 + int(p * 0.10), s),
                )
                if not success:
                    raise Exception(f"Migration failed: {error}")

                # Step 6: Health check
                update.status = UpdateStatus.HEALTH_CHECK.value
                progress(80, "Health check...")

                healthy, issues = await self.backend.health_check()
                if not healthy and config and config.require_healthy_services:
                    raise Exception(f"Health check failed: {', '.join(issues)}")

                # Step 7: Restart (simulated in dev)
                update.status = UpdateStatus.RESTARTING.value
                progress(85, "Restarting services...")

                success, error = await self.backend.restart_services(
                    lambda p, s: progress(85 + int(p * 0.10), s),
                )
                if not success:
                    logger.warning(f"Service restart may have failed: {error}")

                # Step 8: Final health check
                progress(95, "Post-restart health check...")
                await asyncio.sleep(2)

                # Complete
                update.complete()
                db.commit()
                progress(100, "Update completed successfully")

            except Exception as e:
                logger.exception(f"Update failed: {e}")
                update.fail(str(e))
                update.rollback_commit = update.from_commit
                db.commit()

                if update.from_commit:
                    try:
                        await self.backend.rollback(update.from_commit)
                        update.mark_rolled_back(update.from_commit)
                        db.commit()
                    except Exception as rollback_error:
                        logger.error(f"Rollback also failed: {rollback_error}")

        finally:
            db.close()
            self._current_update = None

    def get_update_progress(self, update_id: int) -> Optional[UpdateProgressResponse]:
        """Get progress of an update.

        For production updates running via the shell script, reads live
        progress from the status JSON file. The DB record is the fallback
        and is authoritative once the update is finalized.
        """
        update = self.db.query(UpdateHistory).filter(UpdateHistory.id == update_id).first()
        if not update:
            return None

        # For running prod updates, prefer the live status file
        status = update.status
        progress = update.progress_percent
        step = update.current_step
        error = update.error_message

        if isinstance(self.backend, ProdUpdateBackend) and status in (
            UpdateStatus.PENDING.value,
            UpdateStatus.DOWNLOADING.value,
            UpdateStatus.INSTALLING.value,
            UpdateStatus.MIGRATING.value,
            UpdateStatus.RESTARTING.value,
            UpdateStatus.HEALTH_CHECK.value,
        ):
            file_status = self.backend.read_update_status(update_id)
            if file_status:
                status = file_status.get("status", status)
                progress = file_status.get("progress_percent", progress)
                step = file_status.get("current_step", step)
                error = file_status.get("error_message", error)

        return UpdateProgressResponse(
            update_id=update.id,
            status=status,
            progress_percent=progress,
            current_step=step,
            started_at=update.started_at,
            from_version=update.from_version,
            to_version=update.to_version,
            error_message=error,
            can_rollback=update.from_commit is not None and status in [
                UpdateStatus.FAILED.value,
                UpdateStatus.COMPLETED.value,
            ],
        )

    async def rollback(self, request: RollbackRequest, user_id: int) -> RollbackResponse:
        """Rollback to a previous version."""
        target_commit = request.target_commit

        if not target_commit and request.target_update_id:
            # Get commit from update history
            update = (
                self.db.query(UpdateHistory)
                .filter(UpdateHistory.id == request.target_update_id)
                .first()
            )
            if update:
                target_commit = update.from_commit

        if not target_commit:
            # Get last successful update's from_commit
            last_update = (
                self.db.query(UpdateHistory)
                .filter(UpdateHistory.status == UpdateStatus.COMPLETED.value)
                .order_by(desc(UpdateHistory.completed_at))
                .first()
            )
            if last_update:
                target_commit = last_update.from_commit

        if not target_commit:
            return RollbackResponse(
                success=False,
                message="No rollback target found",
            )

        # Perform rollback
        success, error = await self.backend.rollback(target_commit)

        if not success:
            return RollbackResponse(
                success=False,
                message=f"Rollback failed: {error}",
            )

        # Restore backup if requested
        if request.restore_backup:
            # Find the backup associated with the update
            update = (
                self.db.query(UpdateHistory)
                .filter(UpdateHistory.to_commit == target_commit)
                .first()
            )
            if update and update.backup_id:
                try:
                    from app.services.backup import BackupService
                    backup_service = BackupService(self.db)
                    # Note: Would need to implement restore functionality
                    logger.info(f"Would restore backup {update.backup_id}")
                except Exception as e:
                    logger.warning(f"Backup restore failed: {e}")

        return RollbackResponse(
            success=True,
            message="Rollback completed",
            rolled_back_to=target_commit[:8],
        )

    def get_history(
        self, page: int = 1, page_size: int = 20
    ) -> UpdateHistoryResponse:
        """Get paginated update history."""
        query = self.db.query(UpdateHistory)
        total = query.count()

        updates = (
            query.order_by(desc(UpdateHistory.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return UpdateHistoryResponse(
            updates=[
                UpdateHistoryEntry(
                    id=u.id,
                    from_version=u.from_version,
                    to_version=u.to_version,
                    channel=u.channel,
                    from_commit=u.from_commit,
                    to_commit=u.to_commit,
                    started_at=u.started_at,
                    completed_at=u.completed_at,
                    duration_seconds=u.duration_seconds,
                    status=u.status,
                    error_message=u.error_message,
                    rollback_commit=u.rollback_commit,
                    user_id=u.user_id,
                    can_rollback=u.from_commit is not None,
                )
                for u in updates
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
