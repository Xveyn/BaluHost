"""Persistence for GpuPowerConfig as JSON in a singleton DB row."""
from __future__ import annotations

import logging

from app.core.database import SessionLocal
from app.models.gpu_power import GpuPowerConfigDb
from app.schemas.gpu_power import GpuPowerConfig

logger = logging.getLogger(__name__)


def load_gpu_power_config() -> GpuPowerConfig:
    """Load config from DB; return defaults if no row exists."""
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerConfigDb).filter(GpuPowerConfigDb.id == 1).first()
            if row is None or not row.config_json:
                return GpuPowerConfig()
            return GpuPowerConfig.model_validate_json(row.config_json)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Failed to load GpuPowerConfig from DB: %s; using defaults", exc)
        return GpuPowerConfig()


def save_gpu_power_config(config: GpuPowerConfig) -> bool:
    """Persist config as JSON to the singleton row (id=1). Returns True on success."""
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerConfigDb).filter(GpuPowerConfigDb.id == 1).first()
            payload = config.model_dump_json()
            if row is None:
                row = GpuPowerConfigDb(id=1, config_json=payload)
                db.add(row)
            else:
                row.config_json = payload
            db.commit()
            return True
        finally:
            db.close()
    except Exception as exc:
        logger.error("Failed to save GpuPowerConfig: %s", exc)
        return False
