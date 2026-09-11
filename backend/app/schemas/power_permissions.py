"""Pydantic schemas for user power permissions."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserPowerPermissionsResponse(BaseModel):
    """Response schema for power permissions."""

    user_id: int
    can_soft_sleep: bool = False
    can_wake: bool = False
    can_suspend: bool = False
    can_wol: bool = False
    can_toggle_desktop: bool = False
    can_unlock_session: bool = False
    can_control_audio: bool = False
    can_manage_displays: bool = False
    can_manage_bluetooth: bool = False
    granted_by: Optional[int] = None
    granted_by_username: Optional[str] = None
    granted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserPowerPermissionsUpdate(BaseModel):
    """Request schema for updating power permissions."""

    can_soft_sleep: Optional[bool] = Field(default=None, description="Allow entering soft sleep")
    can_wake: Optional[bool] = Field(default=None, description="Allow waking from soft sleep")
    can_suspend: Optional[bool] = Field(default=None, description="Allow system suspend")
    can_wol: Optional[bool] = Field(default=None, description="Allow sending Wake-on-LAN")
    can_toggle_desktop: Optional[bool] = Field(default=None, description="Allow toggling the desktop (DPMS on/off)")
    can_unlock_session: Optional[bool] = Field(default=None, description="Allow unlocking the desktop session from the web app")
    can_control_audio: Optional[bool] = Field(default=None, description="Allow controlling desktop audio (volume, output device, per-app mixer)")
    can_manage_displays: Optional[bool] = Field(default=None, description="Allow choosing display outputs and video modes")
    can_manage_bluetooth: Optional[bool] = Field(default=None, description="Allow connecting, removing and pairing Bluetooth devices")


class MyPowerPermissionsResponse(BaseModel):
    """Response for the user's own power permissions (used by mobile app)."""

    can_soft_sleep: bool = False
    can_wake: bool = False
    can_suspend: bool = False
    can_wol: bool = False
    can_toggle_desktop: bool = False
    can_unlock_session: bool = False
    can_control_audio: bool = False
    can_manage_displays: bool = False
    can_manage_bluetooth: bool = False
