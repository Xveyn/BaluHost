"""Schemas for rate limit configuration."""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

_ALLOWED_TIME_UNITS = ('second', 'minute', 'hour', 'day')


def _validate_limit_string(v: str) -> str:
    """Validate that a rate-limit string is in 'number/unit' format."""
    if '/' not in v:
        raise ValueError("limit_string must be in format 'number/unit' (e.g., '5/minute')")

    parts = v.split('/')
    if len(parts) != 2:
        raise ValueError("limit_string must have exactly one '/' separator")

    count, unit = parts

    try:
        count_int = int(count)
        if count_int <= 0:
            raise ValueError("Rate limit count must be positive")
    except ValueError:
        raise ValueError("Rate limit count must be a valid positive integer")

    if unit not in _ALLOWED_TIME_UNITS:
        raise ValueError(f"Time unit must be one of: {', '.join(_ALLOWED_TIME_UNITS)}")

    return v


class RateLimitConfigBase(BaseModel):
    endpoint_type: str = Field(..., description="Type of endpoint (e.g., auth_login, file_upload)")
    limit_string: str = Field(..., description="Rate limit string (e.g., '5/minute', '100/hour')")
    description: Optional[str] = Field(None, description="Human-readable description")
    enabled: bool = Field(True, description="Whether this rate limit is active")

    @field_validator('limit_string')
    @classmethod
    def validate_limit_string(cls, v: str) -> str:
        return _validate_limit_string(v)


class RateLimitConfigCreate(RateLimitConfigBase):
    """Schema for creating a new rate limit configuration."""
    pass


class RateLimitConfigUpdate(BaseModel):
    """Schema for updating an existing rate limit configuration."""
    limit_string: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator('limit_string')
    @classmethod
    def validate_limit_string(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_limit_string(v)


class RateLimitConfigResponse(RateLimitConfigBase):
    """Schema for rate limit configuration response."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    updated_by: Optional[int] = None
    
    class Config:
        from_attributes = True


class RateLimitConfigList(BaseModel):
    """Schema for list of rate limit configurations."""
    configs: list[RateLimitConfigResponse]
    total: int
