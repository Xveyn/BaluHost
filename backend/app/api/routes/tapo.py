"""
API routes for Tapo power monitoring.

Device configuration requires admin privileges.
Power monitoring data is accessible to all authenticated users.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.models.tapo_device import TapoDevice
from app.schemas.tapo import (
    TapoDeviceCreate,
    TapoDeviceUpdate,
    TapoDeviceResponse,
    PowerMonitoringResponse,
    CurrentPowerResponse,
)
from app.services import power_monitor, tapo_service
from app.services.audit.logger_db import AuditLoggerDB

router = APIRouter()


# Device Configuration Endpoints (Admin only)

@router.post("/devices", response_model=TapoDeviceResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
def create_tapo_device(
    request: Request, response: Response,
    device_data: TapoDeviceCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> TapoDevice:
    """
    Create a new Tapo device for power monitoring.

    **Admin only.** Credentials are encrypted before storage.
    """
    try:
        device = tapo_service.create_device(db, device_data, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # Audit log
    audit_logger = AuditLoggerDB()
    audit_logger.log_event(
        event_type="TAPO",
        action="create_tapo_device",
        user=current_user.username,
        resource=f"device:{device.id}",
        success=True,
        details={"device_id": device.id, "name": device.name, "ip": device.ip_address}
    )

    return device


@router.get("/devices", response_model=List[TapoDeviceResponse])
@user_limiter.limit(get_limit("admin_operations"))
def list_tapo_devices(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> List[TapoDevice]:
    """
    List all configured Tapo devices.

    **Admin only.** Credentials are not included in response.
    """
    return tapo_service.list_devices(db)


@router.get("/devices/{device_id}", response_model=TapoDeviceResponse)
@user_limiter.limit(get_limit("admin_operations"))
def get_tapo_device(
    request: Request, response: Response,
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> TapoDevice:
    """
    Get a specific Tapo device by ID.

    **Admin only.** Credentials are not included in response.
    """
    device = tapo_service.get_device(db, device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )
    return device


@router.patch("/devices/{device_id}", response_model=TapoDeviceResponse)
@user_limiter.limit(get_limit("admin_operations"))
def update_tapo_device(
    request: Request, response: Response,
    device_id: int,
    device_data: TapoDeviceUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> TapoDevice:
    """
    Update a Tapo device configuration.

    **Admin only.** Partial updates are supported.
    """
    device = tapo_service.get_device(db, device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )

    try:
        updated = tapo_service.update_device(db, device, device_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

    # Audit log
    audit_logger = AuditLoggerDB()
    audit_logger.log_event(
        event_type="TAPO",
        action="update_tapo_device",
        user=current_user.username,
        resource=f"device:{device.id}",
        success=True,
        details={"device_id": device.id, "name": device.name, "updates": list(device_data.model_dump(exclude_unset=True).keys())}
    )

    return updated


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
def delete_tapo_device(
    request: Request, response: Response,
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> None:
    """
    Delete a Tapo device.

    **Admin only.** Device is permanently removed from database.
    """
    device = tapo_service.get_device(db, device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )

    device_name = device.name
    device_ip = device.ip_address

    tapo_service.delete_device(db, device)

    # Audit log
    audit_logger = AuditLoggerDB()
    audit_logger.log_event(
        event_type="TAPO",
        action="delete_tapo_device",
        user=current_user.username,
        resource=f"device:{device_id}",
        success=True,
        details={"device_id": device_id, "name": device_name, "ip": device_ip}
    )


# Power Monitoring Endpoints (All authenticated users)

@router.get("/power/history", response_model=PowerMonitoringResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_power_history(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PowerMonitoringResponse:
    """
    Get power consumption history for all devices.

    Returns historical samples and current total power consumption.
    **Requires authentication.**
    """
    return power_monitor.get_power_history(db)


@router.get("/power/current/{device_id}", response_model=CurrentPowerResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_current_power(
    request: Request, response: Response,
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> CurrentPowerResponse:
    """
    Get current power consumption for a specific device.

    Returns the latest power reading with voltage, current, and energy data.
    **Requires authentication.**
    """
    try:
        return power_monitor.get_current_power(device_id, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
