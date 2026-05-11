"""Deterministic mock history fetcher for dev mode.

Generates realistic-looking NAS energy buckets without contacting any device.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from app.plugins.installed.tapo_smart_plug.history import EnergyBucket
from app.plugins.smart_device.schemas import ImportHistoryInterval


class TapoHistoryMockFetcher:
    """Mock fetcher with deterministic output for reproducible dev/test runs."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._seed = seed

    async def fetch_buckets(
        self,
        ip: str,
        email: str,
        password: str,
        start: date,
        end: date,
        interval: ImportHistoryInterval,
    ) -> List[EnergyBucket]:
        rng = random.Random(self._seed if self._seed is not None else hash((ip, start, end, interval)))

        if interval == ImportHistoryInterval.HOURLY:
            return self._generate_hourly(rng, start, end)
        elif interval == ImportHistoryInterval.DAILY:
            return self._generate_daily(rng, start, end)
        elif interval == ImportHistoryInterval.MONTHLY:
            return self._generate_monthly(rng, start, end)
        return []

    @staticmethod
    def _generate_hourly(rng: random.Random, start: date, end: date) -> List[EnergyBucket]:
        out: List[EnergyBucket] = []
        cur = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
        while cur <= end_dt:
            # NAS hourly: 0.05 - 0.20 kWh
            energy = round(rng.uniform(0.05, 0.20), 4)
            out.append(EnergyBucket(
                bucket_start=cur,
                interval=ImportHistoryInterval.HOURLY,
                energy_kwh=energy,
            ))
            cur += timedelta(hours=1)
        return out

    @staticmethod
    def _generate_daily(rng: random.Random, start: date, end: date) -> List[EnergyBucket]:
        out: List[EnergyBucket] = []
        cur = start
        while cur <= end:
            # NAS daily: 1.5 - 3.5 kWh
            energy = round(rng.uniform(1.5, 3.5), 3)
            out.append(EnergyBucket(
                bucket_start=datetime.combine(cur, datetime.min.time(), tzinfo=timezone.utc),
                interval=ImportHistoryInterval.DAILY,
                energy_kwh=energy,
            ))
            cur += timedelta(days=1)
        return out

    @staticmethod
    def _generate_monthly(rng: random.Random, start: date, end: date) -> List[EnergyBucket]:
        out: List[EnergyBucket] = []
        # Iterate month-by-month
        year, month = start.year, start.month
        end_year_month = (end.year, end.month)
        while (year, month) <= end_year_month:
            energy = round(rng.uniform(50.0, 100.0), 2)
            out.append(EnergyBucket(
                bucket_start=datetime(year, month, 1, tzinfo=timezone.utc),
                interval=ImportHistoryInterval.MONTHLY,
                energy_kwh=energy,
            ))
            month += 1
            if month > 12:
                month = 1
                year += 1
        return out
