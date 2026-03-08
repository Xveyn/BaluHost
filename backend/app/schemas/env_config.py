"""Pydantic schemas for environment configuration management."""

import re
from typing import Optional
from pydantic import BaseModel, field_validator


class EnvVarResponse(BaseModel):
    """Single environment variable (sensitive values masked)."""
    key: str
    value: str
    is_sensitive: bool
    category: str
    description_key: str
    input_type: str  # text | number | boolean | secret
    default: Optional[str] = None
    file: str  # backend | client


class EnvConfigReadResponse(BaseModel):
    """Full env config read response."""
    backend: list[EnvVarResponse]
    client: list[EnvVarResponse]
    categories: list[str]


class EnvVarUpdate(BaseModel):
    """Single variable update."""
    key: str
    value: str

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        if not re.match(r"^[A-Z][A-Z0-9_]*$", v):
            raise ValueError("Key must be uppercase letters, digits, and underscores")
        return v


class EnvConfigUpdateRequest(BaseModel):
    """Update request for one or more variables in a specific file."""
    file: str  # "backend" | "client"
    updates: list[EnvVarUpdate]

    @field_validator("file")
    @classmethod
    def validate_file(cls, v: str) -> str:
        if v not in ("backend", "client"):
            raise ValueError("file must be 'backend' or 'client'")
        return v


class EnvVarRevealResponse(BaseModel):
    """Response for revealing a single sensitive value."""
    key: str
    value: str
