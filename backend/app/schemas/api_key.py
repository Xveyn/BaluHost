"""Pydantic schemas for API Key management."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class ApiKeyCreate(BaseModel):
    """Request schema for creating an API key."""
    name: str
    target_user_id: int
    expires_in_days: Optional[int] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Name must not be empty")
        if len(v) > 100:
            raise ValueError("Name must be at most 100 characters")
        return v

    @field_validator("expires_in_days")
    @classmethod
    def validate_expiry(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (v < 1 or v > 365):
            raise ValueError("Expiration must be between 1 and 365 days")
        return v


class ApiKeyCreated(BaseModel):
    """Response after creating an API key - contains the raw key (shown only once)."""
    id: int
    name: str
    key: str  # Full raw key - only returned once!
    key_prefix: str
    target_user_id: int
    target_username: str
    created_by_username: str
    expires_at: Optional[str] = None
    created_at: str


class ApiKeyPublic(BaseModel):
    """Public view of an API key (no raw key)."""
    id: int
    name: str
    key_prefix: str
    created_by_user_id: int
    created_by_username: str
    target_user_id: int
    target_username: str
    is_active: bool
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    last_used_ip: Optional[str] = None
    use_count: int
    created_at: str
    revoked_at: Optional[str] = None
    revocation_reason: Optional[str] = None

    @property
    def status(self) -> str:
        if not self.is_active:
            return "revoked"
        if self.expires_at:
            from datetime import datetime, timezone
            try:
                exp = datetime.fromisoformat(self.expires_at)
                if exp <= datetime.now(timezone.utc):
                    return "expired"
            except (ValueError, TypeError):
                pass
        return "active"


class ApiKeyListResponse(BaseModel):
    """Response for listing API keys."""
    keys: list[ApiKeyPublic]
    total: int


class EligibleUser(BaseModel):
    """A user eligible as API key target."""
    id: int
    username: str
    role: str
