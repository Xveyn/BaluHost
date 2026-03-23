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

    return {
        "watts": float(watts),
        "voltage": float(voltage) if voltage is not None else None,
        "current": current_a,
        "energy_today": energy_today_kwh,
        "is_online": bool(is_online),
    }


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
    ).all()

    if not samples:
        return None

    # Parse all samples
    parsed = []
    for s in samples:
        p = _parse_power_from_sample(s.data_json)
        if p is not None:
            parsed.append(p)

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

    period_hours = (end_time - start_time).total_seconds() / 3600
    total_energy_kwh = (avg_watts / 1000) * period_hours if online_samples else 0.0

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


def cleanup_old_samples(db: Session, days_to_keep: int = 30) -> int:
    """
    Delete power monitor samples older than specified days.

    Args:
        db: Database session
        days_to_keep: Number of days to retain

    Returns:
        Number of deleted samples
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    deleted = db.query(SmartDeviceSample).filter(
        SmartDeviceSample.capability == _POWER_CAPABILITY,
        SmartDeviceSample.timestamp < cutoff_date,
    ).delete()

    db.commit()

    logger.info(f"Cleaned up {deleted} power monitor samples older than {days_to_keep} days")
    return deleted


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


def get_cumulative_energy_data(
    db: Session,
    device_id: int,
    period: str,
    cost_per_kwh: float
) -> Optional[Dict]:
    """
    Calculate cumulative energy consumption data for charting.

    Args:
        db: Database session
        device_id: Smart device ID
        period: 'today', 'week', or 'month'
        cost_per_kwh: Cost per kWh for cost calculation

    Returns:
        Dict with device info, totals, and data_points array, or None if device not found
    """
    device = db.query(SmartDevice).filter(SmartDevice.id == device_id).first()
    if not device:
        return None

    now = datetime.now(timezone.utc)
    if period == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_time = now - timedelta(days=now.weekday())
        start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    samples = db.query(SmartDeviceSample).filter(
        and_(
            SmartDeviceSample.device_id == device_id,
            SmartDeviceSample.capability == _POWER_CAPABILITY,
            SmartDeviceSample.timestamp >= start_time,
            SmartDeviceSample.timestamp <= now,
        )
    ).order_by(SmartDeviceSample.timestamp).all()

    # Parse and filter online samples
    parsed_samples = []
    for s in samples:
        p = _parse_power_from_sample(s.data_json)
        if p is not None and p["is_online"]:
            parsed_samples.append({"timestamp": s.timestamp, **p})

    if not parsed_samples:
        return {
            "device_id": device_id,
            "device_name": device.name,
            "period": period,
            "cost_per_kwh": cost_per_kwh,
            "currency": "EUR",
            "total_kwh": 0.0,
            "total_cost": 0.0,
            "data_points": []
        }

    # Calculate cumulative energy using trapezoidal integration
    data_points = []
    cumulative_wh = 0.0

    for i, sample in enumerate(parsed_samples):
        if i > 0:
            prev = parsed_samples[i - 1]
            time_diff_hours = (sample["timestamp"] - prev["timestamp"]).total_seconds() / 3600
            avg_power = (prev["watts"] + sample["watts"]) / 2
            cumulative_wh += avg_power * time_diff_hours

        cumulative_kwh = cumulative_wh / 1000
        cumulative_cost = cumulative_kwh * cost_per_kwh

        data_points.append({
            "timestamp": sample["timestamp"].isoformat(),
            "cumulative_kwh": round(cumulative_kwh, 4),
            "cumulative_cost": round(cumulative_cost, 4),
            "instant_watts": round(sample["watts"], 1)
        })

    # Downsample if too many points
    max_points = 200
    if len(data_points) > max_points:
        step = len(data_points) // max_points
        downsampled = [data_points[0]]
        for i in range(step, len(data_points) - 1, step):
            downsampled.append(data_points[i])
        downsampled.append(data_points[-1])
        data_points = downsampled

    total_kwh = cumulative_wh / 1000
    total_cost = total_kwh * cost_per_kwh

    return {
        "device_id": device_id,
        "device_name": device.name,
        "period": period,
        "cost_per_kwh": cost_per_kwh,
        "currency": "EUR",
        "total_kwh": round(total_kwh, 4),
        "total_cost": round(total_cost, 2),
        "data_points": data_points
    }


def get_cumulative_energy_total(
    db: Session,
    period: str,
    cost_per_kwh: float,
) -> Dict:
    """
    Aggregate cumulative energy across all active power-monitoring devices.

    Args:
        db: Database session
        period: 'today', 'week', or 'month'
        cost_per_kwh: Cost per kWh for cost calculation

    Returns:
        Dict with aggregated totals and data_points array
    """
    # Fetch all active devices, filter for power_monitor capability in Python
    all_devices = db.query(SmartDevice).filter(
        SmartDevice.is_active == True,  # noqa: E712
    ).all()
    power_devices = [
        d for d in all_devices
        if isinstance(d.capabilities, list) and _POWER_CAPABILITY in d.capabilities
    ]

    empty_result = {
        "device_id": 0,
        "device_name": "Total",
        "period": period,
        "cost_per_kwh": cost_per_kwh,
        "currency": "EUR",
        "total_kwh": 0.0,
        "total_cost": 0.0,
        "data_points": [],
    }

    if not power_devices:
        return empty_result

    # Collect instant_watts per timestamp from all devices
    watts_by_ts: Dict[str, float] = {}
    for device in power_devices:
        device_data = get_cumulative_energy_data(db, device.id, period, cost_per_kwh)
        if device_data is None:
            continue
        for point in device_data.get("data_points", []):
            ts = point["timestamp"]
            watts_by_ts[ts] = watts_by_ts.get(ts, 0.0) + point["instant_watts"]

    if not watts_by_ts:
        return empty_result

    # Re-compute cumulative via trapezoidal integration on summed watts
    sorted_ts = sorted(watts_by_ts.keys())
    data_points = []
    cumulative_wh = 0.0

    for i, ts in enumerate(sorted_ts):
        if i > 0:
            prev_ts = sorted_ts[i - 1]
            t0 = datetime.fromisoformat(prev_ts)
            t1 = datetime.fromisoformat(ts)
            hours = (t1 - t0).total_seconds() / 3600
            avg_watts = (watts_by_ts[prev_ts] + watts_by_ts[ts]) / 2
            cumulative_wh += avg_watts * hours

        cumulative_kwh = cumulative_wh / 1000
        data_points.append({
            "timestamp": ts,
            "cumulative_kwh": round(cumulative_kwh, 4),
            "cumulative_cost": round(cumulative_kwh * cost_per_kwh, 4),
            "instant_watts": round(watts_by_ts[ts], 1),
        })

    total_kwh = cumulative_wh / 1000
    return {
        "device_id": 0,
        "device_name": "Total",
        "period": period,
        "cost_per_kwh": cost_per_kwh,
        "currency": "EUR",
        "total_kwh": round(total_kwh, 3),
        "total_cost": round(total_kwh * cost_per_kwh, 2),
        "data_points": data_points,
    }
