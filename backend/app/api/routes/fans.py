"""
Fan control API endpoints.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_current_admin, get_db
from app.core.config import get_settings
from app.models.user import User
from app.schemas.fans import (
    FanStatusResponse,
    FanInfo,
    SetFanModeRequest,
    SetFanModeResponse,
    SetFanPWMRequest,
    SetFanPWMResponse,
    UpdateFanCurveRequest,
    UpdateFanCurveResponse,
    FanHistoryResponse,
    FanSampleData,
    SwitchBackendRequest,
    SwitchBackendResponse,
    PermissionStatusResponse,
    FanMode,
)
from app.services.fan_control import get_fan_control_service, FanControlService

logger = logging.getLogger(__name__)
router = APIRouter()


def get_fan_service() -> FanControlService:
    """Dependency to get fan control service instance."""
    return get_fan_control_service()


@router.get("/status", response_model=FanStatusResponse)
async def get_fan_status(
    current_user: User = Depends(get_current_user),
    service: FanControlService = Depends(get_fan_service),
):
    """
    Get current fan status for all fans.

    Requires authentication.
    """
    try:
        status = await service.get_status()

        # Convert to response model
        fans = [FanInfo(**fan_data) for fan_data in status["fans"]]

        return FanStatusResponse(
            fans=fans,
            is_dev_mode=status["is_dev_mode"],
            is_using_linux_backend=status["is_using_linux_backend"],
            permission_status=status["permission_status"],
            backend_available=status["backend_available"],
        )

    except Exception as e:
        logger.error(f"Failed to get fan status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get fan status: {str(e)}")


@router.get("/list", response_model=list[FanInfo])
async def list_fans(
    current_user: User = Depends(get_current_user),
    service: FanControlService = Depends(get_fan_service),
):
    """
    Get list of all available fans.

    Requires authentication.
    """
    try:
        status = await service.get_status()
        fans = [FanInfo(**fan_data) for fan_data in status["fans"]]
        return fans

    except Exception as e:
        logger.error(f"Failed to list fans: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list fans: {str(e)}")


@router.post("/mode", response_model=SetFanModeResponse)
async def set_fan_mode(
    request: SetFanModeRequest,
    current_user: User = Depends(get_current_admin),  # Admin only
    service: FanControlService = Depends(get_fan_service),
):
    """
    Set fan operation mode (auto or manual).

    Requires admin role.
    """
    try:
        # Don't allow setting emergency mode directly
        if request.mode == FanMode.EMERGENCY:
            raise HTTPException(
                status_code=400,
                detail="Cannot manually set emergency mode (triggered automatically)"
            )

        success = await service.set_fan_mode(request.fan_id, request.mode)

        if not success:
            raise HTTPException(status_code=404, detail=f"Fan {request.fan_id} not found")

        return SetFanModeResponse(
            success=True,
            fan_id=request.fan_id,
            mode=request.mode,
            message=f"Fan mode set to {request.mode.value}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set fan mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set fan mode: {str(e)}")


@router.post("/pwm", response_model=SetFanPWMResponse)
async def set_fan_pwm(
    request: SetFanPWMRequest,
    current_user: User = Depends(get_current_admin),  # Admin only
    service: FanControlService = Depends(get_fan_service),
):
    """
    Set manual PWM value for a fan.

    Only works when fan is in manual mode.
    Requires admin role.
    """
    try:
        success, rpm = await service.set_fan_pwm(request.fan_id, request.pwm_percent)

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to set PWM (fan not in manual mode or not found)"
            )

        return SetFanPWMResponse(
            success=True,
            fan_id=request.fan_id,
            pwm_percent=request.pwm_percent,
            actual_rpm=rpm,
            message=f"PWM set to {request.pwm_percent}%",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set fan PWM: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set fan PWM: {str(e)}")


@router.put("/curve", response_model=UpdateFanCurveResponse)
async def update_fan_curve(
    request: UpdateFanCurveRequest,
    current_user: User = Depends(get_current_admin),  # Admin only
    service: FanControlService = Depends(get_fan_service),
):
    """
    Update fan temperature curve for auto mode.

    Requires admin role.
    """
    try:
        success = await service.update_fan_curve(request.fan_id, request.curve_points)

        if not success:
            raise HTTPException(status_code=404, detail=f"Fan {request.fan_id} not found")

        return UpdateFanCurveResponse(
            success=True,
            fan_id=request.fan_id,
            curve_points=request.curve_points,
            message=f"Curve updated with {len(request.curve_points)} points",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update fan curve: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update fan curve: {str(e)}")


@router.get("/history", response_model=FanHistoryResponse)
async def get_fan_history(
    fan_id: Optional[str] = Query(None, description="Filter by fan ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum samples to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    service: FanControlService = Depends(get_fan_service),
):
    """
    Get historical fan performance data.

    Requires authentication.
    """
    try:
        samples, total_count = await service.get_history(fan_id, limit, offset)

        sample_data = [
            FanSampleData(
                timestamp=sample.timestamp,
                fan_id=sample.fan_id,
                pwm_percent=sample.pwm_percent or 0,
                rpm=sample.rpm,
                temperature_celsius=sample.temperature_celsius,
                mode=sample.mode,
            )
            for sample in samples
        ]

        return FanHistoryResponse(
            samples=sample_data,
            total_count=total_count,
            fan_id=fan_id,
        )

    except Exception as e:
        logger.error(f"Failed to get fan history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get fan history: {str(e)}")


@router.post("/backend", response_model=SwitchBackendResponse)
async def switch_backend(
    request: SwitchBackendRequest,
    current_user: User = Depends(get_current_admin),  # Admin only
    service: FanControlService = Depends(get_fan_service),
):
    """
    Switch between Linux hardware backend and dev simulation backend.

    Requires admin role.
    """
    try:
        success, is_using_linux = await service.switch_backend(request.use_linux_backend)

        message = ""
        if success:
            if is_using_linux:
                message = "Switched to Linux hardware backend"
            else:
                message = "Switched to dev simulation backend"
        else:
            if request.use_linux_backend:
                message = "Linux backend not available, staying on current backend"
            else:
                message = "Failed to switch backend"

        return SwitchBackendResponse(
            success=success,
            is_using_linux_backend=is_using_linux,
            backend_available=success,
            message=message,
        )

    except Exception as e:
        logger.error(f"Failed to switch backend: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to switch backend: {str(e)}")


@router.get("/permissions", response_model=PermissionStatusResponse)
async def get_permission_status(
    current_user: User = Depends(get_current_user),
    service: FanControlService = Depends(get_fan_service),
):
    """
    Check permission status for fan control.

    Returns information about whether the service has write access to fan controls.
    """
    try:
        status = await service.get_status()

        has_write = status["permission_status"] == "ok"
        perm_status = status["permission_status"]

        message = ""
        suggestions = []

        if perm_status == "ok":
            message = "Full fan control access available"
        elif perm_status == "readonly":
            message = "Read-only access (no write permissions to /sys/class/hwmon)"
            suggestions = [
                "Add user to cpufreq group: sudo usermod -aG cpufreq $USER",
                "Or configure sudoers for tee access to hwmon files",
                "Example sudoers entry: user ALL=(ALL) NOPASSWD: /usr/bin/tee /sys/class/hwmon/*/*",
            ]
        else:
            message = "Fan control backend unavailable"
            suggestions = [
                "Ensure lm-sensors is installed: sudo apt install lm-sensors",
                "Run sensors-detect: sudo sensors-detect",
                "Check if PWM fans are detected: ls /sys/class/hwmon/*/pwm*",
            ]

        return PermissionStatusResponse(
            has_write_permission=has_write,
            status=perm_status,
            message=message,
            suggestions=suggestions,
        )

    except Exception as e:
        logger.error(f"Failed to check permissions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check permissions: {str(e)}")
