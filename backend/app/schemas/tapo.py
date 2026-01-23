"""
Pydantic schemas for Tapo device power monitoring.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, IPvAnyAddress


class TapoDeviceCreate(BaseModel):
    """Schema for creating a new Tapo device."""
    name: str = Field(..., min_length=1, max_length=255, description="Device name (e.g., 'NAS Power Monitor')")
    device_type: str = Field(default="P115", max_length=50, description="Device model (P115, P110, etc.)")
    ip_address: str = Field(..., description="Device IP address")
    email: str = Field(..., description="Tapo account email (will be encrypted)")
    password: str = Field(..., description="Tapo account password (will be encrypted)")
    is_monitoring: bool = Field(default=True, description="Enable monitoring for this device")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "NAS Power Monitor",
                "device_type": "P115",
                "ip_address": "192.168.1.50",
                "email": "user@example.com",
                "password": "secure_password",
                "is_monitoring": True
            }
        }


class TapoDeviceUpdate(BaseModel):
    """Schema for updating a Tapo device."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    device_type: Optional[str] = Field(None, max_length=50)
    ip_address: Optional[str] = None
    email: Optional[str] = Field(None, description="New email (will be encrypted)")
    password: Optional[str] = Field(None, description="New password (will be encrypted)")
    is_active: Optional[bool] = None
    is_monitoring: Optional[bool] = None


class TapoDeviceResponse(BaseModel):
    """Schema for Tapo device API response (credentials excluded)."""
    id: int
    name: str
    device_type: str
    ip_address: str
    is_active: bool
    is_monitoring: bool
    last_connected: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by_user_id: int

    class Config:
        from_attributes = True


class PowerSample(BaseModel):
    """Single power measurement sample."""
    timestamp: datetime
    watts: float = Field(..., description="Current power consumption in watts")
    voltage: Optional[float] = Field(None, description="Voltage in volts")
    current: Optional[float] = Field(None, description="Current in amperes")
    energy_today: Optional[float] = Field(None, description="Energy consumed today in kWh")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2026-01-23T12:00:00",
                "watts": 120.5,
                "voltage": 230.2,
                "current": 0.523,
                "energy_today": 2.45
            }
        }


class PowerHistory(BaseModel):
    """Power history for a specific device."""
    device_id: int
    device_name: str
    samples: List[PowerSample] = Field(default_factory=list, description="Historical power samples")
    latest_sample: Optional[PowerSample] = Field(None, description="Most recent sample")


class PowerMonitoringResponse(BaseModel):
    """Complete power monitoring response for all devices."""
    devices: List[PowerHistory] = Field(default_factory=list)
    total_current_power: float = Field(0.0, description="Sum of current power from all devices (watts)")
    last_updated: datetime


class CurrentPowerResponse(BaseModel):
    """Current power consumption for a single device."""
    device_id: int
    device_name: str
    current_watts: float
    voltage: Optional[float]
    current: Optional[float]
    energy_today: Optional[float]
    timestamp: datetime
    is_online: bool
