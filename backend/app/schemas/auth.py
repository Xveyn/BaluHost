from datetime import datetime
import re

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.user import UserPublic


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str | None = "user"  # Default role for new registrations

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """
        ✅ Security Fix #4: Enforce password policy.

        Requirements:
        - At least 8 characters
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

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """✅ Security Fix #4: Validate username format and length."""
        v = v.strip()  # Remove leading/trailing whitespace

        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")

        if len(v) > 32:
            raise ValueError("Username must be less than 32 characters")

        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Username can only contain letters, numbers, hyphens, and underscores"
            )

        return v


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
