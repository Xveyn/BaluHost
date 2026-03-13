"""API routes for Firebase configuration management (admin only)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_admin
from app.schemas.user import UserPublic
from app.schemas.firebase_config import (
    FirebaseStatusResponse,
    FirebaseUploadRequest,
    FirebaseUploadResponse,
    FirebaseDeleteResponse,
    FirebaseTestRequest,
    FirebaseTestResponse,
)
from app.services.notifications.firebase import FirebaseService
from app.services.audit_logger_db import get_audit_logger_db
from app.core.rate_limiter import user_limiter, get_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/firebase", tags=["admin", "firebase"])


@router.get("/status", response_model=FirebaseStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_firebase_status(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
):
    """Get Firebase configuration status (admin only)."""
    return FirebaseService.get_status()


@router.post("/upload", response_model=FirebaseUploadResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def upload_firebase_credentials(
    request: Request,
    response: Response,
    payload: FirebaseUploadRequest,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Upload Firebase credentials JSON (admin only)."""
    audit_logger = get_audit_logger_db()

    try:
        result = FirebaseService.save_credentials(payload.credentials_json)
    except Exception as e:
        logger.error("Failed to save Firebase credentials: %s", e)
        audit_logger.log_security_event(
            action="firebase_credentials_upload",
            user=current_user.username,
            details={"error": str(e)},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save credentials",
        )

    audit_logger.log_security_event(
        action="firebase_credentials_upload",
        user=current_user.username,
        details={"project_id": result.get("project_id")},
        success=True,
        db=db,
    )

    return FirebaseUploadResponse(
        success=result["success"],
        project_id=result.get("project_id"),
        message=result["message"],
    )


@router.delete("/credentials", response_model=FirebaseDeleteResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_firebase_credentials(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete Firebase credentials (admin only)."""
    audit_logger = get_audit_logger_db()

    deleted = FirebaseService.delete_credentials()

    audit_logger.log_security_event(
        action="firebase_credentials_delete",
        user=current_user.username,
        details={"file_existed": deleted},
        success=True,
        db=db,
    )

    if deleted:
        return FirebaseDeleteResponse(success=True, message="Credentials deleted")
    return FirebaseDeleteResponse(success=True, message="No credentials file to delete")


@router.post("/test", response_model=FirebaseTestResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def send_test_notification(
    request: Request,
    response: Response,
    payload: FirebaseTestRequest,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Send a test push notification to verify Firebase is working (admin only)."""
    from app.models.mobile import MobileDevice

    if not FirebaseService.is_available():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase is not initialized. Upload credentials first.",
        )

    # Find target devices
    if payload.device_id:
        device = db.query(MobileDevice).filter(
            MobileDevice.id == payload.device_id,
            MobileDevice.is_active == True,
            MobileDevice.push_token.isnot(None),
        ).first()
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found or has no push token",
            )
        devices = [device]
    else:
        # Send to all active devices of the current admin
        devices = db.query(MobileDevice).filter(
            MobileDevice.user_id == current_user.id,
            MobileDevice.is_active == True,
            MobileDevice.push_token.isnot(None),
        ).all()

    if not devices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No devices with push tokens found. Register a device in the BaluApp first.",
        )

    title = payload.title or "BaluHost Test"
    body = payload.body or "Push notifications are working!"

    from firebase_admin import messaging

    sent = 0
    last_message_id = None
    errors = []

    for device in devices:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={
                    "type": "notification",
                    "category": "system",
                    "priority": "1",
                    "action_url": "",
                },
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        icon="ic_notification",
                        color="#38bdf8",
                        sound="default",
                        channel_id="alerts_info",
                    ),
                ),
                token=device.push_token,
            )
            last_message_id = messaging.send(message)
            sent += 1
            logger.info("Test notification sent to %s: %s", device.device_name, last_message_id)
        except Exception as e:
            errors.append(f"{device.device_name}: {e}")
            logger.warning("Test notification failed for %s: %s", device.device_name, e)

    if sent == 0:
        return FirebaseTestResponse(
            success=False,
            message=f"Failed to send: {'; '.join(errors)}",
            sent_to=0,
        )

    msg = f"Sent to {sent} device(s)"
    if errors:
        msg += f", {len(errors)} failed"

    return FirebaseTestResponse(
        success=True,
        message=msg,
        sent_to=sent,
        message_id=last_message_id,
    )
