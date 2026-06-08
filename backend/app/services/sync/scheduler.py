"""Service for scheduled automatic syncs."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.sync_progress import SyncSchedule
from app.services.sync.sleep_check import is_time_in_sleep_window


class SyncSchedulerService:
    """Handle scheduled automatic synchronizations.

    This service owns schedule CRUD and next-run computation only. The actual
    transfers are client-driven (BaluDesk/BaluApp pull); the server-side
    evaluation of a due schedule lives in ``app.services.sync.background`` and is
    invoked by the central scheduler worker (see issue #175).
    """

    def __init__(self, db: Session):
        self.db = db
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
