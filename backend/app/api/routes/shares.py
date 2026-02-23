"""API routes for file sharing."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.models.file_metadata import FileMetadata
from app.models.user import User
from app.schemas.user import UserPublic
from app.services.shares import ShareService
from app.services.audit_logger_db import get_audit_logger_db
from app.schemas.shares import (
    FileShareCreate, FileShareUpdate, FileShareResponse,
    SharedWithMeResponse, ShareStatistics
)

router = APIRouter()


# ===========================
# Helper
# ===========================

def _build_share_response(share, db: Session, current_user: UserPublic) -> FileShareResponse:
    """Build a FileShareResponse with correct owner/target lookups."""
    file_metadata = db.get(FileMetadata, share.file_id)
    target_user = db.get(User, share.shared_with_user_id)
    owner = db.get(User, share.owner_id)

    return FileShareResponse(
        id=share.id,
        file_id=share.file_id,
        owner_id=share.owner_id,
        shared_with_user_id=share.shared_with_user_id,
        can_read=share.can_read,
        can_write=share.can_write,
        can_delete=share.can_delete,
        can_share=share.can_share,
        expires_at=share.expires_at,
        created_at=share.created_at,
        last_accessed_at=share.last_accessed_at,
        is_expired=share.is_expired(),
        is_accessible=share.is_accessible(),
        owner_username=owner.username if owner else None,
        shared_with_username=target_user.username if target_user else None,
        file_name=file_metadata.name if file_metadata else None,
        file_path=file_metadata.path if file_metadata else None,
        file_size=file_metadata.size_bytes if file_metadata else None,
        is_directory=file_metadata.is_directory if file_metadata else False,
    )


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
    stmt = select(User).where(User.is_active == True).order_by(User.username)
    users = db.execute(stmt).scalars().all()
    return [
        {"id": u.id, "username": u.username}
        for u in users
        if u.id != current_user.id
    ]


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

        # Get file and user info for logging
        file_metadata = db.get(FileMetadata, data.file_id)
        target_user = db.get(User, data.shared_with_user_id)

        # Log action
        audit_logger.log_file_share_created(
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_metadata.path if file_metadata else "unknown",
            share_type="user_share",
            shared_with=target_user.username if target_user else "unknown",
            ip_address=request.client.host if request.client else None,
            db=db
        )

        return _build_share_response(file_share, db, current_user)

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
    return [_build_share_response(share, db, current_user) for share in file_shares]


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
    return [_build_share_response(share, db, current_user) for share in file_shares]


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

    response = []
    for share in file_shares:
        file_metadata = db.get(FileMetadata, share.file_id)
        owner = db.get(User, share.owner_id)

        if file_metadata and owner:
            response.append(SharedWithMeResponse(
                share_id=share.id,
                file_id=share.file_id,
                file_name=file_metadata.name,
                file_path=file_metadata.path,
                file_size=file_metadata.size_bytes,
                is_directory=file_metadata.is_directory,
                owner_username=owner.username,
                owner_id=owner.id,
                can_read=share.can_read,
                can_write=share.can_write,
                can_delete=share.can_delete,
                can_share=share.can_share,
                shared_at=share.created_at,
                expires_at=share.expires_at,
                is_expired=share.is_expired()
            ))

    return response


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

        file_metadata = db.get(FileMetadata, file_share.file_id)

        # Log action
        audit_logger.log_file_action(
            action="file_share_updated",
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_metadata.path if file_metadata else "unknown",
            success=True,
            ip_address=request.client.host if request.client else None,
            db=db
        )

        return _build_share_response(file_share, db, current_user)
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
    file_metadata = None
    if file_share:
        file_metadata = db.get(FileMetadata, file_share.file_id)

    success = ShareService.delete_file_share(db, share_id, current_user)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File share not found")

    # Log action
    if file_share:
        audit_logger.log_file_action(
            action="file_share_deleted",
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_metadata.path if file_metadata else "unknown",
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
