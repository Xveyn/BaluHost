"""Pydantic schemas for the setup wizard API."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.auth import _validate_password_strength


class SetupStatusResponse(BaseModel):
    """Response for GET /api/setup/status."""
    setup_required: bool
    completed_steps: list[str] = []


class SetupAdminRequest(BaseModel):
    """Request for POST /api/setup/admin — create initial admin account."""
    username: str
    password: str
    email: Optional[EmailStr] = None
    setup_secret: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")
        if len(v) > 32:
            raise ValueError("Username must be less than 32 characters")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores")
        return v


class SetupAdminResponse(BaseModel):
    """Response for POST /api/setup/admin."""
    success: bool
    setup_token: str
    user_id: int
    username: str


class SetupUserRequest(BaseModel):
    """Request for POST /api/setup/users — create a regular user."""
    username: str
    password: str
    email: Optional[EmailStr] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters long")
        if len(v) > 32:
            raise ValueError("Username must be less than 32 characters")
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores")
        return v


class SetupUserResponse(BaseModel):
    """Response for POST /api/setup/users."""
    success: bool
    user_id: int
    username: str
    email: Optional[str] = None


class SambaConfig(BaseModel):
    """Samba configuration for setup."""
    enabled: bool
    workgroup: str = "WORKGROUP"
    public_browsing: bool = False


class WebdavConfig(BaseModel):
    """WebDAV configuration for setup."""
    enabled: bool
    port: int = 8443
    ssl: bool = False


class SetupFileAccessRequest(BaseModel):
    """Request for POST /api/setup/file-access."""
    samba: Optional[SambaConfig] = None
    webdav: Optional[WebdavConfig] = None


class SetupFileAccessResponse(BaseModel):
    """Response for POST /api/setup/file-access."""
    success: bool
    active_services: list[str]


class SetupCompleteResponse(BaseModel):
    """Response for POST /api/setup/complete."""
    success: bool
    message: str
