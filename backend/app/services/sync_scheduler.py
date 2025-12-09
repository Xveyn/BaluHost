"""Service for scheduled automatic syncs."""

from datetime import datetime, time, timedelta
from typing import Optional, Callable
from sqlalchemy.orm import Session
import asyncio

from app.models.sync_progress import SyncSchedule
from app.services.file_sync import FileSyncService


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
        resolve_conflicts: str = "keep_newest"
    ) -> dict:
        """Create a sync schedule."""
        
        schedule = SyncSchedule(
            user_id=user_id,
            device_id=device_id,
            schedule_type=schedule_type,
            time_of_day=time_of_day or "02:00",
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            sync_deletions=sync_deletions,
            resolve_conflicts=resolve_conflicts
        )
        
        self._calculate_next_run(schedule)
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        
        return {
            "schedule_id": schedule.id,
            "device_id": device_id,
            "schedule_type": schedule_type,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
        }
    
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
        
        for key, value in kwargs.items():
            if hasattr(schedule, key) and value is not None:
                setattr(schedule, key, value)
        
        self._calculate_next_run(schedule)
        self.db.commit()
        
        return {
            "schedule_id": schedule.id,
            "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None
        }
    
    def get_schedules(self, user_id: int) -> list[dict]:
        """Get all schedules for a user."""
        schedules = self.db.query(SyncSchedule).filter(
            SyncSchedule.user_id == user_id,
            SyncSchedule.is_active == True
        ).all()
        
        return [
            {
                "schedule_id": s.id,
                "device_id": s.device_id,
                "schedule_type": s.schedule_type,
                "time_of_day": s.time_of_day,
                "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
                "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None
            }
            for s in schedules
        ]
    
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
    
    async def run_due_syncs(self):
        """
        Check and run all due syncs.
        This should be called periodically by a background task.
        """
        now = datetime.utcnow()
        
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
    
    def _calculate_next_run(self, schedule: SyncSchedule):
        """Calculate next run time for a schedule."""
        now = datetime.utcnow()
        
        if schedule.schedule_type == "daily":
            hour, minute = map(int, schedule.time_of_day.split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if next_run <= now:
                next_run += timedelta(days=1)
            
            schedule.next_run_at = next_run
        
        elif schedule.schedule_type == "weekly":
            hour, minute = map(int, schedule.time_of_day.split(":"))
            target_day = schedule.day_of_week or 0
            
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            days_ahead = target_day - now.weekday()
            
            if days_ahead <= 0:
                days_ahead += 7
            
            next_run += timedelta(days=days_ahead)
            schedule.next_run_at = next_run
        
        elif schedule.schedule_type == "monthly":
            hour, minute = map(int, schedule.time_of_day.split(":"))
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
        # TODO: Implement actual sync execution
        # This would call the file_sync service with the schedule's settings
        pass
