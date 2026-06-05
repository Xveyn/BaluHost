"""Schemas for game library storage usage."""
from typing import List, Optional

from pydantic import BaseModel


class GameEntry(BaseModel):
    """A single installed game/app within a library."""
    app_id: str
    name: str
    size_bytes: int


class GameLibrary(BaseModel):
    """One game library (a directory holding installed games)."""
    provider: str          # e.g. "steam"
    provider_name: str     # e.g. "Steam"
    path: str              # absolute library path on disk
    device_id: Optional[int] = None  # os.stat().st_dev, for mountpoint matching
    total_bytes: int
    game_count: int
    games: List[GameEntry]  # sorted by size_bytes descending


class GameLibrariesResponse(BaseModel):
    """All discovered game libraries across providers."""
    libraries: List[GameLibrary]
    total_bytes: int        # sum across all libraries
    available: bool         # True if at least one provider is available
