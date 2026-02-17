from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import limiter, user_limiter, get_limit
from app.core import security
from app.schemas.auth import (
    LoginRequest, RegisterRequest, TokenResponse,
    TwoFactorRequiredResponse, TwoFactorVerifyRequest,
    TwoFactorSetupResponse, TwoFactorVerifySetupRequest,
    TwoFactorDisableRequest, TwoFactorBackupCodesResponse,
    TwoFactorStatusResponse,
)
from app.schemas.user import UserPublic, UserCreate
from app.services import auth as auth_service
from app.services import users as user_service
from app.services import totp_service
from app.models.user import User as UserModel
from app.services.audit_logger_db import get_audit_logger_db
from app.plugins.emit import emit_hook

router = APIRouter()


@router.post("/login")
@limiter.limit(get_limit("auth_login"))
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
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

    # Check if 2FA is enabled
    if user_record.totp_enabled:
        pending_token = security.create_2fa_pending_token(user_record.id)
        audit_logger.log_security_event(
            action="2fa_pending",
            user=payload.username,
            details={"ip_address": ip_address},
            success=True,
            db=db
        )
        return TwoFactorRequiredResponse(pending_token=pending_token)

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

    # Emit plugin hook for successful login
    emit_hook(
        "on_user_login",
        user_id=user_record.id,
        username=user_record.username,
        ip=ip_address or "",
        user_agent=user_agent,
    )

    return TokenResponse(access_token=token, user=user_public)


@router.post("/verify-2fa", response_model=TokenResponse)
@limiter.limit(get_limit("auth_2fa_verify"))
async def verify_2fa(payload: TwoFactorVerifyRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Verify 2FA code after password authentication."""
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Decode the pending token
    try:
        token_data = security.decode_token(payload.pending_token, token_type="2fa_pending")
        user_id = int(token_data["sub"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired 2FA token")

    user_record = db.query(UserModel).filter(UserModel.id == user_id).first()
    if not user_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Try TOTP code first, then backup code
    code_valid = False
    backup_used = False
    try:
        code_valid = totp_service.verify_code(db, user_id, payload.code)
    except ValueError:
        pass

    if not code_valid:
        # Try as backup code
        try:
            code_valid = totp_service.verify_backup_code(db, user_id, payload.code)
            backup_used = True
        except ValueError:
            pass

    if not code_valid:
        audit_logger.log_security_event(
            action="2fa_failed",
            user=user_record.username,
            details={"ip_address": ip_address},
            success=False,
            error_message="Invalid 2FA code",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")

    # Log successful 2FA verification
    action = "2fa_backup_used" if backup_used else "2fa_verified"
    audit_logger.log_authentication_attempt(
        username=user_record.username,
        success=True,
        ip_address=ip_address,
        user_agent=user_agent,
        db=db
    )
    audit_logger.log_security_event(
        action=action,
        user=user_record.username,
        details={"ip_address": ip_address},
        success=True,
        db=db
    )

    token = auth_service.create_access_token(user_record)
    user_public = user_service.serialize_user(user_record)

    emit_hook(
        "on_user_login",
        user_id=user_record.id,
        username=user_record.username,
        ip=ip_address or "",
        user_agent=user_agent,
    )

    return TokenResponse(access_token=token, user=user_public)


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
@limiter.limit(get_limit("auth_2fa_setup"))
async def setup_2fa(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Generate TOTP secret and QR code for 2FA setup (admin only)."""
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    # Check if already enabled
    user_record = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    if user_record and user_record.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled. Disable it first to reconfigure.",
        )

    setup_data = totp_service.generate_setup(user_record)

    audit_logger.log_security_event(
        action="2fa_setup_initiated",
        user=current_user.username,
        details={"ip_address": ip_address},
        success=True,
        db=db
    )

    return TwoFactorSetupResponse(**setup_data)


@router.post("/2fa/verify-setup", response_model=TwoFactorBackupCodesResponse)
@limiter.limit(get_limit("auth_2fa_setup"))
async def verify_setup_2fa(
    payload: TwoFactorVerifySetupRequest,
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Verify TOTP code to complete 2FA setup, returns backup codes (admin only)."""
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    try:
        backup_codes = totp_service.verify_and_enable(db, current_user.id, payload.secret, payload.code)
    except ValueError as e:
        audit_logger.log_security_event(
            action="2fa_setup_failed",
            user=current_user.username,
            details={"ip_address": ip_address},
            success=False,
            error_message=str(e),
            db=db
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    audit_logger.log_security_event(
        action="2fa_enabled",
        user=current_user.username,
        details={"ip_address": ip_address},
        success=True,
        db=db
    )

    return TwoFactorBackupCodesResponse(backup_codes=backup_codes)


@router.post("/2fa/disable")
@limiter.limit(get_limit("auth_2fa_setup"))
async def disable_2fa(
    payload: TwoFactorDisableRequest,
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Disable 2FA (requires password + TOTP code, admin only)."""
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    # Verify password
    user_record = auth_service.authenticate_user(current_user.username, payload.password, db=db)
    if not user_record:
        audit_logger.log_security_event(
            action="2fa_disable_failed",
            user=current_user.username,
            details={"ip_address": ip_address},
            success=False,
            error_message="Invalid password",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")

    # Verify TOTP code (or backup code)
    code_valid = False
    try:
        code_valid = totp_service.verify_code(db, current_user.id, payload.code)
    except ValueError:
        pass
    if not code_valid:
        try:
            code_valid = totp_service.verify_backup_code(db, current_user.id, payload.code)
        except ValueError:
            pass

    if not code_valid:
        audit_logger.log_security_event(
            action="2fa_disable_failed",
            user=current_user.username,
            details={"ip_address": ip_address},
            success=False,
            error_message="Invalid 2FA code",
            db=db
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")

    totp_service.disable(db, current_user.id)

    audit_logger.log_security_event(
        action="2fa_disabled",
        user=current_user.username,
        details={"ip_address": ip_address},
        success=True,
        db=db
    )

    return {"message": "2FA disabled successfully"}


@router.get("/2fa/status", response_model=TwoFactorStatusResponse)
@user_limiter.limit(get_limit("user_operations"))
async def get_2fa_status(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Get 2FA status for the current user."""
    user_record = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    if not user_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    backup_remaining = 0
    if user_record.totp_enabled:
        backup_remaining = totp_service.get_backup_codes_remaining(db, current_user.id)

    return TwoFactorStatusResponse(
        enabled=user_record.totp_enabled,
        enabled_at=user_record.totp_enabled_at,
        backup_codes_remaining=backup_remaining,
    )


@router.post("/2fa/backup-codes", response_model=TwoFactorBackupCodesResponse)
@limiter.limit(get_limit("auth_2fa_setup"))
async def regenerate_backup_codes(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Regenerate backup codes (invalidates old ones, admin only)."""
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    try:
        backup_codes = totp_service.regenerate_backup_codes(db, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    audit_logger.log_security_event(
        action="2fa_backup_regenerated",
        user=current_user.username,
        details={"ip_address": ip_address},
        success=True,
        db=db
    )

    return TwoFactorBackupCodesResponse(backup_codes=backup_codes)


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

    # Emit plugin hook for user registration
    emit_hook(
        "on_user_created",
        user_id=user_record.id,
        username=user_record.username,
        role=getattr(user_record, "role", "user"),
    )

    return TokenResponse(access_token=token, user=user_public)


@router.get("/me", response_model=UserPublic)
@user_limiter.limit(get_limit("user_operations"))
async def read_current_user(request: Request, response: Response, current_user: UserPublic = Depends(deps.get_current_user)) -> UserPublic:
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

    # Sync Samba password if SMB is enabled for this user
    user_record = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    if user_record and user_record.smb_enabled:
        from app.services import samba_service
        await samba_service.sync_smb_password(current_user.username, new_password)

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
@limiter.limit(get_limit("user_operations"))
async def logout(request: Request, response: Response) -> dict[str, str]:
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
