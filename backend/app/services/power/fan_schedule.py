"""Fan schedule management service.

Handles CRUD operations for fan schedule entries and time-based
curve resolution for the scheduled fan mode.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.fans import FanConfig, FanScheduleEntry, FanCurveProfile
from app.schemas.fans import FanCurvePoint, FanMode

logger = logging.getLogger(__name__)


class FanScheduleService:
    """Manages fan schedule entries and time-based curve resolution."""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    # --- Time helpers ---

    @staticmethod
    def time_in_window(current_minutes: int, start_minutes: int, end_minutes: int) -> bool:
        """Check if current time (in minutes since midnight) falls within a window.

        Supports overnight windows (e.g. 22:00-06:00).

        Args:
            current_minutes: Current time as minutes since midnight (0-1439)
            start_minutes: Window start as minutes since midnight
            end_minutes: Window end as minutes since midnight

        Returns:
            True if current time is within the window
        """
        if start_minutes <= end_minutes:
            return start_minutes <= current_minutes < end_minutes
        else:
            # Overnight window (e.g. 22:00-06:00)
            return current_minutes >= start_minutes or current_minutes < end_minutes

    @staticmethod
    def parse_time_to_minutes(time_str: str) -> int:
        """Parse HH:MM string to minutes since midnight."""
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])

    # --- Curve resolution ---

    def resolve_active_curve(
        self, fan_id: str, default_curve_json: Optional[str], db: Session
    ) -> Tuple[List[dict], Optional[FanScheduleEntry]]:
        """Find the active schedule entry for the current time.

        Args:
            fan_id: Fan identifier
            default_curve_json: Default curve from FanConfig
            db: Database session

        Returns:
            Tuple of (curve_points list, active FanScheduleEntry or None)
        """
        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute

        entries = db.execute(
            select(FanScheduleEntry)
            .where(FanScheduleEntry.fan_id == fan_id)
            .where(FanScheduleEntry.is_enabled == True)
            .order_by(FanScheduleEntry.priority.asc())
        ).scalars().all()

        for entry in entries:
            start = self.parse_time_to_minutes(entry.start_time)
            end = self.parse_time_to_minutes(entry.end_time)
            if self.time_in_window(current_minutes, start, end):
                # If entry references a profile, use the profile's curve
                if entry.profile_id is not None:
                    profile = db.execute(
                        select(FanCurveProfile).where(FanCurveProfile.id == entry.profile_id)
                    ).scalar_one_or_none()
                    if profile:
                        curve = json.loads(profile.curve_json) if profile.curve_json else []
                        if len(curve) >= 2:
                            return curve, entry
                # Fallback to entry's inline curve
                curve = json.loads(entry.curve_json) if entry.curve_json else []
                if len(curve) >= 2:
                    return curve, entry

        # Fallback to default curve
        default_curve = json.loads(default_curve_json) if default_curve_json else []
        return default_curve, None

    # --- CRUD operations ---

    async def get_schedule_entries(self, fan_id: str) -> List[FanScheduleEntry]:
        """Get all schedule entries for a fan."""
        with self.db_session_factory() as db:
            entries = db.execute(
                select(FanScheduleEntry)
                .where(FanScheduleEntry.fan_id == fan_id)
                .order_by(FanScheduleEntry.priority.asc(), FanScheduleEntry.start_time.asc())
            ).scalars().all()
            for entry in entries:
                db.expunge(entry)
            return list(entries)

    async def create_schedule_entry(
        self, fan_id: str, name: str, start_time: str, end_time: str,
        curve_points: Optional[List[FanCurvePoint]] = None,
        priority: int = 0, is_enabled: bool = True,
        profile_id: Optional[int] = None,
    ) -> Optional[FanScheduleEntry]:
        """Create a new schedule entry for a fan.

        Returns None if max entries (8) reached.
        """
        with self.db_session_factory() as db:
            count = db.execute(
                select(func.count()).select_from(
                    select(FanScheduleEntry)
                    .where(FanScheduleEntry.fan_id == fan_id)
                    .subquery()
                )
            ).scalar() or 0

            if count >= 8:
                return None

            curve_json = None
            if curve_points:
                curve_json = json.dumps([p.model_dump() for p in curve_points])

            entry = FanScheduleEntry(
                fan_id=fan_id,
                name=name,
                start_time=start_time,
                end_time=end_time,
                curve_json=curve_json,
                priority=priority,
                is_enabled=is_enabled,
                profile_id=profile_id,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            db.expunge(entry)

            logger.info(f"Created schedule entry '{name}' for {fan_id} ({start_time}-{end_time})")
            return entry

    async def update_schedule_entry(
        self, fan_id: str, entry_id: int, **kwargs
    ) -> Optional[FanScheduleEntry]:
        """Update an existing schedule entry."""
        with self.db_session_factory() as db:
            entry = db.execute(
                select(FanScheduleEntry)
                .where(FanScheduleEntry.id == entry_id)
                .where(FanScheduleEntry.fan_id == fan_id)
            ).scalar_one_or_none()

            if not entry:
                return None

            if 'name' in kwargs and kwargs['name'] is not None:
                entry.name = kwargs['name']
            if 'start_time' in kwargs and kwargs['start_time'] is not None:
                entry.start_time = kwargs['start_time']
            if 'end_time' in kwargs and kwargs['end_time'] is not None:
                entry.end_time = kwargs['end_time']
            if 'curve_points' in kwargs and kwargs['curve_points'] is not None:
                entry.curve_json = json.dumps([p.model_dump() for p in kwargs['curve_points']])
                entry.profile_id = None  # Clear profile when setting inline curve
            if 'profile_id' in kwargs:
                pid = kwargs['profile_id']
                if pid is not None:
                    entry.profile_id = pid
                    entry.curve_json = None  # Clear inline curve when setting profile
                else:
                    entry.profile_id = None
            if 'priority' in kwargs and kwargs['priority'] is not None:
                entry.priority = kwargs['priority']
            if 'is_enabled' in kwargs and kwargs['is_enabled'] is not None:
                entry.is_enabled = kwargs['is_enabled']

            db.commit()
            db.refresh(entry)
            db.expunge(entry)

            logger.info(f"Updated schedule entry {entry_id} for {fan_id}")
            return entry

    async def delete_schedule_entry(self, fan_id: str, entry_id: int) -> bool:
        """Delete a schedule entry."""
        with self.db_session_factory() as db:
            entry = db.execute(
                select(FanScheduleEntry)
                .where(FanScheduleEntry.id == entry_id)
                .where(FanScheduleEntry.fan_id == fan_id)
            ).scalar_one_or_none()

            if not entry:
                return False

            db.delete(entry)
            db.commit()

            logger.info(f"Deleted schedule entry {entry_id} for {fan_id}")
            return True

    async def get_active_schedule_entry(
        self, fan_id: str
    ) -> Tuple[Optional[FanScheduleEntry], Optional[FanScheduleEntry]]:
        """Get the currently active and next schedule entry for a fan.

        Returns:
            Tuple of (active_entry, next_entry)
        """
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return None, None

            _, active_entry = self.resolve_active_curve(fan_id, config.curve_json, db)

            # Find next entry
            now = datetime.now()
            current_minutes = now.hour * 60 + now.minute
            entries = db.execute(
                select(FanScheduleEntry)
                .where(FanScheduleEntry.fan_id == fan_id)
                .where(FanScheduleEntry.is_enabled == True)
                .order_by(FanScheduleEntry.start_time.asc())
            ).scalars().all()

            next_entry = None
            for entry in entries:
                start = self.parse_time_to_minutes(entry.start_time)
                if start > current_minutes and entry != active_entry:
                    next_entry = entry
                    break

            # Wrap around: if no future entry, next is the first one tomorrow
            if next_entry is None and entries:
                for entry in entries:
                    if entry != active_entry:
                        next_entry = entry
                        break

            # Detach from session
            if active_entry:
                db.expunge(active_entry)
            if next_entry and next_entry is not active_entry:
                db.expunge(next_entry)

            return active_entry, next_entry
