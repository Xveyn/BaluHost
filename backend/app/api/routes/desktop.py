"""Desktop (display-manager) control endpoints.

Registered under the /system/sleep/desktop prefix in routes/__init__.py.
"""
import logging

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import get_current_user, get_current_admin
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.desktop import DesktopStatus
from app.services.power.desktop import get_desktop_service
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
    """Return whether the KDE desktop (display manager) is running."""
    return await get_desktop_service().get_status()


@router.post("/disable")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_disable(
    request: Request,
    response: Response,
    current_user=Depends(get_current_admin),
) -> dict:
    """Stop the KDE desktop so the GPU can drop to idle. Admin only."""
    ok, message = await get_desktop_service().disable()
    get_audit_logger_db().log_event(
        event_type="POWER",
        action="desktop_disable",
        user=current_user.username,
        resource="desktop",
        success=ok,
        details={"message": message},
    )
    return {"success": ok, "message": message}


@router.post("/enable")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_enable(
    request: Request,
    response: Response,
    current_user=Depends(get_current_admin),
) -> dict:
    """Start the KDE desktop. Admin only."""
    ok, message = await get_desktop_service().enable()
    get_audit_logger_db().log_event(
        event_type="POWER",
        action="desktop_enable",
        user=current_user.username,
        resource="desktop",
        success=ok,
        details={"message": message},
    )
    return {"success": ok, "message": message}
