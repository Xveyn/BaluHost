"""API routes for file sharing."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.models.user import User
from app.models.file_metadata import FileMetadata
from app.services.shares import ShareService
from app.services.audit_logger_db import get_audit_logger_db
from app.schemas.shares import (
    ShareLinkCreate, ShareLinkUpdate, ShareLinkResponse, ShareLinkAccessRequest,
    FileShareCreate, FileShareUpdate, FileShareResponse,
    SharedWithMeResponse, ShareStatistics
)

router = APIRouter()


# ===========================
# Share Links Routes
# ===========================

@router.post("/links", response_model=ShareLinkResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("share_create"))
async def create_share_link(
    data: ShareLinkCreate,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new public share link."""
    audit_logger = get_audit_logger_db()
    
    try:
        share_link = ShareService.create_share_link(db, current_user.id, data)
        
        # Get file info
        file_metadata = db.get(FileMetadata, data.file_id)
        
        # Log action
        audit_logger.log_file_share_created(
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_metadata.path if file_metadata else "unknown",
            share_type="public_link",
            ip_address=request.client.host if request.client else None,
            db=db
        )
        
        response = ShareLinkResponse(
            id=share_link.id,
            token=share_link.token,
            file_id=share_link.file_id,
            owner_id=share_link.owner_id,
            has_password=bool(share_link.hashed_password),
            allow_download=share_link.allow_download,
            allow_preview=share_link.allow_preview,
            max_downloads=share_link.max_downloads,
            download_count=share_link.download_count,
            expires_at=share_link.expires_at,
            description=share_link.description,
            created_at=share_link.created_at,
            last_accessed_at=share_link.last_accessed_at,
            is_expired=share_link.is_expired(),
            is_accessible=share_link.is_accessible(),
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None
        )
        
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/links", response_model=List[ShareLinkResponse])
@user_limiter.limit(get_limit("share_list"))
async def list_share_links(
    request: Request,
    include_expired: bool = False,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all share links created by the current user."""
    share_links = ShareService.get_user_share_links(db, current_user.id, include_expired)
    
    response = []
    for link in share_links:
        file_metadata = db.get(FileMetadata, link.file_id)
        response.append(ShareLinkResponse(
            id=link.id,
            token=link.token,
            file_id=link.file_id,
            owner_id=link.owner_id,
            has_password=bool(link.hashed_password),
            allow_download=link.allow_download,
            allow_preview=link.allow_preview,
            max_downloads=link.max_downloads,
            download_count=link.download_count,
            expires_at=link.expires_at,
            description=link.description,
            created_at=link.created_at,
            last_accessed_at=link.last_accessed_at,
            is_expired=link.is_expired(),
            is_accessible=link.is_accessible(),
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None
        ))
    
    return response


@router.get("/links/{link_id}", response_model=ShareLinkResponse)
async def get_share_link(
    link_id: int,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific share link."""
    share_link = ShareService.get_share_link(db, link_id, current_user.id)
    if not share_link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    
    file_metadata = db.get(FileMetadata, share_link.file_id)
    
    return ShareLinkResponse(
        id=share_link.id,
        token=share_link.token,
        file_id=share_link.file_id,
        owner_id=share_link.owner_id,
        has_password=bool(share_link.hashed_password),
        allow_download=share_link.allow_download,
        allow_preview=share_link.allow_preview,
        max_downloads=share_link.max_downloads,
        download_count=share_link.download_count,
        expires_at=share_link.expires_at,
        description=share_link.description,
        created_at=share_link.created_at,
        last_accessed_at=share_link.last_accessed_at,
        is_expired=share_link.is_expired(),
        is_accessible=share_link.is_accessible(),
        file_name=file_metadata.name if file_metadata else None,
        file_path=file_metadata.path if file_metadata else None,
        file_size=file_metadata.size_bytes if file_metadata else None
    )


@router.patch("/links/{link_id}", response_model=ShareLinkResponse)
async def update_share_link(
    link_id: int,
    data: ShareLinkUpdate,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Update a share link."""
    audit_logger = get_audit_logger_db()
    
    try:
        share_link = ShareService.update_share_link(db, link_id, current_user.id, data)
        file_metadata = db.get(FileMetadata, share_link.file_id)
        
        # Log action
        audit_logger.log_file_action(
            action="share_link_updated",
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_metadata.path if file_metadata else "unknown",
            success=True,
            ip_address=request.client.host if request.client else None,
            db=db
        )
        
        return ShareLinkResponse(
            id=share_link.id,
            token=share_link.token,
            file_id=share_link.file_id,
            owner_id=share_link.owner_id,
            has_password=bool(share_link.hashed_password),
            allow_download=share_link.allow_download,
            allow_preview=share_link.allow_preview,
            max_downloads=share_link.max_downloads,
            download_count=share_link.download_count,
            expires_at=share_link.expires_at,
            description=share_link.description,
            created_at=share_link.created_at,
            last_accessed_at=share_link.last_accessed_at,
            is_expired=share_link.is_expired(),
            is_accessible=share_link.is_accessible(),
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share_link(
    link_id: int,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a share link."""
    audit_logger = get_audit_logger_db()
    
    # Get link info before deletion for logging
    share_link = ShareService.get_share_link(db, link_id, current_user.id)
    file_metadata = None
    if share_link:
        file_metadata = db.get(FileMetadata, share_link.file_id)
    
    success = ShareService.delete_share_link(db, link_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    
    # Log action
    if share_link:
        audit_logger.log_file_action(
            action="share_link_deleted",
            user_id=current_user.id,
            username=current_user.username,
            file_path=file_metadata.path if file_metadata else "unknown",
            success=True,
            ip_address=request.client.host if request.client else None,
            db=db
        )


# ===========================
# Public Share Link Access
# ===========================

@router.post("/public/{token}/access")
@limiter.limit(get_limit("public_share"))
async def access_share_link(
    token: str,
    data: ShareLinkAccessRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """Verify access to a public share link (with optional password)."""
    share_link = ShareService.get_share_link_by_token(db, token)
    
    if not share_link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    
    if not share_link.is_accessible():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link has expired or reached download limit")
    
    # Verify password if required
    if not ShareService.verify_share_link_password(share_link, data.password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid password")
    
    # Get file info
    file_metadata = db.get(FileMetadata, share_link.file_id)
    
    return {
        "file_id": share_link.file_id,
        "file_name": file_metadata.name if file_metadata else None,
        "file_path": file_metadata.path if file_metadata else None,
        "file_size": file_metadata.size_bytes if file_metadata else None,
        "is_directory": file_metadata.is_directory if file_metadata else False,
        "allow_download": share_link.allow_download,
        "allow_preview": share_link.allow_preview,
        "description": share_link.description
    }


@router.get("/public/{token}/info")
async def get_share_link_info(
    token: str,
    db: Session = Depends(get_db)
):
    """Get basic info about a share link (without authentication)."""
    share_link = ShareService.get_share_link_by_token(db, token)
    
    if not share_link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
    
    file_metadata = db.get(FileMetadata, share_link.file_id)
    
    return {
        "has_password": bool(share_link.hashed_password),
        "is_accessible": share_link.is_accessible(),
        "is_expired": share_link.is_expired(),
        "file_name": file_metadata.name if file_metadata else None,
        "file_size": file_metadata.size_bytes if file_metadata else None,
        "is_directory": file_metadata.is_directory if file_metadata else False,
        "description": share_link.description,
        "expires_at": share_link.expires_at,
        "allow_preview": share_link.allow_preview
    }


# ===========================
# File Share Routes
# ===========================

@router.post("/user-shares", response_model=FileShareResponse, status_code=status.HTTP_201_CREATED)
async def create_file_share(
    data: FileShareCreate,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Share a file with another user."""
    audit_logger = get_audit_logger_db()
    
    try:
        file_share = ShareService.create_file_share(db, current_user.id, data)
        
        # Get file and user info
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
        
        return FileShareResponse(
            id=file_share.id,
            file_id=file_share.file_id,
            owner_id=file_share.owner_id,
            shared_with_user_id=file_share.shared_with_user_id,
            can_read=file_share.can_read,
            can_write=file_share.can_write,
            can_delete=file_share.can_delete,
            can_share=file_share.can_share,
            expires_at=file_share.expires_at,
            created_at=file_share.created_at,
            last_accessed_at=file_share.last_accessed_at,
            is_expired=file_share.is_expired(),
            is_accessible=file_share.is_accessible(),
            owner_username=current_user.username,
            shared_with_username=target_user.username if target_user else None,
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get("/user-shares", response_model=List[FileShareResponse])
async def list_file_shares(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all file shares created by the current user."""
    file_shares = ShareService.get_files_shared_by_user(db, current_user.id)
    
    response = []
    for share in file_shares:
        file_metadata = db.get(FileMetadata, share.file_id)
        target_user = db.get(User, share.shared_with_user_id)
        
        response.append(FileShareResponse(
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
            owner_username=current_user.username,
            shared_with_username=target_user.username if target_user else None,
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None
        ))
    
    return response


@router.get("/user-shares/file/{file_id}", response_model=List[FileShareResponse])
async def list_file_shares_for_file(
    file_id: int,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get all shares for a specific file."""
    file_shares = ShareService.get_file_shares_by_file(db, file_id, current_user.id)
    
    response = []
    for share in file_shares:
        file_metadata = db.get(FileMetadata, share.file_id)
        target_user = db.get(User, share.shared_with_user_id)
        
        response.append(FileShareResponse(
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
            owner_username=current_user.username,
            shared_with_username=target_user.username if target_user else None,
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None
        ))
    
    return response


@router.get("/shared-with-me", response_model=List[SharedWithMeResponse])
async def list_files_shared_with_me(
    current_user: User = Depends(deps.get_current_user),
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
async def update_file_share(
    share_id: int,
    data: FileShareUpdate,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Update a file share."""
    audit_logger = get_audit_logger_db()
    
    try:
        file_share = ShareService.update_file_share(db, share_id, current_user.id, data)
        
        file_metadata = db.get(FileMetadata, file_share.file_id)
        target_user = db.get(User, file_share.shared_with_user_id)
        
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
        
        return FileShareResponse(
            id=file_share.id,
            file_id=file_share.file_id,
            owner_id=file_share.owner_id,
            shared_with_user_id=file_share.shared_with_user_id,
            can_read=file_share.can_read,
            can_write=file_share.can_write,
            can_delete=file_share.can_delete,
            can_share=file_share.can_share,
            expires_at=file_share.expires_at,
            created_at=file_share.created_at,
            last_accessed_at=file_share.last_accessed_at,
            is_expired=file_share.is_expired(),
            is_accessible=file_share.is_accessible(),
            owner_username=current_user.username,
            shared_with_username=target_user.username if target_user else None,
            file_name=file_metadata.name if file_metadata else None,
            file_path=file_metadata.path if file_metadata else None,
            file_size=file_metadata.size_bytes if file_metadata else None
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/user-shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file_share(
    share_id: int,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a file share."""
    audit_logger = get_audit_logger_db()
    
    # Get share info before deletion for logging
    file_share = ShareService.get_file_share(db, share_id, current_user.id)
    file_metadata = None
    if file_share:
        file_metadata = db.get(FileMetadata, file_share.file_id)
    
    success = ShareService.delete_file_share(db, share_id, current_user.id)
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
async def get_share_statistics(
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
):
    """Get sharing statistics for the current user."""
    return ShareService.get_share_statistics(db, current_user.id)
