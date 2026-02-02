"""
Power Preset Service for preset-based power management.

Manages power presets that define CPU clock speeds for each service power property.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.power_preset import PowerPreset
from app.schemas.power import (
    ServicePowerProperty,
    PowerPresetCreate,
    PowerPresetUpdate,
    PowerPresetResponse,
    PowerPresetSummary,
)

logger = logging.getLogger(__name__)


class PowerPresetService:
    """
    Service for managing power presets.

    Provides CRUD operations and clock lookup for service power properties.
    """

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize the preset service.

        Args:
            db: Optional database session. If not provided, creates one internally.
        """
        self._db = db
        self._owns_db = db is None

    def _get_db(self) -> Session:
        """Get or create database session."""
        if self._db is None:
            self._db = SessionLocal()
            self._owns_db = True
        return self._db

    def _close_db(self) -> None:
        """Close database session if we own it."""
        if self._owns_db and self._db is not None:
            self._db.close()
            self._db = None

    async def get_active_preset(self) -> Optional[PowerPreset]:
        """
        Get the currently active preset.

        Returns:
            The active PowerPreset or None if no preset is active.
        """
        db = self._get_db()
        try:
            stmt = select(PowerPreset).where(PowerPreset.is_active == True)
            result = db.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            if self._owns_db:
                self._close_db()

    async def get_preset_by_id(self, preset_id: int) -> Optional[PowerPreset]:
        """
        Get a preset by its ID.

        Args:
            preset_id: The preset ID to look up.

        Returns:
            The PowerPreset or None if not found.
        """
        db = self._get_db()
        try:
            stmt = select(PowerPreset).where(PowerPreset.id == preset_id)
            result = db.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            if self._owns_db:
                self._close_db()

    async def get_preset_by_name(self, name: str) -> Optional[PowerPreset]:
        """
        Get a preset by its name.

        Args:
            name: The preset name to look up.

        Returns:
            The PowerPreset or None if not found.
        """
        db = self._get_db()
        try:
            stmt = select(PowerPreset).where(PowerPreset.name == name)
            result = db.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            if self._owns_db:
                self._close_db()

    async def list_presets(self) -> List[PowerPreset]:
        """
        Get all presets ordered by system preset status and name.

        Returns:
            List of all PowerPreset objects.
        """
        db = self._get_db()
        try:
            stmt = select(PowerPreset).order_by(
                PowerPreset.is_system_preset.desc(),
                PowerPreset.name
            )
            result = db.execute(stmt)
            return list(result.scalars().all())
        finally:
            if self._owns_db:
                self._close_db()

    async def activate_preset(self, preset_id: int) -> bool:
        """
        Activate a preset (deactivates any currently active preset).

        Args:
            preset_id: The ID of the preset to activate.

        Returns:
            True if successful, False if preset not found.
        """
        db = self._get_db()
        try:
            # Get the preset to activate
            stmt = select(PowerPreset).where(PowerPreset.id == preset_id)
            result = db.execute(stmt)
            preset = result.scalar_one_or_none()

            if preset is None:
                logger.warning(f"Preset not found: {preset_id}")
                return False

            # Deactivate all presets
            db.execute(
                PowerPreset.__table__.update().values(is_active=False)
            )

            # Activate the selected preset
            preset.is_active = True
            db.commit()

            logger.info(f"Activated preset: {preset.name} (id={preset_id})")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error activating preset {preset_id}: {e}")
            return False
        finally:
            if self._owns_db:
                self._close_db()

    async def create_preset(self, data: PowerPresetCreate) -> Optional[PowerPreset]:
        """
        Create a new custom preset.

        Args:
            data: The preset data.

        Returns:
            The created PowerPreset or None on error.
        """
        db = self._get_db()
        try:
            # Check for duplicate name
            existing = await self.get_preset_by_name(data.name)
            if existing:
                logger.warning(f"Preset with name '{data.name}' already exists")
                return None

            preset = PowerPreset(
                name=data.name,
                description=data.description,
                is_system_preset=False,  # Custom presets are never system presets
                is_active=False,  # New presets are not active by default
                base_clock_mhz=data.base_clock_mhz,
                idle_clock_mhz=data.idle_clock_mhz,
                low_clock_mhz=data.low_clock_mhz,
                medium_clock_mhz=data.medium_clock_mhz,
                surge_clock_mhz=data.surge_clock_mhz,
            )

            db.add(preset)
            db.commit()
            db.refresh(preset)

            logger.info(f"Created preset: {preset.name} (id={preset.id})")
            return preset

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating preset: {e}")
            return None
        finally:
            if self._owns_db:
                self._close_db()

    async def update_preset(
        self,
        preset_id: int,
        data: PowerPresetUpdate
    ) -> Optional[PowerPreset]:
        """
        Update an existing preset.

        Note: System presets can only have clock values updated, not name/description.

        Args:
            preset_id: The ID of the preset to update.
            data: The update data (only non-None fields are updated).

        Returns:
            The updated PowerPreset or None on error.
        """
        db = self._get_db()
        try:
            stmt = select(PowerPreset).where(PowerPreset.id == preset_id)
            result = db.execute(stmt)
            preset = result.scalar_one_or_none()

            if preset is None:
                logger.warning(f"Preset not found: {preset_id}")
                return None

            # Update fields (respect system preset restrictions)
            if data.name is not None:
                if preset.is_system_preset:
                    logger.warning(f"Cannot change name of system preset: {preset.name}")
                else:
                    # Check for duplicate name
                    existing = await self.get_preset_by_name(data.name)
                    if existing and existing.id != preset_id:
                        logger.warning(f"Preset with name '{data.name}' already exists")
                        return None
                    preset.name = data.name

            if data.description is not None and not preset.is_system_preset:
                preset.description = data.description

            # Clock values can always be updated
            if data.base_clock_mhz is not None:
                preset.base_clock_mhz = data.base_clock_mhz
            if data.idle_clock_mhz is not None:
                preset.idle_clock_mhz = data.idle_clock_mhz
            if data.low_clock_mhz is not None:
                preset.low_clock_mhz = data.low_clock_mhz
            if data.medium_clock_mhz is not None:
                preset.medium_clock_mhz = data.medium_clock_mhz
            if data.surge_clock_mhz is not None:
                preset.surge_clock_mhz = data.surge_clock_mhz

            db.commit()
            db.refresh(preset)

            logger.info(f"Updated preset: {preset.name} (id={preset_id})")
            return preset

        except Exception as e:
            db.rollback()
            logger.error(f"Error updating preset {preset_id}: {e}")
            return None
        finally:
            if self._owns_db:
                self._close_db()

    async def delete_preset(self, preset_id: int) -> bool:
        """
        Delete a custom preset.

        System presets cannot be deleted.

        Args:
            preset_id: The ID of the preset to delete.

        Returns:
            True if deleted, False if not found or is system preset.
        """
        db = self._get_db()
        try:
            stmt = select(PowerPreset).where(PowerPreset.id == preset_id)
            result = db.execute(stmt)
            preset = result.scalar_one_or_none()

            if preset is None:
                logger.warning(f"Preset not found: {preset_id}")
                return False

            if preset.is_system_preset:
                logger.warning(f"Cannot delete system preset: {preset.name}")
                return False

            if preset.is_active:
                logger.warning(f"Cannot delete active preset: {preset.name}")
                return False

            db.delete(preset)
            db.commit()

            logger.info(f"Deleted preset: {preset.name} (id={preset_id})")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting preset {preset_id}: {e}")
            return False
        finally:
            if self._owns_db:
                self._close_db()

    @staticmethod
    def get_clock_for_property(
        preset: PowerPreset,
        power_property: ServicePowerProperty
    ) -> int:
        """
        Get the clock speed (MHz) for a given service power property from a preset.

        Args:
            preset: The power preset to use.
            power_property: The service power property (IDLE, LOW, MEDIUM, SURGE).

        Returns:
            The clock speed in MHz for the given property.
        """
        clock_map = {
            ServicePowerProperty.IDLE: preset.idle_clock_mhz,
            ServicePowerProperty.LOW: preset.low_clock_mhz,
            ServicePowerProperty.MEDIUM: preset.medium_clock_mhz,
            ServicePowerProperty.SURGE: preset.surge_clock_mhz,
        }
        return clock_map.get(power_property, preset.base_clock_mhz)

    @staticmethod
    def get_governor_for_property(power_property: ServicePowerProperty) -> str:
        """
        Get the recommended CPU governor for a service power property.

        Args:
            power_property: The service power property.

        Returns:
            The CPU governor name.
        """
        if power_property == ServicePowerProperty.SURGE:
            return "performance"
        elif power_property == ServicePowerProperty.MEDIUM:
            return "schedutil"
        else:
            return "powersave"

    @staticmethod
    def get_epp_for_property(power_property: ServicePowerProperty) -> str:
        """
        Get the energy performance preference for a service power property.

        Args:
            power_property: The service power property.

        Returns:
            The EPP string.
        """
        epp_map = {
            ServicePowerProperty.IDLE: "power",
            ServicePowerProperty.LOW: "balance_power",
            ServicePowerProperty.MEDIUM: "balance_performance",
            ServicePowerProperty.SURGE: "performance",
        }
        return epp_map.get(power_property, "balance_power")


# Singleton instance
_preset_service: Optional[PowerPresetService] = None


def get_preset_service() -> PowerPresetService:
    """Get the singleton PowerPresetService instance."""
    global _preset_service
    if _preset_service is None:
        _preset_service = PowerPresetService()
    return _preset_service
