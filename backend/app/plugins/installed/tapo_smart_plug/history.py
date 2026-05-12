"""Real Tapo history fetcher using the mihai-dinculescu ``tapo`` library.

Used only for admin-triggered history import. The live polling path stays on
plugp100 (``service.py``). Two libraries coexist intentionally — the tapo
library exposes typed ``get_energy_data`` with hourly/daily/monthly intervals
that plugp100 v5.x does not surface.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from app.plugins.smart_device.schemas import ImportHistoryInterval

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT = 30.0
_HOURLY_MAX_DAYS = 8  # tapo API constraint


@dataclass
class EnergyBucket:
    """One time-bucket of energy data from a Tapo device."""
    bucket_start: datetime          # tz-aware, UTC
    interval: ImportHistoryInterval
    energy_kwh: float


# Type alias for dependency-injected client factory (eases testing without monkeypatching tapo)
ClientFactory = Callable[[str, str], object]  # (email, password) -> tapo.ApiClient-like


def _default_client_factory(email: str, password: str):
    """Default factory: real tapo.ApiClient. Imported lazily so tests can run without the lib."""
    from tapo import ApiClient
    return ApiClient(email, password)


class TapoHistoryFetcher:
    """Fetch historical energy data from a Tapo P110/P115.

    Splits long ranges into multiple API calls to respect the library's
    per-call constraints (Hourly <= 8 days, Daily per quarter, Monthly per year).
    """

    def __init__(self, client_factory: Optional[ClientFactory] = None) -> None:
        self._client_factory = client_factory or _default_client_factory

    async def fetch_buckets(
        self,
        ip: str,
        email: str,
        password: str,
        start: date,
        end: date,
        interval: ImportHistoryInterval,
    ) -> List[EnergyBucket]:
        """Fetch all buckets for the requested range.

        Args:
            ip: Device IP address on the local network.
            email: Tapo cloud account email (used for local key derivation).
            password: Tapo cloud account password.
            start: Inclusive start date (UTC).
            end: Inclusive end date (UTC).
            interval: Bucket granularity.

        Returns:
            Flat list of EnergyBucket, sorted by bucket_start ascending.
            Empty list if no data is available.
        """
        if end < start:
            return []

        client = self._client_factory(email, password)
        device = await asyncio.wait_for(client.p110(ip), timeout=_FETCH_TIMEOUT)

        if interval == ImportHistoryInterval.HOURLY:
            return await self._fetch_hourly(device, start, end)
        elif interval == ImportHistoryInterval.DAILY:
            return await self._fetch_daily(device, start, end)
        elif interval == ImportHistoryInterval.MONTHLY:
            return await self._fetch_monthly(device, start, end)
        else:
            raise ValueError(f"Unsupported interval: {interval}")

    # ------------------------------------------------------------------
    # Per-interval implementations
    # ------------------------------------------------------------------

    async def _fetch_hourly(self, device, start: date, end: date) -> List[EnergyBucket]:
        from tapo.requests import EnergyDataInterval

        buckets: List[EnergyBucket] = []
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=_HOURLY_MAX_DAYS - 1), end)
            result = await asyncio.wait_for(
                device.get_energy_data(EnergyDataInterval.Hourly, chunk_start),
                timeout=_FETCH_TIMEOUT,
            )
            buckets.extend(
                self._buckets_from_result(result, ImportHistoryInterval.HOURLY, bucket_minutes=60)
            )
            chunk_start = chunk_end + timedelta(days=1)

        # Trim trailing buckets past ``end``
        end_cutoff = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
        return [b for b in buckets if b.bucket_start <= end_cutoff]

    async def _fetch_daily(self, device, start: date, end: date) -> List[EnergyBucket]:
        from tapo.requests import EnergyDataInterval

        buckets: List[EnergyBucket] = []
        # We know start is a quarter start (validated upstream). Advance one quarter at a time.
        current = start
        while current <= end:
            result = await asyncio.wait_for(
                device.get_energy_data(EnergyDataInterval.Daily, current),
                timeout=_FETCH_TIMEOUT,
            )
            buckets.extend(
                self._buckets_from_result(result, ImportHistoryInterval.DAILY, bucket_minutes=1440)
            )
            # Move to next quarter (add 3 months -- naive but correct because all quarter starts are day=1)
            month = current.month + 3
            year = current.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            current = date(year, month, 1)

        end_cutoff = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
        return [b for b in buckets if b.bucket_start <= end_cutoff]

    async def _fetch_monthly(self, device, start: date, end: date) -> List[EnergyBucket]:
        from tapo.requests import EnergyDataInterval

        buckets: List[EnergyBucket] = []
        current = start  # must be Jan 1
        while current <= end:
            result = await asyncio.wait_for(
                device.get_energy_data(EnergyDataInterval.Monthly, current),
                timeout=_FETCH_TIMEOUT,
            )
            buckets.extend(
                self._buckets_from_result(result, ImportHistoryInterval.MONTHLY, bucket_minutes=43200)
            )
            current = date(current.year + 1, 1, 1)

        end_cutoff = datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc)
        return [b for b in buckets if b.bucket_start <= end_cutoff]

    # ------------------------------------------------------------------
    # Result decoding
    # ------------------------------------------------------------------

    @staticmethod
    def _buckets_from_result(result, interval: ImportHistoryInterval, bucket_minutes: int) -> List[EnergyBucket]:
        """Convert a tapo ``EnergyDataResult`` into EnergyBucket objects.

        The mihai-dinculescu/tapo library exposes ``entries`` as a list of
        ``EnergyDataIntervalResult`` structs, each with its own:
        - ``start_date_time`` -- datetime (``DateTime<Utc>`` in Rust, tz-aware in Python)
        - ``energy`` -- int, Wh consumed in that bucket

        We use the per-entry timestamps directly instead of stepping by
        ``interval_length`` from the parent ``start_date_time``. This is
        correct by construction for all three intervals (HOURLY/DAILY/MONTHLY),
        including the irregular monthly bucket lengths.

        ``bucket_minutes`` is kept for the function signature but is no longer
        used — the per-entry timestamps make it redundant.
        """
        entries = getattr(result, "entries", None) or []

        out: List[EnergyBucket] = []
        for entry in entries:
            bucket_start = getattr(entry, "start_date_time", None)
            energy_wh = getattr(entry, "energy", None)
            if bucket_start is None or energy_wh is None:
                continue

            # Coerce to tz-aware UTC datetime (defensive — the lib already returns UTC)
            if isinstance(bucket_start, str):
                try:
                    bucket_start = datetime.fromisoformat(bucket_start)
                except ValueError:
                    continue
            if getattr(bucket_start, "tzinfo", None) is None:
                bucket_start = bucket_start.replace(tzinfo=timezone.utc)

            out.append(EnergyBucket(
                bucket_start=bucket_start,
                interval=interval,
                energy_kwh=round(float(energy_wh) / 1000.0, 4),
            ))
        return out
