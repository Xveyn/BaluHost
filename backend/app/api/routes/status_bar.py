"""API routes for the topbar status strip.

GET/PUT /config are admin-only; GET /state is any authenticated user
(filtered server-side by role).

Mounted as a sub-router of ``system.router`` (prefix ``/system``) under
``/statusbar``, so the effective paths are ``/api/system/statusbar/...``.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.status_bar import (
    StatusBarConfigResponse,
    StatusBarConfigUpdate,
    StatusBarStateResponse,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db
from app.services.status_bar.service import StatusBarService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/statusbar/config", response_model=StatusBarConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_statusbar_config(
    request: Request,
    response: Response,
    db: Session = Depends(deps.get_db),
    current_user: UserPublic = Depends(deps.get_current_admin),
) -> StatusBarConfigResponse:
    """Full catalog + persisted config (admin only)."""
    return StatusBarService(db).get_config()


@router.put("/statusbar/config", response_model=StatusBarConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_statusbar_config(
    request: Request,
    response: Response,
    payload: StatusBarConfigUpdate,
    db: Session = Depends(deps.get_db),
    current_user: UserPublic = Depends(deps.get_current_admin),
) -> StatusBarConfigResponse:
    """Bulk-update pill config + bottom-upload toggle (admin only)."""
    service = StatusBarService(db)
    try:
        diff = service.update_config(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # Audit the config change. Best-effort: a logging failure must never break
    # the request. log_event() already swallows DB errors internally, but guard
    # the call site too so an unexpected error here is logged, not propagated.
    try:
        get_audit_logger_db().log_event(
            event_type="SYSTEM_CONFIG",
            user=current_user.username,
            action="status_bar.config_changed",
            resource="status_bar_config",
            details=diff,
            success=True,
            db=db,
        )
    except Exception:  # pragma: no cover - defensive, audit must not break request
        logger.exception("Failed to write status bar config-change audit log")

    return service.get_config()


@router.get("/statusbar/state", response_model=StatusBarStateResponse)
@user_limiter.limit(get_limit("status_polling"))
async def get_statusbar_state(
    request: Request,
    response: Response,
    db: Session = Depends(deps.get_db),
    current_user: UserPublic = Depends(deps.get_current_user),
) -> StatusBarStateResponse:
    """Aggregated pill payload, filtered by the caller's role."""
    return await StatusBarService(db).collect_state(role=current_user.role)
