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
    device_name: str = "iOS Device",
    token_validity_days: int = 90
):
    """
    Generate a QR code token for mobile device registration.
    
    **SECURITY: Localhost-only registration**
    This endpoint can only be accessed from localhost (127.0.0.1, ::1)
    to prevent remote device hijacking.
    
    Only authenticated users can generate tokens.
    Registration token is valid for 5 minutes and can only be used once.
    Device token is valid for token_validity_days (30-180 days).
    
    Parameters:
    - include_vpn: Include WireGuard VPN configuration in QR code
    - device_name: Device name for VPN client registration
    - token_validity_days: Device token validity (30-180 days, default 90)
    
    Raises:
    - 403: If not accessed from localhost
    - 400: If token_validity_days is out of range
    """
    # SECURITY: Validate localhost-only access
    client_host = request.client.host if request.client else None
    localhost_ips = ["127.0.0.1", "::1", "localhost"]
    
    if client_host not in localhost_ips:
        # Allow dev mode with local network IPs for testing
        from app.core.config import get_settings
        settings = get_settings()
        
        # In production or if not explicitly in dev network, reject non-localhost
        if not (settings.nas_mode == "dev" and client_host and client_host.startswith("192.168.")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Mobile device registration is only allowed from localhost for security reasons. "
                       "Please access BaluHost from http://localhost:8000 or http://127.0.0.1:8000"
            )
    
    # Validate token_validity_days range (30 days minimum, 180 days maximum)
    if token_validity_days < 30 or token_validity_days > 180:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="token_validity_days must be between 30 and 180 days"
        )
    
    from app.core.config import get_settings
    settings = get_settings()
    
    # Determine server URL for mobile devices
    if settings.mobile_server_url:
        server_url = settings.mobile_server_url
    else:
        # Auto-detect local IP address for QR code
        import socket
        try:
            # Create a socket to determine the local IP used to reach the internet
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            # Connect to Google DNS (doesn't actually send data)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            # Fallback to localhost if detection fails
            local_ip = "127.0.0.1"
        
        # Use HTTP for mobile (Android network_security_config allows cleartext for local IPs)
        server_url = f"http://{local_ip}:8000"
    
    # Debug output
    print(f"[Mobile Token] Client: {client_host}, Server URL: {server_url}, Token validity: {token_validity_days} days")
    
    return MobileService.generate_registration_token(
        db=db,
        user_id=str(current_user.id),
        server_url=server_url,
        expires_minutes=5,
        include_vpn=include_vpn,
        device_name=device_name,
        token_validity_days=token_validity_days
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
    devices = MobileService.get_user_devices(db=db, user_id=str(current_user.id))
    print(f"[GET DEVICES] User {current_user.id} has {len(devices)} device(s)")
    for dev in devices:
        print(f"  - {dev.id}: {dev.device_name}")
    return devices


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


@router.post("/devices/{device_id}/push-token", response_model=dict)
async def register_push_token(
    device_id: str,
    push_token: str,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Register or update FCM push notification token for a device.
    
    This endpoint should be called by the mobile app:
    - On first app launch after registration
    - When FCM token is refreshed by Firebase SDK
    - On app startup to ensure token is up-to-date
    
    Args:
        device_id: ID of the device
        push_token: Firebase Cloud Messaging registration token
        
    Returns:
        dict: Confirmation with token verification status
    """
    from app.services.firebase_service import FirebaseService
    
    # Verify device belongs to user
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
    
    # Update push token
    device.push_token = push_token
    db.commit()
    
    # Optionally verify token with Firebase (if initialized)
    token_valid = False
    if FirebaseService.is_available():
        token_valid = FirebaseService.verify_token(push_token)
    
    print(f"[Mobile] Registered FCM token for {device.device_name}: {push_token[:20]}... (valid: {token_valid})")
    
    return {
        "success": True,
        "device_id": device_id,
        "token_verified": token_valid,
        "message": "Push token registered successfully"
    }


@router.get("/devices/{device_id}/notifications", response_model=List[dict])
async def get_device_notifications(
    device_id: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user)
):
    """
    Get notification history for a device.
    
    Returns the last N notifications sent to this device,
    including expiration warnings and status updates.
    
    Args:
        device_id: ID of the device
        limit: Maximum number of notifications to return (default 10)
        
    Returns:
        List of notifications with sent_at, type, success status
    """
    from app.models.mobile import ExpirationNotification as ExpirationNotificationModel
    
    # Verify device belongs to user
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
    
    # Query notification history
    notifications = (
        db.query(ExpirationNotificationModel)
        .filter(ExpirationNotificationModel.device_id == device_id)
        .order_by(ExpirationNotificationModel.sent_at.desc())
        .limit(limit)
        .all()
    )
    
    return [
        {
            "id": notif.id,
            "notification_type": notif.notification_type,
            "sent_at": notif.sent_at.isoformat(),
            "success": notif.success,
            "error_message": notif.error_message,
            "device_expires_at": notif.device_expires_at.isoformat() if notif.device_expires_at else None
        }
        for notif in notifications
    ]


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
