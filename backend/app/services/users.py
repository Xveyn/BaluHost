from __future__ import annotations

from typing import Iterable, Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate, UserPublic, UserUpdate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_db() -> Session:
    """Get database session for service layer."""
    return SessionLocal()


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
    should_close = db is None
    if db is None:
        db = _get_db()
    
    try:
        return db.query(User).all()
    finally:
        if should_close:
            db.close()


def get_user(user_id: int | str, db: Optional[Session] = None) -> Optional[User]:
    """Get user by ID from database."""
    should_close = db is None
    if db is None:
        db = _get_db()
    
    try:
        # Support both int and string IDs for backward compatibility
        if isinstance(user_id, str):
            try:
                user_id = int(user_id)
            except ValueError:
                return None
        return db.query(User).filter(User.id == user_id).first()
    finally:
        if should_close:
            db.close()


def get_user_by_username(username: str, db: Optional[Session] = None) -> Optional[User]:
    """Get user by username from database."""
    should_close = db is None
    if db is None:
        db = _get_db()
    
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        if should_close:
            db.close()


def create_user(payload: UserCreate, db: Optional[Session] = None) -> User:
    """Create new user in database."""
    should_close = db is None
    if db is None:
        db = _get_db()
    
    try:
        password_hash = pwd_context.hash(payload.password)
        user = User(
            username=payload.username,
            email=payload.email,
            role=payload.role or "user",
            hashed_password=password_hash,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        if should_close:
            db.close()


def update_user(user_id: int | str, payload: UserUpdate, db: Optional[Session] = None) -> Optional[User]:
    """Update user in database."""
    should_close = db is None
    if db is None:
        db = _get_db()
    
    try:
        user = get_user(user_id, db=db)
        if not user:
            return None

        if payload.username:
            user.username = payload.username
        if payload.email:
            user.email = payload.email
        if payload.role:
            user.role = payload.role
        if payload.password:
            user.hashed_password = pwd_context.hash(payload.password)
        if payload.is_active is not None:
            user.is_active = payload.is_active
        
        db.commit()
        db.refresh(user)
        return user
    finally:
        if should_close:
            db.close()


def delete_user(user_id: int | str, db: Optional[Session] = None) -> bool:
    """Delete user from database."""
    should_close = db is None
    if db is None:
        db = _get_db()
    
    try:
        user = get_user(user_id, db=db)
        if not user:
            return False
        
        db.delete(user)
        db.commit()
        return True
    finally:
        if should_close:
            db.close()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)


def update_user_password(user_id: int | str, new_password: str, db: Optional[Session] = None) -> bool:
    """Update user password in database."""
    should_close = db is None
    if db is None:
        db = _get_db()
    
    try:
        user = get_user(user_id, db=db)
        if not user:
            return False
        
        user.hashed_password = pwd_context.hash(new_password)
        db.commit()
        return True
    finally:
        if should_close:
            db.close()


def serialize_user(user: User) -> UserPublic:
    """Convert database User model to UserPublic schema."""
    return UserPublic(
        id=str(user.id),  # Convert to string for backward compatibility
        username=user.username,
        email=user.email or "",
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
        updated_at=user.updated_at.isoformat() if user.updated_at else None
    )
