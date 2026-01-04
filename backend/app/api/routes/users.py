from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
import os
from pathlib import Path
import uuid
import shutil

from app.api import deps
from app.core.database import get_db
from app.schemas.user import UserCreate, UserPublic, UserUpdate, UsersResponse
from app.services import users as user_service
from app.models.user import User

router = APIRouter()


@router.get("/", response_model=UsersResponse)
async def list_users(
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
async def create_user(
    payload: UserCreate,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> UserPublic:
    if user_service.get_user_by_username(payload.username, db=db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    record = user_service.create_user(payload, db=db)
    return user_service.serialize_user(record)


@router.put("/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> UserPublic:
    record = user_service.update_user(user_id, payload, db=db)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_service.serialize_user(record)


@router.delete("/{user_id}", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> None:
    deleted = user_service.delete_user(user_id, db=db)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.post("/bulk-delete", response_model=dict, status_code=status.HTTP_200_OK)
async def bulk_delete_users(
    user_ids: list[str],
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> dict:
    """Delete multiple users at once."""
    deleted_count = 0
    failed_ids = []
    
    for user_id in user_ids:
        if user_service.delete_user(user_id, db=db):
            deleted_count += 1
        else:
            failed_ids.append(user_id)
    
    return {
        "deleted": deleted_count,
        "failed": len(failed_ids),
        "failed_ids": failed_ids
    }


@router.patch("/{user_id}/toggle-active", response_model=UserPublic)
async def toggle_user_active(
    user_id: str,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
) -> UserPublic:
    """Toggle user active status."""
    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    
    return user_service.serialize_user(user)


@router.post("/{user_id}/avatar", response_model=UserPublic)
async def upload_avatar(
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
    avatars_dir = Path("storage/avatars")
    avatars_dir.mkdir(parents=True, exist_ok=True)
    
    # Delete old avatar if exists
    if user.avatar_url and user.avatar_url.startswith("/avatars/"):
        old_avatar_path = Path("storage") / user.avatar_url.lstrip("/")
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
