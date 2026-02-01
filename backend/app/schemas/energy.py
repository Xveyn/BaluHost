"""
Pydantic schemas for energy monitoring and statistics.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class PowerSampleSchema(BaseModel):
    """Individual power sample record."""
    id: int
    device_id: int
    timestamp: datetime
    watts: float
    voltage: Optional[float]
    current: Optional[float]
    energy_today: Optional[float]
    is_online: bool

    class Config:
        from_attributes = True


class EnergyPeriodStats(BaseModel):
    """Energy statistics for a time period."""
    device_id: int
    device_name: str
    start_time: datetime
    end_time: datetime
    samples_count: int
    avg_watts: float = Field(..., description="Average power consumption in watts")
    min_watts: float = Field(..., description="Minimum power consumption in watts")
    max_watts: float = Field(..., description="Maximum power consumption in watts")
    total_energy_kwh: float = Field(..., description="Total energy consumed in kWh")
    uptime_percentage: float = Field(..., description="Percentage of time device was online")
    downtime_minutes: int = Field(..., description="Total downtime in minutes")

    class Config:
        json_schema_extra = {
            "example": {
                "device_id": 1,
                "device_name": "NAS Power Monitor",
                "start_time": "2026-01-23T00:00:00",
                "end_time": "2026-01-23T23:59:59",
                "samples_count": 288,
                "avg_watts": 28.5,
                "min_watts": 22.0,
                "max_watts": 45.2,
                "total_energy_kwh": 0.684,
                "uptime_percentage": 99.3,
                "downtime_minutes": 10
            }
        }


class HourlySample(BaseModel):
    """Hourly averaged power sample for charting."""
    timestamp: str = Field(..., description="ISO timestamp of the hour")
    avg_watts: float = Field(..., description="Average watts for this hour")
    sample_count: int = Field(..., description="Number of samples in this hour")


class EnergyDashboard(BaseModel):
    """Complete energy monitoring dashboard data."""
    device_id: int
    device_name: str

    # Statistics
    today: Optional[EnergyPeriodStats]
    week: Optional[EnergyPeriodStats]
    month: Optional[EnergyPeriodStats]

    # Chart data (last 24 hours)
    hourly_samples: List[HourlySample] = Field(default_factory=list)

    # Current status
    current_watts: float = Field(0.0, description="Current power consumption")
    is_online: bool = Field(True, description="Device online status")
    last_updated: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "device_id": 1,
                "device_name": "NAS Power Monitor",
                "today": {
                    "device_id": 1,
                    "device_name": "NAS Power Monitor",
                    "start_time": "2026-01-23T00:00:00",
                    "end_time": "2026-01-23T23:59:59",
                    "samples_count": 288,
                    "avg_watts": 28.5,
                    "min_watts": 22.0,
                    "max_watts": 45.2,
                    "total_energy_kwh": 0.684,
                    "uptime_percentage": 99.3,
                    "downtime_minutes": 10
                },
                "hourly_samples": [
                    {"timestamp": "2026-01-23T00:00:00", "avg_watts": 25.2, "sample_count": 12},
                    {"timestamp": "2026-01-23T01:00:00", "avg_watts": 24.8, "sample_count": 12}
                ],
                "current_watts": 27.3,
                "is_online": True,
                "last_updated": "2026-01-23T15:30:00"
            }
        }


class EnergyCostEstimate(BaseModel):
    """Energy cost estimation."""
    device_id: int
    device_name: str
    period_name: str = Field(..., description="e.g. 'Today', 'This Week', 'This Month'")
    total_kwh: float
    cost_per_kwh: float = Field(0.40, description="Cost per kWh in currency")
    estimated_cost: float = Field(..., description="Estimated cost in currency")
    currency: str = Field("EUR", description="Currency code")

    class Config:
        json_schema_extra = {
            "example": {
                "device_id": 1,
                "device_name": "NAS Power Monitor",
                "period_name": "Today",
                "total_kwh": 0.684,
                "cost_per_kwh": 0.40,
                "estimated_cost": 0.27,
                "currency": "EUR"
            }
        }


class EnergyPriceConfigRead(BaseModel):
    """Read schema for energy price configuration."""
    id: int
    cost_per_kwh: float = Field(..., description="Cost per kWh in currency")
    currency: str = Field(..., description="Currency code (e.g., EUR, USD)")
    updated_at: datetime
    updated_by_user_id: Optional[int]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "cost_per_kwh": 0.40,
                "currency": "EUR",
                "updated_at": "2026-01-28T12:00:00",
                "updated_by_user_id": 1
            }
        }


class EnergyPriceConfigUpdate(BaseModel):
    """Update schema for energy price configuration."""
    cost_per_kwh: float = Field(..., ge=0.01, le=10.0, description="Cost per kWh (0.01-10.00)")
    currency: str = Field("EUR", max_length=10, description="Currency code")

    class Config:
        json_schema_extra = {
            "example": {
                "cost_per_kwh": 0.42,
                "currency": "EUR"
            }
        }


class CumulativeDataPoint(BaseModel):
    """Single data point for cumulative energy chart."""
    timestamp: str = Field(..., description="ISO timestamp")
    cumulative_kwh: float = Field(..., description="Cumulative energy in kWh")
    cumulative_cost: float = Field(..., description="Cumulative cost in currency")
    instant_watts: float = Field(..., description="Instantaneous power in watts")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2026-01-28T12:00:00",
                "cumulative_kwh": 0.125,
                "cumulative_cost": 0.05,
                "instant_watts": 28.5
            }
        }


class CumulativeEnergyResponse(BaseModel):
    """Response with cumulative energy data for charting."""
    device_id: int
    device_name: str
    period: str = Field(..., description="today, week, or month")
    cost_per_kwh: float
    currency: str
    total_kwh: float = Field(..., description="Total energy for the period")
    total_cost: float = Field(..., description="Total cost for the period")
    data_points: List[CumulativeDataPoint] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "device_id": 1,
                "device_name": "NAS Power Monitor",
                "period": "today",
                "cost_per_kwh": 0.40,
                "currency": "EUR",
                "total_kwh": 0.684,
                "total_cost": 0.27,
                "data_points": [
                    {
                        "timestamp": "2026-01-28T00:00:00",
                        "cumulative_kwh": 0.0,
                        "cumulative_cost": 0.0,
                        "instant_watts": 25.0
                    }
                ]
            }
        }
