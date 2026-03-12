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
