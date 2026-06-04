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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_device import SmartDevice, SmartDeviceSample

logger = logging.getLogger(__name__)

# Fixed default; can be made configurable later without changing callers.
SMART_DEVICE_SAMPLE_RETENTION_DAYS = 30


def cleanup_smart_device_samples(
    db: Session,
    plugin_name: str,
    days_to_keep: int,
) -> int:
    """Delete samples for devices owned by ``plugin_name`` older than the cutoff.

    Covers all capabilities of that plugin's devices. Rows whose ``data_json``
    contains ``"imported_from"`` (manually imported history) are always kept.
    ``days_to_keep <= 0`` means unlimited — nothing is deleted.

    Returns the number of deleted rows.
    """
    if days_to_keep <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    device_ids = select(SmartDevice.id).where(SmartDevice.plugin_name == plugin_name)

    deleted = db.query(SmartDeviceSample).filter(
        SmartDeviceSample.device_id.in_(device_ids),
        SmartDeviceSample.timestamp < cutoff,
        ~SmartDeviceSample.data_json.contains('"imported_from"'),
    ).delete(synchronize_session=False)

    db.commit()
    if deleted:
        logger.info(
            "Cleaned up %d smart_device_samples for plugin '%s' older than %d days "
            "(imported rows preserved)",
            deleted, plugin_name, days_to_keep,
        )
    return deleted
