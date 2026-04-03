from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterable, Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.database import SessionLocal, ensure_db
from app.models.user import User
from app.schemas.user import UserCreate, UserPublic, UserUpdate
from app.services.files.storage_permissions import set_storage_dir_permissions

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = logging.getLogger(__name__)

SHARED_DIR_NAME = "Shared"


def _get_db() -> Session:
    """Get database session for service layer."""
    return SessionLocal()


def _get_storage_root() -> Path:
    """Get the resolved storage root path."""
    return Path(settings.nas_storage_path).expanduser().resolve()


def _create_home_directory(username: str, user_id: int, db: Optional[Session] = None) -> None:
    """Create a home directory for a user in the storage root.

    Idempotent: skips creation if the directory and metadata already exist.
    """
    from app.services.files.metadata_db import get_metadata, create_metadata

    storage_root = _get_storage_root()
    home_dir = storage_root / username
    home_dir.mkdir(parents=True, exist_ok=True)
    set_storage_dir_permissions(home_dir)

    existing = get_metadata(username, db=db)
    if not existing:
        create_metadata(
            relative_path=username,
            name=username,
            owner_id=user_id,
            size_bytes=0,
            is_directory=True,
            db=db,
        )
    logger.info("Home directory ensured for user '%s' at %s", username, home_dir)


def ensure_user_home_directories(db: Optional[Session] = None) -> None:
    """Ensure home directories exist for all non-admin users and create the Shared folder."""
    from app.services.files.metadata_db import get_metadata, create_metadata

    with ensure_db(db) as session:
        storage_root = _get_storage_root()

        # Ensure Shared folder
        shared_dir = storage_root / SHARED_DIR_NAME
        shared_dir.mkdir(parents=True, exist_ok=True)
        set_storage_dir_permissions(shared_dir)
        existing_shared = get_metadata(SHARED_DIR_NAME, db=session)
        if not existing_shared:
            # Shared folder owned by admin (owner_id is NOT NULL in DB)
            admin_user = session.query(User).filter(User.role == "admin").first()
            if admin_user:
                create_metadata(
                    relative_path=SHARED_DIR_NAME,
                    name=SHARED_DIR_NAME,
                    owner_id=admin_user.id,
                    size_bytes=0,
                    is_directory=True,
                    db=session,
                )
                logger.info("Shared directory created at %s", shared_dir)

        # Ensure home dirs for all non-admin users
        users = session.query(User).filter(User.role != "admin").all()
        for user in users:
            _create_home_directory(user.username, user.id, db=session)


def _rename_home_directory(old_username: str, new_username: str, db: Optional[Session] = None) -> None:
    """Rename a user's home directory and update all related metadata paths."""
    from app.services.files.metadata_db import rename_metadata
    from app.models.file_metadata import FileMetadata

    with ensure_db(db) as session:
        storage_root = _get_storage_root()
        old_dir = storage_root / old_username
        new_dir = storage_root / new_username

        if old_dir.exists():
            old_dir.rename(new_dir)

        # Rename the home directory metadata entry itself
        rename_metadata(
            old_path=old_username,
            new_path=new_username,
            new_name=new_username,
            db=session,
        )

        # Update all child metadata paths with the old prefix
        old_prefix = f"{old_username}/"
        new_prefix = f"{new_username}/"
        children = session.query(FileMetadata).filter(
            FileMetadata.path.startswith(old_prefix)
        ).all()
        for child in children:
            child.path = new_prefix + child.path[len(old_prefix):]
            if child.parent_path and child.parent_path.startswith(old_prefix):
                child.parent_path = new_prefix + child.parent_path[len(old_prefix):]
            elif child.parent_path == old_username:
                child.parent_path = new_username
        session.commit()
        logger.info("Renamed home directory from '%s' to '%s'", old_username, new_username)


def ensure_admin_user(settings: Settings) -> None:
    """Ensure admin user exists in database."""
    db = _get_db()
    try:
        existing = get_user_by_username(settings.admin_username, db=db)
        if existing:
            return

        payload = UserCreate(
            username=settings.admin_username,
            email=settings.admin_email,
            password=settings.admin_password,
            role=settings.admin_role,
        )
        create_user(payload, db=db)
    finally:
        db.close()


def list_users(db: Optional[Session] = None) -> Iterable[User]:
    """List all users from database."""
    with ensure_db(db) as session:
        return session.query(User).all()


def get_user(user_id: int | str, db: Optional[Session] = None) -> Optional[User]:
    """Get user by ID from database."""
    with ensure_db(db) as session:
        # Support both int and string IDs for backward compatibility
        if isinstance(user_id, str):
            try:
                user_id = int(user_id)
            except ValueError:
                return None
        return session.query(User).filter(User.id == user_id).first()


def get_user_by_username(username: str, db: Optional[Session] = None) -> Optional[User]:
    """Get user by username from database."""
    with ensure_db(db) as session:
        return session.query(User).filter(User.username == username).first()


def create_user(payload: UserCreate, db: Optional[Session] = None) -> User:
    """Create new user in database."""
    with ensure_db(db) as session:
        password_hash = pwd_context.hash(payload.password)
        # Convert empty string to None for email (database nullable field)
        email = payload.email if payload.email and payload.email.strip() else None
        user = User(
            username=payload.username,
            email=email,
            role=(getattr(payload, "role", None) or "user"),
            hashed_password=password_hash,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        # Create home directory for non-admin users
        if user.role != "admin":
            try:
                _create_home_directory(user.username, user.id, db=session)
            except Exception:
                logger.warning("Failed to create home directory for user '%s'", user.username, exc_info=True)

        return user


def update_user(user_id: int | str, payload: UserUpdate, db: Optional[Session] = None) -> Optional[User]:
    """Update user in database."""
    with ensure_db(db) as session:
        user = get_user(user_id, db=session)
        if not user:
            return None

        old_username = user.username

        if payload.username:
            user.username = payload.username
        if payload.email is not None:
            # Convert empty string to None for email (database nullable field)
            user.email = payload.email if payload.email.strip() else None
        if payload.role:
            user.role = payload.role
        if payload.password:
            user.hashed_password = pwd_context.hash(payload.password)
        if payload.is_active is not None:
            user.is_active = payload.is_active

        session.commit()
        session.refresh(user)

        # Rename home directory if username changed and user is not admin
        if payload.username and payload.username != old_username and user.role != "admin":
            try:
                _rename_home_directory(old_username, payload.username, db=session)
            except Exception:
                logger.warning(
                    "Failed to rename home directory from '%s' to '%s'",
                    old_username, payload.username, exc_info=True,
                )

        return user


def delete_user(user_id: int | str, db: Optional[Session] = None) -> bool:
    """Delete user from database."""
    with ensure_db(db) as session:
        user = get_user(user_id, db=session)
        if not user:
            return False

        username = user.username
        is_admin = user.role == "admin"

        session.delete(user)
        session.commit()

        # Remove home directory for non-admin users
        if not is_admin:
            try:
                storage_root = _get_storage_root()
                home_dir = storage_root / username
                if home_dir.exists():
                    shutil.rmtree(home_dir)
                    logger.info("Deleted home directory for user '%s'", username)
            except Exception:
                logger.warning("Failed to delete home directory for user '%s'", username, exc_info=True)

        return True


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


def update_user_password(user_id: int | str, new_password: str, db: Optional[Session] = None) -> bool:
    """Update user password in database."""
    with ensure_db(db) as session:
        user = get_user(user_id, db=session)
        if not user:
            return False

        user.hashed_password = pwd_context.hash(new_password)
        session.commit()
        return True


def list_users_filtered(
    db: Session,
    *,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[list[User], dict]:
    """List users with filters/sorting and compute aggregate stats.

    Returns (filtered_users, stats_dict) where stats_dict has keys:
    total, active, inactive, admins.
    """
    from sqlalchemy import or_, func

    query = db.query(User)

    if search:
        query = query.filter(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )
    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    _SORTABLE_FIELDS = {"username", "created_at", "email", "role", "is_active"}
    if sort_by not in _SORTABLE_FIELDS:
        sort_by = "created_at"
    sort_column = getattr(User, sort_by, User.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    filtered_users = query.all()

    total_count = db.query(func.count(User.id)).scalar()
    active_count = db.query(func.count(User.id)).filter(User.is_active == True).scalar()  # noqa: E712
    admin_count = db.query(func.count(User.id)).filter(User.role == "admin").scalar()

    stats = {
        "total": total_count,
        "active": active_count,
        "inactive": total_count - active_count,
        "admins": admin_count,
    }
    return filtered_users, stats


def toggle_active(user_id: int | str, db: Session) -> Optional[User]:
    """Toggle a user's is_active flag. Returns the updated user or None."""
    user = get_user(user_id, db=db)
    if user is None:
        return None
    user.is_active = not user.is_active
    db.commit()
    db.refresh(user)
    return user


def update_avatar_url(user_id: int | str, avatar_url: str, db: Session) -> Optional[User]:
    """Set the avatar_url for a user. Returns the updated user or None."""
    user = get_user(user_id, db=db)
    if user is None:
        return None
    user.avatar_url = avatar_url
    db.commit()
    db.refresh(user)
    return user


def set_smb_enabled(user_id: int, enabled: bool, db: Session) -> Optional[User]:
    """Toggle the smb_enabled flag for a user.

    Returns the updated user, or None if not found.
    """
    user = get_user(user_id, db=db)
    if user is None:
        return None
    user.smb_enabled = enabled
    db.commit()
    db.refresh(user)
    return user


def serialize_user(user: User) -> UserPublic:
    """Convert database User model to UserPublic schema."""
    return UserPublic(
        id=user.id,  # Keep as int - matches UserPublic schema
        username=user.username,
        email=user.email if user.email else None,  # Return None instead of empty string
        role=user.role,
        is_active=user.is_active,
        smb_enabled=user.smb_enabled,
        created_at=user.created_at.isoformat() if user.created_at else "",
        updated_at=user.updated_at.isoformat() if user.updated_at else None
    )
