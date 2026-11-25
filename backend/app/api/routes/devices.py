"""API routes for unified device management (Mobile + Desktop/Sync devices)."""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db
from app.services.mobile import (
    list_all_devices,
    update_mobile_device_name as svc_update_mobile_name,
    update_desktop_device_name as svc_update_desktop_name,
    remove_desktop_device as svc_remove_desktop_device,
)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("/all")
@user_limiter.limit(get_limit("admin_operations"))
async def get_all_devices(
    request: Request, response: Response,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get all registered devices (Mobile + Desktop) for the current user.

    - Regular users see only their own devices
    - Admins see all devices from all users with username included

    Returns unified device list with:
    - id: Device ID
    - name: User-friendly device name
    - type: 'mobile' or 'desktop'
    - platform: 'ios', 'android', 'windows', 'mac', 'linux'
    - user_id: Owner user ID
    - username: Owner username (admins only)
    - last_seen: Last activity timestamp
    - created_at: Registration timestamp
    - is_active: Active status (mobile only)
    """
    return list_all_devices(db, current_user.id, current_user.role == "admin")


@router.patch("/mobile/{device_id}/name")
@user_limiter.limit(get_limit("admin_operations"))
async def update_mobile_device_name(
    request: Request, response: Response,
    device_id: str,
    name: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Update mobile device name.

    Users can only update their own devices.
    Admins can update any device.
    """
    try:
        result = svc_update_mobile_name(
            db, device_id, name, current_user.id, current_user.role == "admin"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    return result


@router.patch("/desktop/{device_id}/name")
@user_limiter.limit(get_limit("admin_operations"))
async def update_desktop_device_name(
    request: Request, response: Response,
    device_id: str,
    name: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Update desktop sync device name.

    Users can only update their own devices.
    Admins can update any device.
    """
    try:
        result = svc_update_desktop_name(
            db, device_id, name, current_user.id, current_user.role == "admin"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    return result


@router.delete("/desktop/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def remove_desktop_device(
    request: Request, response: Response,
    device_id: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Remove a desktop sync device and revoke its pairing (refresh tokens).

    Users can only remove their own devices. Admins can remove any device.
    """
    try:
        result = svc_remove_desktop_device(
            db, device_id, current_user.id, current_user.role == "admin"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    get_audit_logger_db().log_security_event(
        action="desktop_device_removed",
        user=current_user.username,
        resource=device_id,
        details={"user": current_user.username, "device_id": device_id},
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        db=db,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
