"""Pydantic models for WebDAV API responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class WebdavStatusResponse(BaseModel):
    """Detailed WebDAV server status (admin only)."""
    is_running: bool
    port: int
    ssl_enabled: bool
    started_at: Optional[datetime] = None
    worker_pid: Optional[int] = None
    last_heartbeat: Optional[datetime] = None
    error_message: Optional[str] = None
    connection_url: Optional[str] = None


class OsConnectionInfo(BaseModel):
    """Mount instructions for a specific OS."""
    os: str
    label: str
    command: str
    notes: Optional[str] = None


class WebdavConnectionInfo(BaseModel):
    """OS-specific mount instructions with personalised username."""
    is_running: bool
    port: int
    ssl_enabled: bool
    username: str
    connection_url: str
    instructions: list[OsConnectionInfo]
