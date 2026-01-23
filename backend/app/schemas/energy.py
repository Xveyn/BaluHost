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
