"""Pydantic schemas for the Desktop Device Code Flow."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class DeviceCodeRequest(BaseModel):
    """Request from BaluDesk to initiate pairing."""

    device_id: str = Field(..., min_length=1, max_length=255)
    device_name: str = Field(..., min_length=1, max_length=255)
    platform: str = Field(..., pattern=r"^(windows|mac|linux)$")


class DeviceCodeResponse(BaseModel):
    """Response with codes for BaluDesk to display / poll."""

    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


class DeviceCodePollRequest(BaseModel):
    """BaluDesk polls with the device_code."""

    device_code: str = Field(..., min_length=1, max_length=64)


class DeviceCodePollResponse(BaseModel):
    """Poll result — status + optional tokens on approval."""

    status: str  # "authorization_pending" | "approved" | "expired" | "denied"
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None
    user: Optional[dict] = None


class ApproveDeviceCodeRequest(BaseModel):
    """Web-UI submits the 6-digit code."""

    user_code: str = Field(..., pattern=r"^\d{6}$")

    @field_validator("user_code")
    @classmethod
    def validate_user_code(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("user_code must be exactly 6 digits")
        return v


class DeviceCodeApprovalInfo(BaseModel):
    """Device details shown to the user before approval."""

    device_name: str
    device_id: str
    platform: str
    created_at: datetime
    expires_at: datetime
