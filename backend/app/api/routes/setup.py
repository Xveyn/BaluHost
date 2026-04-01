"""Setup wizard API endpoints.

All endpoints (except /status) are gated: they return 403 if setup is
not required (users exist or SKIP_SETUP is set).

Note on the post-admin endpoints (/users, /file-access, /complete):
After the admin account is created, `is_setup_required()` returns False
because a user now exists. These endpoints use the setup token issued by
/admin (validated via `get_setup_user`) as the gate. We only block them
when the setup wizard has been explicitly marked complete via /complete.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import limiter, get_limit
from app.core.security import create_setup_token
from app.schemas.setup import (
    SetupStatusResponse,
    SetupAdminRequest,
    SetupAdminResponse,
    SetupUserRequest,
    SetupUserResponse,
    SetupFileAccessRequest,
    SetupFileAccessResponse,
    SetupCompleteResponse,
)
from app.schemas.user import UserCreate
from app.services import users as user_service
from app.services.setup import service as setup_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup"])


def _require_setup_not_complete(db: Session) -> None:
    """Raise 403 if the setup wizard has been explicitly completed.

    Used by post-admin endpoints (users, file-access, complete) that must
    accept requests even after admin creation (which causes is_setup_required
    to return False because a user now exists in the DB).
    """
    if setup_service.is_setup_complete(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup has already been completed",
        )


def _require_setup_mode(db: Session) -> None:
    """Raise 403 if setup is not required.

    Used only for /status check and /admin — endpoints that must be
    unreachable once any user exists or setup is complete.
    """
    if not setup_service.is_setup_required(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup has already been completed",
        )


@router.get("/status", response_model=SetupStatusResponse)
async def get_setup_status(db: Session = Depends(get_db)) -> SetupStatusResponse:
    """Check if initial setup is required."""
    required = setup_service.is_setup_required(db)
    completed = setup_service.get_completed_steps(db) if required else []
    return SetupStatusResponse(setup_required=required, completed_steps=completed)


@router.post("/admin", response_model=SetupAdminResponse)
@limiter.limit(get_limit("setup_admin"))
async def create_admin(
    request: Request,
    response: Response,
    payload: SetupAdminRequest,
    db: Session = Depends(get_db),
) -> SetupAdminResponse:
    """Create the initial admin account (Step 1). Protected by multiple security layers."""
    _require_setup_mode(db)

    # Setup secret check
    if settings.setup_secret:
        if payload.setup_secret != settings.setup_secret:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid setup secret",
            )
    else:
        # No secret configured — enforce local-network-only access (production only).
        # In dev mode this check is skipped to keep tests and local development simple.
        # In prod mode any non-private IP address is rejected.
        if not settings.is_dev_mode:
            client_ip = request.client.host if request.client else None
            if client_ip:
                from app.core.network_utils import is_private_or_local_ip
                if not is_private_or_local_ip(client_ip):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Setup is only available from the local network",
                    )

    existing = user_service.get_user_by_username(payload.username, db=db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' already exists",
        )

    user = user_service.create_user(
        UserCreate(
            username=payload.username,
            email=payload.email or None,
            password=payload.password,
            role="admin",
        ),
        db=db,
    )

    token = create_setup_token(user_id=user.id, username=user.username)
    logger.info("Setup admin '%s' created (id=%d)", user.username, user.id)

    return SetupAdminResponse(
        success=True,
        setup_token=token,
        user_id=user.id,
        username=user.username,
    )


@router.post("/users", response_model=SetupUserResponse)
async def create_user(
    request: Request,
    response: Response,
    payload: SetupUserRequest,
    _setup_user=Depends(deps.get_setup_user),
    db: Session = Depends(get_db),
) -> SetupUserResponse:
    """Create a regular user during setup (Step 2)."""
    _require_setup_not_complete(db)

    existing = user_service.get_user_by_username(payload.username, db=db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' already exists",
        )

    user = user_service.create_user(
        UserCreate(
            username=payload.username,
            email=payload.email or None,
            password=payload.password,
            role="user",
        ),
        db=db,
    )

    logger.info("Setup user '%s' created (id=%d)", user.username, user.id)
    return SetupUserResponse(
        success=True,
        user_id=user.id,
        username=user.username,
        email=user.email,
    )


@router.delete("/users/{user_id}")
async def delete_setup_user(
    user_id: int,
    _setup_user=Depends(deps.get_setup_user),
    db: Session = Depends(get_db),
):
    """Delete a user created during setup. Cannot delete admin."""
    _require_setup_not_complete(db)

    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete admin user during setup",
        )

    user_service.delete_user(user_id, db=db)
    return {"success": True, "user_id": user_id}


@router.post("/file-access", response_model=SetupFileAccessResponse)
async def configure_file_access(
    request: Request,
    response: Response,
    payload: SetupFileAccessRequest,
    _setup_user=Depends(deps.get_setup_user),
    db: Session = Depends(get_db),
) -> SetupFileAccessResponse:
    """Configure file access protocols (Step 4)."""
    _require_setup_not_complete(db)

    samba_enabled = payload.samba is not None and payload.samba.enabled
    webdav_enabled = payload.webdav is not None and payload.webdav.enabled

    if not samba_enabled and not webdav_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file access protocol must be enabled",
        )

    active: list[str] = []

    if samba_enabled:
        logger.info("Setup: Samba enabled (workgroup=%s)", payload.samba.workgroup)
        active.append("samba")

    if webdav_enabled:
        logger.info(
            "Setup: WebDAV enabled (port=%d, ssl=%s)",
            payload.webdav.port,
            payload.webdav.ssl,
        )
        active.append("webdav")

    return SetupFileAccessResponse(success=True, active_services=active)


@router.post("/complete", response_model=SetupCompleteResponse)
async def complete_setup(
    _setup_user=Depends(deps.get_setup_user),
    db: Session = Depends(get_db),
) -> SetupCompleteResponse:
    """Mark initial setup as complete."""
    _require_setup_not_complete(db)
    setup_service.complete_setup(db)
    logger.info("Setup wizard completed")
    return SetupCompleteResponse(success=True, message="Setup completed successfully")
