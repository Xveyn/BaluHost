"""Desktop (display-manager) control endpoints.

Registered under the /system/sleep/desktop prefix in routes/__init__.py.
"""
import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_power_toggle_desktop
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.desktop import DesktopStatus
from app.services.power.desktop import get_desktop_service
from app.services.power.session_lock import current_lock_state, lock_if_permitted, unlock_if_permitted
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
    """Return whether the desktop displays are on (running) or off (stopped).

    Also carries the session's lock state, so the power menu can decide in a
    single request whether to offer "unlock".
    """
    status = await get_desktop_service().get_status()
    return status.model_copy(update={"session_locked": await current_lock_state()})


@router.post("/unlock")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_unlock(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Unlock the graphical desktop session, leaving the displays alone.

    The "enable" route unlocks as a side effect of turning the displays on;
    this is the same action for the case where they are already on.

    Authorization is deliberately NOT a route dependency: ``unlock_if_permitted``
    is the single place where both gates (LAN/VPN + the ``can_unlock_session``
    right, admins by role) are evaluated and audited. A role gate in front of it
    would be a second, silently diverging rule. A refusal is therefore a 200
    with ``success: false``, not a 403.
    """
    try:
        ok, message = await unlock_if_permitted(
            user=current_user,
            client_host=request.client.host if request.client else None,
            db=db,
        )
    except Exception:  # a failed unlock is an outcome, never a 5xx
        logger.exception("Session unlock failed unexpectedly")
        ok, message = False, "unlock failed unexpectedly"
    return {"success": ok, "message": message}


@router.post("/lock")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_lock(
    request: Request,
    response: Response,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Lock the graphical desktop session, leaving the displays alone.

    The mirror of ``/unlock``, worth having separately from "disable desktop":
    turning the displays off (DPMS) does NOT lock the session, so someone
    standing at the dark screen can still move the mouse and see the desktop.
    This closes that gap - e.g. locking remotely after leaving without
    locking, or reacting to a compromised account.

    Authorization is deliberately NOT a route dependency, for the same reason
    as ``/unlock``: ``lock_if_permitted`` is the single place the permission
    gate is evaluated and audited. Unlike ``/unlock`` it carries no network
    gate - locking only closes the desktop, so a stolen web account gains
    nothing from being able to lock it from anywhere. A refusal is therefore
    a 200 with ``success: false``, not a 403.
    """
    try:
        ok, message = await lock_if_permitted(
            user=current_user,
            client_host=request.client.host if request.client else None,
            db=db,
        )
    except Exception:  # a failed lock is an outcome, never a 5xx
        logger.exception("Session lock failed unexpectedly")
        ok, message = False, "lock failed unexpectedly"
    return {"success": ok, "message": message}


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
    db: Session = Depends(get_db),
) -> dict:
    """Turn the desktop displays back on (DPMS) and unlock the session.

    Admin or a delegated user with the can_toggle_desktop permission. The
    unlock is an ADD-ON: it needs its own permission plus a request from
    LAN/VPN, and failing it never fails the call - the displays are on either
    way.
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
    try:
        session_unlocked, unlock_message = await unlock_if_permitted(
            user=current_user,
            client_host=request.client.host if request.client else None,
            db=db,
        )
    except Exception:  # belt and braces: the displays are already on
        logger.exception("Session unlock failed unexpectedly")
        session_unlocked, unlock_message = False, "unlock failed unexpectedly"
    return {
        "success": ok,
        "message": message,
        "session_unlocked": session_unlocked,
        "unlock_message": unlock_message,
    }
