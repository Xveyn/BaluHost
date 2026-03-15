"""API routes for file sharing."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.user import UserPublic
from app.services.files.shares import ShareService
from app.services.audit.logger_db import get_audit_logger_db
from app.schemas.shares import (
    FileShareCreate, FileShareUpdate, FileShareResponse,
    SharedWithMeResponse, ShareStatistics
)

router = APIRouter()


# ===========================
# File Share Routes
# ===========================

@router.get("/users", response_model=List[dict])
@user_limiter.limit(get_limit("share_list"))
async def list_shareable_users(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get a minimal user list for share target selection (any authenticated user)."""
    return ShareService.list_shareable_users(db, current_user.id)


@router.post("/user-shares", response_model=FileShareResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("share_create"))
async def create_file_share(
    data: FileShareCreate,
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Share a file with another user."""
    audit_logger = get_audit_logger_db()

    try:
        file_share = ShareService.create_file_share(db, current_user, data)

        file_path = ShareService.get_file_path_for_share(file_share, db)
        target_username = ShareService.get_username(db, data.shared_with_user_id)

        audit_logger.log_file_share_created(
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_path or "unknown",
            share_type="user_share",
            shared_with=target_username or "unknown",
            ip_address=request.client.host if request.client else None,
            db=db
        )

        return ShareService.build_share_response(file_share, db)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/user-shares", response_model=List[FileShareResponse])
@user_limiter.limit(get_limit("share_list"))
async def list_file_shares(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all file shares created by the current user."""
    file_shares = ShareService.get_files_shared_by_user(db, current_user.id, current_user)
    return [ShareService.build_share_response(share, db) for share in file_shares]


@router.get("/user-shares/file/{file_id}", response_model=List[FileShareResponse])
@user_limiter.limit(get_limit("share_list"))
async def list_file_shares_for_file(
    file_id: int,
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all shares for a specific file."""
    file_shares = ShareService.get_file_shares_by_file(db, file_id, current_user)
    return [ShareService.build_share_response(share, db) for share in file_shares]


@router.get("/shared-with-me", response_model=List[SharedWithMeResponse])
@user_limiter.limit(get_limit("share_list"))
async def list_files_shared_with_me(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all files shared with the current user."""
    file_shares = ShareService.get_files_shared_with_user(db, current_user.id)

    result = []
    for share in file_shares:
        item = ShareService.build_shared_with_me_response(share, db)
        if item:
            result.append(item)
    return result


@router.patch("/user-shares/{share_id}", response_model=FileShareResponse)
@user_limiter.limit(get_limit("share_create"))
async def update_file_share(
    share_id: int,
    data: FileShareUpdate,
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Update a file share."""
    audit_logger = get_audit_logger_db()

    try:
        file_share = ShareService.update_file_share(db, share_id, current_user, data)
        file_path = ShareService.get_file_path_for_share(file_share, db)

        audit_logger.log_file_action(
            action="file_share_updated",
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_path or "unknown",
            success=True,
            ip_address=request.client.host if request.client else None,
            db=db
        )

        return ShareService.build_share_response(file_share, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/user-shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("share_create"))
async def delete_file_share(
    share_id: int,
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a file share."""
    audit_logger = get_audit_logger_db()

    # Get share info before deletion for logging
    file_share = ShareService.get_file_share(db, share_id, current_user)
    file_path = None
    if file_share:
        file_path = ShareService.get_file_path_for_share(file_share, db)

    success = ShareService.delete_file_share(db, share_id, current_user)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File share not found")

    if file_share:
        audit_logger.log_file_action(
            action="file_share_deleted",
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_path or "unknown",
            success=True,
            ip_address=request.client.host if request.client else None,
            db=db
        )


@router.get("/statistics", response_model=ShareStatistics)
@user_limiter.limit(get_limit("share_list"))
async def get_share_statistics(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get sharing statistics for the current user."""
    return ShareService.get_share_statistics(db, current_user.id)
