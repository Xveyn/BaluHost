"""Admin endpoints for the system-wide auth policy."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.auth_policy import AuthPolicyResponse, AuthPolicyUpdate
from app.services.auth_policy import get_auth_policy
from app.services.audit.logger_db import get_audit_logger_db

router = APIRouter()


def _to_response(p) -> AuthPolicyResponse:
    return AuthPolicyResponse(
        pin_login_enabled=p.pin_login_enabled,
        pin_grace_window_seconds=p.pin_grace_window_seconds,
    )


@router.get("", response_model=AuthPolicyResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def read_auth_policy(
    request: Request, response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> AuthPolicyResponse:
    return _to_response(get_auth_policy(db))


@router.put("", response_model=AuthPolicyResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_auth_policy(
    body: AuthPolicyUpdate,
    request: Request, response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> AuthPolicyResponse:
    policy = get_auth_policy(db)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    get_audit_logger_db().log_security_event(
        action="auth_policy_updated", user=current_user.username,
        details=data, success=True, db=db,
    )
    return _to_response(policy)
