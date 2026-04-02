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
from app.services.audit.logger_db import get_audit_logger_db

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

    if not user.is_active:
        audit_logger.log_security_event(
            action="inactive_user_access",
            user=user.username,
            success=False,
            error_message="User account is inactive",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
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


async def get_setup_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserPublic:
    """
    Validate a setup token.

    Only accepts JWT with type='setup'. Used for setup wizard endpoints
    after admin creation (Step 1).
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Setup token required",
        )

    try:
        payload: TokenPayload = auth_service.decode_token(token, token_type="setup")
    except auth_service.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired setup token",
        )

    user = user_service.get_user(payload.sub, db=db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Setup user not found",
        )

    return user_service.serialize_user(user)


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


def _make_power_dependency(action: str):
    """Factory for power-action-specific auth dependencies."""

    async def get_power_authorized_user(
        request: Request,
        user: UserPublic = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> UserPublic:
        """Allow admins or users with the specific power permission."""
        if user.role == "admin":
            return user

        from app.services.power_permissions import check_permission

        if check_permission(db, user.id, action):
            return user

        audit_logger = get_audit_logger_db()
        audit_logger.log_authorization_failure(
            user=user.username,
            action=f"power_{action}_denied",
            required_permission=f"power:{action}",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: power:{action} required",
        )

    return get_power_authorized_user


require_power_soft_sleep = _make_power_dependency("soft_sleep")
require_power_wake = _make_power_dependency("wake")
require_power_suspend = _make_power_dependency("suspend")
require_power_wol = _make_power_dependency("wol")


async def require_sync_allowed(request: Request) -> None:
    """Dependency that blocks automatic sync requests during sleep mode.

    Reads X-Sync-Trigger header:
    - "auto" / "scheduled" -> blocked during sleep (503)
    - "manual" / missing   -> allowed (auto-wake middleware handles waking)
    """
    from app.services.power.sleep import get_sleep_manager
    from app.schemas.sleep import SleepState

    trigger = (request.headers.get("X-Sync-Trigger") or "manual").lower()
    if trigger not in ("auto", "scheduled"):
        return  # manual or unknown -> allow

    manager = get_sleep_manager()
    if manager is None:
        return  # sleep manager not running -> allow

    state = manager._current_state
    if state == SleepState.AWAKE:
        return  # system is awake -> allow

    # Compute next_wake_at and retry_after from config
    config = manager._load_config()
    next_wake_at = None
    retry_after = None
    if config and config.schedule_enabled:
        from datetime import datetime, timedelta
        now = datetime.now()
        h, m = map(int, config.schedule_wake_time.split(":"))
        wake_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if wake_dt <= now:
            wake_dt += timedelta(days=1)
        next_wake_at = wake_dt.isoformat()
        retry_after = int((wake_dt - now).total_seconds())

    raise HTTPException(
        status_code=503,
        detail="Sync blocked: NAS is in sleep mode",
        headers={"Retry-After": str(retry_after)} if retry_after else {},
    )
