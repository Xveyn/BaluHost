"""Service for scheduled automatic syncs."""

from datetime import datetime, time, timedelta, timezone
from typing import Optional, Callable
from sqlalchemy.orm import Session
import asyncio

from app.models.sync_progress import SyncSchedule
from app.services.sync.file_sync import FileSyncService
from app.services.sync.sleep_check import is_time_in_sleep_window


class SyncSchedulerService:
    """Handle scheduled automatic synchronizations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.sync_service = FileSyncService(db)
        self._scheduler_tasks = {}
    
    def create_schedule(
        self,
        user_id: int,
        device_id: str,
        schedule_type: str,  # 'daily', 'weekly', 'monthly', 'on_change'
        time_of_day: Optional[str] = None,  # "02:00"
        day_of_week: Optional[int] = None,  # 0=Monday
        day_of_month: Optional[int] = None,
        sync_deletions: bool = True,
        resolve_conflicts: str = "keep_newest",
        auto_vpn: bool = False
    ) -> dict:
        """Create a sync schedule."""

        self._validate_time_against_sleep(time_of_day or "02:00")

        schedule = SyncSchedule(
            user_id=user_id,
            device_id=device_id,
            schedule_type=schedule_type,
            time_of_day=time_of_day or "02:00",
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            sync_deletions=sync_deletions,
            resolve_conflicts=resolve_conflicts,
            auto_vpn=auto_vpn
        )

        self._calculate_next_run(schedule)
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)

        return self._schedule_to_dict(schedule)
    
    def update_schedule(
        self,
        schedule_id: int,
        user_id: int,
        **kwargs
    ) -> Optional[dict]:
        """Update a sync schedule."""

        schedule = self.db.query(SyncSchedule).filter(
            SyncSchedule.id == schedule_id,
            SyncSchedule.user_id == user_id
        ).first()

        if not schedule:
            return None

        # Validate updated time against sleep window BEFORE mutating the model
        new_time = kwargs.get("time_of_day") or schedule.time_of_day
        if new_time:
            self._validate_time_against_sleep(new_time)

        for key, value in kwargs.items():
            if hasattr(schedule, key) and value is not None:
                setattr(schedule, key, value)

        self._calculate_next_run(schedule)
        self.db.commit()
        self.db.refresh(schedule)

        return self._schedule_to_dict(schedule)
    
    def get_schedules(self, user_id: int) -> list[dict]:
        """Get all schedules for a user (including disabled)."""
        schedules = self.db.query(SyncSchedule).filter(
            SyncSchedule.user_id == user_id
        ).all()

        return [self._schedule_to_dict(s) for s in schedules]

    def disable_schedule(self, schedule_id: int, user_id: int) -> bool:
        """Disable a schedule."""
        schedule = self.db.query(SyncSchedule).filter(
            SyncSchedule.id == schedule_id,
            SyncSchedule.user_id == user_id
        ).first()

        if not schedule:
            return False

        schedule.is_active = False
        self.db.commit()
        return True

    def delete_schedule(self, schedule_id: int, user_id: int) -> bool:
        """Permanently delete a schedule."""
        schedule = self.db.query(SyncSchedule).filter(
            SyncSchedule.id == schedule_id,
            SyncSchedule.user_id == user_id
        ).first()

        if not schedule:
            return False

        self.db.delete(schedule)
        self.db.commit()
        return True

    def enable_schedule(self, schedule_id: int, user_id: int) -> bool:
        """Enable a previously disabled schedule."""
        schedule = self.db.query(SyncSchedule).filter(
            SyncSchedule.id == schedule_id,
            SyncSchedule.user_id == user_id
        ).first()

        if not schedule:
            return False

        schedule.is_active = True
        self._calculate_next_run(schedule)
        self.db.commit()
        return True

    def _resolve_device_name(self, device_id: str) -> str | None:
        """Look up device name from mobile_devices or sync_states."""
        from app.models.mobile import MobileDevice
        from app.models.sync_state import SyncState

        mobile = self.db.query(MobileDevice.device_name).filter(
            MobileDevice.id == device_id
        ).first()
        if mobile:
            return mobile[0]

        desktop = self.db.query(SyncState.device_name).filter(
            SyncState.device_id == device_id
        ).first()
        if desktop:
            return desktop[0]

        return None

    def _schedule_to_dict(self, schedule: SyncSchedule) -> dict:
        """Convert a SyncSchedule model to a response dict."""
        return {
            "schedule_id": schedule.id,
            "device_id": schedule.device_id,
            "device_name": self._resolve_device_name(schedule.device_id),
            "schedule_type": schedule.schedule_type,
            "time_of_day": schedule.time_of_day,
            "day_of_week": schedule.day_of_week,
            "day_of_month": schedule.day_of_month,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
            "enabled": schedule.is_active,
            "sync_deletions": schedule.sync_deletions,
            "resolve_conflicts": schedule.resolve_conflicts,
            "auto_vpn": schedule.auto_vpn,
        }
    
    async def run_due_syncs(self):
        """
        Check and run all due syncs.
        This should be called periodically by a background task.
        """
        now = datetime.now(timezone.utc)
        
        due_schedules = self.db.query(SyncSchedule).filter(
            SyncSchedule.is_active == True,
            SyncSchedule.next_run_at <= now
        ).all()
        
        for schedule in due_schedules:
            try:
                # TODO: Trigger actual sync
                # await self._execute_sync(schedule)
                
                schedule.last_run_at = now
                self._calculate_next_run(schedule)
                self.db.commit()
            except Exception as e:
                print(f"Error running sync {schedule.id}: {e}")
    
    def _get_sleep_config(self):
        """Load sleep config from DB for validation."""
        from sqlalchemy import select
        from app.models.sleep import SleepConfig as SleepConfigModel
        try:
            return self.db.execute(
                select(SleepConfigModel).where(SleepConfigModel.id == 1)
            ).scalar_one_or_none()
        except Exception:
            return None

    def _validate_time_against_sleep(self, time_of_day: str) -> None:
        """Raise ValueError if time_of_day falls within the sleep window."""
        config = self._get_sleep_config()
        if not config or not config.schedule_enabled:
            return
        if is_time_in_sleep_window(time_of_day, config.schedule_sleep_time, config.schedule_wake_time):
            raise ValueError(
                f"Sync schedule conflicts with sleep window "
                f"({config.schedule_sleep_time}-{config.schedule_wake_time}). "
                f"Choose a time outside the sleep window."
            )

    def _calculate_next_run(self, schedule: SyncSchedule):
        """Calculate next run time for a schedule."""
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
                microsecond=0
            )
            
            if next_run <= now:
                # Move to next month
                next_run = (next_run + timedelta(days=32)).replace(day=target_day)
            
            schedule.next_run_at = next_run
        
        elif schedule.schedule_type == "on_change":
            # No scheduled time, runs on file change
            schedule.next_run_at = None
    
    async def _execute_sync(self, schedule: SyncSchedule):
        """Execute a sync for a schedule."""
        # Implement a lightweight server-side sync planner.
        # The real client/device will consume these instructions and perform file transfers.
        from datetime import datetime as _dt
        from app.models.sync_state import SyncState, SyncMetadata
        now = _dt.utcnow()

        # Find registered sync state for this device
        sync_state = self.db.query(SyncState).filter(
            SyncState.user_id == schedule.user_id,
            SyncState.device_id == schedule.device_id
        ).first()

        if not sync_state:
            # Nothing to do if device is not registered
            return {
                "schedule_id": schedule.id,
                "status": "no_device_registered"
            }

        # Gather pending metadata for this sync_state
        pending = self.db.query(SyncMetadata).filter(
            SyncMetadata.sync_state_id == sync_state.id
        ).all()

        plan = {"to_download": [], "to_delete": [], "conflicts": []}

        for meta in pending:
            # Simple heuristic:
            # - if conflict detected -> report conflict
            # - if marked deleted on server -> instruct deletion
            # - otherwise instruct client to download server version
            if meta.conflict_detected:
                plan["conflicts"].append({
                    "file_metadata_id": meta.file_metadata_id,
                    "local_modified_at": meta.local_modified_at.isoformat() if meta.local_modified_at else None,
                    "server_modified_at": meta.server_modified_at.isoformat() if meta.server_modified_at else None,
                })
            elif meta.is_deleted:
                plan["to_delete"].append({
                    "file_metadata_id": meta.file_metadata_id
                })
            else:
                plan["to_download"].append({
                    "file_metadata_id": meta.file_metadata_id,
                    "content_hash": meta.content_hash,
                    "file_size": meta.file_size,
                    "server_modified_at": meta.server_modified_at.isoformat() if meta.server_modified_at else None
                })

            # mark that we've scheduled this metadata for sync
            meta.sync_modified_at = now

        # Update sync_state timestamps and change token
        sync_state.last_sync = now
        sync_state.last_change_token = self.sync_service._generate_change_token()

        # Persist changes
        self.db.commit()

        return {
            "schedule_id": schedule.id,
            "device_id": schedule.device_id,
            "status": "scheduled",
            "plan": plan,
            "executed_at": now.isoformat()
        }
