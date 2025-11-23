from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserPublic
from app.services import auth as auth_service
from app.services import users as user_service
from app.services.audit_logger_db import get_audit_logger_db

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
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


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
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

    user_record = user_service.create_user(payload, db=db)
    
    # Log successful registration
    audit_logger.log_security_event(
        action="user_registered",
        user=payload.username,
        details={"ip_address": ip_address, "role": user_record.get("role")} if ip_address else {"role": user_record.get("role")},
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
async def change_password(
    payload: dict,
    request: Request,
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
