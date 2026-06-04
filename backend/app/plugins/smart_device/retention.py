"""Retention for the shared `smart_device_samples` time-series table.

`smart_device_samples` is written by the SmartDevicePoller for EVERY capability
of EVERY smart_device plugin (power_monitor, switch, sensor, dimmer, color), so
retention is a plugin-category concern — not a monitoring "power metric" one.

Rows flagged ``imported_from`` in their JSON (manually imported history, e.g.
Tapo energy history) are preserved regardless of age.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.smart_device import SmartDeviceSample

logger = logging.getLogger(__name__)

# Fixed default; can be made configurable later without changing callers.
SMART_DEVICE_SAMPLE_RETENTION_DAYS = 30


def cleanup_old_smart_device_samples(
    db: Session,
    days_to_keep: int = SMART_DEVICE_SAMPLE_RETENTION_DAYS,
) -> int:
    """Delete smart_device_samples older than the cutoff across ALL capabilities.

    Imported rows (``data_json`` contains ``"imported_from"``) are preserved.

    Returns the number of deleted rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    deleted = db.query(SmartDeviceSample).filter(
        SmartDeviceSample.timestamp < cutoff,
        ~SmartDeviceSample.data_json.contains('"imported_from"'),
    ).delete(synchronize_session=False)

    db.commit()
    if deleted:
        logger.info(
            "Cleaned up %d smart_device_samples older than %d days (imported rows preserved)",
            deleted, days_to_keep,
        )
    return deleted
