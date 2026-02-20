"""API routes for API Key management (admin only)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_admin
from app.schemas.user import UserPublic
from app.schemas.api_key import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyPublic,
    ApiKeyListResponse,
    EligibleUser,
)
from app.services.api_key_service import ApiKeyService
from app.services.audit_logger_db import get_audit_logger_db
from app.core.rate_limiter import limiter, get_limit
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def _serialize_api_key(api_key) -> ApiKeyPublic:
    """Convert ApiKey model to ApiKeyPublic schema."""
    return ApiKeyPublic(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        created_by_user_id=api_key.created_by_user_id,
        created_by_username=api_key.created_by.username if api_key.created_by else "unknown",
        target_user_id=api_key.target_user_id,
        target_username=api_key.target_user.username if api_key.target_user else "unknown",
        is_active=api_key.is_active,
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
        last_used_at=api_key.last_used_at.isoformat() if api_key.last_used_at else None,
        last_used_ip=api_key.last_used_ip,
        use_count=api_key.use_count,
        created_at=api_key.created_at.isoformat() if api_key.created_at else "",
        revoked_at=api_key.revoked_at.isoformat() if api_key.revoked_at else None,
        revocation_reason=api_key.revocation_reason,
    )


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_limit("admin_operations"))
async def create_api_key(
    request: Request,
    response: Response,
    payload: ApiKeyCreate,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Create a new API key. The raw key is only returned in this response."""
    audit_logger = get_audit_logger_db()

    try:
        api_key, raw_key = ApiKeyService.create_api_key(
            db=db,
            name=payload.name,
            created_by_id=current_user.id,
            target_user_id=payload.target_user_id,
            expires_in_days=payload.expires_in_days,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    audit_logger.log_security_event(
        action="api_key_created",
        user=current_user.username,
        success=True,
        details=f"key_id={api_key.id} name='{api_key.name}' target_user_id={api_key.target_user_id}",
        db=db,
    )

    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=api_key.key_prefix,
        target_user_id=api_key.target_user_id,
        target_username=api_key.target_user.username if api_key.target_user else "unknown",
        created_by_username=current_user.username,
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
        created_at=api_key.created_at.isoformat() if api_key.created_at else "",
    )


@router.get("", response_model=ApiKeyListResponse)
@limiter.limit(get_limit("admin_operations"))
async def list_api_keys(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """List all API keys created by the current admin."""
    keys = ApiKeyService.list_api_keys(db, current_user.id)
    return ApiKeyListResponse(
        keys=[_serialize_api_key(k) for k in keys],
        total=len(keys),
    )


@router.get("/eligible-users", response_model=list[EligibleUser])
@limiter.limit(get_limit("admin_operations"))
async def get_eligible_users(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get users eligible as API key targets (self + non-admin active users)."""
    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712
    eligible = []
    for u in users:
        # Include self (admin) and all non-admin active users
        if u.id == current_user.id or u.role != "admin":
            eligible.append(EligibleUser(id=u.id, username=u.username, role=u.role))
    return eligible


@router.get("/{key_id}", response_model=ApiKeyPublic)
@limiter.limit(get_limit("admin_operations"))
async def get_api_key(
    request: Request,
    response: Response,
    key_id: int,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Get details of a specific API key."""
    api_key = ApiKeyService.get_api_key(db, key_id, current_user.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return _serialize_api_key(api_key)


@router.delete("/{key_id}", status_code=status.HTTP_200_OK)
@limiter.limit(get_limit("admin_operations"))
async def revoke_api_key(
    request: Request,
    response: Response,
    key_id: int,
    reason: Optional[str] = None,
    current_user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Revoke an API key."""
    audit_logger = get_audit_logger_db()

    success = ApiKeyService.revoke_api_key(db, key_id, current_user.id, reason)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked",
        )

    audit_logger.log_security_event(
        action="api_key_revoked",
        user=current_user.username,
        success=True,
        details=f"key_id={key_id} reason='{reason or 'none'}'",
        db=db,
    )

    return {"detail": "API key revoked successfully"}
