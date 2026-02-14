"""Pydantic models for Samba (SMB/CIFS) API."""

from typing import Optional

from pydantic import BaseModel

from app.schemas.webdav import OsConnectionInfo


class SambaConnection(BaseModel):
    """A single active SMB connection."""
    pid: str
    username: str
    machine: str


class SambaStatusResponse(BaseModel):
    """Samba server status (admin only)."""
    is_running: bool
    version: Optional[str] = None
    active_connections: list[SambaConnection] = []
    smb_users_count: int = 0


class SambaUserStatus(BaseModel):
    """SMB status for a single user."""
    user_id: int
    username: str
    role: str
    smb_enabled: bool
    is_active: bool


class SambaUsersResponse(BaseModel):
    """List of users with their SMB status."""
    users: list[SambaUserStatus]


class SambaUserToggleRequest(BaseModel):
    """Request to toggle SMB access for a user."""
    enabled: bool
    password: Optional[str] = None


class SambaConnectionInfo(BaseModel):
    """SMB connection info with per-OS mount instructions."""
    is_running: bool
    share_name: str
    smb_path: str
    username: str
    instructions: list[OsConnectionInfo]
