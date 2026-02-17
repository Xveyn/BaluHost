"""
Fan control schemas for request/response validation.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime


class FanMode(str, Enum):
    """Fan operation mode."""
    AUTO = "auto"
    MANUAL = "manual"
    EMERGENCY = "emergency"
    SCHEDULED = "scheduled"


class CurvePreset(str, Enum):
    """Predefined fan curve presets."""
    SILENT = "silent"
    BALANCED = "balanced"
    PERFORMANCE = "performance"
    CUSTOM = "custom"


# Preset curve definitions
CURVE_PRESETS: Dict[str, List[dict]] = {
    "silent": [
        {"temp": 40, "pwm": 30},
        {"temp": 55, "pwm": 35},
        {"temp": 70, "pwm": 55},
        {"temp": 80, "pwm": 75},
        {"temp": 90, "pwm": 100},
    ],
    "balanced": [
        {"temp": 35, "pwm": 30},
        {"temp": 50, "pwm": 50},
        {"temp": 70, "pwm": 80},
        {"temp": 85, "pwm": 100},
    ],
    "performance": [
        {"temp": 30, "pwm": 40},
        {"temp": 45, "pwm": 60},
        {"temp": 60, "pwm": 85},
        {"temp": 75, "pwm": 100},
    ],
}


class FanCurvePoint(BaseModel):
    """Single point in a temperature-PWM curve."""
    temp: float = Field(..., ge=0, le=150, description="Temperature in Celsius")
    pwm: int = Field(..., ge=0, le=100, description="PWM percentage (0-100)")

    class Config:
        json_schema_extra = {
            "example": {
                "temp": 50.0,
                "pwm": 60
            }
        }


class FanInfo(BaseModel):
    """Information about a single fan."""
    fan_id: str = Field(..., description="Unique fan identifier (e.g., hwmon0_pwm1)")
    name: str = Field(..., description="Human-readable fan name")
    rpm: Optional[int] = Field(None, description="Current RPM (revolutions per minute)")
    pwm_percent: int = Field(..., ge=0, le=100, description="Current PWM percentage")
    temperature_celsius: Optional[float] = Field(None, description="Associated temperature sensor reading")
    mode: FanMode = Field(..., description="Current operation mode")
    is_active: bool = Field(True, description="Whether fan control is active")
    min_pwm_percent: int = Field(30, ge=0, le=100)
    max_pwm_percent: int = Field(100, ge=0, le=100)
    emergency_temp_celsius: float = Field(85.0, ge=0, le=150)
    temp_sensor_id: Optional[str] = Field(None, description="Associated temperature sensor ID")
    curve_points: List[FanCurvePoint] = Field(default_factory=list)
    hysteresis_celsius: float = Field(3.0, ge=0, le=15, description="Temperature hysteresis to prevent oscillation")

    class Config:
        json_schema_extra = {
            "example": {
                "fan_id": "hwmon0_pwm1",
                "name": "CPU Fan",
                "rpm": 2400,
                "pwm_percent": 65,
                "temperature_celsius": 58.5,
                "mode": "auto",
                "is_active": True,
                "min_pwm_percent": 30,
                "max_pwm_percent": 100,
                "emergency_temp_celsius": 85.0,
                "temp_sensor_id": "hwmon0_temp1",
                "curve_points": [
                    {"temp": 35, "pwm": 30},
                    {"temp": 50, "pwm": 50},
                    {"temp": 70, "pwm": 80},
                    {"temp": 85, "pwm": 100}
                ],
                "hysteresis_celsius": 3.0
            }
        }


class FanStatusResponse(BaseModel):
    """Response for fan status endpoint."""
    fans: List[FanInfo] = Field(..., description="List of all fans")
    is_dev_mode: bool = Field(..., description="Whether running in dev/simulation mode")
    is_using_linux_backend: bool = Field(..., description="Whether using Linux hardware backend")
    permission_status: str = Field(..., description="Permission status (ok/readonly/unavailable)")
    backend_available: bool = Field(..., description="Whether backend is available")

    class Config:
        json_schema_extra = {
            "example": {
                "fans": [],
                "is_dev_mode": True,
                "is_using_linux_backend": False,
                "permission_status": "ok",
                "backend_available": True
            }
        }


class SetFanModeRequest(BaseModel):
    """Request to change fan mode."""
    fan_id: str = Field(..., description="Fan identifier")
    mode: FanMode = Field(..., description="Target mode (auto or manual)")

    class Config:
        json_schema_extra = {
            "example": {
                "fan_id": "hwmon0_pwm1",
                "mode": "auto"
            }
        }


class SetFanModeResponse(BaseModel):
    """Response for mode change."""
    success: bool
    fan_id: str
    mode: FanMode
    message: Optional[str] = None


class SetFanPWMRequest(BaseModel):
    """Request to set manual PWM value."""
    fan_id: str = Field(..., description="Fan identifier")
    pwm_percent: int = Field(..., ge=0, le=100, description="PWM percentage (0-100)")

    class Config:
        json_schema_extra = {
            "example": {
                "fan_id": "hwmon0_pwm1",
                "pwm_percent": 75
            }
        }


class SetFanPWMResponse(BaseModel):
    """Response for PWM change."""
    success: bool
    fan_id: str
    pwm_percent: int
    actual_rpm: Optional[int] = None
    message: Optional[str] = None


class UpdateFanCurveRequest(BaseModel):
    """Request to update fan temperature curve."""
    fan_id: str = Field(..., description="Fan identifier")
    curve_points: List[FanCurvePoint] = Field(..., min_length=2, max_length=10)

    @field_validator('curve_points')
    @classmethod
    def validate_curve_points(cls, points: List[FanCurvePoint]) -> List[FanCurvePoint]:
        """Ensure curve points are sorted by temperature."""
        if len(points) < 2:
            raise ValueError("Curve must have at least 2 points")

        sorted_points = sorted(points, key=lambda p: p.temp)

        # Check for duplicate temperatures
        temps = [p.temp for p in sorted_points]
        if len(temps) != len(set(temps)):
            raise ValueError("Curve points must have unique temperatures")

        return sorted_points

    class Config:
        json_schema_extra = {
            "example": {
                "fan_id": "hwmon0_pwm1",
                "curve_points": [
                    {"temp": 35, "pwm": 30},
                    {"temp": 50, "pwm": 50},
                    {"temp": 70, "pwm": 80},
                    {"temp": 85, "pwm": 100}
                ]
            }
        }


class UpdateFanCurveResponse(BaseModel):
    """Response for curve update."""
    success: bool
    fan_id: str
    curve_points: List[FanCurvePoint]
    message: Optional[str] = None


class FanSampleData(BaseModel):
    """Single historical sample."""
    timestamp: datetime
    fan_id: str
    pwm_percent: int
    rpm: Optional[int]
    temperature_celsius: Optional[float]
    mode: str


class FanHistoryResponse(BaseModel):
    """Response for history endpoint."""
    samples: List[FanSampleData]
    total_count: int
    fan_id: Optional[str] = None


class SwitchBackendRequest(BaseModel):
    """Request to switch between dev and Linux backend."""
    use_linux_backend: bool = Field(..., description="True for Linux hardware, False for dev simulation")

    class Config:
        json_schema_extra = {
            "example": {
                "use_linux_backend": True
            }
        }


class SwitchBackendResponse(BaseModel):
    """Response for backend switch."""
    success: bool
    is_using_linux_backend: bool
    backend_available: bool
    message: Optional[str] = None


class PermissionStatusResponse(BaseModel):
    """Response for permission status check."""
    has_write_permission: bool
    status: str  # ok, readonly, unavailable
    message: str
    suggestions: List[str] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "has_write_permission": False,
                "status": "readonly",
                "message": "No write permission to /sys/class/hwmon",
                "suggestions": [
                    "Add user to cpufreq group: sudo usermod -aG cpufreq $USER",
                    "Or configure sudoers for tee access"
                ]
            }
        }


class PresetInfo(BaseModel):
    """Information about a fan curve preset."""
    name: str = Field(..., description="Preset name (silent, balanced, performance)")
    label: str = Field(..., description="Human-readable label")
    description: str = Field(..., description="Description of the preset behavior")
    curve_points: List[FanCurvePoint] = Field(..., description="Curve points for this preset")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "balanced",
                "label": "Balanced",
                "description": "Balance between noise and cooling performance",
                "curve_points": [
                    {"temp": 35, "pwm": 30},
                    {"temp": 50, "pwm": 50},
                    {"temp": 70, "pwm": 80},
                    {"temp": 85, "pwm": 100}
                ]
            }
        }


class PresetsResponse(BaseModel):
    """Response for listing available presets."""
    presets: List[PresetInfo] = Field(..., description="List of available presets")


class ApplyPresetRequest(BaseModel):
    """Request to apply a preset to a fan."""
    fan_id: str = Field(..., description="Fan identifier")
    preset: CurvePreset = Field(..., description="Preset to apply")

    class Config:
        json_schema_extra = {
            "example": {
                "fan_id": "hwmon0_pwm1",
                "preset": "balanced"
            }
        }


class ApplyPresetResponse(BaseModel):
    """Response for preset application."""
    success: bool
    fan_id: str
    preset: str
    curve_points: List[FanCurvePoint]
    message: Optional[str] = None


class UpdateFanConfigRequest(BaseModel):
    """Request to update fan configuration (hysteresis, etc.)."""
    fan_id: str = Field(..., description="Fan identifier")
    hysteresis_celsius: Optional[float] = Field(None, ge=0, le=15, description="Temperature hysteresis (0-15°C)")
    min_pwm_percent: Optional[int] = Field(None, ge=0, le=100, description="Minimum PWM percentage")
    max_pwm_percent: Optional[int] = Field(None, ge=0, le=100, description="Maximum PWM percentage")
    emergency_temp_celsius: Optional[float] = Field(None, ge=0, le=150, description="Emergency temperature threshold")

    class Config:
        json_schema_extra = {
            "example": {
                "fan_id": "hwmon0_pwm1",
                "hysteresis_celsius": 5.0
            }
        }


class UpdateFanConfigResponse(BaseModel):
    """Response for fan config update."""
    success: bool
    fan_id: str
    hysteresis_celsius: float
    min_pwm_percent: int
    max_pwm_percent: int
    emergency_temp_celsius: float
    message: Optional[str] = None


# --- Schedule Schemas ---

class FanScheduleEntrySchema(BaseModel):
    """Schema for a fan schedule entry."""
    id: int
    fan_id: str
    name: str = Field(..., min_length=1, max_length=100)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="Start time in HH:MM format")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="End time in HH:MM format")
    curve_points: List[FanCurvePoint] = Field(..., min_length=2, max_length=10)
    priority: int = Field(0, ge=0, le=100)
    is_enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateFanScheduleEntryRequest(BaseModel):
    """Request to create a new fan schedule entry."""
    name: str = Field(..., min_length=1, max_length=100, description="Schedule entry label")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="Start time in HH:MM format")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="End time in HH:MM format")
    curve_points: List[FanCurvePoint] = Field(..., min_length=2, max_length=10)
    priority: int = Field(0, ge=0, le=100, description="Lower number = higher priority")
    is_enabled: bool = Field(True, description="Whether this entry is active")

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate HH:MM format with valid hour/minute ranges."""
        parts = v.split(':')
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time value")
        return v

    @field_validator('curve_points')
    @classmethod
    def validate_curve_points(cls, points: List[FanCurvePoint]) -> List[FanCurvePoint]:
        """Ensure curve points are sorted by temperature with unique temps."""
        if len(points) < 2:
            raise ValueError("Curve must have at least 2 points")
        sorted_points = sorted(points, key=lambda p: p.temp)
        temps = [p.temp for p in sorted_points]
        if len(temps) != len(set(temps)):
            raise ValueError("Curve points must have unique temperatures")
        return sorted_points

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Night Mode",
                "start_time": "22:00",
                "end_time": "06:00",
                "curve_points": [
                    {"temp": 40, "pwm": 30},
                    {"temp": 60, "pwm": 45},
                    {"temp": 80, "pwm": 70},
                    {"temp": 90, "pwm": 100}
                ],
                "priority": 0,
                "is_enabled": True
            }
        }


class UpdateFanScheduleEntryRequest(BaseModel):
    """Request to update an existing fan schedule entry."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    start_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    curve_points: Optional[List[FanCurvePoint]] = Field(None, min_length=2, max_length=10)
    priority: Optional[int] = Field(None, ge=0, le=100)
    is_enabled: Optional[bool] = None

    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        parts = v.split(':')
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Invalid time value")
        return v

    @field_validator('curve_points')
    @classmethod
    def validate_curve_points(cls, points: Optional[List[FanCurvePoint]]) -> Optional[List[FanCurvePoint]]:
        if points is None:
            return points
        if len(points) < 2:
            raise ValueError("Curve must have at least 2 points")
        sorted_points = sorted(points, key=lambda p: p.temp)
        temps = [p.temp for p in sorted_points]
        if len(temps) != len(set(temps)):
            raise ValueError("Curve points must have unique temperatures")
        return sorted_points


class FanScheduleListResponse(BaseModel):
    """Response for listing schedule entries."""
    entries: List[FanScheduleEntrySchema]
    fan_id: str
    total_count: int


class ActiveScheduleInfo(BaseModel):
    """Information about the currently active schedule entry."""
    active_entry: Optional[FanScheduleEntrySchema] = None
    next_entry: Optional[FanScheduleEntrySchema] = None
    is_using_default_curve: bool = True
