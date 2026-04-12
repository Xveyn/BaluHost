"""Dev-only impersonation endpoint.

Allows an admin to obtain a full JWT for any user without re-authenticating.
Only registered when `settings.is_dev_mode` is True (see routes/__init__.py).
Belt-and-suspenders: the route itself also rejects non-dev mode at runtime.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import limiter, get_limit
from app.core.security import create_access_token
from app.schemas.user import UserPublic
from app.services import users as user_service
from app.services.audit.logger_db import get_audit_logger_db

router = APIRouter()


@router.post("/impersonate/{user_id}")
@limiter.limit(get_limit("auth_login"))
async def impersonate_user(
    user_id: int,
    request: Request,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Issue an access token for the target user. Admin + dev-mode only."""
    # Runtime gate (in addition to the registration gate in routes/__init__.py).
    if not settings.is_dev_mode:
        raise HTTPException(status_code=404)

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself")

    target = user_service.get_user(user_id, db=db)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_access_token(
        target,
        expires_delta=timedelta(minutes=30),
        impersonated_by=admin.id,
    )

    audit_logger = get_audit_logger_db()
    audit_logger.log_security_event(
        action="dev_impersonation_started",
        user=admin.username,
        resource=f"user:{target.id}",
        details={
            "admin_id": admin.id,
            "target_user_id": target.id,
            "target_username": target.username,
        },
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        db=db,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_service.serialize_user(target),
    }
