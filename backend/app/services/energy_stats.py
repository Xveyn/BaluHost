"""
Energy statistics service.

Provides aggregated energy consumption statistics, downtime tracking,
and historical analysis of power usage from Tapo devices.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models.power_sample import PowerSample
from app.models.tapo_device import TapoDevice
from app.core.config import settings

logger = logging.getLogger(__name__)


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


def save_power_sample(
    db: Session,
    device_id: int,
    watts: float,
    voltage: Optional[float],
    current: Optional[float],
    energy_today: Optional[float],
    is_online: bool = True
) -> PowerSample:
    """
    Save a power sample to the database.

    Args:
        db: Database session
        device_id: Tapo device ID
        watts: Current power consumption in watts
        voltage: Voltage in volts
        current: Current in amperes
        energy_today: Energy consumed today in kWh
        is_online: Whether device is online

    Returns:
        Created PowerSample instance
    """
    sample = PowerSample(
        device_id=device_id,
        timestamp=datetime.utcnow(),
        watts=watts,
        voltage=voltage,
        current=current,
        energy_today=energy_today,
        is_online=is_online
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
        device_id: Tapo device ID
        start_time: Period start time
        end_time: Period end time

    Returns:
        EnergyPeriod with statistics, or None if no data
    """
    # Get device info
    device = db.query(TapoDevice).filter(TapoDevice.id == device_id).first()
    if not device:
        return None

    # Query samples in period
    samples = db.query(PowerSample).filter(
        and_(
            PowerSample.device_id == device_id,
            PowerSample.timestamp >= start_time,
            PowerSample.timestamp <= end_time
        )
    ).all()

    if not samples:
        return None

    # Calculate statistics
    samples_count = len(samples)
    online_samples = [s for s in samples if s.is_online]
    offline_samples = [s for s in samples if not s.is_online]

    # Power statistics (only from online samples)
    if online_samples:
        avg_watts = sum(s.watts for s in online_samples) / len(online_samples)
        min_watts = min(s.watts for s in online_samples)
        max_watts = max(s.watts for s in online_samples)
    else:
        avg_watts = 0.0
        min_watts = 0.0
        max_watts = 0.0

    # Calculate total energy (approximate integration)
    # Assume samples are evenly distributed; use average power * time
    period_hours = (end_time - start_time).total_seconds() / 3600
    total_energy_kwh = (avg_watts / 1000) * period_hours if online_samples else 0.0

    # Uptime calculation
    uptime_percentage = (len(online_samples) / samples_count * 100) if samples_count > 0 else 0.0

    # Downtime in minutes (approximate)
    # Assume each sample represents a fixed interval (e.g., 5 minutes)
    sample_interval_minutes = 5  # Should match power_monitor sampling interval
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
    now = datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return get_period_stats(db, device_id, start_of_day, now)


def get_week_stats(db: Session, device_id: int) -> Optional[EnergyPeriod]:
    """Get statistics for the current week."""
    now = datetime.utcnow()
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    return get_period_stats(db, device_id, start_of_week, now)


def get_month_stats(db: Session, device_id: int) -> Optional[EnergyPeriod]:
    """Get statistics for the current month."""
    now = datetime.utcnow()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return get_period_stats(db, device_id, start_of_month, now)


def get_hourly_samples(
    db: Session,
    device_id: int,
    hours: int = 24
) -> List[Dict]:
    """
    Get hourly averaged power samples for charting.

    Args:
        db: Database session
        device_id: Tapo device ID
        hours: Number of hours to look back

    Returns:
        List of dicts with timestamp and avg_watts
    """
    start_time = datetime.utcnow() - timedelta(hours=hours)

    # Query and group by hour (SQLite compatible using strftime)
    # strftime('%Y-%m-%d %H:00:00', timestamp) groups by hour
    hourly_data = db.query(
        func.strftime('%Y-%m-%d %H:00:00', PowerSample.timestamp).label('hour'),
        func.avg(PowerSample.watts).label('avg_watts'),
        func.count(PowerSample.id).label('sample_count')
    ).filter(
        and_(
            PowerSample.device_id == device_id,
            PowerSample.timestamp >= start_time,
            PowerSample.is_online == True
        )
    ).group_by('hour').order_by('hour').all()

    return [
        {
            'timestamp': row.hour,  # Already formatted as ISO-like string
            'avg_watts': round(row.avg_watts, 1),
            'sample_count': row.sample_count
        }
        for row in hourly_data
    ]


def cleanup_old_samples(db: Session, days_to_keep: int = 30) -> int:
    """
    Delete power samples older than specified days.

    Args:
        db: Database session
        days_to_keep: Number of days to retain

    Returns:
        Number of deleted samples
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

    deleted = db.query(PowerSample).filter(
        PowerSample.timestamp < cutoff_date
    ).delete()

    db.commit()

    logger.info(f"Cleaned up {deleted} power samples older than {days_to_keep} days")
    return deleted
