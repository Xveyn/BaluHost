"""Installed, launchable Steam games - one manifest per game, nothing else.

Deliberately NOT built on services/game_libraries/service.get_game_libraries():
that one swallows provider failures (a spun-down mount would read as "nothing
installed" and turn a launch into a 404), takes app ids from
libraryfolders.vdf even when no manifest exists, and reads sizes nobody here
needs.

A game counts as installed when ``appmanifest_<id>.acf`` exists in one of the
steamapps directories, its name is readable, and it is not a Steam tool
(Proton, runtimes, redistributables). The id comes from the file name and is
checked like the id in a launch request, so nothing unvalidated ever reaches a
steam:// URL.

All of this is blocking filesystem I/O - call via asyncio.to_thread.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.game_libraries import vdf
from app.services.game_libraries.steam import find_steamapps_dirs, is_tool_app

# fullmatch, not \d (matches Unicode digits) and not $ (matches before "\n").
_APP_ID_RE = re.compile(r"[0-9]{1,10}")
_MANIFEST_RE = re.compile(r"appmanifest_([0-9]{1,10})\.acf")
_NAME_MAX = 200
_LIST_TTL_SECONDS = 30.0
_LIST_CACHE: dict[str, object] = {}


@dataclass(frozen=True)
class InstalledGame:
    app_id: str
    name: str


# The Windows dev box has no Steam library; same titles as the game_libraries mock.
DEV_GAMES: tuple[InstalledGame, ...] = (
    InstalledGame("1091500", "Cyberpunk 2077"),
    InstalledGame("570", "Dota 2"),
    InstalledGame("730", "Counter-Strike 2"),
)


class LibraryUnavailable(Exception):
    """No steamapps directory could be found at all."""


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def reset_cache() -> None:
    """Drop the list cache. Intended for tests."""
    _LIST_CACHE.clear()


def is_valid_app_id(app_id: str) -> bool:
    """True for 1-10 ASCII digits and nothing else."""
    return _APP_ID_RE.fullmatch(app_id) is not None


def _read_name(manifest: Path) -> Optional[str]:
    """The launchable display name in *manifest*, or None."""
    try:
        data = vdf.parse(manifest.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        # Missing or corrupt: not launchable, and no reason to break the rest.
        return None
    state = data.get("AppState")
    if not isinstance(state, dict):
        return None
    raw = state.get("name")
    if not isinstance(raw, str) or not raw.strip():
        return None
    name = raw.strip()
    if is_tool_app(name):
        return None
    return name[:_NAME_MAX]


def _scan(dirs: list[Path]) -> list[InstalledGame]:
    found: dict[str, InstalledGame] = {}
    for steamapps in dirs:
        try:
            manifests = sorted(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            match = _MANIFEST_RE.fullmatch(manifest.name)
            if match is None:
                continue
            app_id = match.group(1)
            if app_id in found:
                continue
            name = _read_name(manifest)
            if name is not None:
                found[app_id] = InstalledGame(app_id, name)
    return sorted(found.values(), key=lambda game: game.name.casefold())


def list_installed_games() -> list[InstalledGame]:
    """Every launchable game, sorted by name. Cached per worker for 30 s."""
    now = _monotonic()
    checked_at = _LIST_CACHE.get("checked_at")
    if isinstance(checked_at, float) and now - checked_at < _LIST_TTL_SECONDS:
        return list(_LIST_CACHE["games"])  # type: ignore[arg-type]

    dirs = find_steamapps_dirs()
    if not dirs:
        if not settings.is_dev_mode:
            raise LibraryUnavailable("no steamapps directory found")
        games = sorted(DEV_GAMES, key=lambda game: game.name.casefold())
    else:
        games = _scan(dirs)

    _LIST_CACHE["checked_at"] = now
    _LIST_CACHE["games"] = games
    return list(games)


def find_installed_game(app_id: str) -> Optional[InstalledGame]:
    """The launchable game with *app_id*, read fresh from its manifest, or None."""
    if not is_valid_app_id(app_id):
        return None
    dirs = find_steamapps_dirs()
    if not dirs:
        if not settings.is_dev_mode:
            raise LibraryUnavailable("no steamapps directory found")
        return next((game for game in DEV_GAMES if game.app_id == app_id), None)
    for steamapps in dirs:
        name = _read_name(steamapps / f"appmanifest_{app_id}.acf")
        if name is not None:
            return InstalledGame(app_id, name)
    return None
