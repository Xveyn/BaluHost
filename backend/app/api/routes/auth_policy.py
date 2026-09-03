"""Admin endpoints for the system-wide auth policy."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
        idle_timeout_minutes=p.idle_timeout_minutes,
        idle_warning_seconds=p.idle_warning_seconds,
        access_token_minutes=p.access_token_minutes,
    )


def _check_idle_window_fits(policy) -> None:
    """The idle window must end before the access token does.

    Otherwise the session dies at the token's expiry - a 401 that logs the user
    out with no dialog and no countdown, which looks like a bug rather than a
    setting. Validated against the MERGED state, so a partial update cannot
    sneak past by changing one field at a time.

    An idle timeout of 0 means "no idle logout"; then the token is the only
    limit, which is honest and needs no check.
    """
    if policy.idle_timeout_minutes == 0:
        return
    idle_window = policy.idle_timeout_minutes * 60 + policy.idle_warning_seconds
    token_window = policy.access_token_minutes * 60
    if idle_window > token_window:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The idle window ({idle_window // 60} min including the warning) "
                f"outlives the access token ({policy.access_token_minutes} min). "
                "Users would be logged out without the warning dialog. Raise the "
                "token lifetime or shorten the idle timeout."
            ),
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
    try:
        _check_idle_window_fits(policy)
    except HTTPException:
        # Nothing is committed yet, but the instance already carries the
        # rejected values - expire it so a later read in this request sees the
        # stored ones again.
        db.rollback()
        raise
    db.commit()
    db.refresh(policy)
    get_audit_logger_db().log_security_event(
        action="auth_policy_updated", user=current_user.username,
        details=data, success=True, db=db,
    )
    return _to_response(policy)
