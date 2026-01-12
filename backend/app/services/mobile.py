"""Service for mobile device management and registration."""

import secrets
import qrcode
import io
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.mobile import (
    MobileDevice,
    MobileRegistrationToken,
    CameraBackup,
    SyncFolder,
    UploadQueue
)
from app.models.user import User
from app.schemas.mobile import (
    MobileDeviceCreate,
    MobileDeviceUpdate,
    MobileRegistrationToken as MobileRegistrationTokenSchema,
    CameraBackupSettings,
    CameraBackupStatus,
    SyncFolderCreate,
)
from app.services import auth as auth_service
import logging

logger = logging.getLogger(__name__)


class MobileService:
    """Service for mobile device operations."""
    
    @staticmethod
    def generate_registration_token(
        db: Session,
        user_id: str,
        server_url: str,
        expires_minutes: int = 5,
        include_vpn: bool = False,
        device_name: str = "iOS Device",
        token_validity_days: int = 90
    ) -> MobileRegistrationTokenSchema:
        """Generate a one-time registration token for mobile device pairing.
        
        Args:
            token_validity_days: How long the device authorization will be valid (30-180 days)
        """
        # Generate secure random token
        token = f"reg_{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
        
        # Save token to database
        db_token = MobileRegistrationToken(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
            used=False
        )
        db.add(db_token)
        db.commit()
        
        # Generate VPN config if requested
        vpn_config_base64 = None
        if include_vpn:
            try:
                from app.services.vpn import VPNService
                from app.models.vpn import FritzBoxVPNConfig
                
                # PRIORITY 1: Check for Fritz!Box config (uploaded by admin)
                fritzbox_config = db.query(FritzBoxVPNConfig).filter(
                    FritzBoxVPNConfig.is_active == True
                ).first()
                
                if fritzbox_config:
                    # Use Fritz!Box config (shared for all clients)
                    vpn_config_base64 = VPNService.get_fritzbox_config_base64(db)
                else:
                    # FALLBACK: Auto-generate client-specific config (existing behavior)
                    server_endpoint = server_url.replace("http://", "").replace("https://", "").split(":")[0]
                    vpn_response = VPNService.create_client_config(
                        db=db,
                        user_id=int(user_id),
                        device_name=device_name,
                        server_public_endpoint=server_endpoint,
                    )
                    vpn_config_base64 = vpn_response.config_base64
            except Exception as e:
                # VPN generation failed, continue without VPN
                logger.warning(f"VPN config generation failed: {e}")
        
        # Generate QR code with registration data
        import json
        qr_data = {
            "token": token,
            "server": server_url,
            "expires_at": expires_at.isoformat(),
            "device_token_validity_days": token_validity_days
        }
        if vpn_config_base64:
            qr_data["vpn_config"] = vpn_config_base64
        
        # Create QR code image with JSON data
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(json.dumps(qr_data))
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return MobileRegistrationTokenSchema(
            token=token,
            server_url=server_url,
            expires_at=expires_at,
            qr_code=qr_code_base64,
            vpn_config=vpn_config_base64,
            device_token_validity_days=token_validity_days
        )
    
    @staticmethod
    def register_device(
        db: Session,
        device_data: MobileDeviceCreate
    ) -> dict:
        """Register a new mobile device using a registration token."""
        # Validate token
        token_record = db.query(MobileRegistrationToken).filter(
            MobileRegistrationToken.token == device_data.token
        ).first()
        
        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid registration token"
            )
        
        if token_record.used:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Registration token already used"
            )
        
        # Check token expiration
        token_expires = token_record.expires_at
        if token_expires is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid registration token"
            )
        
        if token_expires.tzinfo is None:
            token_expires = token_expires.replace(tzinfo=timezone.utc)
        if token_expires < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Registration token expired"
            )
        
        # Mark token as used
        token_record.used = True
        
        # Extract device info
        device_info = device_data.device_info
        
        # Calculate device token expiration
        # Use provided token_validity_days or default to 90 days
        token_validity_days = device_data.token_validity_days or 90
        
        # Enforce security constraints (30-180 days)
        if token_validity_days < 30:
            token_validity_days = 30
        elif token_validity_days > 180:
            token_validity_days = 180
        
        device_expires_at = datetime.now(timezone.utc) + timedelta(days=token_validity_days)
        
        # Create mobile device
        device = MobileDevice(
            user_id=token_record.user_id,
            device_name=device_info.device_name,
            device_type=device_info.device_type,
            device_model=device_info.device_model,
            os_version=device_info.os_version,
            app_version=device_info.app_version,
            push_token=device_data.push_token,
            is_active=True,
            expires_at=device_expires_at
        )
        db.add(device)
        db.flush()  # Generate device.id before creating camera_backup
        
        # Create default camera backup settings
        camera_backup = CameraBackup(
            device_id=device.id,
            enabled=True,
            quality="original",
            wifi_only=True,
            delete_after_upload=False,
            video_backup=True
        )
        db.add(camera_backup)
        
        db.commit()
        db.refresh(device)
        
        # Get user info
        user = db.query(User).filter(User.id == token_record.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Generate auth tokens
        access_token = auth_service.create_access_token(user=user)
        refresh_token = auth_service.create_access_token(user=user, expires_minutes=60*24*30)  # 30 days
        
        # Format timestamps with timezone for Android parsing (ISO 8601 with Z suffix)
        created_at_iso = user.created_at.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z' if user.created_at else datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        last_seen_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": int(user.id),
                "username": user.username,
                "email": user.email or "",
                "role": user.role,
                "created_at": created_at_iso,
                "is_active": True
            },
            "device": {
                "id": str(device.id),  # UUID as string
                "user_id": int(device.user_id),  # Integer matching database schema
                "device_name": device.device_name,
                "device_type": device.device_type,
                "device_model": device.device_model or "",
                "last_seen": last_seen_iso,
                "is_active": device.is_active
            }
        }
    
    @staticmethod
    def get_user_devices(db: Session, user_id: int) -> List[MobileDevice]:
        """Get all mobile devices for a user."""
        return db.query(MobileDevice).filter(
            MobileDevice.user_id == user_id
        ).all()
    
    @staticmethod
    def get_all_devices_with_users(db: Session) -> List[dict]:
        """Get all mobile devices with username (Admin only)."""
        from sqlalchemy import select
        from app.models.user import User
        
        devices = db.query(MobileDevice).join(
            User, MobileDevice.user_id == User.id
        ).all()
        
        # Konvertiere zu dict und füge username hinzu
        result = []
        for device in devices:
            user = db.query(User).filter(User.id == device.user_id).first()
            device_dict = {
                "id": device.id,
                "user_id": device.user_id,
                "username": user.username if user else "Unknown",
                "device_name": device.device_name,
                "device_type": device.device_type,
                "device_model": device.device_model,
                "os_version": device.os_version,
                "app_version": device.app_version,
                "is_active": device.is_active,
                "last_sync": device.last_sync.isoformat() if device.last_sync else None,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                "expires_at": device.expires_at.isoformat() if device.expires_at else None,
                "created_at": device.created_at.isoformat(),
                "updated_at": device.updated_at.isoformat() if device.updated_at else None
            }
            result.append(device_dict)
        
        return result
    
    @staticmethod
    def get_device(db: Session, device_id: str, user_id: int) -> Optional[MobileDevice]:
        """Get a specific mobile device."""
        device = db.query(MobileDevice).filter(
            MobileDevice.id == device_id,
            MobileDevice.user_id == user_id
        ).first()
        return device
    
    @staticmethod
    def update_device(
        db: Session,
        device_id: str,
        user_id: int,
        device_update: MobileDeviceUpdate
    ) -> MobileDevice:
        """Update mobile device settings."""
        device = MobileService.get_device(db, device_id, user_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )
        
        update_data = device_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(device, field, value)
        
        db.commit()
        db.refresh(device)
        return device
    
    @staticmethod
    def delete_device(db: Session, device_id: str, user_id: int) -> bool:
        """Delete a mobile device."""
        logger.debug(f"Attempting to delete device_id={device_id} for user_id={user_id}")
        device = MobileService.get_device(db, device_id, user_id)
        if not device:
            logger.warning(f"Device not found: device_id={device_id}, user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )

        logger.info(f"Deleting device: {device.device_name} (id={device_id})")
        db.delete(device)
        db.commit()
        logger.info(f"Device deleted successfully: {device.device_name}")
        return True
    
    @staticmethod
    def get_camera_backup_settings(db: Session, device_id: str) -> Optional[CameraBackup]:
        """Get camera backup settings for a device."""
        return db.query(CameraBackup).filter(
            CameraBackup.device_id == device_id
        ).first()
    
    @staticmethod
    def update_camera_backup_settings(
        db: Session,
        device_id: str,
        settings: CameraBackupSettings
    ) -> CameraBackup:
        """Update camera backup settings."""
        backup = MobileService.get_camera_backup_settings(db, device_id)
        if not backup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera backup settings not found"
            )
        
        for field, value in settings.dict().items():
            setattr(backup, field, value)
        
        db.commit()
        db.refresh(backup)
        return backup
    
    @staticmethod
    def get_sync_folders(db: Session, device_id: str) -> List[SyncFolder]:
        """Get all sync folders for a device."""
        return db.query(SyncFolder).filter(
            SyncFolder.device_id == device_id
        ).all()
    
    @staticmethod
    def create_sync_folder(
        db: Session,
        device_id: str,
        folder_data: SyncFolderCreate
    ) -> SyncFolder:
        """Create a new sync folder configuration."""
        sync_folder = SyncFolder(
            device_id=device_id,
            local_path=folder_data.local_path,
            remote_path=folder_data.remote_path,
            sync_type=folder_data.sync_type,
            auto_sync=folder_data.auto_sync
        )
        db.add(sync_folder)
        db.commit()
        db.refresh(sync_folder)
        return sync_folder
