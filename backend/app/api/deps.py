from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.auth import TokenPayload
from app.schemas.user import UserPublic
from app.services import auth as auth_service
from app.services import users as user_service
from app.services.audit_logger_db import get_audit_logger_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserPublic:
    audit_logger = get_audit_logger_db()
    
    if not token:
        print("[AUTH] Kein Token im Request!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload: TokenPayload = auth_service.decode_token(token)
        print(f"[AUTH] Token-Payload: sub={payload.sub}, role={getattr(payload, 'role', None)}")
    except auth_service.InvalidTokenError as exc:
        print("[AUTH] Token ungültig oder abgelaufen!")
        audit_logger.log_security_event(
            action="invalid_token",
            user="unknown",
            success=False,
            error_message="Invalid or expired token",
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc

    user = user_service.get_user(payload.sub, db=db)
    print(f"[AUTH] User aus DB: {user}")
    if not user:
        audit_logger.log_security_event(
            action="deleted_user_access",
            user=payload.sub,
            success=False,
            error_message="User no longer exists",
            db=db
        )
        print("[AUTH] User existiert nicht mehr!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    return user_service.serialize_user(user)


async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[UserPublic]:
    """Get current user if token is provided, otherwise return None."""
    if not token:
        return None
    
    try:
        payload: TokenPayload = auth_service.decode_token(token)
        user = user_service.get_user(payload.sub, db=db)
        if not user:
            return None
        return user_service.serialize_user(user)
    except auth_service.InvalidTokenError:
        return None


async def get_current_admin(
    user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> UserPublic:
    print(f"[AUTH] get_current_admin: user={user.username}, role={user.role}")
    if user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_authorization_failure(
            user=user.username,
            action="admin_access_denied",
            required_permission="admin",
            db=db
        )
        print("[AUTH] Admin-Check fehlgeschlagen!")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    print("[AUTH] Admin-Check erfolgreich!")
    return user
