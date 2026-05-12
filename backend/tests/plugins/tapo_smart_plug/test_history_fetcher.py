"""Tests for TapoHistoryFetcher — uses a fake tapo client via monkeypatch."""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.plugins.installed.tapo_smart_plug.history import TapoHistoryFetcher, EnergyBucket
from app.plugins.smart_device.schemas import ImportHistoryInterval


class _FakeEnergyDataResult:
    """Stub mimicking tapo's EnergyDataResult (mihai-dinculescu library)."""
    def __init__(self, start_dt: datetime, interval_minutes: int, entries: list[int]):
        self.start_date_time = start_dt
        self.interval_length = interval_minutes
        self.entries = entries


class _FakeTapoP110:
    """Fake P110 device. The test seeds it with canned responses per interval."""
    def __init__(self, responses_by_call):
        self._responses = list(responses_by_call)
        self.calls = []

    async def get_energy_data(self, interval, start_date):
        self.calls.append((interval, start_date))
        return self._responses.pop(0)


class _FakeApiClient:
    def __init__(self, device):
        self._device = device

    async def p110(self, ip):
        return self._device


@pytest.mark.asyncio
async def test_fetch_hourly_single_chunk():
    """Hourly fetch for <= 8 days fits in one API call. All 24 buckets are returned, including zero-Wh entries."""
    # 24 hours of data for 2026-04-01, in Wh — zero entries are NOT filtered here
    # (any filtering is deferred to the import_service layer)
    fake_device = _FakeTapoP110([
        _FakeEnergyDataResult(
            start_dt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            interval_minutes=60,
            entries=[10, 20, 30] + [0] * 21,  # 3 buckets, rest zero
        )
    ])
    fake_client = _FakeApiClient(fake_device)

    fetcher = TapoHistoryFetcher(client_factory=lambda email, pw: fake_client)
    buckets = await fetcher.fetch_buckets(
        ip="192.168.1.10",
        email="x@y", password="pw",
        start=date(2026, 4, 1),
        end=date(2026, 4, 1),
        interval=ImportHistoryInterval.HOURLY,
    )

    assert len(buckets) == 24  # all 24 buckets, even zero entries (drop later if needed)
    assert buckets[0].bucket_start == datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)
    assert buckets[0].energy_kwh == pytest.approx(0.010)
    assert buckets[0].interval == ImportHistoryInterval.HOURLY


@pytest.mark.asyncio
async def test_fetch_hourly_chunks_above_8_days():
    """A 16-day hourly range must be split into 2 API calls."""
    # Two empty chunks just to count the calls
    fake_device = _FakeTapoP110([
        _FakeEnergyDataResult(
            start_dt=datetime(2026, 4, 1, tzinfo=timezone.utc),
            interval_minutes=60, entries=[],
        ),
        _FakeEnergyDataResult(
            start_dt=datetime(2026, 4, 9, tzinfo=timezone.utc),
            interval_minutes=60, entries=[],
        ),
    ])
    fake_client = _FakeApiClient(fake_device)
    fetcher = TapoHistoryFetcher(client_factory=lambda email, pw: fake_client)

    await fetcher.fetch_buckets(
        ip="192.168.1.10", email="x@y", password="pw",
        start=date(2026, 4, 1), end=date(2026, 4, 16),
        interval=ImportHistoryInterval.HOURLY,
    )

    assert len(fake_device.calls) == 2  # split into two 8-day chunks


@pytest.mark.asyncio
async def test_fetch_monthly_single_year():
    """Monthly fetch starting Jan 1: 12 buckets, one per month."""
    fake_device = _FakeTapoP110([
        _FakeEnergyDataResult(
            start_dt=datetime(2026, 1, 1, tzinfo=timezone.utc),
            interval_minutes=43200,  # 30 days in minutes -- tapo's monthly convention
            entries=[100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210],
        )
    ])
    fake_client = _FakeApiClient(fake_device)
    fetcher = TapoHistoryFetcher(client_factory=lambda email, pw: fake_client)

    buckets = await fetcher.fetch_buckets(
        ip="192.168.1.10", email="x@y", password="pw",
        start=date(2026, 1, 1), end=date(2026, 12, 31),
        interval=ImportHistoryInterval.MONTHLY,
    )

    assert len(buckets) == 12
    assert buckets[0].bucket_start.month == 1
    assert buckets[11].bucket_start.month == 12
    assert buckets[0].energy_kwh == pytest.approx(0.100)
