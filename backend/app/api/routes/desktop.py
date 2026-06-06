"""Desktop (display-manager) control endpoints.

Registered under the /system/sleep/desktop prefix in routes/__init__.py.
"""
import logging

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_current_user, require_power_toggle_desktop
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.desktop import DesktopStatus
from app.services.power.desktop import get_desktop_service
from app.services.notifications.events import emit_desktop_disabled, emit_desktop_enabled
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=DesktopStatus)
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_status(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
) -> DesktopStatus:
    """Return whether the desktop displays are on (running) or off (stopped)."""
    return await get_desktop_service().get_status()


@router.post("/disable")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_disable(
    request: Request,
    response: Response,
    current_user=Depends(require_power_toggle_desktop),
) -> dict:
    """Turn the desktop displays off (DPMS) so the GPU can drop to idle.

    Keeps the KWin session running; stopping sddm would instead light all
    outputs via the framebuffer console and pin the dGPU at ~78W. Admin or a
    delegated user with the can_toggle_desktop permission.
    """
    ok, message = await get_desktop_service().disable()
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action="desktop_disable",
        user=current_user.username,
        resource="desktop",
        success=ok,
        details={"message": message},
    )
    if current_user.role != "admin":
        # Mirror the sleep routes: record that a delegated (non-admin) user
        # invoked a privileged power action, for the security-audit trail.
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="toggle_desktop",
            details={"action": "desktop_disable"},
            success=True,
        )
    if ok:
        try:
            await emit_desktop_disabled(current_user.username)
        except Exception as exc:  # best-effort: never break the toggle
            logger.warning("Desktop-disabled notification failed: %s", exc)
    return {"success": ok, "message": message}


@router.post("/enable")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_enable(
    request: Request,
    response: Response,
    current_user=Depends(require_power_toggle_desktop),
) -> dict:
    """Turn the desktop displays back on (DPMS).

    Admin or a delegated user with the can_toggle_desktop permission.
    """
    ok, message = await get_desktop_service().enable()
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action="desktop_enable",
        user=current_user.username,
        resource="desktop",
        success=ok,
        details={"message": message},
    )
    if current_user.role != "admin":
        # Mirror the sleep routes: record that a delegated (non-admin) user
        # invoked a privileged power action, for the security-audit trail.
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="toggle_desktop",
            details={"action": "desktop_enable"},
            success=True,
        )
    if ok:
        try:
            await emit_desktop_enabled(current_user.username)
        except Exception as exc:  # best-effort: never break the toggle
            logger.warning("Desktop-enabled notification failed: %s", exc)
    return {"success": ok, "message": message}
