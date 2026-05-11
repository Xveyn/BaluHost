"""Tests for TapoSmartPlugPlugin.import_history() — top-level plugin entry point."""
from datetime import date, datetime, timezone

import pytest

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin
from app.plugins.installed.tapo_smart_plug.history import EnergyBucket
from app.plugins.smart_device.schemas import (
    ImportHistoryConflictStrategy,
    ImportHistoryInterval,
)


class _StubFetcher:
    """Returns pre-canned buckets regardless of arguments."""
    def __init__(self, buckets):
        self._buckets = buckets
        self.last_call = None

    async def fetch_buckets(self, ip, email, password, start, end, interval):
        self.last_call = {"ip": ip, "email": email, "interval": interval}
        return list(self._buckets)


@pytest.fixture
def device_row(db_session):
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


@pytest.mark.asyncio
async def test_import_history_writes_samples(db_session, device_row, monkeypatch):
    plugin = TapoSmartPlugPlugin()

    stub = _StubFetcher([
        EnergyBucket(datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                     ImportHistoryInterval.HOURLY, 0.1),
        EnergyBucket(datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc),
                     ImportHistoryInterval.HOURLY, 0.15),
    ])

    # Inject the fetcher and cached device info
    plugin._fetcher_override = stub
    plugin._device_info[str(device_row.id)] = type("Info", (), {
        "ip": "192.168.1.50", "email": "test@example.com", "password": "pw",
    })()

    response = await plugin.import_history(
        db=db_session,
        device_id=device_row.id,
        interval=ImportHistoryInterval.HOURLY,
        start=date(2026, 4, 1),
        end=date(2026, 4, 1),
        conflict_strategy=ImportHistoryConflictStrategy.LIVE_WINS,
    )

    assert response.buckets_fetched == 2
    assert response.samples_inserted == 2
    assert response.interval == ImportHistoryInterval.HOURLY
    assert stub.last_call["ip"] == "192.168.1.50"

    rows = db_session.query(SmartDeviceSample).filter(
        SmartDeviceSample.device_id == device_row.id,
    ).count()
    assert rows == 2
