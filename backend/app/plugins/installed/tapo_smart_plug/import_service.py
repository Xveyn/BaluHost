"""History import orchestration: buckets → SmartDeviceSample rows with conflict resolution."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from app.models.smart_device import SmartDeviceSample
from app.plugins.installed.tapo_smart_plug.history import EnergyBucket
from app.plugins.smart_device.schemas import (
    ImportHistoryConflictStrategy,
    ImportHistoryInterval,
)

logger = logging.getLogger(__name__)

_POWER_CAPABILITY = "power_monitor"
_DEFAULT_VOLTAGE = 230.0  # EU; consistent with live polling extraction


# Bucket duration in hours used for watts synthesis. Monthly uses an average
# month length (30.4375 days) — acceptable since aggregation only divides by
# the actual period_hours observed at query time (see energy.py:215).
_BUCKET_HOURS = {
    ImportHistoryInterval.HOURLY: 1.0,
    ImportHistoryInterval.DAILY: 24.0,
    ImportHistoryInterval.MONTHLY: 24.0 * 30.4375,
}


@dataclass
class ImportWriteResult:
    """Accounting of one import pass."""
    samples_inserted: int = 0
    samples_skipped_idempotent: int = 0
    samples_skipped_live: int = 0
    live_samples_deleted: int = 0


class TapoHistoryImportService:
    """Convert EnergyBuckets to SmartDeviceSamples and persist them with conflict handling."""

    def write_buckets(
        self,
        db: Session,
        device_id: int,
        buckets: List[EnergyBucket],
        conflict_strategy: ImportHistoryConflictStrategy,
    ) -> ImportWriteResult:
        result = ImportWriteResult()

        for bucket in buckets:
            bucket_end = bucket.bucket_start + timedelta(hours=_BUCKET_HOURS[bucket.interval])

            # Idempotency: previously imported bucket with same start ts
            # Safe: live power_monitor data_json is machine-generated and never contains this key.
            existing_imported = (
                db.query(SmartDeviceSample)
                .filter(
                    SmartDeviceSample.device_id == device_id,
                    SmartDeviceSample.capability == _POWER_CAPABILITY,
                    SmartDeviceSample.timestamp == bucket.bucket_start,
                    SmartDeviceSample.data_json.contains('"imported_from"'),
                )
                .first()
            )
            if existing_imported is not None:
                result.samples_skipped_idempotent += 1
                continue

            # Overlap with live samples in this bucket's range
            # Safe: live power_monitor data_json is machine-generated and never contains this key.
            overlapping = (
                db.query(SmartDeviceSample)
                .filter(
                    SmartDeviceSample.device_id == device_id,
                    SmartDeviceSample.capability == _POWER_CAPABILITY,
                    SmartDeviceSample.timestamp >= bucket.bucket_start,
                    SmartDeviceSample.timestamp < bucket_end,
                    ~SmartDeviceSample.data_json.contains('"imported_from"'),
                )
                .all()
            )

            if overlapping:
                if conflict_strategy == ImportHistoryConflictStrategy.LIVE_WINS:
                    result.samples_skipped_live += 1
                    continue
                # IMPORT_WINS — bulk delete the overlapping live rows
                overlap_ids = [row.id for row in overlapping]
                db.query(SmartDeviceSample).filter(
                    SmartDeviceSample.id.in_(overlap_ids)
                ).delete(synchronize_session=False)
                result.live_samples_deleted += len(overlap_ids)

            db.add(self._bucket_to_sample(device_id, bucket))
            result.samples_inserted += 1

        db.commit()
        return result

    @staticmethod
    def _bucket_to_sample(device_id: int, bucket: EnergyBucket) -> SmartDeviceSample:
        hours = _BUCKET_HOURS[bucket.interval]
        watts = (bucket.energy_kwh * 1000.0) / hours if hours > 0 else 0.0
        current_a = watts / _DEFAULT_VOLTAGE if watts > 0 else 0.0

        data = {
            "watts": round(watts, 1),
            "voltage": _DEFAULT_VOLTAGE,
            "current": round(current_a, 3),
            "energy_today_kwh": None,
            "is_online": True,
            "imported_from": "tapo_history",
            "bucket_interval": bucket.interval.value,
            "bucket_energy_kwh": bucket.energy_kwh,
        }
        return SmartDeviceSample(
            device_id=device_id,
            capability=_POWER_CAPABILITY,
            data_json=json.dumps(data),
            timestamp=bucket.bucket_start,
        )
