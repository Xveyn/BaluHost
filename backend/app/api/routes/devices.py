"""API routes for unified device management (Mobile + Desktop/Sync devices)."""

from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.models.mobile import MobileDevice
from app.models.sync_state import SyncState
from app.models.user import User

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
    devices = []

    # Fetch mobile devices
    if current_user.role == "admin":
        # Admin sees all mobile devices
        mobile_devices = db.query(MobileDevice, User.username).join(
            User, MobileDevice.user_id == User.id
        ).all()

        for device, username in mobile_devices:
            devices.append({
                "id": device.id,
                "name": device.device_name,
                "type": "mobile",
                "platform": device.device_type,  # 'ios' or 'android'
                "model": device.device_model,
                "os_version": device.os_version,
                "app_version": device.app_version,
                "user_id": device.user_id,
                "username": username,
                "last_seen": device.last_seen,
                "last_sync": device.last_sync,
                "created_at": device.created_at,
                "is_active": device.is_active,
                "expires_at": device.expires_at
            })
    else:
        # Regular user sees only their mobile devices
        mobile_devices = db.query(MobileDevice).filter(
            MobileDevice.user_id == current_user.id
        ).all()

        for device in mobile_devices:
            devices.append({
                "id": device.id,
                "name": device.device_name,
                "type": "mobile",
                "platform": device.device_type,
                "model": device.device_model,
                "os_version": device.os_version,
                "app_version": device.app_version,
                "user_id": device.user_id,
                "username": None,  # Not visible to regular users
                "last_seen": device.last_seen,
                "last_sync": device.last_sync,
                "created_at": device.created_at,
                "is_active": device.is_active,
                "expires_at": device.expires_at
            })

    # Fetch desktop/sync devices
    if current_user.role == "admin":
        # Admin sees all sync devices
        sync_devices = db.query(SyncState, User.username).join(
            User, SyncState.user_id == User.id
        ).all()

        for device, username in sync_devices:
            devices.append({
                "id": device.device_id,
                "name": device.device_name or device.device_id,
                "type": "desktop",
                "platform": "unknown",  # Desktop sync doesn't track platform yet
                "model": None,
                "os_version": None,
                "app_version": None,
                "user_id": device.user_id,
                "username": username,
                "last_seen": device.last_sync,
                "last_sync": device.last_sync,
                "created_at": device.created_at,
                "is_active": True,  # Sync devices don't have active flag
                "expires_at": None  # Desktop devices don't expire
            })
    else:
        # Regular user sees only their sync devices
        sync_devices = db.query(SyncState).filter(
            SyncState.user_id == current_user.id
        ).all()

        for device in sync_devices:
            devices.append({
                "id": device.device_id,
                "name": device.device_name or device.device_id,
                "type": "desktop",
                "platform": "unknown",
                "model": None,
                "os_version": None,
                "app_version": None,
                "user_id": device.user_id,
                "username": None,
                "last_seen": device.last_sync,
                "last_sync": device.last_sync,
                "created_at": device.created_at,
                "is_active": True,
                "expires_at": None
            })

    # Sort by created_at descending (newest first)
    devices.sort(
        key=lambda x: x["created_at"].replace(tzinfo=None) if x["created_at"] else datetime.min,
        reverse=True
    )

    return devices


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
    device = db.query(MobileDevice).filter(MobileDevice.id == device_id).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    # Check permissions
    if current_user.role != "admin" and device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this device"
        )

    device.device_name = name
    db.commit()

    return {"success": True, "device_id": device_id, "name": name}


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
    device = db.query(SyncState).filter(SyncState.device_id == device_id).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    # Check permissions
    if current_user.role != "admin" and device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update this device"
        )

    device.device_name = name
    db.commit()

    return {"success": True, "device_id": device_id, "name": name}
