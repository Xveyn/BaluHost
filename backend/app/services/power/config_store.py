"""
Power management configuration persistence.

Handles loading/saving auto-scaling and dynamic mode configs from/to the database,
as well as persisting profile change and demand logs.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.database import SessionLocal
from app.models.power import PowerProfileLog, PowerDemandLog
from app.schemas.power import (
    AutoScalingConfig,
    DynamicModeConfig,
    PowerProfile,
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
