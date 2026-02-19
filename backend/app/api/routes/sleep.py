"""
Sleep mode API endpoints.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from app.api.deps import get_current_user, get_current_admin
from app.core.rate_limiter import user_limiter, get_limit
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
    body: EnterSoftSleepRequest = EnterSoftSleepRequest(),
    current_user: User = Depends(get_current_admin),
) -> dict:
    """Enter soft sleep mode (admin only)."""
    manager = _get_manager()
    reason = body.reason or f"manual by {current_user.username}"
    ok = await manager.enter_soft_sleep(reason, SleepTrigger.MANUAL)
    if not ok:
        raise HTTPException(status_code=409, detail="Cannot enter soft sleep from current state")
    logger.info("Soft sleep activated by %s", current_user.username)
    return {"success": True, "message": "Entered soft sleep mode"}


@router.post("/wake")
@user_limiter.limit(get_limit("admin_operations"))
async def wake_from_sleep(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
) -> dict:
    """Exit soft sleep mode (admin only)."""
    manager = _get_manager()
    ok = await manager.exit_soft_sleep(f"manual wake by {current_user.username}")
    if not ok:
        raise HTTPException(status_code=409, detail="Cannot wake from current state")
    logger.info("Manual wake triggered by %s", current_user.username)
    return {"success": True, "message": "Exited soft sleep mode"}


@router.post("/suspend")
@user_limiter.limit(get_limit("admin_operations"))
async def enter_suspend(
    request: Request, response: Response,
    body: EnterSuspendRequest = EnterSuspendRequest(),
    current_user: User = Depends(get_current_admin),
) -> dict:
    """Enter true system suspend (admin only)."""
    manager = _get_manager()
    reason = body.reason or f"manual suspend by {current_user.username}"
    ok = await manager.enter_true_suspend(
        reason, SleepTrigger.MANUAL, wake_at=body.wake_at,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="Cannot suspend from current state")
    logger.info("System suspend triggered by %s", current_user.username)
    return {"success": True, "message": "System suspended"}


@router.post("/wol")
@user_limiter.limit(get_limit("admin_operations"))
async def send_wol(
    request: Request, response: Response,
    body: WolRequest = WolRequest(),
    current_user: User = Depends(get_current_admin),
) -> dict:
    """Send a Wake-on-LAN magic packet (admin only)."""
    manager = _get_manager()
    ok = await manager.send_wol(body.mac_address, body.broadcast_address)
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to send WoL packet (no MAC address configured?)")
    logger.info("WoL packet sent by %s", current_user.username)
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
