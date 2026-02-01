"""
API routes for energy monitoring and statistics.

Provides detailed energy consumption statistics, downtime tracking,
and historical analysis based on Tapo device power measurements.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.models.tapo_device import TapoDevice
from app.schemas.energy import (
    EnergyPeriodStats,
    HourlySample,
    EnergyDashboard,
    EnergyCostEstimate,
    EnergyPriceConfigRead,
    EnergyPriceConfigUpdate,
    CumulativeDataPoint,
    CumulativeEnergyResponse
)
from app.services import energy_stats, power_monitor
from app.core.config import settings

router = APIRouter()


@router.get("/dashboard/{device_id}", response_model=EnergyDashboard)
async def get_energy_dashboard(
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> EnergyDashboard:
    """
    Get complete energy monitoring dashboard for a device.

    Returns statistics for today, this week, and this month,
    plus hourly chart data for the last 24 hours.
    """
    # Verify device exists
    device = db.query(TapoDevice).filter(TapoDevice.id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found"
        )

    # Get statistics for different periods
    today_stats = energy_stats.get_today_stats(db, device_id)
    week_stats = energy_stats.get_week_stats(db, device_id)
    month_stats = energy_stats.get_month_stats(db, device_id)

    # Get hourly samples for chart (last 24 hours)
    hourly_samples_data = energy_stats.get_hourly_samples(db, device_id, hours=24)
    hourly_samples = [
        HourlySample(**sample) for sample in hourly_samples_data
    ]

    # Get current power from live monitoring
    current_power_data = power_monitor.get_current_power(device_id, db)

    # Convert EnergyPeriod objects to Pydantic models
    today_model = None
    if today_stats:
        today_model = EnergyPeriodStats(
            device_id=today_stats.device_id,
            device_name=today_stats.device_name,
            start_time=today_stats.start_time,
            end_time=today_stats.end_time,
            samples_count=today_stats.samples_count,
            avg_watts=today_stats.avg_watts,
            min_watts=today_stats.min_watts,
            max_watts=today_stats.max_watts,
            total_energy_kwh=today_stats.total_energy_kwh,
            uptime_percentage=today_stats.uptime_percentage,
            downtime_minutes=today_stats.downtime_minutes
        )

    week_model = None
    if week_stats:
        week_model = EnergyPeriodStats(
            device_id=week_stats.device_id,
            device_name=week_stats.device_name,
            start_time=week_stats.start_time,
            end_time=week_stats.end_time,
            samples_count=week_stats.samples_count,
            avg_watts=week_stats.avg_watts,
            min_watts=week_stats.min_watts,
            max_watts=week_stats.max_watts,
            total_energy_kwh=week_stats.total_energy_kwh,
            uptime_percentage=week_stats.uptime_percentage,
            downtime_minutes=week_stats.downtime_minutes
        )

    month_model = None
    if month_stats:
        month_model = EnergyPeriodStats(
            device_id=month_stats.device_id,
            device_name=month_stats.device_name,
            start_time=month_stats.start_time,
            end_time=month_stats.end_time,
            samples_count=month_stats.samples_count,
            avg_watts=month_stats.avg_watts,
            min_watts=month_stats.min_watts,
            max_watts=month_stats.max_watts,
            total_energy_kwh=month_stats.total_energy_kwh,
            uptime_percentage=month_stats.uptime_percentage,
            downtime_minutes=month_stats.downtime_minutes
        )

    return EnergyDashboard(
        device_id=device.id,
        device_name=device.name,
        today=today_model,
        week=week_model,
        month=month_model,
        hourly_samples=hourly_samples,
        current_watts=current_power_data.current_watts,
        is_online=current_power_data.is_online,
        last_updated=current_power_data.timestamp
    )


@router.get("/stats/{device_id}/today", response_model=Optional[EnergyPeriodStats])
async def get_today_energy_stats(
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Optional[EnergyPeriodStats]:
    """Get energy statistics for today."""
    stats = energy_stats.get_today_stats(db, device_id)
    if not stats:
        return None

    return EnergyPeriodStats(
        device_id=stats.device_id,
        device_name=stats.device_name,
        start_time=stats.start_time,
        end_time=stats.end_time,
        samples_count=stats.samples_count,
        avg_watts=stats.avg_watts,
        min_watts=stats.min_watts,
        max_watts=stats.max_watts,
        total_energy_kwh=stats.total_energy_kwh,
        uptime_percentage=stats.uptime_percentage,
        downtime_minutes=stats.downtime_minutes
    )


@router.get("/stats/{device_id}/week", response_model=Optional[EnergyPeriodStats])
async def get_week_energy_stats(
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Optional[EnergyPeriodStats]:
    """Get energy statistics for this week."""
    stats = energy_stats.get_week_stats(db, device_id)
    if not stats:
        return None

    return EnergyPeriodStats(
        device_id=stats.device_id,
        device_name=stats.device_name,
        start_time=stats.start_time,
        end_time=stats.end_time,
        samples_count=stats.samples_count,
        avg_watts=stats.avg_watts,
        min_watts=stats.min_watts,
        max_watts=stats.max_watts,
        total_energy_kwh=stats.total_energy_kwh,
        uptime_percentage=stats.uptime_percentage,
        downtime_minutes=stats.downtime_minutes
    )


@router.get("/stats/{device_id}/month", response_model=Optional[EnergyPeriodStats])
async def get_month_energy_stats(
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Optional[EnergyPeriodStats]:
    """Get energy statistics for this month."""
    stats = energy_stats.get_month_stats(db, device_id)
    if not stats:
        return None

    return EnergyPeriodStats(
        device_id=stats.device_id,
        device_name=stats.device_name,
        start_time=stats.start_time,
        end_time=stats.end_time,
        samples_count=stats.samples_count,
        avg_watts=stats.avg_watts,
        min_watts=stats.min_watts,
        max_watts=stats.max_watts,
        total_energy_kwh=stats.total_energy_kwh,
        uptime_percentage=stats.uptime_percentage,
        downtime_minutes=stats.downtime_minutes
    )


@router.get("/cost/{device_id}", response_model=EnergyCostEstimate)
async def get_energy_cost_estimate(
    device_id: int,
    period: str = Query("today", regex="^(today|week|month)$"),
    cost_per_kwh: float = Query(0.40, gt=0, description="Cost per kWh"),
    currency: str = Query("EUR", max_length=3),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> EnergyCostEstimate:
    """
    Calculate estimated energy cost for a period.

    Args:
        device_id: Tapo device ID
        period: 'today', 'week', or 'month'
        cost_per_kwh: Cost per kilowatt-hour (default: 0.40 EUR)
        currency: Currency code (default: EUR)
    """
    # Get device
    device = db.query(TapoDevice).filter(TapoDevice.id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found"
        )

    # Get stats for requested period
    if period == "today":
        stats = energy_stats.get_today_stats(db, device_id)
        period_name = "Today"
    elif period == "week":
        stats = energy_stats.get_week_stats(db, device_id)
        period_name = "This Week"
    else:  # month
        stats = energy_stats.get_month_stats(db, device_id)
        period_name = "This Month"

    if not stats:
        # No data yet
        return EnergyCostEstimate(
            device_id=device_id,
            device_name=device.name,
            period_name=period_name,
            total_kwh=0.0,
            cost_per_kwh=cost_per_kwh,
            estimated_cost=0.0,
            currency=currency
        )

    estimated_cost = stats.total_energy_kwh * cost_per_kwh

    return EnergyCostEstimate(
        device_id=device_id,
        device_name=device.name,
        period_name=period_name,
        total_kwh=stats.total_energy_kwh,
        cost_per_kwh=cost_per_kwh,
        estimated_cost=round(estimated_cost, 2),
        currency=currency
    )


@router.get("/hourly/{device_id}", response_model=List[HourlySample])
async def get_hourly_samples(
    device_id: int,
    hours: int = Query(24, ge=1, le=168, description="Hours to look back (max 7 days)"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> List[HourlySample]:
    """
    Get hourly averaged power samples for charting.

    Args:
        device_id: Tapo device ID
        hours: Number of hours to look back (1-168)
    """
    samples_data = energy_stats.get_hourly_samples(db, device_id, hours)
    return [HourlySample(**sample) for sample in samples_data]


@router.get("/price", response_model=EnergyPriceConfigRead)
async def get_energy_price(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> EnergyPriceConfigRead:
    """
    Get the current energy price configuration.

    Returns the cost per kWh and currency settings.
    """
    config = energy_stats.get_energy_price_config(db)
    return EnergyPriceConfigRead.model_validate(config)


@router.put("/price", response_model=EnergyPriceConfigRead)
async def update_energy_price(
    update_data: EnergyPriceConfigUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> EnergyPriceConfigRead:
    """
    Update the energy price configuration.

    Requires admin privileges.

    Args:
        update_data: New price configuration (cost_per_kwh: 0.01-10.00, currency)
    """
    config = energy_stats.update_energy_price_config(
        db=db,
        cost_per_kwh=update_data.cost_per_kwh,
        currency=update_data.currency,
        user_id=current_user.id
    )
    return EnergyPriceConfigRead.model_validate(config)


@router.get("/cumulative/{device_id}", response_model=CumulativeEnergyResponse)
async def get_cumulative_energy(
    device_id: int,
    period: str = Query("today", pattern="^(today|week|month)$"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> CumulativeEnergyResponse:
    """
    Get cumulative energy consumption data for charting.

    Returns data points with cumulative kWh and cost over time.

    Args:
        device_id: Tapo device ID
        period: 'today', 'week', or 'month'
    """
    # Get current price config
    price_config = energy_stats.get_energy_price_config(db)

    # Get cumulative data
    data = energy_stats.get_cumulative_energy_data(
        db=db,
        device_id=device_id,
        period=period,
        cost_per_kwh=price_config.cost_per_kwh
    )

    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {device_id} not found"
        )

    # Update currency from config
    data["currency"] = price_config.currency

    # Convert data points to schema
    data_points = [CumulativeDataPoint(**dp) for dp in data["data_points"]]

    return CumulativeEnergyResponse(
        device_id=data["device_id"],
        device_name=data["device_name"],
        period=data["period"],
        cost_per_kwh=data["cost_per_kwh"],
        currency=data["currency"],
        total_kwh=data["total_kwh"],
        total_cost=data["total_cost"],
        data_points=data_points
    )
