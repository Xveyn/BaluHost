"""
GPU power management runtime state persistence.

DB-backed helpers that replace ``GpuPowerManagerService``'s in-process
state with rows in ``gpu_power_runtime_state`` and ``gpu_power_demands``.
Same pattern as ``app.services.power.config_store`` for the CPU manager.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional

from app.core.database import SessionLocal
from app.models.gpu_power import GpuPowerDemand, GpuPowerRuntimeState
from app.schemas.gpu_power import GpuPowerDemandInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Runtime state (singleton row id=1)
# ---------------------------------------------------------------------------


def load_runtime_state() -> dict[str, Any]:
    """
    Load the singleton ``gpu_power_runtime_state`` row.

    Returns a dict with keys: current_state, detected, vendor,
    has_write_permission, last_transition, last_reason. Falls back to
    safe defaults if the row is missing.
    """
    defaults: dict[str, Any] = {
        "current_state": "active",
        "detected": False,
        "vendor": None,
        "has_write_permission": False,
        "last_transition": None,
        "last_reason": None,
    }
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerRuntimeState).filter(GpuPowerRuntimeState.id == 1).first()
            if row is None:
                return defaults
            return {
                "current_state": row.current_state or "active",
                "detected": bool(row.detected),
                "vendor": row.vendor,
                "has_write_permission": bool(row.has_write_permission),
                "last_transition": row.last_transition,
                "last_reason": row.last_reason,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to load gpu_power_runtime_state: {exc}")
        return defaults


def update_runtime_state(**fields: Any) -> bool:
    """
    Update fields on the singleton ``gpu_power_runtime_state`` row.

    Always stamps ``updated_at`` and ``updated_by_pid``. Creates the row
    if absent (defensive — the migration seeds it).
    """
    if not fields:
        return True
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerRuntimeState).filter(GpuPowerRuntimeState.id == 1).first()
            if row is None:
                row = GpuPowerRuntimeState(id=1, current_state="active")
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
            logger.warning(f"Failed to update gpu_power_runtime_state: {exc}")
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for gpu_power_runtime_state: {exc}")
        return False


# ---------------------------------------------------------------------------
# Active demands (DB-backed, replaces in-memory _demands dict)
# ---------------------------------------------------------------------------


def upsert_demand(
    source: str,
    registered_at: datetime,
    expires_at: Optional[datetime],
    description: Optional[str],
) -> bool:
    """Insert or update a ``gpu_power_demands`` row keyed by source."""
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerDemand).filter(GpuPowerDemand.source == source).first()
            if row is None:
                row = GpuPowerDemand(
                    source=source,
                    registered_at=registered_at,
                    expires_at=expires_at,
                    description=description,
                )
                db.add(row)
            else:
                row.registered_at = registered_at
                row.expires_at = expires_at
                row.description = description
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to upsert gpu power demand '{source}': {exc}")
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for gpu power demand upsert: {exc}")
        return False


def delete_demand(source: str) -> bool:
    """Remove a ``gpu_power_demands`` row. Returns True if a row was deleted."""
    try:
        db = SessionLocal()
        try:
            row = db.query(GpuPowerDemand).filter(GpuPowerDemand.source == source).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to delete gpu power demand '{source}': {exc}")
            return False
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for gpu power demand delete: {exc}")
        return False


def list_active_demands() -> List[GpuPowerDemandInfo]:
    """Return all rows in ``gpu_power_demands`` as ``GpuPowerDemandInfo``."""
    try:
        db = SessionLocal()
        try:
            rows = db.query(GpuPowerDemand).all()
            return [
                GpuPowerDemandInfo(
                    source=row.source,
                    registered_at=row.registered_at,
                    expires_at=row.expires_at,
                    description=row.description,
                )
                for row in rows
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to list gpu power demands: {exc}")
        return []


def delete_expired_demands(now: Optional[datetime] = None) -> List[GpuPowerDemandInfo]:
    """Remove rows whose ``expires_at`` is in the past. Returns the removed list."""
    cutoff = now or datetime.now(timezone.utc)
    try:
        db = SessionLocal()
        try:
            rows = (
                db.query(GpuPowerDemand)
                .filter(GpuPowerDemand.expires_at.isnot(None))
                .filter(GpuPowerDemand.expires_at <= cutoff)
                .all()
            )
            expired = [
                GpuPowerDemandInfo(
                    source=row.source,
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
            logger.warning(f"Failed to delete expired gpu power demands: {exc}")
            return []
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to open session for expired-demand cleanup: {exc}")
        return []
