from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import limiter, get_limit
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserPublic, UserCreate
from app.services import auth as auth_service
from app.services import users as user_service
from app.services.audit_logger_db import get_audit_logger_db

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
@limiter.limit(get_limit("auth_login"))
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    
    user_record = auth_service.authenticate_user(payload.username, payload.password, db=db)
    if not user_record:
        # Log failed login attempt
        audit_logger.log_authentication_attempt(
            username=payload.username,
            success=False,
            ip_address=ip_address,
            user_agent=user_agent,
            error_message="Invalid credentials",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Log successful login
    audit_logger.log_authentication_attempt(
        username=payload.username,
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
        db=db
    )
    
    token = auth_service.create_access_token(user_record)
    user_public = user_service.serialize_user(user_record)
    return TokenResponse(access_token=token, user=user_public)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_limit("auth_register"))
async def register(payload: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None
    
    exists = user_service.get_user_by_username(payload.username, db=db)
    if exists:
        # Log registration attempt with existing username
        audit_logger.log_security_event(
            action="registration_duplicate",
            user=payload.username,
            details={"ip_address": ip_address} if ip_address else {},
            success=False,
            error_message="Username already exists",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    # Convert RegisterRequest to UserCreate
    user_create = UserCreate(
        username=payload.username,
        email=payload.email,
        password=payload.password,
        role=payload.role or "user"
    )
    user_record = user_service.create_user(user_create, db=db)
    
    # Log successful registration
    audit_logger.log_security_event(
        action="user_registered",
        user=payload.username,
        details={"ip_address": ip_address, "role": getattr(user_record, "role", None)} if ip_address else {"role": getattr(user_record, "role", None)},
        success=True,
        db=db
    )
    
    token = auth_service.create_access_token(user_record)
    user_public = user_service.serialize_user(user_record)
    return TokenResponse(access_token=token, user=user_public)


@router.get("/me", response_model=UserPublic)
async def read_current_user(current_user: UserPublic = Depends(deps.get_current_user)) -> UserPublic:
    return current_user


@router.post("/change-password")
@limiter.limit(get_limit("auth_password_change"))  # ✅ Security Fix #5
async def change_password(
    payload: dict,
    request: Request,
    response: Response,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(get_db)
) -> dict[str, str]:
    """Change user password."""
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None
    
    current_password = payload.get("current_password")
    new_password = payload.get("new_password")
    
    if not current_password or not new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing passwords")
    
    # Verify current password
    user_record = auth_service.authenticate_user(current_user.username, current_password, db=db)
    if not user_record:
        audit_logger.log_security_event(
            action="password_change_failed",
            user=current_user.username,
            error_message="Invalid current password",
            ip_address=ip_address,
            db=db
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid current password")
    
    # Update password
    user_service.update_user_password(current_user.id, new_password, db=db)
    
    # Log successful password change
    audit_logger.log_security_event(
        action="password_changed",
        user=current_user.username,
        success=True,
        ip_address=ip_address,
        db=db
    )
    
    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout() -> dict[str, str]:
    return {"message": "Logged out"}


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(get_limit("auth_refresh"))  # ✅ Security Fix #5
async def refresh_token(
    payload: dict,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
) -> TokenResponse:
    """
    Refresh access token using a refresh token (for mobile clients).

    Mobile clients receive a long-lived refresh token (30 days) during registration.
    This endpoint allows them to obtain new access tokens without re-authentication.

    ✅ Security Fix #6: Now checks if refresh token has been revoked.
    """
    from app.services.token_service import token_service

    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    refresh_token_str = payload.get("refresh_token")
    if not refresh_token_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing refresh_token"
        )

    # Verify refresh token
    try:
        token_data = auth_service.decode_token(refresh_token_str)
        user_id = token_data.sub  # TokenPayload is a Pydantic model, use attribute access

        # ✅ Security Fix #6: Check if token has been revoked
        jti = getattr(token_data, 'jti', None)
        if jti and token_service.is_token_revoked(db, jti):
            audit_logger.log_security_event(
                action="refresh_token_revoked",
                user=f"user_id:{user_id}",
                error_message="Refresh token has been revoked",
                ip_address=ip_address,
                db=db
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked"
            )

        # Get user from database
        user_record = user_service.get_user(int(user_id), db=db)
        if not user_record:
            audit_logger.log_security_event(
                action="refresh_token_invalid_user",
                user=f"user_id:{user_id}",
                error_message="User not found",
                ip_address=ip_address,
                db=db
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Check if user is active
        if not getattr(user_record, "is_active", True):
            audit_logger.log_security_event(
                action="refresh_token_inactive_user",
                user=getattr(user_record, "username", None),
                error_message="User account is inactive",
                ip_address=ip_address,
                db=db
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive"
            )

        # ✅ Security Fix #6: Update token usage timestamp
        if jti:
            token_service.update_token_usage(db, jti, ip_address=ip_address)

        # Generate new access token
        new_access_token = auth_service.create_access_token(user_record)

        # Log successful token refresh
        audit_logger.log_security_event(
            action="token_refreshed",
            user=getattr(user_record, "username", None),
            success=True,
            ip_address=ip_address,
            db=db
        )

        user_public = user_service.serialize_user(user_record)
        return TokenResponse(access_token=new_access_token, user=user_public)

    except HTTPException:
        raise
    except Exception as e:
        audit_logger.log_security_event(
            action="refresh_token_failed",
            user="unknown",
            error_message=str(e),
            ip_address=ip_address,
            db=db
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
