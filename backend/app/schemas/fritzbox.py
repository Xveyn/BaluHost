"""Pydantic schemas for Fritz!Box integration API."""
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.validators import validate_mac_address


class FritzBoxConfigResponse(BaseModel):
    """Fritz!Box configuration (read — never exposes password)."""
    host: str
    port: int
    username: str
    nas_mac_address: Optional[str]
    enabled: bool
    has_password: bool = Field(description="True if password is set")


class FritzBoxConfigUpdate(BaseModel):
    """Partial update for Fritz!Box configuration."""
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = Field(default=None, description="Plain text in, encrypted at storage")
    nas_mac_address: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("nas_mac_address", mode="before")
    @classmethod
    def _validate_mac(cls, v: Optional[str]) -> Optional[str]:
        return validate_mac_address(v)


class FritzBoxTestResponse(BaseModel):
    """Result of Fritz!Box connection test."""
    success: bool
    message: str


class FritzBoxWolResponse(BaseModel):
    """Result of Fritz!Box WoL send."""
    success: bool
    message: str
