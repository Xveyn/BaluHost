# Steam Game Library in Storage Usage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Game Libraries" card to Settings → Storage that auto-discovers Steam libraries and shows total size plus a per-game drill-down, built on an extensible provider interface.

**Architecture:** A new `game_libraries` backend service iterates registered `GameLibraryProvider`s. The first provider, `SteamProvider`, parses `libraryfolders.vdf` + `appmanifest_*.acf` (metadata only, no directory scan) and returns libraries with per-game sizes. A read-only endpoint `GET /api/games/libraries` (auth: any user) feeds a new React card rendered in `StorageTab.tsx`.

**Tech Stack:** Python/FastAPI, Pydantic v2, pytest. React 18 + TypeScript, Tailwind, lucide-react, i18next.

**Spec:** `docs/superpowers/specs/2026-06-05-steam-game-library-storage-design.md`

**Branch:** `feat/steam-game-library-storage` (already created)

**Conventions to follow:**
- Backend: services hold logic, routes are thin (`backend/app/services/CLAUDE.md`). Type hints + docstrings required.
- Tests run from `backend/`: `cd backend && python -m pytest ...`. Test env defaults to dev mode (`NAS_MODE=dev`).
- Frontend type check: `cd client && npx tsc --noEmit`.
- Repo uses `core.autocrlf=true` on Windows — git normalizes line endings; the `LF will be replaced by CRLF` warning on commit is expected and harmless.

---

## Task 1: VDF parser

Minimal parser for Valve's KeyValues format — just enough for `libraryfolders.vdf` and `appmanifest_*.acf`. stdlib only (no `vdf` PyPI package).

**Files:**
- Create: `backend/app/services/game_libraries/__init__.py`
- Create: `backend/app/services/game_libraries/vdf.py`
- Test: `backend/tests/game_libraries/test_vdf.py`

- [ ] **Step 1: Create the package init**

Create `backend/app/services/game_libraries/__init__.py` with a single docstring line:

```python
"""Game library discovery (Steam and future launchers) for storage usage."""
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/game_libraries/test_vdf.py`:

```python
"""Tests for the minimal VDF (Valve KeyValues) parser."""

from app.services.game_libraries import vdf

SAMPLE = '''
"libraryfolders"
{
    "0"
    {
        "path"          "/home/sven/.local/share/Steam"
        "apps"
        {
            "228980"        "462054788"
            "1070560"       "222208995"
        }
    }
    "1"
    {
        "path"          "/mnt/cache-vcl/SteamLibrary"
        "apps"
        {
            "400"           "4347052354"
        }
    }
}
'''


def test_parse_nested_libraryfolders():
    data = vdf.parse(SAMPLE)
    libs = data["libraryfolders"]
    assert libs["0"]["path"] == "/home/sven/.local/share/Steam"
    assert libs["0"]["apps"]["228980"] == "462054788"
    assert libs["1"]["path"] == "/mnt/cache-vcl/SteamLibrary"
    assert libs["1"]["apps"]["400"] == "4347052354"


def test_parse_appmanifest_shape():
    acf = '"AppState"\n{\n    "appid" "730"\n    "name" "Counter-Strike 2"\n    "SizeOnDisk" "35000000000"\n}'
    data = vdf.parse(acf)
    assert data["AppState"]["name"] == "Counter-Strike 2"
    assert data["AppState"]["SizeOnDisk"] == "35000000000"


def test_parse_empty_and_malformed():
    assert vdf.parse("") == {}
    # A key with no value (trailing) must not raise.
    assert isinstance(vdf.parse('"orphan"'), dict)


def test_parse_unescapes_backslashes():
    data = vdf.parse('"path" "C:\\\\Program Files (x86)\\\\Steam"')
    assert data["path"] == "C:\\Program Files (x86)\\Steam"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/game_libraries/test_vdf.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.game_libraries.vdf'`

- [ ] **Step 4: Implement the parser**

Create `backend/app/services/game_libraries/vdf.py`:

```python
"""Minimal parser for Valve's KeyValues (VDF) text format.

Supports only the subset Steam uses in ``libraryfolders.vdf`` and
``appmanifest_*.acf``: quoted keys/values and ``{}`` nested blocks. No macros,
no conditionals, no unquoted tokens. stdlib only — deliberately not the ``vdf``
PyPI package (repo rule: no new deps for small features).
"""
from __future__ import annotations

import re

# Matches a quoted string (group 1), an opening brace (group 2), or a closing
# brace (group 3). Backslash escapes inside quotes are tolerated.
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|(\{)|(\})')


def _unescape(s: str) -> str:
    return s.replace('\\\\', '\\').replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')


def parse(text: str) -> dict:
    """Parse VDF *text* into nested dicts. Leaf values are ``str``."""
    tokens: list[tuple[str, str]] = []
    for m in _TOKEN.finditer(text):
        if m.group(1) is not None:
            tokens.append(("str", _unescape(m.group(1))))
        elif m.group(2):
            tokens.append(("open", "{"))
        else:
            tokens.append(("close", "}"))

    root: dict = {}
    stack: list[dict] = [root]
    i, n = 0, len(tokens)
    while i < n:
        kind, val = tokens[i]
        if kind == "close":
            if len(stack) > 1:
                stack.pop()
            i += 1
            continue
        if kind == "open":
            # Anonymous block without a key — not expected in Steam files; skip.
            i += 1
            continue
        # kind == "str": this token is a key; the next token decides its value.
        key = val
        if i + 1 >= n:
            break  # dangling key, ignore
        nkind, nval = tokens[i + 1]
        if nkind == "open":
            child: dict = {}
            stack[-1][key] = child
            stack.append(child)
            i += 2
        elif nkind == "str":
            stack[-1][key] = nval
            i += 2
        else:  # "close" right after a key — malformed; store empty and let it close.
            stack[-1][key] = ""
            i += 1
    return root
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/game_libraries/test_vdf.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/game_libraries/__init__.py backend/app/services/game_libraries/vdf.py backend/tests/game_libraries/test_vdf.py
git commit -m "feat(games): minimal VDF parser for Steam metadata"
```

---

## Task 2: Schemas

Pydantic response shapes for the game-libraries API.

**Files:**
- Create: `backend/app/schemas/games.py`
- Test: `backend/tests/game_libraries/test_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/game_libraries/test_schemas.py`:

```python
"""Tests for game library schemas."""

from app.schemas.games import GameEntry, GameLibrary, GameLibrariesResponse


def test_schema_round_trip():
    lib = GameLibrary(
        provider="steam",
        provider_name="Steam",
        path="/mnt/cache-vcl/SteamLibrary",
        device_id=42,
        total_bytes=100,
        game_count=1,
        games=[GameEntry(app_id="730", name="CS2", size_bytes=100)],
    )
    resp = GameLibrariesResponse(libraries=[lib], total_bytes=100, available=True)
    dumped = resp.model_dump(mode="json")
    assert dumped["libraries"][0]["games"][0]["name"] == "CS2"
    assert dumped["available"] is True


def test_device_id_optional():
    lib = GameLibrary(
        provider="steam", provider_name="Steam", path="/x",
        total_bytes=0, game_count=0, games=[],
    )
    assert lib.device_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/game_libraries/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.games'`

- [ ] **Step 3: Implement the schemas**

Create `backend/app/schemas/games.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/game_libraries/test_schemas.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/games.py backend/tests/game_libraries/test_schemas.py
git commit -m "feat(games): GameLibrary response schemas"
```

---

## Task 3: Provider interface + SteamProvider

The extensible seam plus the Steam implementation (vdf + acf parsing, realpath dedup, metadata-only sizes).

**Files:**
- Create: `backend/app/services/game_libraries/provider.py`
- Create: `backend/app/services/game_libraries/steam.py`
- Test: `backend/tests/game_libraries/test_steam_provider.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/game_libraries/test_steam_provider.py`:

```python
"""Tests for the Steam game library provider."""

from pathlib import Path

from app.services.game_libraries import steam


def _make_library(root: Path, apps: dict[str, tuple[int, str | None]]) -> None:
    """Create a fake Steam root at *root* with the given apps.

    apps maps appid -> (size_bytes, name_or_None). When name is None, no .acf is
    written (simulates a missing manifest -> fallback name).
    """
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    apps_lines = "\n".join(f'            "{aid}" "{size}"' for aid, (size, _n) in apps.items())
    vdf_text = (
        '"libraryfolders"\n{\n    "0"\n    {\n'
        f'        "path"  "{root.as_posix()}"\n'
        '        "apps"\n        {\n'
        f'{apps_lines}\n'
        '        }\n    }\n}\n'
    )
    (steamapps / "libraryfolders.vdf").write_text(vdf_text, encoding="utf-8")
    for aid, (size, name) in apps.items():
        if name is not None:
            (steamapps / f"appmanifest_{aid}.acf").write_text(
                f'"AppState"\n{{\n    "appid" "{aid}"\n    "name" "{name}"\n    "SizeOnDisk" "{size}"\n}}\n',
                encoding="utf-8",
            )


def test_is_available_false_when_no_steam(tmp_path, monkeypatch):
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(tmp_path / "nope")])
    assert steam.SteamProvider().is_available() is False


def test_get_libraries_reads_sizes_names_sorted(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {
        "111": (5000, "Game A"),
        "222": (3000, "Game B"),
        "333": (1000, None),  # no .acf -> fallback name
    })
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    provider = steam.SteamProvider()
    assert provider.is_available() is True

    libs = provider.get_libraries()
    assert len(libs) == 1
    lib = libs[0]
    assert lib.provider == "steam"
    assert lib.provider_name == "Steam"
    assert lib.total_bytes == 9000
    assert lib.game_count == 3
    assert [g.size_bytes for g in lib.games] == [5000, 3000, 1000]  # desc
    assert lib.games[0].name == "Game A"
    assert lib.games[2].name == "App 333"  # fallback for missing .acf
    assert lib.device_id is not None


def test_get_libraries_dedupes_roots_pointing_to_same_lib(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {"111": (5000, "Game A")})
    # Two candidate roots that resolve to the same vdf must yield one library.
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root), str(root)])
    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/game_libraries/test_steam_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.game_libraries.steam'`

- [ ] **Step 3: Implement the provider protocol**

Create `backend/app/services/game_libraries/provider.py`:

```python
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
```

- [ ] **Step 4: Implement the Steam provider**

Create `backend/app/services/game_libraries/steam.py`:

```python
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
            try:
                size = int(size_str)
            except (TypeError, ValueError):
                size = 0
            name = self._read_app_name(steamapps, str(app_id)) or f"App {app_id}"
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/game_libraries/test_steam_provider.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/game_libraries/provider.py backend/app/services/game_libraries/steam.py backend/tests/game_libraries/test_steam_provider.py
git commit -m "feat(games): SteamProvider with provider interface"
```

---

## Task 4: Aggregation service + dev mock

Iterate providers, aggregate, and fall back to a mock in dev mode when nothing real is found (so the Windows dev UI renders).

**Files:**
- Create: `backend/app/services/game_libraries/service.py`
- Test: `backend/tests/game_libraries/test_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/game_libraries/test_service.py`:

```python
"""Tests for the game library aggregation service."""

from app.schemas.games import GameEntry, GameLibrary
from app.services.game_libraries import service


class _FakeProvider:
    id = "fake"
    name = "Fake"

    def __init__(self, available: bool, libs):
        self._available = available
        self._libs = libs

    def is_available(self) -> bool:
        return self._available

    def get_libraries(self):
        return self._libs


def _lib(total: int) -> GameLibrary:
    return GameLibrary(
        provider="fake", provider_name="Fake", path="/x", device_id=1,
        total_bytes=total, game_count=1,
        games=[GameEntry(app_id="1", name="g", size_bytes=total)],
    )


def test_aggregates_available_providers(monkeypatch):
    monkeypatch.setattr(service, "PROVIDERS", [_FakeProvider(True, [_lib(100), _lib(200)])])
    resp = service.get_game_libraries()
    assert resp.available is True
    assert resp.total_bytes == 300
    assert len(resp.libraries) == 2


def test_provider_exception_is_swallowed(monkeypatch):
    class Boom:
        id = "boom"; name = "Boom"
        def is_available(self): return True
        def get_libraries(self): raise RuntimeError("nope")
    monkeypatch.setattr(service, "PROVIDERS", [Boom()])
    resp = service.get_game_libraries()
    # available flips True (provider reported available) but no libraries.
    assert resp.libraries == []


def test_dev_mock_when_no_real_libraries(monkeypatch):
    monkeypatch.setattr(service, "PROVIDERS", [_FakeProvider(False, [])])
    # Tests run with NAS_MODE=dev, so the mock kicks in.
    resp = service.get_game_libraries()
    assert resp.available is True
    assert len(resp.libraries) == 1
    assert resp.libraries[0].provider == "steam"
    assert resp.total_bytes == resp.libraries[0].total_bytes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/game_libraries/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.game_libraries.service'`

- [ ] **Step 3: Implement the service**

Create `backend/app/services/game_libraries/service.py`:

```python
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

    if not libraries and settings.is_dev_mode:
        return _dev_mock()

    total = sum(lib.total_bytes for lib in libraries)
    return GameLibrariesResponse(libraries=libraries, total_bytes=total, available=available)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/game_libraries/test_service.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/game_libraries/service.py backend/tests/game_libraries/test_service.py
git commit -m "feat(games): provider aggregation service with dev mock"
```

---

## Task 5: API route + registration

Thin read-only endpoint, any authenticated user.

**Files:**
- Create: `backend/app/api/routes/games.py`
- Modify: `backend/app/api/routes/__init__.py`
- Test: `backend/tests/game_libraries/test_games_route.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/game_libraries/test_games_route.py`:

```python
"""Tests for the game libraries API route."""


def test_libraries_requires_auth(client):
    resp = client.get("/api/games/libraries")
    assert resp.status_code in (401, 403)


def test_libraries_returns_schema(client, auth_headers):
    resp = client.get("/api/games/libraries", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "libraries" in body
    assert "total_bytes" in body
    assert "available" in body
    assert isinstance(body["libraries"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/game_libraries/test_games_route.py -v`
Expected: FAIL — 404 on `/api/games/libraries` (route not registered yet)

- [ ] **Step 3: Create the route module**

Create `backend/app/api/routes/games.py`:

```python
"""Game library storage usage endpoints (read-only, auto-discovered)."""
from fastapi import APIRouter, Depends, Request, Response

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.games import GameLibrariesResponse
from app.schemas.user import UserPublic
from app.services.game_libraries import service as game_libraries_service

router = APIRouter()


@router.get("/libraries", response_model=GameLibrariesResponse)
@user_limiter.limit(get_limit("system_monitor"))
def get_game_libraries(
    request: Request,
    response: Response,
    _: UserPublic = Depends(deps.get_current_user),
) -> GameLibrariesResponse:
    """Detected game libraries with per-game size."""
    return game_libraries_service.get_game_libraries()
```

- [ ] **Step 4: Register the router**

In `backend/app/api/routes/__init__.py`:

Add `games` to the import block (e.g. on the line with `docs,` / `setup,` — append `games,`):

```python
    docs,
    setup,
    games,
)
```

Then add the registration (place it after the `setup.router` line, before the dev-only block at line ~86):

```python
api_router.include_router(games.router, prefix="/games", tags=["games"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/game_libraries/test_games_route.py -v`
Expected: PASS (2 tests). In dev test mode with no real Steam install, the service returns the dev mock, so `available` is True and `libraries` has one entry.

- [ ] **Step 6: Run the whole new suite + a sanity import check**

Run: `cd backend && python -m pytest tests/game_libraries/ -v`
Expected: all PASS (vdf, schemas, steam, service, route).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/games.py backend/app/api/routes/__init__.py backend/tests/game_libraries/test_games_route.py
git commit -m "feat(games): GET /api/games/libraries endpoint"
```

---

## Task 6: Document the new service module

Keep `services/CLAUDE.md` in sync (repo convention).

**Files:**
- Modify: `backend/app/services/CLAUDE.md`

- [ ] **Step 1: Add the submodule entry**

In `backend/app/services/CLAUDE.md`, under "### Service Subdirectories", add a bullet near the other feature modules:

```markdown
**`game_libraries/`** — Game library storage usage (Steam now, provider-extensible)
- `provider.py` — `GameLibraryProvider` protocol + registry seam
- `steam.py` — Steam discovery via `libraryfolders.vdf` + `appmanifest_*.acf` (metadata only)
- `vdf.py` — minimal Valve KeyValues parser (stdlib)
- `service.py` — aggregate across providers, dev-mode mock
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/CLAUDE.md
git commit -m "docs(games): document game_libraries service module"
```

---

## Task 7: Frontend API client

Typed fetch for the new endpoint.

**Files:**
- Create: `client/src/api/games.ts`

- [ ] **Step 1: Implement the API client**

Create `client/src/api/games.ts`:

```ts
import { apiClient } from '../lib/api';

export interface GameEntry {
  app_id: string;
  name: string;
  size_bytes: number;
}

export interface GameLibrary {
  provider: string;
  provider_name: string;
  path: string;
  device_id: number | null;
  total_bytes: number;
  game_count: number;
  games: GameEntry[];
}

export interface GameLibrariesResponse {
  libraries: GameLibrary[];
  total_bytes: number;
  available: boolean;
}

export const getGameLibraries = async (): Promise<GameLibrariesResponse> => {
  const response = await apiClient.get('/api/games/libraries');
  return response.data;
};
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/api/games.ts
git commit -m "feat(client): games API client + types"
```

---

## Task 8: GameLibrariesCard component

The card with aggregate + expandable per-game list, styled like the existing storage cards.

**Files:**
- Create: `client/src/components/settings/GameLibrariesCard.tsx`

- [ ] **Step 1: Implement the component**

Create `client/src/components/settings/GameLibrariesCard.tsx`:

```tsx
/**
 * GameLibrariesCard -- shows detected game libraries (Steam et al.) with a
 * per-library aggregate and an expandable per-game list, for the Storage tab.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Gamepad2, ChevronDown, ChevronRight } from 'lucide-react';
import { formatBytes } from '../../lib/formatters';
import type { GameLibrary } from '../../api/games';

interface GameLibrariesCardProps {
  libraries: GameLibrary[] | null;  // null = still loading
  available: boolean;
}

export default function GameLibrariesCard({ libraries, available }: GameLibrariesCardProps) {
  const { t } = useTranslation('settings');
  const [openLibs, setOpenLibs] = useState<Record<string, boolean>>({});

  const toggle = (key: string) =>
    setOpenLibs((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="card border-slate-800/60 bg-slate-900/55 shadow-[0_4px_24px_rgba(99,102,241,0.06)] hover:shadow-[0_8px_32px_rgba(99,102,241,0.12)] transition-shadow">
      <h3 className="text-base sm:text-lg font-semibold mb-4 flex items-center">
        <Gamepad2 className="w-4 h-4 sm:w-5 sm:h-5 mr-2 text-indigo-400" />
        {t('storage.games.title')}
      </h3>

      {libraries === null ? (
        <div className="space-y-3 animate-pulse">
          <div className="h-16 rounded-lg bg-slate-700/30" />
        </div>
      ) : !available || libraries.length === 0 ? (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-slate-800/60 border border-slate-700/40">
          <Gamepad2 className="w-5 h-5 text-slate-500" />
          <p className="text-sm text-slate-400">{t('storage.games.empty')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {libraries.map((lib, idx) => {
            const key = `${lib.provider}:${lib.path}:${idx}`;
            const open = !!openLibs[key];
            return (
              <div key={key} className="p-4 rounded-xl bg-slate-800/40 border border-slate-700/30">
                <button
                  type="button"
                  onClick={() => toggle(key)}
                  className="w-full flex items-center justify-between gap-3 text-left"
                  aria-expanded={open}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                        {lib.provider_name}
                      </span>
                      <span className="text-sm font-semibold tabular-nums">{formatBytes(lib.total_bytes)}</span>
                    </div>
                    <p className="text-xs text-slate-500 truncate mt-1">{lib.path}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-slate-400">
                      {t('storage.games.count', { count: lib.game_count })}
                    </span>
                    {open
                      ? <ChevronDown className="h-4 w-4 text-slate-500" />
                      : <ChevronRight className="h-4 w-4 text-slate-500" />}
                  </div>
                </button>

                {open && (
                  <ul className="mt-3 space-y-1 text-xs sm:text-sm border-t border-slate-700/40 pt-3">
                    {lib.games.map((g) => (
                      <li key={g.app_id} className="flex justify-between gap-2">
                        <span className="text-slate-300 truncate">{g.name}</span>
                        <span className="text-slate-400 tabular-nums shrink-0">{formatBytes(g.size_bytes)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/settings/GameLibrariesCard.tsx
git commit -m "feat(client): GameLibrariesCard component"
```

---

## Task 9: Wire the card into StorageTab + i18n

Load the data and render the card; add translation strings.

**Files:**
- Modify: `client/src/components/settings/StorageTab.tsx`
- Modify: `client/src/i18n/locales/de/settings.json`
- Modify: `client/src/i18n/locales/en/settings.json`

- [ ] **Step 1: Add German strings**

In `client/src/i18n/locales/de/settings.json`, inside the existing `"storage"` object (alongside `systemStorage`, `vclTitle`, `cacheTitle`, ...), add a `games` block:

```json
"games": {
  "title": "Spielbibliotheken",
  "empty": "Keine Spielbibliothek erkannt",
  "count": "{{count}} Spiele"
}
```

- [ ] **Step 2: Add English strings**

In `client/src/i18n/locales/en/settings.json`, inside the existing `"storage"` object, add:

```json
"games": {
  "title": "Game Libraries",
  "empty": "No game library detected",
  "count": "{{count}} games"
}
```

- [ ] **Step 3: Import the card and API in StorageTab**

In `client/src/components/settings/StorageTab.tsx`, add to the imports near the other component/api imports (after the `StorageBreakdownRing` import at line ~10):

```tsx
import GameLibrariesCard from './GameLibrariesCard';
import { getGameLibraries } from '../../api/games';
import type { GameLibrariesResponse } from '../../api/games';
```

- [ ] **Step 4: Add state + loader**

In the component body, add a state declaration after `const [cacheOverview, setCacheOverview] = useState<SSDCacheStats[] | null>(null);` (line ~31):

```tsx
  const [gameLibraries, setGameLibraries] = useState<GameLibrariesResponse | null>(null);
```

Add the loader call inside the existing `useEffect` (after `loadCacheOverview();`, line ~36):

```tsx
    loadGameLibraries();
```

Add the loader function after `loadCacheOverview` (after line ~64):

```tsx
  const loadGameLibraries = async () => {
    try {
      const data = await getGameLibraries();
      setGameLibraries(data);
    } catch {
      setGameLibraries({ libraries: [], total_bytes: 0, available: false });
    }
  };
```

- [ ] **Step 5: Render the card**

In `StorageTab.tsx`, add the card immediately after the closing `</div>` of the SSD Cache block and before the final `</>` (the SSD Cache card is the last block, ending around line 313):

```tsx
      {/* Game Libraries */}
      <GameLibrariesCard
        libraries={gameLibraries?.libraries ?? null}
        available={gameLibraries?.available ?? false}
      />
```

Note: while loading, `gameLibraries` is `null`, so `libraries` is `null` → the card shows its loading skeleton. After load, `libraries` is an array (possibly empty) → card shows data or its empty state.

- [ ] **Step 6: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 7: Commit**

```bash
git add client/src/components/settings/StorageTab.tsx client/src/i18n/locales/de/settings.json client/src/i18n/locales/en/settings.json
git commit -m "feat(client): show Game Libraries card in Storage tab"
```

---

## Task 10: Final verification

- [ ] **Step 1: Backend — full game_libraries suite + a broad smoke**

Run: `cd backend && python -m pytest tests/game_libraries/ -v`
Expected: all PASS.

Then a quick import/route smoke across the app:

Run: `cd backend && python -m pytest tests/ -k "games or mountpoint or storage_breakdown" -v --timeout=60`
Expected: PASS (no regressions in neighboring storage tests).

- [ ] **Step 2: Frontend — type check**

Run: `cd client && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Confirm clean tree**

Run: `git status`
Expected: clean (all changes committed).

- [ ] **Step 4: (Optional) Manual prod check**

On BaluNode after deploy, open Settings → Storage. The "Spielbibliotheken" card should list the `/mnt/cache-vcl/SteamLibrary` library (~530 GB) with an expandable game list, plus the smaller home library. If empty unexpectedly, check the backend can read `~/.steam/steam/steamapps/libraryfolders.vdf` as the service user (`sven`).

---

## Notes for the implementer

- **Run from the right dir:** backend tests from `backend/`, tsc from `client/`.
- **Dev mock is intentional:** in dev/test mode with no Steam install, `GET /api/games/libraries` returns a 3-game mock so the UI renders. On the prod box (real Steam under `sven`), real data wins — the mock only triggers when `libraries` is empty AND `settings.is_dev_mode`.
- **No directory scanning:** all sizes come from `libraryfolders.vdf` (`apps` block) and `appmanifest_*.acf` (`name`). Do not add `os.walk`/`du`-style size computation.
- **Provider extensibility:** a future Epic/Heroic/Lutris provider is a new class added to `PROVIDERS` in `service.py` — no schema, route, or frontend change required.
- **Runtime/tool apps** (e.g. "Steam Linux Runtime", Proton) appear as regular games by design (per spec decision). No filtering in v1.
```
