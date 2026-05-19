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
    CoreUptimeWindowCreate,
    CoreUptimeWindowUpdate,
    CoreUptimeWindowResponse,
)
from app.models.sleep import CoreUptimeWindow as CoreUptimeWindowModel
from app.services.power.sleep import get_sleep_manager
from app.services.power import os_sleep_inspector
from app.services.power import os_auto_suspend
from app.schemas.sleep import OsSleepReportResponse, OsAutoSuspendResponse, OsAutoSuspendUpdate

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
    db: Session = Depends(get_db),
) -> SleepConfigResponse:
    """Update sleep mode configuration (admin only)."""
    manager = _get_manager()
    try:
        result = manager.update_config(body)
        logger.info("Sleep config updated by %s", current_user.username)
        # Audit log if always-awake fields were touched
        touched = body.model_dump(exclude_unset=True)
        if "always_awake_enabled" in touched or "always_awake_until" in touched:
            get_audit_logger_db().log_security_event(
                action="always_awake_toggled",
                user=current_user.username,
                resource="sleep_config",
                details={
                    "enabled": result.always_awake_enabled,
                    "until": result.always_awake_until.isoformat() if result.always_awake_until else None,
                },
                success=True,
                db=db,
            )
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


@router.get("/os-settings", response_model=OsSleepReportResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_os_sleep_settings(
    request: Request, response: Response,
    force: bool = False,
    current_user: User = Depends(get_current_admin),
) -> OsSleepReportResponse:
    """Read-only snapshot of OS-level sleep configuration (admin only)."""
    report = os_sleep_inspector.inspect_os_sleep(force_refresh=force)
    return OsSleepReportResponse(
        platform_supported=report.platform_supported,
        logind=report.logind,
        sleep_conf=report.sleep_conf,
        targets=report.targets,
        issues=[
            {"severity": i.severity, "key": i.key, "message": i.message, "detail": i.detail}
            for i in report.issues
        ],
        sources=report.sources,
        collected_at=report.collected_at,
    )


@router.get("/os-auto-suspend", response_model=OsAutoSuspendResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_os_auto_suspend_route(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
) -> OsAutoSuspendResponse:
    """Read OS-level auto-suspend setting from the active power manager (admin)."""
    return os_auto_suspend.get_os_auto_suspend()


@router.put("/os-auto-suspend", response_model=OsAutoSuspendResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_os_auto_suspend_route(
    request: Request, response: Response,
    body: OsAutoSuspendUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> OsAutoSuspendResponse:
    """Write OS-level auto-suspend setting to the active power manager (admin)."""
    try:
        previous = os_auto_suspend.get_os_auto_suspend()
        result = os_auto_suspend.set_os_auto_suspend(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    get_audit_logger_db().log_security_event(
        action="os_auto_suspend_update",
        user=current_user.username,
        resource=result.source,
        details={
            "previous": {
                "enabled": previous.enabled,
                "timeout_minutes": previous.timeout_minutes,
                "action": previous.action.value,
            },
            "new": {
                "enabled": result.enabled,
                "timeout_minutes": result.timeout_minutes,
                "action": result.action.value,
            },
        },
        success=True,
        db=db,
    )
    logger.info("OS auto-suspend updated by %s (source=%s)", current_user.username, result.source)
    return result


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


# ---------------------------------------------------------------------------
# Core Operating Hours — Window CRUD
# ---------------------------------------------------------------------------

def _csv_to_list(csv: str) -> list[int]:
    return sorted({int(x) for x in csv.split(",") if x.strip()})


def _list_to_csv(items: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(items)))


def _to_response(row: CoreUptimeWindowModel) -> CoreUptimeWindowResponse:
    return CoreUptimeWindowResponse(
        id=row.id,
        enabled=row.enabled,
        label=row.label,
        start_time=row.start_time,
        end_time=row.end_time,
        weekdays=_csv_to_list(row.weekdays),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/core-uptime/windows",
    response_model=list[CoreUptimeWindowResponse],
)
@user_limiter.limit(get_limit("admin_operations"))
async def list_core_uptime_windows(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[CoreUptimeWindowResponse]:
    """List all core-uptime windows (admin only)."""
    rows = db.query(CoreUptimeWindowModel).order_by(CoreUptimeWindowModel.id.asc()).all()
    return [_to_response(r) for r in rows]


@router.post(
    "/core-uptime/windows",
    response_model=CoreUptimeWindowResponse,
    status_code=201,
)
@user_limiter.limit(get_limit("admin_operations"))
async def create_core_uptime_window(
    request: Request, response: Response,
    body: CoreUptimeWindowCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> CoreUptimeWindowResponse:
    """Create a new core-uptime window (admin only)."""
    row = CoreUptimeWindowModel(
        enabled=body.enabled,
        label=body.label,
        start_time=body.start_time,
        end_time=body.end_time,
        weekdays=_list_to_csv(body.weekdays),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    get_audit_logger_db().log_security_event(
        action="core_uptime_window_create",
        user=current_user.username,
        resource=str(row.id),
        details={"start": row.start_time, "end": row.end_time, "weekdays": row.weekdays},
        success=True,
        db=db,
    )
    return _to_response(row)


@router.put(
    "/core-uptime/windows/{window_id}",
    response_model=CoreUptimeWindowResponse,
)
@user_limiter.limit(get_limit("admin_operations"))
async def update_core_uptime_window(
    request: Request, response: Response,
    window_id: int,
    body: CoreUptimeWindowUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> CoreUptimeWindowResponse:
    """Partially update a core-uptime window (admin only)."""
    row = db.get(CoreUptimeWindowModel, window_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Window not found")

    update_data = body.model_dump(exclude_unset=True)
    if "weekdays" in update_data and update_data["weekdays"] is not None:
        update_data["weekdays"] = _list_to_csv(update_data["weekdays"])
    for field, value in update_data.items():
        setattr(row, field, value)

    # Validate end != start after partial update
    if row.start_time == row.end_time:
        raise HTTPException(status_code=422, detail="start_time and end_time must differ")

    db.commit()
    db.refresh(row)

    get_audit_logger_db().log_security_event(
        action="core_uptime_window_update",
        user=current_user.username,
        resource=str(row.id),
        details=update_data,
        success=True,
        db=db,
    )
    return _to_response(row)


@router.delete(
    "/core-uptime/windows/{window_id}",
    status_code=204,
)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_core_uptime_window(
    request: Request, response: Response,
    window_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a core-uptime window (admin only)."""
    row = db.get(CoreUptimeWindowModel, window_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Window not found")

    db.delete(row)
    db.commit()

    get_audit_logger_db().log_security_event(
        action="core_uptime_window_delete",
        user=current_user.username,
        resource=str(window_id),
        details={},
        success=True,
        db=db,
    )
    return Response(status_code=204)
