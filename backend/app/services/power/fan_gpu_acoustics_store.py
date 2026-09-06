"""Persistenz der GPU-Akustik-Konfiguration (#516).

Singleton-Zeile, JSON-Feld -- gleiches Muster wie config_store.py fuer die
GPU-Power-Konfiguration.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fans import GpuFanAcousticsConfigDb
from app.schemas.gpu_fan_acoustics import GpuFanAcousticsConfig

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


def load_acoustics_config(db: Session) -> GpuFanAcousticsConfig:
    """Die gespeicherte Konfiguration, sonst leere Vorgaben.

    Ein Fehler beim Lesen darf den Start nicht verhindern: ohne Konfiguration
    verwaltet BaluHost eben nichts, und das ist ein gueltiger Zustand.
    """
    try:
        row = db.execute(
            select(GpuFanAcousticsConfigDb)
            .where(GpuFanAcousticsConfigDb.id == _SINGLETON_ID)
        ).scalar_one_or_none()
        if row is None or not row.config_json:
            return GpuFanAcousticsConfig()
        return GpuFanAcousticsConfig.model_validate_json(row.config_json)
    except Exception as exc:
        logger.warning("GPU-Akustik-Konfiguration nicht lesbar: %s", exc)
        return GpuFanAcousticsConfig()


def save_acoustics_config(db: Session, config: GpuFanAcousticsConfig) -> bool:
    """Konfiguration ablegen. False bei einem Datenbankfehler."""
    try:
        row = db.execute(
            select(GpuFanAcousticsConfigDb)
            .where(GpuFanAcousticsConfigDb.id == _SINGLETON_ID)
        ).scalar_one_or_none()
        if row is None:
            row = GpuFanAcousticsConfigDb(id=_SINGLETON_ID)
            db.add(row)
        row.config_json = config.model_dump_json()
        row.updated_by_pid = os.getpid()
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("GPU-Akustik-Konfiguration nicht schreibbar: %s", exc)
        return False
