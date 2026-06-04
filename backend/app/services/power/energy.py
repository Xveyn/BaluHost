"""
Energy statistics service.

Provides aggregated energy consumption statistics, downtime tracking,
and historical analysis of power usage from smart devices with power_monitor capability.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from sqlalchemy import func, and_, cast, Float
from sqlalchemy.orm import Session

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.models.energy_price_config import EnergyPriceConfig
from app.core.config import settings
from app.core.database import DATABASE_URL

logger = logging.getLogger(__name__)

# The capability name used by power-monitoring plugins
_POWER_CAPABILITY = "power_monitor"

# A live-sample gap longer than this is treated as downtime: the trapezoidal
# integration does NOT bridge it (the poller was down / device asleep, ~0 draw).
# Imported buckets carry their own energy and are exempt from this cap.
GAP_THRESHOLD_MINUTES = 15


class EnergyPeriod:
    """Energy consumption statistics for a time period."""

    def __init__(
        self,
        device_id: int,
        device_name: str,
        start_time: datetime,
        end_time: datetime,
        samples_count: int,
        avg_watts: float,
        min_watts: float,
        max_watts: float,
        total_energy_kwh: float,
        uptime_percentage: float,
        downtime_minutes: int
    ):
        self.device_id = device_id
        self.device_name = device_name
        self.start_time = start_time
        self.end_time = end_time
        self.samples_count = samples_count
        self.avg_watts = avg_watts
        self.min_watts = min_watts
        self.max_watts = max_watts
        self.total_energy_kwh = total_energy_kwh
        self.uptime_percentage = uptime_percentage
        self.downtime_minutes = downtime_minutes


def _parse_power_from_sample(data_json: str) -> Optional[Dict]:
    """Parse a SmartDeviceSample data_json into power fields.

    Supports both legacy format (save_power_sample: current_power, current_ma,
    energy_today_wh) and plugin format (PowerReading model_dump: watts,
    current, energy_today_kwh).

    Returns dict with watts, voltage, current, energy_today, is_online
    or None if parsing fails.
    """
    try:
        data = json.loads(data_json)
    except (json.JSONDecodeError, TypeError):
        return None

    # watts: plugin format "watts", legacy format "current_power"
    watts = data.get("watts") if data.get("watts") is not None else data.get("current_power", 0.0)
    if watts is None:
        watts = 0.0

    voltage = data.get("voltage")

    # current: plugin format "current" (amps), legacy format "current_ma" (milliamps)
    current_a_direct = data.get("current")
    current_ma = data.get("current_ma")
    if current_a_direct is not None:
        current_a = float(current_a_direct)
    elif current_ma is not None:
        current_a = current_ma / 1000.0
    else:
        current_a = None

    # energy: plugin format "energy_today_kwh" (kWh), legacy format "energy_today_wh" (Wh)
    energy_today_kwh_direct = data.get("energy_today_kwh")
    energy_today_wh = data.get("energy_today_wh")
    if energy_today_kwh_direct is not None:
        energy_today_kwh = float(energy_today_kwh_direct)
    elif energy_today_wh is not None:
        energy_today_kwh = energy_today_wh / 1000.0
    else:
        energy_today_kwh = None

    is_online = data.get("is_online", True)

    bucket_energy_kwh = data.get("bucket_energy_kwh")

    return {
        "watts": float(watts),
        "voltage": float(voltage) if voltage is not None else None,
        "current": current_a,
        "energy_today": energy_today_kwh,
        "is_online": bool(is_online),
        "imported": bool(data.get("imported_from")),
        "bucket_energy_kwh": float(bucket_energy_kwh) if bucket_energy_kwh is not None else None,
    }


def _interval_energy_wh(prev: Dict, cur: Dict) -> float:
    """Energy in Wh attributed to the interval ending at ``cur``.

    ``prev`` and ``cur`` are parsed sample dicts (from ``_parse_power_from_sample``,
    so they always carry ``timestamp``, ``watts``, ``imported`` and
    ``bucket_energy_kwh``).

    - Imported buckets contribute their own measured ``bucket_energy_kwh``
      (no integration, independent of the gap to ``prev``).
    - Live samples are trapezoid-integrated only when the gap to ``prev`` is
      within ``GAP_THRESHOLD_MINUTES``; larger gaps are treated as downtime
      (0 Wh — the poller was down / device asleep, drawing ~0).
    """
    if cur["imported"] and cur["bucket_energy_kwh"] is not None:
        return cur["bucket_energy_kwh"] * 1000.0
    gap_h = (cur["timestamp"] - prev["timestamp"]).total_seconds() / 3600.0
    if gap_h * 60.0 > GAP_THRESHOLD_MINUTES:
        return 0.0
    return (prev["watts"] + cur["watts"]) / 2.0 * gap_h


def save_power_sample(
    db: Session,
    device_id: int,
    watts: float,
    voltage: Optional[float],
    current: Optional[float],
    energy_today: Optional[float],
    is_online: bool = True
) -> SmartDeviceSample:
    """
    Save a power sample to the database as a SmartDeviceSample.

    Args:
        db: Database session
        device_id: Smart device ID
        watts: Current power consumption in watts
        voltage: Voltage in volts
        current: Current in amperes
        energy_today: Energy consumed today in kWh
        is_online: Whether device is online

    Returns:
        Created SmartDeviceSample instance
    """
    data = {
        "current_power": watts,
        "voltage": voltage,
        "current_ma": int(current * 1000) if current is not None else None,
        "energy_today_wh": int(energy_today * 1000) if energy_today is not None else None,
        "is_online": is_online,
    }

    sample = SmartDeviceSample(
        device_id=device_id,
        capability=_POWER_CAPABILITY,
        data_json=json.dumps(data),
        timestamp=datetime.now(timezone.utc),
    )

    db.add(sample)
    db.commit()
    db.refresh(sample)

    return sample


def get_period_stats(
    db: Session,
    device_id: int,
    start_time: datetime,
    end_time: datetime
) -> Optional[EnergyPeriod]:
    """
    Calculate energy statistics for a specific time period.

    Args:
        db: Database session
        device_id: Smart device ID
        start_time: Period start time
        end_time: Period end time

    Returns:
        EnergyPeriod with statistics, or None if no data
    """
    device = db.query(SmartDevice).filter(SmartDevice.id == device_id).first()
    if not device:
        return None

    samples = db.query(SmartDeviceSample).filter(
        and_(
            SmartDeviceSample.device_id == device_id,
            SmartDeviceSample.capability == _POWER_CAPABILITY,
            SmartDeviceSample.timestamp >= start_time,
            SmartDeviceSample.timestamp <= end_time,
        )
    ).order_by(SmartDeviceSample.timestamp).all()

    if not samples:
        return None

    # Parse all samples (keep timestamps for integration)
    parsed = []
    for s in samples:
        p = _parse_power_from_sample(s.data_json)
        if p is not None:
            parsed.append({"timestamp": s.timestamp, **p})

    if not parsed:
        return None

    samples_count = len(parsed)
    online_samples = [p for p in parsed if p["is_online"]]
    offline_samples = [p for p in parsed if not p["is_online"]]

    if online_samples:
        avg_watts = sum(p["watts"] for p in online_samples) / len(online_samples)
        min_watts = min(p["watts"] for p in online_samples)
        max_watts = max(p["watts"] for p in online_samples)
    else:
        avg_watts = 0.0
        min_watts = 0.0
        max_watts = 0.0

    _, total_wh = _device_cumulative_series(online_samples)
    total_energy_kwh = total_wh / 1000.0

    uptime_percentage = (len(online_samples) / samples_count * 100) if samples_count > 0 else 0.0

    sample_interval_minutes = 5
    downtime_minutes = len(offline_samples) * sample_interval_minutes

    return EnergyPeriod(
        device_id=device_id,
        device_name=device.name,
        start_time=start_time,
        end_time=end_time,
        samples_count=samples_count,
        avg_watts=round(avg_watts, 1),
        min_watts=round(min_watts, 1),
        max_watts=round(max_watts, 1),
        total_energy_kwh=round(total_energy_kwh, 3),
        uptime_percentage=round(uptime_percentage, 1),
        downtime_minutes=downtime_minutes
    )


def get_today_stats(db: Session, device_id: int) -> Optional[EnergyPeriod]:
    """Get statistics for today."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return get_period_stats(db, device_id, start_of_day, now)


def get_week_stats(db: Session, device_id: int) -> Optional[EnergyPeriod]:
    """Get statistics for the current week."""
    now = datetime.now(timezone.utc)
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    return get_period_stats(db, device_id, start_of_week, now)


def get_month_stats(db: Session, device_id: int) -> Optional[EnergyPeriod]:
    """Get statistics for the current month."""
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return get_period_stats(db, device_id, start_of_month, now)


def get_hourly_samples(
    db: Session,
    device_id: int,
    hours: int = 24
) -> List[Dict]:
    """
    Get hourly averaged power samples for charting.

    Since SmartDeviceSample stores data as JSON, we fetch all samples
    in the time range and aggregate in Python.

    Args:
        db: Database session
        device_id: Smart device ID
        hours: Number of hours to look back

    Returns:
        List of dicts with timestamp and avg_watts
    """
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    samples = db.query(SmartDeviceSample).filter(
        and_(
            SmartDeviceSample.device_id == device_id,
            SmartDeviceSample.capability == _POWER_CAPABILITY,
            SmartDeviceSample.timestamp >= start_time,
        )
    ).order_by(SmartDeviceSample.timestamp).all()

    # Group by hour and calculate averages
    hourly: Dict[str, List[float]] = {}
    for s in samples:
        p = _parse_power_from_sample(s.data_json)
        if p is None or not p["is_online"]:
            continue
        hour_key = s.timestamp.strftime('%Y-%m-%d %H:00:00')
        hourly.setdefault(hour_key, []).append(p["watts"])

    return [
        {
            'timestamp': hour_key,
            'avg_watts': round(sum(watts_list) / len(watts_list), 1),
            'sample_count': len(watts_list),
        }
        for hour_key, watts_list in sorted(hourly.items())
    ]


def get_energy_price_config(db: Session) -> EnergyPriceConfig:
    """
    Get the energy price configuration (singleton).

    Creates the default configuration if it doesn't exist.

    Args:
        db: Database session

    Returns:
        EnergyPriceConfig instance
    """
    config = db.query(EnergyPriceConfig).filter(EnergyPriceConfig.id == 1).first()

    if not config:
        config = EnergyPriceConfig(
            id=1,
            cost_per_kwh=0.40,
            currency="EUR",
            updated_at=datetime.now(timezone.utc)
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        logger.info("Created default energy price config")

    return config


def update_energy_price_config(
    db: Session,
    cost_per_kwh: float,
    currency: str,
    user_id: Optional[int] = None
) -> EnergyPriceConfig:
    """
    Update the energy price configuration.

    Args:
        db: Database session
        cost_per_kwh: New cost per kWh
        currency: Currency code
        user_id: ID of user making the update

    Returns:
        Updated EnergyPriceConfig instance
    """
    config = get_energy_price_config(db)
    config.cost_per_kwh = cost_per_kwh
    config.currency = currency
    config.updated_at = datetime.now(timezone.utc)
    config.updated_by_user_id = user_id

    db.commit()
    db.refresh(config)

    logger.info(f"Updated energy price to {cost_per_kwh} {currency} by user {user_id}")
    return config


def _resolve_period_range(period: str, now: datetime) -> tuple[datetime, datetime]:
    """Map a named period to a (start, end=now) window.

    Args:
        period: One of "today", "week", or "month". Any other value falls
            through to the month window (start of the current month).
        now: The reference "now" timestamp (UTC).

    Returns:
        Tuple of (start, now).
    """
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:  # month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


def _load_parsed_online_sorted(db: Session, device_id: int,
                               start_time: datetime, end_time: datetime) -> List[Dict]:
    """Query power samples in [start, end], parse, keep online, sorted by time."""
    samples = db.query(SmartDeviceSample).filter(
        and_(
            SmartDeviceSample.device_id == device_id,
            SmartDeviceSample.capability == _POWER_CAPABILITY,
            SmartDeviceSample.timestamp >= start_time,
            SmartDeviceSample.timestamp <= end_time,
        )
    ).order_by(SmartDeviceSample.timestamp).all()
    parsed: List[Dict] = []
    for s in samples:
        p = _parse_power_from_sample(s.data_json)
        if p is not None and p["is_online"]:
            parsed.append({"timestamp": s.timestamp, **p})
    return parsed


def _device_cumulative_series(parsed: List[Dict]) -> tuple[List[Dict], float]:
    """Full-resolution cumulative series from online, time-sorted samples.

    Returns (points, total_wh); points are
    {"timestamp": datetime, "cumulative_kwh": float, "instant_watts": float}.
    Energy is accumulated internally in Wh and converted to kWh per point.
    """
    points: List[Dict] = []
    cumulative_wh = 0.0
    for i, s in enumerate(parsed):
        if i > 0:
            cumulative_wh += _interval_energy_wh(parsed[i - 1], s)
        points.append({
            "timestamp": s["timestamp"],
            "cumulative_kwh": cumulative_wh / 1000.0,
            "instant_watts": s["watts"],
        })
    return points, cumulative_wh


def _downsample(data_points: List[Dict], max_points: int = 200) -> List[Dict]:
    """Evenly thin a list of chart points to ~max_points (first and last kept)."""
    if len(data_points) <= max_points:
        return data_points
    step = len(data_points) // max_points
    out = [data_points[0]]
    for i in range(step, len(data_points) - 1, step):
        out.append(data_points[i])
    out.append(data_points[-1])
    return out


def get_cumulative_energy_data(
    db: Session,
    device_id: int,
    period: str,
    cost_per_kwh: float,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Optional[Dict]:
    """
    Calculate cumulative energy consumption data for charting.

    Args:
        db: Database session
        device_id: Smart device ID
        period: 'today', 'week', or 'month'
        cost_per_kwh: Cost per kWh for cost calculation
        start: Optional explicit window start (keyword-only); overrides period
        end: Optional explicit window end (keyword-only); overrides period

    Returns:
        Dict with device info, totals, and data_points array, or None if device not found
    """
    device = db.query(SmartDevice).filter(SmartDevice.id == device_id).first()
    if not device:
        return None

    now = datetime.now(timezone.utc)
    if start is not None and end is not None:
        start_time, end_time = start, end
        period_label = "custom"
    else:
        start_time, end_time = _resolve_period_range(period, now)
        period_label = period

    parsed_samples = _load_parsed_online_sorted(db, device_id, start_time, end_time)

    if not parsed_samples:
        if start is not None and end is not None:
            zero_points = [
                {"timestamp": start_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
                {"timestamp": end_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
            ]
            return {
                "device_id": device_id,
                "device_name": device.name,
                "period": period_label,
                "cost_per_kwh": cost_per_kwh,
                "currency": "EUR",
                "total_kwh": 0.0,
                "total_cost": 0.0,
                "data_points": zero_points,
            }
        return {
            "device_id": device_id,
            "device_name": device.name,
            "period": period_label,
            "cost_per_kwh": cost_per_kwh,
            "currency": "EUR",
            "total_kwh": 0.0,
            "total_cost": 0.0,
            "data_points": []
        }

    series, total_wh = _device_cumulative_series(parsed_samples)
    data_points = [
        {
            "timestamp": p["timestamp"].isoformat(),
            "cumulative_kwh": round(p["cumulative_kwh"], 4),
            "cumulative_cost": round(p["cumulative_kwh"] * cost_per_kwh, 4),
            "instant_watts": round(p["instant_watts"], 1),
        }
        for p in series
    ]
    data_points = _downsample(data_points)

    total_kwh = total_wh / 1000.0
    total_cost = total_kwh * cost_per_kwh
    return {
        "device_id": device_id,
        "device_name": device.name,
        "period": period_label,
        "cost_per_kwh": cost_per_kwh,
        "currency": "EUR",
        "total_kwh": round(total_kwh, 4),
        "total_cost": round(total_cost, 2),
        "data_points": data_points,
    }


def get_cumulative_energy_total(
    db: Session,
    period: str,
    cost_per_kwh: float,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict:
    """Aggregate cumulative energy across all active power-monitoring devices.

    Builds each device's full-resolution cumulative curve (import-aware,
    gap-capped) and sums them via carry-forward over the merged timeline, so
    the Total equals the exact sum of per-device totals.
    """
    now = datetime.now(timezone.utc)
    if start is not None and end is not None:
        start_time, end_time, period_label = start, end, "custom"
    else:
        start_time, end_time = _resolve_period_range(period, now)
        period_label = period

    all_devices = db.query(SmartDevice).filter(
        SmartDevice.is_active == True,  # noqa: E712
    ).all()
    power_devices = [
        d for d in all_devices
        if isinstance(d.capabilities, list) and _POWER_CAPABILITY in d.capabilities
    ]

    def _result(total_kwh: float, data_points: List[Dict]) -> Dict:
        return {
            "device_id": 0,
            "device_name": "Total",
            "period": period_label,
            "cost_per_kwh": cost_per_kwh,
            "currency": "EUR",
            "total_kwh": round(total_kwh, 4),
            "total_cost": round(total_kwh * cost_per_kwh, 2),
            "data_points": data_points,
        }

    # Per-device full-resolution series
    device_series: List[List[Dict]] = []
    for d in power_devices:
        parsed = _load_parsed_online_sorted(db, d.id, start_time, end_time)
        series, _ = _device_cumulative_series(parsed)
        if series:
            device_series.append(series)

    if not device_series:
        if start is not None and end is not None:
            return _result(0.0, [
                {"timestamp": start_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
                {"timestamp": end_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
            ])
        return _result(0.0, [])

    # Carry-forward sum across devices over the merged timeline
    threshold = timedelta(minutes=GAP_THRESHOLD_MINUTES)
    all_ts = sorted({p["timestamp"] for s in device_series for p in s})
    n = len(device_series)
    idx = [0] * n
    last_cum = [0.0] * n
    last_w = [0.0] * n
    last_w_ts: List[Optional[datetime]] = [None] * n

    data_points: List[Dict] = []
    for ts in all_ts:
        for k, s in enumerate(device_series):
            while idx[k] < len(s) and s[idx[k]]["timestamp"] <= ts:
                last_cum[k] = s[idx[k]]["cumulative_kwh"]
                last_w[k] = s[idx[k]]["instant_watts"]
                last_w_ts[k] = s[idx[k]]["timestamp"]
                idx[k] += 1
        combined_cum = sum(last_cum)
        combined_w = sum(
            last_w[k] if (last_w_ts[k] is not None and ts - last_w_ts[k] <= threshold) else 0.0
            for k in range(n)
        )
        data_points.append({
            "timestamp": ts.isoformat(),
            "cumulative_kwh": round(combined_cum, 4),
            "cumulative_cost": round(combined_cum * cost_per_kwh, 4),
            "instant_watts": round(combined_w, 1),
        })

    total_kwh = sum(last_cum)  # final cumulative == sum of device totals
    return _result(total_kwh, _downsample(data_points))
