"""Steam game library provider.

Discovers Steam libraries by parsing ``steamapps/libraryfolders.vdf`` and the
per-app ``appmanifest_<appid>.acf`` files. All sizes come from metadata — there
is no directory scanning.
"""
import logging
import os
from pathlib import Path
from typing import List, Optional

from app.schemas.games import GameEntry, GameLibrary
from app.services.game_libraries import vdf

logger = logging.getLogger(__name__)

# Standard Steam roots. "~" is expanded against the service user's home. The
# Windows entries are a convenience for local dev boxes.
_CANDIDATE_ROOTS = [
    "~/.steam/steam",
    "~/.steam/root",
    "~/.local/share/Steam",
    "~/.var/app/com.valvesoftware.Steam/data/Steam",   # Flatpak
    "~/snap/steam/common/.local/share/Steam",          # Snap
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
]

# Display-name prefixes/exact matches that identify Steam tools & runtimes,
# not real games. Compared case-insensitively against the .acf "name".
_TOOL_NAME_PREFIXES = ("proton", "steam linux runtime")
_TOOL_NAME_EXACT = ("steamworks common redistributables",)


def _is_tool_app(name: str) -> bool:
    """True if *name* is a Steam tool/runtime (Proton, Linux Runtime, redist)."""
    n = name.strip().lower()
    if n in _TOOL_NAME_EXACT:
        return True
    return any(n.startswith(prefix) for prefix in _TOOL_NAME_PREFIXES)


class SteamProvider:
    id = "steam"
    name = "Steam"

    def _find_steam_roots(self) -> List[Path]:
        """Existing roots whose ``steamapps/libraryfolders.vdf`` is readable.

        De-duplicated by the realpath of the vdf file so a symlinked root
        (``~/.steam/steam`` -> ``~/.local/share/Steam``) is only counted once.
        """
        seen: set[str] = set()
        roots: List[Path] = []
        for cand in _CANDIDATE_ROOTS:
            p = Path(os.path.expanduser(cand))
            vdf_file = p / "steamapps" / "libraryfolders.vdf"
            if not vdf_file.is_file():
                continue
            real = os.path.realpath(str(vdf_file))
            if real in seen:
                continue
            seen.add(real)
            roots.append(p)
        return roots

    def is_available(self) -> bool:
        return bool(self._find_steam_roots())

    def get_libraries(self) -> List[GameLibrary]:
        libraries: List[GameLibrary] = []
        seen_lib_paths: set[str] = set()
        for root in self._find_steam_roots():
            vdf_file = root / "steamapps" / "libraryfolders.vdf"
            try:
                data = vdf.parse(vdf_file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                logger.debug("Could not read %s", vdf_file, exc_info=True)
                continue
            folders = data.get("libraryfolders", {})
            if not isinstance(folders, dict):
                continue
            for entry in folders.values():
                if not isinstance(entry, dict):
                    continue
                lib_path = entry.get("path")
                apps = entry.get("apps")
                if not isinstance(lib_path, str) or not isinstance(apps, dict):
                    continue
                real_lib = os.path.realpath(lib_path)
                if real_lib in seen_lib_paths:
                    continue
                seen_lib_paths.add(real_lib)
                lib = self._build_library(lib_path, apps)
                if lib.game_count > 0:
                    libraries.append(lib)
        return libraries

    def _build_library(self, lib_path: str, apps: dict) -> GameLibrary:
        steamapps = Path(lib_path) / "steamapps"
        games: List[GameEntry] = []
        total = 0
        for app_id, size_str in apps.items():
            name = self._read_app_name(steamapps, str(app_id)) or f"App {app_id}"
            if _is_tool_app(name):
                continue
            try:
                size = int(size_str)
            except (TypeError, ValueError):
                size = 0
            games.append(GameEntry(app_id=str(app_id), name=name, size_bytes=size))
            total += size
        games.sort(key=lambda g: g.size_bytes, reverse=True)
        return GameLibrary(
            provider=self.id,
            provider_name=self.name,
            path=lib_path,
            device_id=self._device_id(lib_path),
            total_bytes=total,
            game_count=len(games),
            games=games,
        )

    @staticmethod
    def _read_app_name(steamapps: Path, app_id: str) -> Optional[str]:
        acf = steamapps / f"appmanifest_{app_id}.acf"
        try:
            data = vdf.parse(acf.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None
        state = data.get("AppState")
        if isinstance(state, dict):
            name = state.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return None

    @staticmethod
    def _device_id(path: str) -> Optional[int]:
        try:
            return os.stat(path).st_dev
        except OSError:
            return None
