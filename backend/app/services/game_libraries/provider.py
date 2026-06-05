"""Provider interface for game library discovery.

Each launcher (Steam, Epic/Heroic, Lutris, ...) implements GameLibraryProvider.
Adding a launcher means adding a class to PROVIDERS in ``service.py`` — no other
code changes.
"""
from typing import List, Protocol, runtime_checkable

from app.schemas.games import GameLibrary


@runtime_checkable
class GameLibraryProvider(Protocol):
    id: str    # short stable id, e.g. "steam"
    name: str  # display name, e.g. "Steam"

    def is_available(self) -> bool:
        """True if this launcher is installed/discoverable for the service user."""
        ...

    def get_libraries(self) -> List[GameLibrary]:
        """Return all libraries this provider can see, with per-game sizes."""
        ...
