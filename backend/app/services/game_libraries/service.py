"""Aggregate game library storage usage across providers."""
import logging
from typing import List

from app.core.config import settings
from app.schemas.games import GameEntry, GameLibrary, GameLibrariesResponse
from app.services.game_libraries.provider import GameLibraryProvider
from app.services.game_libraries.steam import SteamProvider

logger = logging.getLogger(__name__)

# Registry — add a launcher here to surface it. Order = display order.
PROVIDERS: List[GameLibraryProvider] = [SteamProvider()]


def _dev_mock() -> GameLibrariesResponse:
    """A small fake library so the dev UI (Windows, no Steam) renders."""
    games = [
        GameEntry(app_id="1091500", name="Cyberpunk 2077", size_bytes=117_000_000_000),
        GameEntry(app_id="570", name="Dota 2", size_bytes=42_000_000_000),
        GameEntry(app_id="730", name="Counter-Strike 2", size_bytes=35_000_000_000),
    ]
    lib = GameLibrary(
        provider="steam", provider_name="Steam",
        path="/mnt/cache-vcl/SteamLibrary", device_id=None,
        total_bytes=sum(g.size_bytes for g in games),
        game_count=len(games), games=games,
    )
    return GameLibrariesResponse(libraries=[lib], total_bytes=lib.total_bytes, available=True)


def get_game_libraries() -> GameLibrariesResponse:
    """Discover and aggregate game libraries across all registered providers."""
    libraries: List[GameLibrary] = []
    available = False
    for provider in PROVIDERS:
        try:
            if not provider.is_available():
                continue
            available = True
            libraries.extend(provider.get_libraries())
        except Exception:
            logger.debug("Game provider %s failed", getattr(provider, "id", "?"), exc_info=True)

    if not libraries and not available and settings.is_dev_mode:
        return _dev_mock()

    total = sum(lib.total_bytes for lib in libraries)
    return GameLibrariesResponse(libraries=libraries, total_bytes=total, available=available)
