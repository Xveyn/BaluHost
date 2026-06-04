"""Tests for category-wide smart-device sample retention."""
import json
from datetime import datetime, timezone, timedelta

import pytest

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.smart_device.retention import (
    cleanup_old_smart_device_samples,
    SMART_DEVICE_SAMPLE_RETENTION_DAYS,
)


@pytest.fixture
def device(db_session):
    d = SmartDevice(
        name="Test Plug", plugin_name="tapo_smart_plug",
        device_type_id="tapo_p110", address="192.168.1.50",
        capabilities=["power_monitor", "switch"], is_active=True,
        is_online=True, created_by_user_id=1,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def _add(db_session, device_id, capability, days_ago, extra=None):
    data = {"v": 1}
    if extra:
        data.update(extra)
    db_session.add(SmartDeviceSample(
        device_id=device_id, capability=capability,
        data_json=json.dumps(data),
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    ))
    db_session.commit()


def test_default_is_30_days():
    assert SMART_DEVICE_SAMPLE_RETENTION_DAYS == 30


def test_deletes_all_capabilities_older_than_cutoff(db_session, device):
    _add(db_session, device.id, "power_monitor", days_ago=60)
    _add(db_session, device.id, "switch", days_ago=60)
    _add(db_session, device.id, "power_monitor", days_ago=1)

    deleted = cleanup_old_smart_device_samples(db_session, days_to_keep=30)

    assert deleted == 2
    assert db_session.query(SmartDeviceSample).count() == 1


def test_preserves_imported_rows(db_session, device):
    _add(db_session, device.id, "power_monitor", days_ago=60)  # live, old -> deleted
    _add(db_session, device.id, "power_monitor", days_ago=60,
         extra={"imported_from": "tapo_history"})              # imported -> kept

    deleted = cleanup_old_smart_device_samples(db_session, days_to_keep=30)

    assert deleted == 1
    remaining = db_session.query(SmartDeviceSample).all()
    assert len(remaining) == 1
    assert json.loads(remaining[0].data_json).get("imported_from") == "tapo_history"


def test_nothing_to_delete(db_session, device):
    _add(db_session, device.id, "switch", days_ago=1)
    assert cleanup_old_smart_device_samples(db_session, days_to_keep=30) == 0


def test_poller_cleanup_gate():
    """The poller only runs cleanup once per interval."""
    from app.plugins.smart_device.poller import SmartDevicePoller, _SAMPLE_CLEANUP_INTERVAL

    poller = SmartDevicePoller()
    # Never cleaned -> should run immediately.
    assert poller._should_cleanup_samples(now=0.0) is True
    poller._last_sample_cleanup = 1000.0
    # Too soon.
    assert poller._should_cleanup_samples(now=1000.0 + _SAMPLE_CLEANUP_INTERVAL - 1) is False
    # Interval elapsed.
    assert poller._should_cleanup_samples(now=1000.0 + _SAMPLE_CLEANUP_INTERVAL) is True
