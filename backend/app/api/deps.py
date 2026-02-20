from datetime import datetime, timezone
from typing import Optional
import logging

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

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False)


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserPublic:
    audit_logger = get_audit_logger_db()

    if not token:
        logger.debug("No authentication token in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- API Key path ---
    if token.startswith("balu_"):
        from app.services.api_key_service import ApiKeyService

        api_key = ApiKeyService.validate_api_key(db, token)
        if not api_key:
            audit_logger.log_security_event(
                action="invalid_api_key",
                user="unknown",
                success=False,
                error_message="Invalid or expired API key",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        user = user_service.get_user(api_key.target_user_id, db=db)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key target user inactive",
            )

        # Record usage with client IP
        client_ip = request.client.host if request.client else None
        ApiKeyService.record_usage(db, api_key, ip=client_ip)

        # Store metadata for audit trail
        request.state.auth_method = "api_key"
        request.state.api_key_id = api_key.id
        return user_service.serialize_user(user)

    # --- JWT path (existing logic) ---
    try:
        payload: TokenPayload = auth_service.decode_token(token)
        logger.debug(f"Token decoded: sub={payload.sub}, role={getattr(payload, 'role', None)}")
    except auth_service.InvalidTokenError as exc:
        logger.warning("Invalid or expired authentication token")
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
    logger.debug(f"Retrieved user from database: {user.username if user else 'None'}")
    if not user:
        audit_logger.log_security_event(
            action="deleted_user_access",
            user=payload.sub,
            success=False,
            error_message="User no longer exists",
            db=db
        )
        logger.warning(f"User {payload.sub} no longer exists in database")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    return user_service.serialize_user(user)


async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[UserPublic]:
    """Get current user if token is provided, otherwise return None."""
    if not token:
        return None

    # --- API Key path ---
    if token.startswith("balu_"):
        from app.services.api_key_service import ApiKeyService

        api_key = ApiKeyService.validate_api_key(db, token)
        if not api_key:
            return None
        user = user_service.get_user(api_key.target_user_id, db=db)
        if not user or not user.is_active:
            return None
        client_ip = request.client.host if request.client else None
        ApiKeyService.record_usage(db, api_key, ip=client_ip)
        request.state.auth_method = "api_key"
        request.state.api_key_id = api_key.id
        return user_service.serialize_user(user)

    # --- JWT path ---
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
    logger.debug(f"Admin check for user={user.username}, role={user.role}")
    if user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_authorization_failure(
            user=user.username,
            action="admin_access_denied",
            required_permission="admin",
            db=db
        )
        logger.warning(f"Admin access denied for user {user.username} (role={user.role})")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: Admin required",
        )
    logger.debug(f"Admin access granted for user {user.username}")
    return user


async def verify_mobile_device_token(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserPublic:
    """
    Verify mobile device authentication and check if device token hasn't expired.
    
    This dependency should be used for mobile-specific endpoints that require
    valid device authorization.
    
    Raises:
        HTTPException(401): If device token has expired
        HTTPException(403): If device not found or inactive
    """
    from datetime import datetime
    from app.models.mobile import MobileDevice
    
    # First get the current user (validates JWT)
    user = await get_current_user(request=request, token=token, db=db)
    
    # Extract device ID from request headers (mobile app should send this)
    device_id = request.headers.get("X-Device-ID")
    
    if not device_id:
        # If no device ID in header, skip device-specific checks
        # (allows web access to mobile endpoints for management)
        return user
    
    # Check if device exists and belongs to user
    device = db.query(MobileDevice).filter(
        MobileDevice.id == device_id,
        MobileDevice.user_id == str(user.id)
    ).first()
    
    if not device:
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="unknown_device_access",
            user=user.username,
            success=False,
            error_message=f"Device {device_id} not found",
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device not found or not authorized"
        )
    
    # Check if device is active
    if not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device has been deactivated"
        )
    
    # Check if device token has expired
    if device.expires_at and device.expires_at < datetime.now(timezone.utc):
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="expired_device_token",
            user=user.username,
            success=False,
            error_message=f"Device {device.device_name} token expired at {device.expires_at}",
            db=db
        )
        
        # Automatically deactivate expired device
        device.is_active = False
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Device authorization expired. Please re-register your device. "
                   f"Expired on: {device.expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    
    return user
