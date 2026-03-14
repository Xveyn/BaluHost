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
from app.services.audit.logger_db import get_audit_logger_db
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


def _dry_run_validate(messaging, title: str, body: str, device_names: str | None) -> FirebaseTestResponse:
    """Validate Firebase config with a dry-run send (no real push delivered)."""
    try:
        dry_msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic="dry_run_validation",
        )
        messaging.send(dry_msg, dry_run=True)
    except Exception as e:
        logger.warning("Firebase dry-run validation failed: %s", e)
        return FirebaseTestResponse(
            success=False,
            message=f"Firebase configuration error: {e}",
            sent_to=0,
        )

    if device_names:
        msg = (
            f"Firebase configuration verified (dry-run). "
            f"Devices [{device_names}] have no push token — "
            f"open BaluApp once so it registers its FCM token."
        )
    else:
        msg = (
            "Firebase configuration verified (dry-run). "
            "No devices registered — pair a device in BaluApp first."
        )
    return FirebaseTestResponse(success=True, message=msg, sent_to=0)


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
    from app.services.notifications.firebase_devices import (
        get_active_device_by_id,
        get_active_devices_for_user,
    )

    if not FirebaseService.is_available():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase is not initialized. Upload credentials first.",
        )

    title = payload.title or "BaluHost Test"
    body = payload.body or "Push notifications are working!"

    from firebase_admin import messaging

    # Direct FCM token provided — send directly without device lookup
    if payload.token:
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
                token=payload.token,
            )
            message_id = messaging.send(message)
            logger.info("Test notification sent to manual token: %s", message_id)
            return FirebaseTestResponse(
                success=True,
                message="Sent to manual FCM token",
                sent_to=1,
                message_id=message_id,
            )
        except Exception as e:
            logger.warning("Test notification to manual token failed: %s", e)
            return FirebaseTestResponse(
                success=False,
                message=f"Failed: {e}",
                sent_to=0,
            )

    # Find target devices
    if payload.device_id:
        device = get_active_device_by_id(db, payload.device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Device not found",
            )
        if not device.push_token:
            # Device exists but has no push token — dry-run validate instead
            return _dry_run_validate(messaging, title, body, device.device_name)
        devices = [device]
    else:
        # Send to all active devices of the current admin
        all_devices = get_active_devices_for_user(db, current_user.id)
        devices = [d for d in all_devices if d.push_token]

        if not devices and all_devices:
            # Devices registered but none have push tokens
            names = ", ".join(d.device_name for d in all_devices)
            return _dry_run_validate(messaging, title, body, names)

        if not devices:
            # No devices at all
            return _dry_run_validate(messaging, title, body, None)

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
