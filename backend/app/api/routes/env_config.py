"""API routes for environment configuration management (admin only)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_admin
from app.schemas.user import UserPublic
from app.schemas.env_config import (
    EnvConfigReadResponse,
    EnvConfigUpdateRequest,
    EnvVarRevealResponse,
)
from app.services import env_config as env_config_service
from app.services.audit.logger_db import get_audit_logger_db
from app.core.rate_limiter import user_limiter, get_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/env-config", tags=["admin", "env-config"])


@router.get("", response_model=EnvConfigReadResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_env_config(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Read all curated environment variables (admin only).

    Sensitive values are masked with dots. Use /reveal/{key} to see them.
    """
    audit_logger = get_audit_logger_db()

    result = env_config_service.read_all_vars()

    audit_logger.log_security_event(
        action="env_config_read",
        user=current_user.username,
        details={"backend_count": len(result["backend"]), "client_count": len(result["client"])},
        success=True,
        db=db,
    )

    return result


@router.put("")
@user_limiter.limit(get_limit("admin_operations"))
async def update_env_config(
    request: Request,
    response: Response,
    payload: EnvConfigUpdateRequest,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Update environment variables in a specific file (admin only)."""
    audit_logger = get_audit_logger_db()

    try:
        changed = env_config_service.update_vars(
            payload.file,
            [{"key": u.key, "value": u.value} for u in payload.updates],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Log with redacted values for sensitive keys
    redacted_changes = {}
    for u in payload.updates:
        if u.key in changed:
            if env_config_service._is_sensitive(u.key):
                redacted_changes[u.key] = "<redacted>"
            else:
                redacted_changes[u.key] = u.value

    audit_logger.log_security_event(
        action="env_config_updated",
        user=current_user.username,
        details={
            "file": payload.file,
            "changed_keys": changed,
            "values": redacted_changes,
        },
        success=True,
        db=db,
    )

    return {"changed": changed, "count": len(changed)}


@router.get("/reveal/{key}", response_model=EnvVarRevealResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def reveal_env_var(
    request: Request,
    response: Response,
    key: str,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Reveal the actual value of a sensitive variable (admin only)."""
    audit_logger = get_audit_logger_db()

    try:
        value = env_config_service.reveal_var(key)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    audit_logger.log_security_event(
        action="env_config_revealed",
        user=current_user.username,
        details={"key": key},
        success=True,
        db=db,
    )

    return EnvVarRevealResponse(key=key, value=value)
