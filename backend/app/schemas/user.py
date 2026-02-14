from pydantic import BaseModel, EmailStr, field_validator
import re


class UserBase(BaseModel):
    username: str
    email: EmailStr | None = None


class UserCreate(UserBase):
    password: str
    role: str | None = "user"

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """✅ Security Fix #4: Enforce password policy."""
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
        """✅ Security Fix #4: Validate username format."""
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")
        if len(v) > 32:
            raise ValueError("Username must be less than 32 characters")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores")
        return v


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserPublic(UserBase):
    id: int
    role: str
    is_active: bool
    smb_enabled: bool = False
    created_at: str
    updated_at: str | None = None
    # email is already inherited as EmailStr | None from UserBase


class UsersResponse(BaseModel):
    users: list[UserPublic]
    total: int
    active: int
    inactive: int
    admins: int
