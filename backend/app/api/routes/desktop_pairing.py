"""API routes for the Desktop Device Code Flow (BaluDesk pairing)."""

import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.models.user import User
from app.schemas.desktop_pairing import (
    ApproveDeviceCodeRequest,
    DeviceCodeApprovalInfo,
    DeviceCodePollRequest,
    DeviceCodePollResponse,
    DeviceCodeRequest,
    DeviceCodeResponse,
)
from app.services.desktop_pairing import DesktopPairingService
from app.services.audit import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/desktop-pairing", tags=["desktop-pairing"])


@router.post("/device-code", response_model=DeviceCodeResponse)
@limiter.limit(get_limit("desktop_pairing_request"))
async def request_device_code(
    request: Request,
    response: Response,
    payload: DeviceCodeRequest,
    db: Session = Depends(get_db),
):
    """BaluDesk requests a new pairing code (unauthenticated)."""
    server_url = str(request.base_url).rstrip("/")
    result = DesktopPairingService.request_device_code(db, payload, server_url)

    audit = get_audit_logger_db()
    audit.log_event(
        event_type="DESKTOP_PAIRING",
        user=None,
        action="device_code_requested",
        resource=payload.device_name,
        details={"device_id": payload.device_id, "platform": payload.platform},
        success=True,
        db=db,
    )

    return result


@router.post("/poll", response_model=DeviceCodePollResponse)
@limiter.limit(get_limit("desktop_pairing_poll"))
async def poll_device_code(
    request: Request,
    response: Response,
    payload: DeviceCodePollRequest,
    db: Session = Depends(get_db),
):
    """BaluDesk polls for approval status (unauthenticated)."""
    return DesktopPairingService.poll_device_code(db, payload.device_code)


@router.post("/verify", response_model=DeviceCodeApprovalInfo)
@user_limiter.limit(get_limit("desktop_pairing_verify"))
async def verify_device_code(
    request: Request,
    response: Response,
    payload: ApproveDeviceCodeRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Web-UI verifies a user_code and returns device info for confirmation."""
    return DesktopPairingService.verify_code(db, payload.user_code)


@router.post("/approve")
@user_limiter.limit(get_limit("desktop_pairing_approve"))
async def approve_device_code(
    request: Request,
    response: Response,
    payload: ApproveDeviceCodeRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Web-UI approves a pairing request."""
    DesktopPairingService.approve_code(db, payload.user_code, current_user.id)

    audit = get_audit_logger_db()
    audit.log_event(
        event_type="DESKTOP_PAIRING",
        user=current_user.username,
        action="device_code_approved",
        resource=payload.user_code,
        details={"user_id": current_user.id},
        success=True,
        db=db,
    )

    return {"status": "approved"}


@router.post("/deny")
@user_limiter.limit(get_limit("desktop_pairing_approve"))
async def deny_device_code(
    request: Request,
    response: Response,
    payload: ApproveDeviceCodeRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Web-UI denies a pairing request."""
    DesktopPairingService.deny_code(db, payload.user_code)

    audit = get_audit_logger_db()
    audit.log_event(
        event_type="DESKTOP_PAIRING",
        user=current_user.username,
        action="device_code_denied",
        resource=payload.user_code,
        details={"user_id": current_user.id},
        success=True,
        db=db,
    )

    return {"status": "denied"}
