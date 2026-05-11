"""Tests for TapoHistoryImportService — DB-touching, uses db_session fixture."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.installed.tapo_smart_plug.history import EnergyBucket
from app.plugins.installed.tapo_smart_plug.import_service import TapoHistoryImportService
from app.plugins.smart_device.schemas import (
    ImportHistoryConflictStrategy,
    ImportHistoryInterval,
)


@pytest.fixture
def device_row(db_session):
    """A SmartDevice row to attach samples to. Re-uses existing helper fixtures if available."""
    d = SmartDevice(
        name="Test Tapo",
        plugin_name="tapo_smart_plug",
        device_type_id="tapo_p110",
        address="192.168.1.50",
        capabilities=["switch", "power_monitor"],
        is_active=True,
        is_online=True,
        created_by_user_id=1,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


@pytest.fixture
def hourly_buckets():
    """Three consecutive hourly buckets starting at 2026-04-01 10:00 UTC."""
    base = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
    return [
        EnergyBucket(base + timedelta(hours=i), ImportHistoryInterval.HOURLY, 0.1 * (i + 1))
        for i in range(3)
    ]


def test_buckets_to_samples_marks_imported(db_session, device_row, hourly_buckets):
    svc = TapoHistoryImportService()
    result = svc.write_buckets(
        db_session, device_row.id, hourly_buckets,
        conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
    )
    assert result.samples_inserted == 3

    rows = db_session.query(SmartDeviceSample).filter(
        SmartDeviceSample.device_id == device_row.id,
    ).order_by(SmartDeviceSample.timestamp).all()
    assert len(rows) == 3

    first_data = json.loads(rows[0].data_json)
    assert first_data["imported_from"] == "tapo_history"
    assert first_data["bucket_interval"] == "hourly"
    assert first_data["is_online"] is True
    # 0.1 kWh / 1 hour = 100 W
    assert first_data["watts"] == pytest.approx(100.0)


def test_idempotent_skip(db_session, device_row, hourly_buckets):
    """Second import of the same buckets must skip them (2B: per-timestamp check)."""
    svc = TapoHistoryImportService()
    svc.write_buckets(db_session, device_row.id, hourly_buckets,
                      conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS)

    # Second pass
    result = svc.write_buckets(db_session, device_row.id, hourly_buckets,
                               conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS)
    assert result.samples_inserted == 0
    assert result.samples_skipped_idempotent == 3

    rows = db_session.query(SmartDeviceSample).filter(
        SmartDeviceSample.device_id == device_row.id,
    ).all()
    assert len(rows) == 3  # not duplicated


def test_live_wins_skips_overlap(db_session, device_row, hourly_buckets):
    """If a live (non-imported) sample exists in a bucket's range, the bucket is skipped."""
    # Seed a live sample at 2026-04-01 10:30 — inside the first bucket's hour
    live = SmartDeviceSample(
        device_id=device_row.id,
        capability="power_monitor",
        data_json=json.dumps({"watts": 80.0, "is_online": True}),
        timestamp=datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc),
    )
    db_session.add(live)
    db_session.commit()

    svc = TapoHistoryImportService()
    result = svc.write_buckets(
        db_session, device_row.id, hourly_buckets,
        conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
    )
    assert result.samples_inserted == 2          # bucket 2 and 3
    assert result.samples_skipped_live == 1      # bucket 1 blocked by live sample
    assert result.live_samples_deleted == 0


def test_import_wins_deletes_overlapping_live(db_session, device_row, hourly_buckets):
    """IMPORT_WINS removes live samples whose timestamp falls inside an imported bucket."""
    live = SmartDeviceSample(
        device_id=device_row.id,
        capability="power_monitor",
        data_json=json.dumps({"watts": 80.0, "is_online": True}),
        timestamp=datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc),
    )
    db_session.add(live)
    db_session.commit()

    svc = TapoHistoryImportService()
    result = svc.write_buckets(
        db_session, device_row.id, hourly_buckets,
        conflict_strategy=ImportHistoryConflictStrategy.IMPORT_WINS,
    )
    assert result.samples_inserted == 3
    assert result.live_samples_deleted == 1

    rows = db_session.query(SmartDeviceSample).filter(
        SmartDeviceSample.device_id == device_row.id,
    ).all()
    # 3 imported, 0 live left
    assert len(rows) == 3
    for r in rows:
        assert json.loads(r.data_json).get("imported_from") == "tapo_history"


def test_synthesized_watts_for_daily(db_session, device_row):
    """1.2 kWh over a 24h daily bucket → 50 W."""
    bucket = EnergyBucket(
        bucket_start=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        interval=ImportHistoryInterval.DAILY,
        energy_kwh=1.2,
    )
    svc = TapoHistoryImportService()
    svc.write_buckets(db_session, device_row.id, [bucket],
                      conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS)

    row = db_session.query(SmartDeviceSample).filter(
        SmartDeviceSample.device_id == device_row.id,
    ).one()
    data = json.loads(row.data_json)
    assert data["watts"] == pytest.approx(50.0)
