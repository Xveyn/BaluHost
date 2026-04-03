"""Pydantic schemas for user notification routing."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationRoutingResponse(BaseModel):
    """Response schema for notification routing (admin view)."""

    user_id: int
    receive_raid: bool = False
    receive_smart: bool = False
    receive_backup: bool = False
    receive_scheduler: bool = False
    receive_system: bool = False
    receive_security: bool = False
    receive_sync: bool = False
    receive_vpn: bool = False
    granted_by: Optional[int] = None
    granted_by_username: Optional[str] = None
    granted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationRoutingUpdate(BaseModel):
    """Request schema for updating notification routing."""

    receive_raid: Optional[bool] = Field(default=None, description="Receive RAID notifications")
    receive_smart: Optional[bool] = Field(default=None, description="Receive SMART notifications")
    receive_backup: Optional[bool] = Field(default=None, description="Receive Backup notifications")
    receive_scheduler: Optional[bool] = Field(default=None, description="Receive Scheduler notifications")
    receive_system: Optional[bool] = Field(default=None, description="Receive System notifications")
    receive_security: Optional[bool] = Field(default=None, description="Receive Security notifications")
    receive_sync: Optional[bool] = Field(default=None, description="Receive Sync notifications")
    receive_vpn: Optional[bool] = Field(default=None, description="Receive VPN notifications")


class MyNotificationRoutingResponse(BaseModel):
    """Response for the user's own routing (read-only, no admin metadata)."""

    receive_raid: bool = False
    receive_smart: bool = False
    receive_backup: bool = False
    receive_scheduler: bool = False
    receive_system: bool = False
    receive_security: bool = False
    receive_sync: bool = False
    receive_vpn: bool = False
