"""Fan curve profile management service.

Handles CRUD operations for fan curve profiles and applying
profiles/presets to fans.
"""
import json
import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.fans import FanConfig, FanCurveProfile
from app.schemas.fans import FanCurvePoint

logger = logging.getLogger(__name__)


class FanProfileService:
    """Manages fan curve profiles (system and user-defined)."""

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory

    async def list_profiles(self) -> List[FanCurveProfile]:
        """Get all fan curve profiles."""
        with self.db_session_factory() as db:
            profiles = db.execute(
                select(FanCurveProfile).order_by(
                    FanCurveProfile.is_system.desc(),
                    FanCurveProfile.name.asc(),
                )
            ).scalars().all()
            for p in profiles:
                db.expunge(p)
            return list(profiles)

    async def get_profile(self, profile_id: int) -> Optional[FanCurveProfile]:
        """Get a single profile by ID."""
        with self.db_session_factory() as db:
            profile = db.execute(
                select(FanCurveProfile).where(FanCurveProfile.id == profile_id)
            ).scalar_one_or_none()
            if profile:
                db.expunge(profile)
            return profile

    async def create_profile(
        self, name: str, curve_points: List[FanCurvePoint], description: Optional[str] = None
    ) -> Optional[FanCurveProfile]:
        """Create a new user curve profile.

        Returns None if max user profiles (20) reached or name already exists.
        """
        with self.db_session_factory() as db:
            user_count = db.execute(
                select(func.count()).select_from(
                    select(FanCurveProfile)
                    .where(FanCurveProfile.is_system == False)
                    .subquery()
                )
            ).scalar() or 0
            if user_count >= 20:
                return None

            existing = db.execute(
                select(FanCurveProfile).where(FanCurveProfile.name == name)
            ).scalar_one_or_none()
            if existing:
                return None

            curve_json = json.dumps([p.model_dump() for p in curve_points])
            profile = FanCurveProfile(
                name=name,
                description=description,
                curve_json=curve_json,
                is_system=False,
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
            db.expunge(profile)

            logger.info(f"Created curve profile '{name}'")
            return profile

    async def update_profile(
        self, profile_id: int, **kwargs
    ) -> Optional[FanCurveProfile]:
        """Update a curve profile.

        Rejects name changes on system profiles.
        Returns None if profile not found or name conflict.
        """
        with self.db_session_factory() as db:
            profile = db.execute(
                select(FanCurveProfile).where(FanCurveProfile.id == profile_id)
            ).scalar_one_or_none()

            if not profile:
                return None

            if profile.is_system:
                kwargs.pop('name', None)

            if 'name' in kwargs and kwargs['name'] is not None:
                existing = db.execute(
                    select(FanCurveProfile)
                    .where(FanCurveProfile.name == kwargs['name'])
                    .where(FanCurveProfile.id != profile_id)
                ).scalar_one_or_none()
                if existing:
                    return None
                profile.name = kwargs['name']

            if 'description' in kwargs:
                profile.description = kwargs['description']

            if 'curve_points' in kwargs and kwargs['curve_points'] is not None:
                profile.curve_json = json.dumps([p.model_dump() for p in kwargs['curve_points']])

            db.commit()
            db.refresh(profile)
            db.expunge(profile)

            logger.info(f"Updated curve profile {profile_id}")
            return profile

    async def delete_profile(self, profile_id: int) -> bool:
        """Delete a curve profile.

        Rejects deletion of system profiles. FK SET NULL handles schedule entries.
        """
        with self.db_session_factory() as db:
            profile = db.execute(
                select(FanCurveProfile).where(FanCurveProfile.id == profile_id)
            ).scalar_one_or_none()

            if not profile:
                return False

            if profile.is_system:
                return False

            db.delete(profile)
            db.commit()

            logger.info(f"Deleted curve profile '{profile.name}' (id={profile_id})")
            return True

    async def apply_profile_to_fan(
        self, fan_id: str, profile_id: int
    ) -> Tuple[bool, List[FanCurvePoint]]:
        """Apply a profile's curve to a fan's FanConfig.

        Copies the profile's curve points to the fan's curve_json.

        Args:
            fan_id: Fan identifier
            profile_id: Profile ID

        Returns:
            (success, curve_points)
        """
        profile = await self.get_profile(profile_id)
        if not profile:
            return False, []

        points = json.loads(profile.curve_json)
        curve_points = [FanCurvePoint(temp=p["temp"], pwm=p["pwm"]) for p in points]

        success = await self._update_fan_curve(fan_id, curve_points)
        if success:
            logger.info(f"Applied profile '{profile.name}' to {fan_id}")

        return success, curve_points

    async def apply_preset(
        self, fan_id: str, preset_name: str
    ) -> Tuple[bool, List[FanCurvePoint]]:
        """Apply a preset curve to a fan.

        Looks up system profiles from DB first, falls back to CURVE_PRESETS dict.

        Args:
            fan_id: Fan identifier
            preset_name: Preset name (silent, balanced, performance)

        Returns:
            (success, curve_points)
        """
        curve_points: Optional[List[FanCurvePoint]] = None

        # Try DB system profile first
        with self.db_session_factory() as db:
            profile = db.execute(
                select(FanCurveProfile)
                .where(FanCurveProfile.name == preset_name)
                .where(FanCurveProfile.is_system == True)
            ).scalar_one_or_none()
            if profile:
                points = json.loads(profile.curve_json)
                curve_points = [FanCurvePoint(temp=p["temp"], pwm=p["pwm"]) for p in points]

        # Fallback to hardcoded presets
        if curve_points is None:
            from app.schemas.fans import CURVE_PRESETS
            if preset_name not in CURVE_PRESETS:
                logger.warning(f"Unknown preset: {preset_name}")
                return False, []
            preset_points = CURVE_PRESETS[preset_name]
            curve_points = [FanCurvePoint(temp=p["temp"], pwm=p["pwm"]) for p in preset_points]

        success = await self._update_fan_curve(fan_id, curve_points)
        if success:
            logger.info(f"Applied {preset_name} preset to {fan_id}")

        return success, curve_points

    async def _update_fan_curve(self, fan_id: str, curve_points: List[FanCurvePoint]) -> bool:
        """Update fan temperature curve in DB."""
        with self.db_session_factory() as db:
            config = db.execute(
                select(FanConfig).where(FanConfig.fan_id == fan_id)
            ).scalar_one_or_none()

            if not config:
                return False

            curve_json = json.dumps([p.model_dump() for p in curve_points])
            config.curve_json = curve_json
            db.commit()

        logger.info(f"Updated curve for {fan_id} with {len(curve_points)} point(s)")
        return True
