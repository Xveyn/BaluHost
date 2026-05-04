"""
Power management configuration persistence.

Handles loading/saving auto-scaling and dynamic mode configs from/to the database,
as well as persisting profile change and demand logs.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional

from app.core.database import SessionLocal
from app.models.power import (
    PowerDemand,
    PowerDemandLog,
    PowerProfileLog,
    PowerRuntimeState,
)
from app.schemas.power import (
    AutoScalingConfig,
    DynamicModeConfig,
    PowerDemandInfo,
    PowerProfile,
    ServicePowerProperty,
)

logger = logging.getLogger(__name__)


def load_auto_scaling_config() -> AutoScalingConfig:
    """Load auto-scaling config from database."""
    try:
        from app.models.power import PowerAutoScalingConfig

        db = SessionLocal()
        try:
            db_config = db.query(PowerAutoScalingConfig).filter(
                PowerAutoScalingConfig.id == 1
            ).first()

            if db_config:
                config = AutoScalingConfig(
                    enabled=db_config.enabled,
                    cpu_surge_threshold=db_config.cpu_surge_threshold,
                    cpu_medium_threshold=db_config.cpu_medium_threshold,
                    cpu_low_threshold=db_config.cpu_low_threshold,
                    cooldown_seconds=db_config.cooldown_seconds,
                    use_cpu_monitoring=db_config.use_cpu_monitoring
                )
                logger.info(f"Loaded auto-scaling config from DB: enabled={config.enabled}")
                return config
            else:
                # No config in DB yet, use defaults
                logger.info("No auto-scaling config in DB, using defaults")
                return AutoScalingConfig()  # type: ignore[call-arg]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error loading auto-scaling config from DB: {e}")
        return AutoScalingConfig()  # type: ignore[call-arg]


def save_auto_scaling_config(config: AutoScalingConfig) -> bool:
    """Save auto-scaling config to database."""
    try:
        from app.models.power import PowerAutoScalingConfig

        db = SessionLocal()
        try:
            db_config = db.query(PowerAutoScalingConfig).filter(
                PowerAutoScalingConfig.id == 1
            ).first()

            if db_config:
                # Update existing config
                db_config.enabled = config.enabled
                db_config.cpu_surge_threshold = config.cpu_surge_threshold
                db_config.cpu_medium_threshold = config.cpu_medium_threshold
                db_config.cpu_low_threshold = config.cpu_low_threshold
                db_config.cooldown_seconds = config.cooldown_seconds
                db_config.use_cpu_monitoring = config.use_cpu_monitoring
            else:
                # Create new config (singleton)
                db_config = PowerAutoScalingConfig(
                    id=1,
                    enabled=config.enabled,
                    cpu_surge_threshold=config.cpu_surge_threshold,
                    cpu_medium_threshold=config.cpu_medium_threshold,
                    cpu_low_threshold=config.cpu_low_threshold,
                    cooldown_seconds=config.cooldown_seconds,
                    use_cpu_monitoring=config.use_cpu_monitoring
                )
                db.add(db_config)

            db.commit()
            logger.info(f"Saved auto-scaling config to DB: enabled={config.enabled}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving auto-scaling config to DB: {e}")
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error saving auto-scaling config to DB: {e}")
        return False


def load_dynamic_mode_config() -> Optional[DynamicModeConfig]:
    """Load dynamic mode config from database."""
    try:
        from app.models.power import PowerDynamicModeConfig

        db = SessionLocal()
        try:
            db_config = db.query(PowerDynamicModeConfig).filter(
                PowerDynamicModeConfig.id == 1
            ).first()

            if db_config:
                config = DynamicModeConfig(
                    enabled=db_config.enabled,
                    governor=db_config.governor,
                    min_freq_mhz=db_config.min_freq_mhz,
                    max_freq_mhz=db_config.max_freq_mhz,
                )
                logger.info(f"Loaded dynamic mode config from DB: enabled={config.enabled}")
                return config
            else:
                logger.info("No dynamic mode config in DB, using defaults")
                return DynamicModeConfig()  # type: ignore[call-arg]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error loading dynamic mode config from DB: {e}")
        return DynamicModeConfig()  # type: ignore[call-arg]


def save_dynamic_mode_config(config: DynamicModeConfig) -> bool:
    """Save dynamic mode config to database."""
    try:
        from app.models.power import PowerDynamicModeConfig

        db = SessionLocal()
        try:
            db_config = db.query(PowerDynamicModeConfig).filter(
                PowerDynamicModeConfig.id == 1
            ).first()

            if db_config:
                db_config.enabled = config.enabled
                db_config.governor = config.governor
                db_config.min_freq_mhz = config.min_freq_mhz
                db_config.max_freq_mhz = config.max_freq_mhz
            else:
                db_config = PowerDynamicModeConfig(
                    id=1,
                    enabled=config.enabled,
                    governor=config.governor,
                    min_freq_mhz=config.min_freq_mhz,
                    max_freq_mhz=config.max_freq_mhz,
                )
                db.add(db_config)

            db.commit()
            logger.info(f"Saved dynamic mode config to DB: enabled={config.enabled}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving dynamic mode config to DB: {e}")
            return False
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error saving dynamic mode config to DB: {e}")
        return False


def persist_profile_change(
    profile: PowerProfile,
    previous_profile: PowerProfile,
    reason: str,
    source: Optional[str],
    frequency_mhz: Optional[float],
) -> None:
    """Persist a profile change to the database."""
    try:
        db = SessionLocal()
        try:
            log = PowerProfileLog(
                profile=profile.value,
                previous_profile=previous_profile.value,
                reason=reason,
                source=source,
                frequency_mhz=frequency_mhz,
            )
            db.add(log)
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.warning(f"Failed to persist profile change to DB: {db_err}")
        finally:
            db.close()
    except Exception as db_err:
        logger.warning(f"Failed to create DB session for profile log: {db_err}")


def persist_demand_log(
    action: str,
    source: str,
    level: str,
    description: Optional[str],
    resulting_profile: str,
    timeout_seconds: Optional[int] = None,
) -> None:
    """Persist a demand registration/unregistration/expiration to the database."""
    try:
        db = SessionLocal()
        try:
            log = PowerDemandLog(
                action=action,
                source=source,
                level=level,
                description=description,
                timeout_seconds=timeout_seconds,
                resulting_profile=resulting_profile,
            )
            db.add(log)
            db.commit()
        except Exception as db_err:
            db.rollback()
            logger.warning(f"Failed to persist demand {action} to DB: {db_err}")
        finally:
            db.close()
    except Exception as db_err:
        logger.warning(f"Failed to create DB session for demand log: {db_err}")


# ---------------------------------------------------------------------------
# Runtime state (singleton row id=1) — replaces in-memory PowerManager state
# ---------------------------------------------------------------------------


def load_runtime_state() -> dict[str, Any]:
    """
    Load the singleton power_runtime_state row.

    Returns a dict with keys: current_profile, current_property,
    manual_override_until, cooldown_until, dynamic_mode_enabled,
    last_profile_change, backend_kind. Falls back to safe defaults
    if the row is missing.
    """
    defaults: dict[str, Any] = {
        "current_profile": "idle",
        "current_property": None,
        "manual_override_until": None,
        "cooldown_until": None,
        "dynamic_mode_enabled": False,
        "last_profile_change": None,
        "backend_kind": None,
    }
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerRuntimeState).filter(PowerRuntimeState.id == 1).first()
            if row is None:
                return defaults
            return {
                "current_profile": row.current_profile or "idle",
                "current_property": row.current_property,
                "manual_override_until": row.manual_override_until,
                "cooldown_until": row.cooldown_until,
                "dynamic_mode_enabled": bool(row.dynamic_mode_enabled),
                "last_profile_change": row.last_profile_change,
                "backend_kind": row.backend_kind,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to load power_runtime_state: {exc}")
        return defaults


def update_runtime_state(**fields: Any) -> bool:
    """
    Update fields on the singleton power_runtime_state row.

    Always stamps ``updated_at`` and ``updated_by_pid``. Creates the row if
    it does not exist (defensive — migration seeds it).

    Returns True on success, False on DB error.
    """
    if not fields:
        return True
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerRuntimeState).filter(PowerRuntimeState.id == 1).first()
            if row is None:
                row = PowerRuntimeState(id=1, current_profile="idle")
                db.add(row)
            for key, value in fields.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            row.updated_by_pid = os.getpid()
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to update power_runtime_state: {exc}")
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for power_runtime_state: {exc}")
        return False


# ---------------------------------------------------------------------------
# Active demands (DB-backed, replaces in-memory _demands dict)
# ---------------------------------------------------------------------------


def upsert_demand(
    source: str,
    level: PowerProfile,
    power_property: ServicePowerProperty,
    registered_at: datetime,
    expires_at: Optional[datetime],
    description: Optional[str],
) -> bool:
    """
    Insert or update a power_demands row keyed by source.

    Returns True on success, False on DB error.
    """
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerDemand).filter(PowerDemand.source == source).first()
            if row is None:
                row = PowerDemand(
                    source=source,
                    level=level.value,
                    power_property=power_property.value,
                    description=description,
                    registered_at=registered_at,
                    expires_at=expires_at,
                )
                db.add(row)
            else:
                row.level = level.value
                row.power_property = power_property.value
                row.description = description
                row.registered_at = registered_at
                row.expires_at = expires_at
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to upsert power demand '{source}': {exc}")
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for power demand upsert: {exc}")
        return False


def delete_demand(source: str) -> bool:
    """
    Remove a power_demands row.

    Returns True if a row was deleted, False if no row matched or on DB error.
    """
    try:
        db = SessionLocal()
        try:
            row = db.query(PowerDemand).filter(PowerDemand.source == source).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to delete power demand '{source}': {exc}")
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for power demand delete: {exc}")
        return False


def list_active_demands() -> List[PowerDemandInfo]:
    """Return all power_demands rows as PowerDemandInfo objects."""
    try:
        db = SessionLocal()
        try:
            rows = db.query(PowerDemand).all()
            return [
                PowerDemandInfo(
                    source=row.source,
                    level=PowerProfile(row.level),
                    power_property=ServicePowerProperty(row.power_property),
                    registered_at=row.registered_at,
                    expires_at=row.expires_at,
                    description=row.description,
                )
                for row in rows
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to list power demands: {exc}")
        return []


def delete_expired_demands(now: Optional[datetime] = None) -> List[PowerDemandInfo]:
    """
    Remove power_demands rows whose ``expires_at`` is in the past.

    Returns the list of removed demands so callers can persist audit logs
    and trigger profile recalculation.
    """
    cutoff = now or datetime.now(timezone.utc)
    try:
        db = SessionLocal()
        try:
            rows = (
                db.query(PowerDemand)
                .filter(PowerDemand.expires_at.isnot(None))
                .filter(PowerDemand.expires_at <= cutoff)
                .all()
            )
            expired = [
                PowerDemandInfo(
                    source=row.source,
                    level=PowerProfile(row.level),
                    power_property=ServicePowerProperty(row.power_property),
                    registered_at=row.registered_at,
                    expires_at=row.expires_at,
                    description=row.description,
                )
                for row in rows
            ]
            for row in rows:
                db.delete(row)
            db.commit()
            return expired
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to delete expired power demands: {exc}")
            return []
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for expired-demand cleanup: {exc}")
        return []
