"""
Sleep mode API endpoints.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from app.api.deps import (
    get_current_user,
    get_current_admin,
    require_power_soft_sleep,
    require_power_wake,
    require_power_suspend,
    require_power_wol,
)
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.power_permissions import MyPowerPermissionsResponse
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.services.audit.logger_db import get_audit_logger_db
from app.models.user import User
from app.schemas.sleep import (
    SleepStatusResponse,
    SleepConfigResponse,
    SleepConfigUpdate,
    SleepCapabilities,
    SleepHistoryResponse,
    EnterSoftSleepRequest,
    EnterSuspendRequest,
    WolRequest,
    SleepTrigger,
)
from app.services.power.sleep import get_sleep_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_manager():
    """Get the sleep manager service or raise 503."""
    manager = get_sleep_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="Sleep mode service not running")
    return manager


@router.get("/status", response_model=SleepStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_sleep_status(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
) -> SleepStatusResponse:
    """Get current sleep mode status and activity metrics."""
    manager = _get_manager()
    return manager.get_status()


@router.post("/soft")
@user_limiter.limit(get_limit("admin_operations"))
async def enter_soft_sleep(
    request: Request, response: Response,
    body: Optional[EnterSoftSleepRequest] = None,
    current_user: User = Depends(require_power_soft_sleep),
    db: Session = Depends(get_db),
) -> dict:
    """Enter soft sleep mode (admin or delegated users)."""
    manager = _get_manager()
    reason = (body.reason if body else None) or f"manual by {current_user.username}"
    ok = await manager.enter_soft_sleep(reason, SleepTrigger.MANUAL)
    if not ok:
        raise HTTPException(status_code=409, detail="Cannot enter soft sleep from current state")
    logger.info("Soft sleep activated by %s", current_user.username)
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="soft_sleep",
            details={"action": "soft_sleep"},
            success=True,
            db=db,
        )
    return {"success": True, "message": "Entered soft sleep mode"}


@router.post("/wake")
@user_limiter.limit(get_limit("admin_operations"))
async def wake_from_sleep(
    request: Request, response: Response,
    current_user: User = Depends(require_power_wake),
    db: Session = Depends(get_db),
) -> dict:
    """Exit soft sleep mode (admin or delegated users)."""
    manager = _get_manager()
    ok = await manager.exit_soft_sleep(f"manual wake by {current_user.username}")
    if not ok:
        raise HTTPException(status_code=409, detail="Cannot wake from current state")
    logger.info("Manual wake triggered by %s", current_user.username)
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="wake",
            details={"action": "wake"},
            success=True,
            db=db,
        )
    return {"success": True, "message": "Exited soft sleep mode"}


@router.post("/suspend")
@user_limiter.limit(get_limit("admin_operations"))
async def enter_suspend(
    request: Request, response: Response,
    body: Optional[EnterSuspendRequest] = None,
    current_user: User = Depends(require_power_suspend),
    db: Session = Depends(get_db),
) -> dict:
    """Enter true system suspend (admin or delegated users)."""
    manager = _get_manager()
    reason = (body.reason if body else None) or f"manual suspend by {current_user.username}"
    ok = await manager.enter_true_suspend(
        reason, SleepTrigger.MANUAL, wake_at=body.wake_at if body else None,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="Cannot suspend from current state")
    logger.info("System suspend triggered by %s", current_user.username)
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="suspend",
            details={"action": "suspend"},
            success=True,
            db=db,
        )
    return {"success": True, "message": "System suspended"}


@router.post("/wol")
@user_limiter.limit(get_limit("admin_operations"))
async def send_wol(
    request: Request, response: Response,
    body: Optional[WolRequest] = None,
    current_user: User = Depends(require_power_wol),
    db: Session = Depends(get_db),
) -> dict:
    """Send a Wake-on-LAN magic packet (admin or delegated users)."""
    manager = _get_manager()
    ok = await manager.send_wol(
        body.mac_address if body else None,
        body.broadcast_address if body else None,
        method=body.method if body else "local",
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to send WoL packet (no MAC address configured?)")
    logger.info("WoL packet sent by %s", current_user.username)
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="wol",
            details={"action": "wol"},
            success=True,
            db=db,
        )
    return {"success": True, "message": "WoL packet sent"}


@router.get("/config", response_model=SleepConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_sleep_config(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
) -> SleepConfigResponse:
    """Get sleep mode configuration (admin only)."""
    manager = _get_manager()
    return manager.get_config()


@router.put("/config", response_model=SleepConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_sleep_config(
    request: Request, response: Response,
    body: SleepConfigUpdate,
    current_user: User = Depends(get_current_admin),
) -> SleepConfigResponse:
    """Update sleep mode configuration (admin only)."""
    manager = _get_manager()
    try:
        result = manager.update_config(body)
        logger.info("Sleep config updated by %s", current_user.username)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {e}")


@router.get("/history", response_model=SleepHistoryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_sleep_history(
    request: Request, response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_admin),
) -> SleepHistoryResponse:
    """Get sleep state change history (admin only)."""
    manager = _get_manager()
    return manager.get_history(limit=limit, offset=offset)


@router.get("/capabilities", response_model=SleepCapabilities)
@user_limiter.limit(get_limit("admin_operations"))
async def get_sleep_capabilities(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
) -> SleepCapabilities:
    """Check system capabilities for sleep features (admin only)."""
    manager = _get_manager()
    return await manager.get_capabilities()


@router.get("/my-permissions", response_model=MyPowerPermissionsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_my_power_permissions(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyPowerPermissionsResponse:
    """Get the current user's power permissions (for mobile app)."""
    if current_user.role == "admin":
        return MyPowerPermissionsResponse(
            can_soft_sleep=True, can_wake=True, can_suspend=True, can_wol=True,
        )
    from app.services.power_permissions import get_permissions
    perms = get_permissions(db, current_user.id)
    return MyPowerPermissionsResponse(
        can_soft_sleep=perms.can_soft_sleep,
        can_wake=perms.can_wake,
        can_suspend=perms.can_suspend,
        can_wol=perms.can_wol,
    )
