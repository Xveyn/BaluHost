from datetime import datetime
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserPublic
from app.schemas.validators import validate_username


class LoginRequest(BaseModel):
    username: str
    password: str


def _validate_password_strength(v: str) -> str:
    """
    Shared password strength validation.

    Requirements:
    - At least 8 characters
    - At most 128 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - No common passwords
    """
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters long")

    if len(v) > 128:
        raise ValueError("Password must be less than 128 characters")

    if not re.search(r"[A-Z]", v):
        raise ValueError("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", v):
        raise ValueError("Password must contain at least one lowercase letter")

    if not re.search(r"\d", v):
        raise ValueError("Password must contain at least one number")

    # Common password blacklist
    common_passwords = [
        "password", "password123", "Password123",
        "admin", "admin123", "Admin123",
        "12345678", "qwerty", "letmein",
        "welcome", "changeme"
    ]

    if v.lower() in [p.lower() for p in common_passwords]:
        raise ValueError("Password is too common. Please choose a stronger password")

    return v


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """✅ Security Fix #4: Enforce password policy."""
        return _validate_password_strength(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """✅ Security Fix #4: Validate username format and length."""
        return validate_username(v)


class TokenPayload(BaseModel):
    sub: str
    username: str
    role: str
    exp: datetime
    jti: str | None = None  # ✅ Security Fix #6: JWT ID for refresh token revocation


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        """Enforce password policy on new password."""
        return _validate_password_strength(v)


class RecoveryCodesGenerateRequest(BaseModel):
    code: str | None = None              # fresh TOTP/backup code (when 2FA enabled)
    current_password: str | None = None  # password re-entry (when 2FA disabled)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class RecoveryCodesStatusResponse(BaseModel):
    configured: bool
    remaining: int


class RecoveryResetRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    recovery_code: str = Field(min_length=1, max_length=32)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# --- 2FA Schemas ---

class TwoFactorRequiredResponse(BaseModel):
    requires_2fa: bool = True
    pending_token: str
    token_type: str = "2fa_pending"


class TwoFactorVerifyRequest(BaseModel):
    pending_token: str
    code: str


class TwoFactorSetupResponse(BaseModel):
    qr_code: str
    provisioning_uri: str
    secret: str


class TwoFactorVerifySetupRequest(BaseModel):
    secret: str
    code: str


class TwoFactorDisableRequest(BaseModel):
    password: str
    code: str


class TwoFactorBackupCodesResponse(BaseModel):
    backup_codes: list[str]


class TwoFactorStatusResponse(BaseModel):
    enabled: bool
    enabled_at: datetime | None = None
    backup_codes_remaining: int = 0


# --- PIN login schemas ---

def _validate_pin(v: str) -> str:
    """PIN policy: 4–8 digits, no all-same, no strictly sequential pattern."""
    if not re.fullmatch(r"\d{4,8}", v):
        raise ValueError("PIN must be 4 to 8 digits")
    if len(set(v)) == 1:
        raise ValueError("PIN must not be all the same digit")
    digits = [int(c) for c in v]
    ascending = all(digits[i + 1] - digits[i] == 1 for i in range(len(digits) - 1))
    descending = all(digits[i] - digits[i + 1] == 1 for i in range(len(digits) - 1))
    if ascending or descending:
        raise ValueError("PIN must not be a sequential pattern")
    return v


class PinLoginRequest(BaseModel):
    username: str
    pin: str


class PinSetRequest(BaseModel):
    pin: str
    code: str  # fresh TOTP or backup code

    @field_validator("pin")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_pin(v)


class PinRemoveRequest(BaseModel):
    code: str  # fresh TOTP or backup code


class PinStatusResponse(BaseModel):
    pin_enabled: bool
