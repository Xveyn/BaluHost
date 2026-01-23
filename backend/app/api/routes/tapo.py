"""
API routes for Tapo power monitoring.

Device configuration requires admin privileges.
Power monitoring data is accessible to all authenticated users.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.models.tapo_device import TapoDevice
from app.schemas.tapo import (
    TapoDeviceCreate,
    TapoDeviceUpdate,
    TapoDeviceResponse,
    PowerMonitoringResponse,
    CurrentPowerResponse,
)
from app.services import power_monitor
from app.services.vpn_encryption import VPNEncryption
from app.services.audit_logger_db import AuditLoggerDB

router = APIRouter()


# Device Configuration Endpoints (Admin only)

@router.post("/devices", response_model=TapoDeviceResponse, status_code=status.HTTP_201_CREATED)
def create_tapo_device(
    device_data: TapoDeviceCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> TapoDevice:
    """
    Create a new Tapo device for power monitoring.

    **Admin only.** Credentials are encrypted before storage.
    """
    # Check if device with same IP already exists
    existing = db.query(TapoDevice).filter(
        TapoDevice.ip_address == device_data.ip_address
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Device with IP {device_data.ip_address} already exists"
        )

    # Encrypt credentials
    try:
        email_encrypted = VPNEncryption.encrypt_key(device_data.email)
        password_encrypted = VPNEncryption.encrypt_key(device_data.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Encryption failed: {str(e)}"
        )

    # Create device
    device = TapoDevice(
        name=device_data.name,
        device_type=device_data.device_type,
        ip_address=device_data.ip_address,
        email_encrypted=email_encrypted,
        password_encrypted=password_encrypted,
        is_active=True,
        is_monitoring=device_data.is_monitoring,
        created_by_user_id=current_user.id,
    )

    db.add(device)
    db.commit()
    db.refresh(device)

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
def list_tapo_devices(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> List[TapoDevice]:
    """
    List all configured Tapo devices.

    **Admin only.** Credentials are not included in response.
    """
    devices = db.query(TapoDevice).order_by(TapoDevice.created_at.desc()).all()
    return devices


@router.get("/devices/{device_id}", response_model=TapoDeviceResponse)
def get_tapo_device(
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> TapoDevice:
    """
    Get a specific Tapo device by ID.

    **Admin only.** Credentials are not included in response.
    """
    device = db.query(TapoDevice).filter(TapoDevice.id == device_id).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )

    return device


@router.patch("/devices/{device_id}", response_model=TapoDeviceResponse)
def update_tapo_device(
    device_id: int,
    device_data: TapoDeviceUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> TapoDevice:
    """
    Update a Tapo device configuration.

    **Admin only.** Partial updates are supported.
    """
    device = db.query(TapoDevice).filter(TapoDevice.id == device_id).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )

    # Update fields
    update_data = device_data.model_dump(exclude_unset=True)

    # Encrypt credentials if provided
    if "email" in update_data:
        try:
            device.email_encrypted = VPNEncryption.encrypt_key(update_data["email"])
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Email encryption failed: {str(e)}"
            )
        del update_data["email"]

    if "password" in update_data:
        try:
            device.password_encrypted = VPNEncryption.encrypt_key(update_data["password"])
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Password encryption failed: {str(e)}"
            )
        del update_data["password"]

    # Apply remaining updates
    for field, value in update_data.items():
        setattr(device, field, value)

    db.commit()
    db.refresh(device)

    # Audit log
    audit_logger = AuditLoggerDB()
    audit_logger.log_event(
        event_type="TAPO",
        action="update_tapo_device",
        user=current_user.username,
        resource=f"device:{device.id}",
        success=True,
        details={"device_id": device.id, "name": device.name, "updates": list(update_data.keys())}
    )

    return device


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tapo_device(
    device_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
) -> None:
    """
    Delete a Tapo device.

    **Admin only.** Device is permanently removed from database.
    """
    device = db.query(TapoDevice).filter(TapoDevice.id == device_id).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device with ID {device_id} not found"
        )

    device_name = device.name
    device_ip = device.ip_address

    db.delete(device)
    db.commit()

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
async def get_power_history(
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
async def get_current_power(
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
