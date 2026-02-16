from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
import os
from pathlib import Path
import uuid
import shutil

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.core.config import settings
from app.core.database import get_db
from app.schemas.user import UserCreate, UserPublic, UserUpdate, UsersResponse
from app.services import users as user_service
from app.models.user import User
from app.services.audit_logger_db import get_audit_logger_db

router = APIRouter()


@router.get("/", response_model=UsersResponse)
@user_limiter.limit(get_limit("user_operations"))
async def list_users(
    request: Request,
    response: Response,
    search: str | None = Query(None, description="Search by username or email"),
    role: str | None = Query(None, description="Filter by role"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    sort_by: str = Query("created_at", description="Sort by field"),
    sort_order: str = Query("desc", description="Sort order (asc/desc)"),
    _: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
) -> UsersResponse:
    # Build query
    query = db.query(User)
    
    # Apply filters
    if search:
        query = query.filter(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    
    if role:
        query = query.filter(User.role == role)
    
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    # Apply sorting
    sort_column = getattr(User, sort_by, User.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Get filtered users
    filtered_users = query.all()
    
    # Calculate statistics (from all users, not filtered)
    total_count = db.query(func.count(User.id)).scalar()
    active_count = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    inactive_count = total_count - active_count
    admin_count = db.query(func.count(User.id)).filter(User.role == "admin").scalar()
    
    users = [user_service.serialize_user(record) for record in filtered_users]
    
    return UsersResponse(
        users=users,
        total=total_count,
        active=active_count,
        inactive=inactive_count,
        admins=admin_count
    )


@router.post("/", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("user_operations"))
async def create_user(
    request: Request,
    response: Response,
    payload: UserCreate,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> UserPublic:
    audit_logger = get_audit_logger_db()

    if user_service.get_user_by_username(payload.username, db=db):
        audit_logger.log_user_management(
            action="user_create_failed",
            admin_user=current_admin.username,
            target_user=payload.username,
            details={"reason": "username_already_exists"},
            success=False,
            error_message="Username already exists",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    record = user_service.create_user(payload, db=db)

    # Sync Samba password if SMB is enabled for this user
    if record.smb_enabled:
        from app.services import samba_service
        await samba_service.sync_smb_password(record.username, payload.password)
        await samba_service.regenerate_shares_config()
        await samba_service.reload_samba()

    audit_logger.log_user_management(
        action="user_created",
        admin_user=current_admin.username,
        target_user=payload.username,
        details={"role": payload.role, "email": payload.email},
        success=True,
        db=db
    )

    return user_service.serialize_user(record)


@router.put("/{user_id}", response_model=UserPublic)
@user_limiter.limit(get_limit("user_operations"))
async def update_user(
    request: Request,
    response: Response,
    user_id: str,
    payload: UserUpdate,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> UserPublic:
    audit_logger = get_audit_logger_db()

    # Get old user data for comparison
    old_user = user_service.get_user(user_id, db=db)
    if not old_user:
        audit_logger.log_user_management(
            action="user_update_failed",
            admin_user=current_admin.username,
            target_user=user_id,
            success=False,
            error_message="User not found",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    record = user_service.update_user(user_id, payload, db=db)

    # Sync Samba password if changed and SMB is enabled
    if payload.password and record.smb_enabled:
        from app.services import samba_service
        await samba_service.sync_smb_password(record.username, payload.password)

    # Log changes
    details = {}
    if payload.role and payload.role != old_user.role:
        details["role_changed"] = f"{old_user.role} -> {payload.role}"
    if payload.email and payload.email != old_user.email:
        details["email_changed"] = True
    if payload.password:
        details["password_changed"] = True

    audit_logger.log_user_management(
        action="user_updated",
        admin_user=current_admin.username,
        target_user=old_user.username,
        details=details,
        success=True,
        db=db
    )

    return user_service.serialize_user(record)


@router.delete("/{user_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("user_operations"))
async def delete_user(
    request: Request,
    response: Response,
    user_id: str,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> None:
    audit_logger = get_audit_logger_db()

    # Get user info before deletion
    user = user_service.get_user(user_id, db=db)
    if not user:
        audit_logger.log_user_management(
            action="user_delete_failed",
            admin_user=current_admin.username,
            target_user=user_id,
            success=False,
            error_message="User not found",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Remove Samba access before deleting the user
    if user.smb_enabled:
        from app.services import samba_service
        await samba_service.remove_smb_user(user.username)
        await samba_service.regenerate_shares_config()
        await samba_service.reload_samba()

    username = user.username
    deleted = user_service.delete_user(user_id, db=db)

    audit_logger.log_user_management(
        action="user_deleted",
        admin_user=current_admin.username,
        target_user=username,
        details={"user_id": user_id},
        success=True,
        db=db
    )


@router.post("/bulk-delete", response_model=dict, status_code=status.HTTP_200_OK)
@user_limiter.limit(get_limit("user_operations"))
async def bulk_delete_users(
    request: Request,
    response: Response,
    user_ids: list[str],
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> dict:
    """Delete multiple users at once."""
    audit_logger = get_audit_logger_db()
    deleted_count = 0
    failed_ids = []
    deleted_usernames = []

    for user_id in user_ids:
        user = user_service.get_user(user_id, db=db)
        if user and user_service.delete_user(user_id, db=db):
            deleted_count += 1
            deleted_usernames.append(user.username)
        else:
            failed_ids.append(user_id)

    audit_logger.log_user_management(
        action="user_bulk_delete",
        admin_user=current_admin.username,
        target_user=f"{deleted_count} users",
        details={
            "deleted_count": deleted_count,
            "failed_count": len(failed_ids),
            "deleted_users": deleted_usernames
        },
        success=True,
        db=db
    )

    return {
        "deleted": deleted_count,
        "failed": len(failed_ids),
        "failed_ids": failed_ids
    }


@router.patch("/{user_id}/toggle-active", response_model=UserPublic)
@user_limiter.limit(get_limit("user_operations"))
async def toggle_user_active(
    request: Request,
    response: Response,
    user_id: str,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> UserPublic:
    """Toggle user active status."""
    audit_logger = get_audit_logger_db()

    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    old_status = user.is_active
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)

    audit_logger.log_user_management(
        action="user_status_toggled",
        admin_user=current_admin.username,
        target_user=user.username,
        details={
            "old_status": "active" if old_status else "inactive",
            "new_status": "active" if user.is_active else "inactive"
        },
        success=True,
        db=db
    )

    return user_service.serialize_user(user)


@router.post("/{user_id}/avatar", response_model=UserPublic)
@user_limiter.limit(get_limit("user_operations"))
async def upload_avatar(
    request: Request,
    response: Response,
    user_id: str,
    avatar: UploadFile = File(...),
    current_user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
) -> UserPublic:
    """Upload avatar for a user. Users can only upload their own avatar."""
    # Check if user is uploading their own avatar or is admin
    if current_user.id != int(user_id) and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only upload your own avatar"
        )
    
    # Get the user
    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if avatar.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image files (JPEG, PNG, GIF, WebP) are allowed"
        )
    
    # Create avatars directory if it doesn't exist
    avatars_dir = Path(settings.nas_storage_path) / ".system" / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    # Delete old avatar if exists
    if user.avatar_url and user.avatar_url.startswith("/avatars/"):
        old_avatar_path = avatars_dir / Path(user.avatar_url).name
        try:
            old_avatar_path.unlink()
        except FileNotFoundError:
            pass
    
    # Generate unique filename
    file_ext = Path(avatar.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = avatars_dir / unique_filename
    
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(avatar.file, buffer)
    
    # Update user avatar_url
    user.avatar_url = f"/avatars/{unique_filename}"
    db.commit()
    db.refresh(user)
    
    return user_service.serialize_user(user)
