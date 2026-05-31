"""Schemas for the desktop (display-manager) toggle feature."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DesktopState(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class DesktopStatus(BaseModel):
    """Current state of the desktop display manager."""

    state: DesktopState
    display_manager: str = Field(description="Name of the display-manager unit, e.g. 'sddm'")
    detail: Optional[str] = Field(default=None, description="Optional human-readable detail")
