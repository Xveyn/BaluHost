from datetime import date, timezone

import pytest

from app.plugins.installed.tapo_smart_plug.history_mock import TapoHistoryMockFetcher
from app.plugins.smart_device.schemas import ImportHistoryInterval


@pytest.mark.asyncio
async def test_mock_hourly_returns_24_buckets_per_day():
    fetcher = TapoHistoryMockFetcher(seed=42)
    buckets = await fetcher.fetch_buckets(
        ip="x", email="x", password="x",
        start=date(2026, 4, 1), end=date(2026, 4, 1),
        interval=ImportHistoryInterval.HOURLY,
    )
    assert len(buckets) == 24
    # First bucket starts at 00:00 UTC
    assert buckets[0].bucket_start.hour == 0
    assert buckets[0].bucket_start.tzinfo is not None
    # All values are reasonable for a NAS (0 - 0.3 kWh/h)
    for b in buckets:
        assert 0.0 <= b.energy_kwh <= 0.3


@pytest.mark.asyncio
async def test_mock_monthly_returns_12_buckets_for_full_year():
    fetcher = TapoHistoryMockFetcher(seed=42)
    buckets = await fetcher.fetch_buckets(
        ip="x", email="x", password="x",
        start=date(2026, 1, 1), end=date(2026, 12, 31),
        interval=ImportHistoryInterval.MONTHLY,
    )
    assert len(buckets) == 12
    assert buckets[0].bucket_start.month == 1
    assert buckets[11].bucket_start.month == 12
