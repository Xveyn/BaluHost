"""API routes for mobile device management (BaluMobile)."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.schemas.user import UserPublic
from app.schemas.mobile import (
    MobileDevice as MobileDeviceSchema,
    MobileDeviceCreate,
    MobileDeviceUpdate,
    MobileRegistrationToken,
    MobileRegistrationResponse,
    CameraBackupSettings,
    CameraBackupStatus,
    SyncFolder as SyncFolderSchema,
    SyncFolderCreate,
)
from app.services.mobile import MobileService

router = APIRouter(prefix="/mobile", tags=["mobile"])


@router.post("/token/generate", response_model=MobileRegistrationToken)
async def generate_registration_token(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
    include_vpn: bool = False,
    device_name: str = "iOS Device"
):
    """
    Generate a QR code token for mobile device registration.
    
    Only authenticated users can generate tokens.
    Token is valid for 5 minutes and can only be used once.
    
    Parameters:
    - include_vpn: Include WireGuard VPN configuration in QR code
    - device_name: Device name for VPN client registration
    """
    from app.core.config import get_settings
    settings = get_settings()
    
    # ALWAYS use configured URL for mobile devices (ignore request URL to avoid .local domains)
    # Use HTTP for mobile during dev (Android network_security_config allows cleartext for 192.168.178.x)
    server_url = settings.mobile_server_url or "http://192.168.178.21:8000"
    
    # Debug output
    print(f"[Mobile Token] Using server URL: {server_url}")
    
    return MobileService.generate_registration_token(
        db=db,
        user_id=str(current_user.id),
        server_url=server_url,
        expires_minutes=5,
        include_vpn=include_vpn,
        device_name=device_name
    )


@router.post("/register", response_model=MobileRegistrationResponse)
async def register_device(
    device_data: MobileDeviceCreate,
    db: Session = Depends(get_db)
):
    """
    Register a new mobile device using a registration token.
    
    This endpoint is called by BaluMobile app after scanning the QR code.
    Returns access token and user info for the registered device.
    """
    return MobileService.register_device(db=db, device_data=device_data)


@router.get("/devices", response_model=List[MobileDeviceSchema])
async def get_devices(
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get all registered mobile devices for the current user.
    """
    return MobileService.get_user_devices(db=db, user_id=str(current_user.id))


@router.get("/devices/{device_id}", response_model=MobileDeviceSchema)
async def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get details of a specific mobile device.
    """
    device = MobileService.get_device(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id)
    )
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    return device


@router.patch("/devices/{device_id}", response_model=MobileDeviceSchema)
async def update_device(
    device_id: str,
    device_update: MobileDeviceUpdate,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Update mobile device settings (name, push token, active status).
    """
    return MobileService.update_device(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id),
        device_update=device_update
    )


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Delete a mobile device registration.
    """
    MobileService.delete_device(
        db=db,
        device_id=device_id,
        user_id=str(current_user.id)
    )
    return None


# Camera Backup Endpoints


@router.get("/camera/settings/{device_id}", response_model=CameraBackupSettings)
async def get_camera_backup_settings(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get camera backup settings for a device.
    """
    settings = MobileService.get_camera_backup_settings(db=db, device_id=device_id)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera backup settings not found"
        )
    return settings


@router.put("/camera/settings/{device_id}", response_model=CameraBackupSettings)
async def update_camera_backup_settings(
    device_id: str,
    settings: CameraBackupSettings,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Update camera backup settings.
    """
    return MobileService.update_camera_backup_settings(
        db=db,
        device_id=device_id,
        settings=settings
    )


# Sync Folder Endpoints


@router.get("/sync/folders/{device_id}", response_model=List[SyncFolderSchema])
async def get_sync_folders(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get all sync folders for a device.
    """
    return MobileService.get_sync_folders(db=db, device_id=device_id)


@router.post("/sync/folders/{device_id}", response_model=SyncFolderSchema)
async def create_sync_folder(
    device_id: str,
    folder_data: SyncFolderCreate,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Create a new sync folder configuration.
    """
    return MobileService.create_sync_folder(
        db=db,
        device_id=device_id,
        folder_data=folder_data
    )
