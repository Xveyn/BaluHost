# Status-Bar-Plugin-Pills + Steam-Gaming-Plugin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein bundled Plugin zeigt in der Topbar-Statusleiste eine Pill „Gaming Session" (plus Spielname), sobald auf der Box ein Steam-Spiel läuft — über einen neuen, allgemeinen Plugin-Extension-Point.

**Architecture:** Der Detector erkennt das laufende Spiel durch einen `/proc`-Scan nach Steams `reaper SteamLaunch AppId=<n>`-Wrapper; der Name kommt aus `appmanifest_<id>.acf` über den bestehenden VDF-Parser. Plugins deklarieren Pills über `get_status_pills()` und liefern deren Zustand über `collect_status_pill()`; `StatusBarService` mischt sie gleichberechtigt in den Katalog, inklusive DB-Config-Rows für an/aus, Reihenfolge und Sichtbarkeit.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 / SQLAlchemy 2.0, pytest (`asyncio_mode = "auto"`), React 18 + TypeScript + Vitest, lucide-react.

**Spec:** `docs/superpowers/specs/2026-07-22-status-bar-plugin-pills-steam-gaming-design.md`

## Global Constraints

- Backend-Tests laufen aus `backend/`: `python -m pytest <pfad> -q --no-cov`. Der Repo-Default in `pyproject.toml` schaltet Coverage an; für Einzelläufe `--no-cov` verwenden.
- `ruff check <geänderte dateien>` muss sauber sein (CI-Gate).
- Frontend: `npx vitest run <pfad>` aus `client/`; vor dem Abschluss zusätzlich `npx eslint .` und `npm run build`.
- Keine neuen Dependencies. Alles mit Stdlib + vorhandenen Paketen.
- Kein `subprocess`, kein `sudo`. Es wird ausschließlich aus `/proc` und aus Steam-Dateien **gelesen**.
- Collectors dürfen niemals nach außen werfen — eine kaputte Pill darf die Leiste nicht abschießen.
- Kommentare und Docstrings auf Englisch (Repo-Konvention); Commit-Betreff Englisch.
- Plugin-Pills starten mit `enabled=True` (bewusste Abweichung von der Core-Konvention `enabled=False`).

---

## File Structure

**Neu:**

| Datei | Verantwortung |
|---|---|
| `backend/app/plugins/installed/steam_gaming/__init__.py` | Plugin-Klasse: Metadaten, Pill-Spec, Collector, Übersetzungen |
| `backend/app/plugins/installed/steam_gaming/detector.py` | `/proc`-Scan → AppID des laufenden Spiels |
| `backend/app/plugins/installed/steam_gaming/names.py` | AppID → Spielname (mit Caches) |
| `backend/tests/plugins/test_steam_gaming_detector.py` | Detector-Tests gegen ein Fake-`/proc` |
| `backend/tests/plugins/test_steam_gaming_names.py` | Namensauflösung + Caches |
| `backend/tests/plugins/test_steam_gaming_plugin.py` | Pill-Spec, Collector, TTL-Cache, Dev-Mock |
| `backend/tests/services/test_status_bar_plugin_pills.py` | Extension-Point im StatusBarService |
| `client/src/components/topbar/__tests__/pillRenderers.test.tsx` | Renderer-Zweig für Plugin-Texte |

**Geändert:**

| Datei | Änderung |
|---|---|
| `backend/app/schemas/status_bar.py` | `PILL_IDS`-Literal → `PillId` mit Validator; `label_text`/`translations` an `PillState`, `name_text`/`translations` an `PillCatalogEntry` |
| `backend/app/services/status_bar/catalog.py` | `PillDefinition` um `plugin_name`, `name_text`, `translations` erweitert |
| `backend/app/services/status_bar/service.py` | Effektiver Katalog inkl. Plugin-Pills; Dispatch mit Timeout |
| `backend/app/services/game_libraries/steam.py` | Neue öffentliche Funktion `find_steamapps_dirs()` |
| `backend/app/plugins/base.py` | `StatusPillSpec`, `get_status_pills()`, `collect_status_pill()` |
| `backend/app/plugins/manager.py` | Öffentliches `iter_enabled_plugins()` |
| `backend/tests/services/test_status_bar_service.py:92-97` | Drift-Test auf `CORE_PILL_IDS` umstellen |
| `client/src/api/statusBar.ts` | `PillId` → `string`; neue Felder |
| `client/src/components/topbar/pillRenderers.tsx` | Zweig auf `resolvePluginString` |
| `client/src/components/topbar/iconMap.ts` | `Gamepad2` ergänzen |
| `client/src/components/status-bar-config/PillRow.tsx` | Plugin-Namen auflösen |
| `backend/app/plugins/CLAUDE.md` | Extension-Point dokumentieren |

---

### Task 1: Detector — laufendes Spiel aus `/proc` erkennen

**Files:**
- Create: `backend/app/plugins/installed/steam_gaming/__init__.py`
- Create: `backend/app/plugins/installed/steam_gaming/detector.py`
- Test: `backend/tests/plugins/test_steam_gaming_detector.py`

**Interfaces:**
- Consumes: nichts
- Produces: `detector.detect_running_app_id(proc_root: Path = Path("/proc")) -> str | None`

Hintergrund: Auf der Prod-Box startet Steam Spiele so (gemessen):

```
591737  /bin/sh -c mangohud …/steam-launch-wrapper -- …/reaper SteamLaunch AppId=1449560 -- …
591762  …/ubuntu12_32/reaper SteamLaunch AppId=1449560 -- … Proton 10.0/proton … MetroExodus.exe
```

Dieselbe AppID erscheint also zweimal. Da die Funktion genau eine AppID zurückgibt, löst sich das Duplikat von selbst auf; der PID-Vergleich sorgt nur dafür, dass die Antwort nicht von der Reihenfolge in `/proc` abhängt.

- [ ] **Step 1: Write the failing test**

`backend/tests/plugins/test_steam_gaming_detector.py`:

```python
"""Detecting the running Steam game from /proc (see spec 2026-07-22)."""

from pathlib import Path

from app.plugins.installed.steam_gaming import detector


def _fake_proc(tmp_path: Path, procs: dict[int, str]) -> Path:
    """Build a /proc-shaped tree: <pid>/cmdline with NUL-separated argv."""
    root = tmp_path / "proc"
    root.mkdir()
    for pid, cmdline in procs.items():
        entry = root / str(pid)
        entry.mkdir()
        (entry / "cmdline").write_bytes(cmdline.replace(" ", "\x00").encode())
    (root / "meminfo").write_text("not a pid dir")
    return root


REAPER = "/home/sven/.local/share/Steam/ubuntu12_32/reaper SteamLaunch AppId=1449560 -- /proton"
WRAPPER = "/bin/sh -c mangohud steam-launch-wrapper -- reaper SteamLaunch AppId=1449560 -- /proton"


def test_no_game_running_returns_none(tmp_path):
    root = _fake_proc(tmp_path, {1: "/sbin/init", 4367: "/usr/bin/steam"})

    assert detector.detect_running_app_id(root) is None


def test_finds_the_app_id_of_a_running_game(tmp_path):
    root = _fake_proc(tmp_path, {1: "/sbin/init", 591762: REAPER})

    assert detector.detect_running_app_id(root) == "1449560"


def test_mangohud_duplicate_yields_one_app_id(tmp_path):
    """The wrapper and the reaper both carry AppId= for the same game."""
    root = _fake_proc(tmp_path, {591737: WRAPPER, 591762: REAPER})

    assert detector.detect_running_app_id(root) == "1449560"


def test_lowest_pid_wins_when_two_app_ids_are_present(tmp_path):
    """Deterministic answer instead of /proc directory order."""
    root = _fake_proc(tmp_path, {
        900: "reaper SteamLaunch AppId=222 -- /x",
        800: "reaper SteamLaunch AppId=111 -- /x",
    })

    assert detector.detect_running_app_id(root) == "111"


def test_unreadable_and_vanished_entries_are_skipped(tmp_path):
    """A process can die between listdir() and read()."""
    root = _fake_proc(tmp_path, {591762: REAPER})
    (root / "999").mkdir()  # pid dir without cmdline — vanished mid-scan

    assert detector.detect_running_app_id(root) == "1449560"


def test_missing_proc_returns_none(tmp_path):
    """Windows dev boxes have no /proc at all."""
    assert detector.detect_running_app_id(tmp_path / "nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_detector.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.installed.steam_gaming'`

- [ ] **Step 3: Create the plugin package**

`backend/app/plugins/installed/steam_gaming/__init__.py`:

```python
"""Steam gaming plugin: shows a status-strip pill while a game is running."""
```

- [ ] **Step 4: Write the detector**

`backend/app/plugins/installed/steam_gaming/detector.py`:

```python
"""Detect a running Steam game by scanning /proc for Steam's launch wrapper.

Steam launches every title — native or Proton — through
``reaper SteamLaunch AppId=<n> -- …``, so the AppID is right there in the
command line. Alternatives were measured and rejected: ``registry.vdf``'s
``RunningAppID`` is no longer maintained by Steam (always 0, upstream bug
ValveSoftware/steam-for-linux#9672), and Steam creates no per-game systemd
scope. See the design doc for the measurements.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator, Optional

DEFAULT_PROC_ROOT = Path("/proc")

_APPID_RE = re.compile(r"SteamLaunch\s+AppId=(\d+)")


def _iter_cmdlines(proc_root: Path) -> Iterator[tuple[int, str]]:
    """Yield ``(pid, cmdline)`` for every readable process directory."""
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return  # no /proc (Windows dev box) or not readable
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            raw = (proc_root / entry / "cmdline").read_bytes()
        except OSError:
            continue  # process vanished between listdir() and read()
        yield int(entry), raw.replace(b"\x00", b" ").decode("utf-8", "replace")


def detect_running_app_id(proc_root: Path = DEFAULT_PROC_ROOT) -> Optional[str]:
    """AppID of the running Steam game, or None.

    The design assumes at most one game at a time. Should two different
    AppIDs ever be present, the lowest PID wins — not because multiple games
    are supported, but so the answer cannot flip between polls based on
    directory order.
    """
    best_pid: Optional[int] = None
    best_app_id: Optional[str] = None
    for pid, cmdline in _iter_cmdlines(proc_root):
        match = _APPID_RE.search(cmdline)
        if match is None:
            continue
        if best_pid is None or pid < best_pid:
            best_pid, best_app_id = pid, match.group(1)
    return best_app_id
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_detector.py -q --no-cov`
Expected: PASS — 6 passed

- [ ] **Step 6: Lint and commit**

```bash
cd backend && python -m ruff check app/plugins/installed/steam_gaming tests/plugins/test_steam_gaming_detector.py
cd .. && git add backend/app/plugins/installed/steam_gaming backend/tests/plugins/test_steam_gaming_detector.py
git commit -m "feat(steam-gaming): detect the running game from Steam's reaper wrapper"
```

---

### Task 2: AppID → Spielname

**Files:**
- Create: `backend/app/plugins/installed/steam_gaming/names.py`
- Modify: `backend/app/services/game_libraries/steam.py` (neue Funktion am Dateiende)
- Test: `backend/tests/plugins/test_steam_gaming_names.py`

**Interfaces:**
- Consumes: `app.services.game_libraries.vdf.parse(text) -> dict`
- Produces:
  - `steam.find_steamapps_dirs() -> list[Path]`
  - `names.resolve_name(app_id: str) -> str | None`
  - `names.reset_caches() -> None` (nur für Tests)

`SteamProvider._find_steam_roots()` ist privat und liefert nur die Steam-*Roots*; die eigentliche Bibliothek der Box liegt woanders (`/mnt/cache-vcl/SteamLibrary`) und steht in `libraryfolders.vdf`. Deshalb eine eigene öffentliche Funktion, die beide Ebenen zusammenführt.

- [ ] **Step 1: Write the failing test**

`backend/tests/plugins/test_steam_gaming_names.py`:

```python
"""Resolving a Steam AppID to its display name."""

from pathlib import Path

import pytest

from app.plugins.installed.steam_gaming import names


@pytest.fixture(autouse=True)
def _clean_caches():
    names.reset_caches()
    yield
    names.reset_caches()


def _library(tmp_path: Path, app_id: str, game_name: str) -> Path:
    steamapps = tmp_path / "SteamLibrary" / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / f"appmanifest_{app_id}.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"%s"\n\t"name"\t\t"%s"\n\t"SizeOnDisk"\t"123"\n}\n'
        % (app_id, game_name),
        encoding="utf-8",
    )
    return steamapps


def test_resolves_the_name_from_the_app_manifest(tmp_path, monkeypatch):
    steamapps = _library(tmp_path, "1449560", "Metro Exodus Enhanced Edition")
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    assert names.resolve_name("1449560") == "Metro Exodus Enhanced Edition"


def test_unknown_app_id_resolves_to_none(tmp_path, monkeypatch):
    """Non-Steam shortcuts have a synthetic AppID and no manifest."""
    steamapps = _library(tmp_path, "1449560", "Metro Exodus Enhanced Edition")
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    assert names.resolve_name("3000000000") is None


def test_corrupt_manifest_resolves_to_none(tmp_path, monkeypatch):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    (steamapps / "appmanifest_55.acf").write_text("{{{ not vdf", encoding="utf-8")
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    assert names.resolve_name("55") is None


def test_a_resolved_name_is_cached(tmp_path, monkeypatch):
    steamapps = _library(tmp_path, "1449560", "Metro Exodus Enhanced Edition")
    calls = []

    def _counting():
        calls.append(1)
        return [steamapps]

    monkeypatch.setattr(names, "find_steamapps_dirs", _counting)

    assert names.resolve_name("1449560") == "Metro Exodus Enhanced Edition"
    assert names.resolve_name("1449560") == "Metro Exodus Enhanced Edition"
    assert len(calls) == 1, "a game name never changes — resolve it once"


def test_a_miss_is_retried_after_the_ttl(tmp_path, monkeypatch):
    """A manifest can appear while a game is still installing."""
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    monkeypatch.setattr(names, "find_steamapps_dirs", lambda: [steamapps])

    clock = {"now": 1000.0}
    monkeypatch.setattr(names, "_monotonic", lambda: clock["now"])

    assert names.resolve_name("77") is None

    (steamapps / "appmanifest_77.acf").write_text(
        '"AppState"\n{\n\t"name"\t\t"Later Installed"\n}\n', encoding="utf-8"
    )
    assert names.resolve_name("77") is None, "still inside the negative TTL"

    clock["now"] += names._MISS_TTL_SECONDS + 1
    assert names.resolve_name("77") == "Later Installed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_names.py -q --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.installed.steam_gaming.names'`

- [ ] **Step 3: Add the library-directory helper**

Am Ende von `backend/app/services/game_libraries/steam.py` anfügen:

```python
def find_steamapps_dirs() -> List[Path]:
    """Every readable ``steamapps`` directory across all Steam libraries.

    Combines the standard Steam roots with the library paths declared in
    ``libraryfolders.vdf`` — on a real box the games usually live on a
    different mount than the Steam installation itself.
    """
    provider = SteamProvider()
    dirs: List[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        steamapps = path / "steamapps"
        if not steamapps.is_dir():
            return
        real = os.path.realpath(str(steamapps))
        if real in seen:
            return
        seen.add(real)
        dirs.append(steamapps)

    for root in provider._find_steam_roots():
        _add(root)
        try:
            data = vdf.parse(
                (root / "steamapps" / "libraryfolders.vdf").read_text(
                    encoding="utf-8", errors="replace"
                )
            )
        except OSError:
            continue
        folders = data.get("libraryfolders", {})
        if not isinstance(folders, dict):
            continue
        for entry in folders.values():
            if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                _add(Path(entry["path"]))
    return dirs
```

- [ ] **Step 4: Write the name resolver**

`backend/app/plugins/installed/steam_gaming/names.py`:

```python
"""Resolve a Steam AppID to its display name via ``appmanifest_<id>.acf``."""
from __future__ import annotations

import time
from typing import Optional

from app.services.game_libraries import vdf
from app.services.game_libraries.steam import find_steamapps_dirs

# A game's name never changes, so hits are cached for the process lifetime.
_NAME_CACHE: dict[str, str] = {}

# Misses are retried: a manifest appears while a game is still installing,
# and non-Steam shortcuts never get one at all.
_MISS_CACHE: dict[str, float] = {}
_MISS_TTL_SECONDS = 60.0


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def reset_caches() -> None:
    """Drop both caches. Intended for tests."""
    _NAME_CACHE.clear()
    _MISS_CACHE.clear()


def _read_manifest_name(app_id: str) -> Optional[str]:
    for steamapps in find_steamapps_dirs():
        manifest = steamapps / f"appmanifest_{app_id}.acf"
        try:
            data = vdf.parse(manifest.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        except Exception:
            # A corrupt manifest must not break detection for other libraries.
            continue
        state = data.get("AppState")
        if not isinstance(state, dict):
            continue
        name = state.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def resolve_name(app_id: str) -> Optional[str]:
    """Display name for *app_id*, or None when it cannot be resolved."""
    cached = _NAME_CACHE.get(app_id)
    if cached is not None:
        return cached

    missed_at = _MISS_CACHE.get(app_id)
    if missed_at is not None and _monotonic() - missed_at < _MISS_TTL_SECONDS:
        return None

    name = _read_manifest_name(app_id)
    if name is None:
        _MISS_CACHE[app_id] = _monotonic()
        return None

    _NAME_CACHE[app_id] = name
    _MISS_CACHE.pop(app_id, None)
    return name
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_names.py tests/game_libraries -q --no-cov`
Expected: PASS — die neuen 5 Tests plus die bestehenden `game_libraries`-Tests (5 Dateien unter `tests/game_libraries/`) unverändert grün

- [ ] **Step 6: Lint and commit**

```bash
cd backend && python -m ruff check app/plugins/installed/steam_gaming app/services/game_libraries/steam.py tests/plugins/test_steam_gaming_names.py
cd .. && git add backend/app/plugins/installed/steam_gaming/names.py backend/app/services/game_libraries/steam.py backend/tests/plugins/test_steam_gaming_names.py
git commit -m "feat(steam-gaming): resolve an AppID to its game name via appmanifest"
```

---

### Task 3: Extension-Point in Schemas, PluginBase und PluginManager

**Files:**
- Modify: `backend/app/schemas/status_bar.py`
- Modify: `backend/app/services/status_bar/catalog.py:11-21`
- Modify: `backend/app/plugins/base.py`
- Modify: `backend/app/plugins/manager.py`
- Modify: `backend/tests/services/test_status_bar_service.py:92-97`
- Test: `backend/tests/services/test_status_bar_plugin_pills.py` (Teil 1)

**Interfaces:**
- Consumes: nichts
- Produces:
  - `schemas.status_bar.CORE_PILL_IDS: frozenset[str]`
  - `schemas.status_bar.PillId` (validierter `str`)
  - `plugins.base.StatusPillSpec`
  - `PluginBase.get_status_pills() -> List[StatusPillSpec]`
  - `PluginBase.collect_status_pill(pill_id: str, db: Session) -> Optional[dict]`
  - `PluginManager.iter_enabled_plugins() -> Iterator[tuple[str, PluginBase]]`

- [ ] **Step 1: Write the failing test**

`backend/tests/services/test_status_bar_plugin_pills.py`:

```python
"""Plugin-contributed status-strip pills (spec 2026-07-22)."""

import pytest
from pydantic import ValidationError

from app.schemas.status_bar import CORE_PILL_IDS, PillState


def test_core_pill_ids_are_still_accepted():
    pill = PillState(id="power", kind="state", tone="info", label_key="x", href="/y")
    assert pill.id == "power"


def test_namespaced_plugin_pill_ids_are_accepted():
    pill = PillState(
        id="plugin:steam_gaming:session", kind="state", tone="info",
        label_key="pill.session", label_text="Gaming Session", href="/plugins",
    )
    assert pill.label_text == "Gaming Session"


def test_unknown_pill_ids_are_still_rejected():
    with pytest.raises(ValidationError):
        PillState(id="not_a_pill", kind="state", tone="info", label_key="x", href="/y")


def test_a_plugin_cannot_squat_a_core_id_shape():
    """Only the plugin: namespace is open — bare new ids stay closed."""
    with pytest.raises(ValidationError):
        PillState(id="gaming", kind="state", tone="info", label_key="x", href="/y")


def test_core_pill_ids_match_the_catalog():
    """Drift detection, replaces the old Literal-vs-catalog assertion."""
    from app.services.status_bar.catalog import CATALOG

    assert CORE_PILL_IDS == {p.id for p in CATALOG}


def test_plugin_base_declares_no_pills_by_default():
    from app.plugins.base import PluginBase

    assert PluginBase.get_status_pills(object()) == []  # type: ignore[arg-type]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_status_bar_plugin_pills.py -q --no-cov`
Expected: FAIL — `ImportError: cannot import name 'CORE_PILL_IDS' from 'app.schemas.status_bar'`

- [ ] **Step 3: Open up the pill-id type**

In `backend/app/schemas/status_bar.py` den Kopf ersetzen — `PILL_IDS` entfällt vollständig:

```python
"""Pydantic schemas for the topbar status strip."""
import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel
from pydantic.functional_validators import AfterValidator

# Core pills. Kept in sync with CATALOG via test_core_pill_ids_match_the_catalog.
# Duplicated here rather than imported from the catalog, which imports this
# module — the test is what keeps the two honest.
CORE_PILL_IDS: frozenset[str] = frozenset({
    "power", "pihole", "uploads", "sync", "raid", "sleep", "vpn", "temp",
    "always_awake", "scheduler", "backup", "desktop",
})

# Plugin pills are namespaced by the core as plugin:<plugin_name>:<suffix>, so
# they can never collide with a core id.
_PLUGIN_PILL_RE = re.compile(r"^plugin:[a-z0-9_]+:[a-z0-9_]+$")


def _validate_pill_id(value: str) -> str:
    if value in CORE_PILL_IDS or _PLUGIN_PILL_RE.match(value):
        return value
    raise ValueError(
        f"unknown pill id {value!r}: expected a core pill or plugin:<name>:<suffix>"
    )


PillId = Annotated[str, AfterValidator(_validate_pill_id)]
```

Dann in denselben Datei alle drei Verwendungen umstellen und die neuen Felder ergänzen:

```python
class PillConfigItem(BaseModel):
    pill_id: PillId
    ...


class PillCatalogEntry(BaseModel):
    """One catalog pill plus its persisted config — for the admin config GET."""
    pill_id: PillId
    name_key: str
    ...
    display_mode_configurable: bool
    name_text: Optional[str] = None       # literal fallback for plugin pills
    translations: Optional[dict] = None   # plugin translations, resolved client-side


class PillState(BaseModel):
    """A rendered pill for the /state payload."""
    id: PillId
    ...
    extra: Optional[dict] = None
    label_text: Optional[str] = None      # literal fallback for plugin pills
    translations: Optional[dict] = None   # plugin translations, resolved client-side
```

- [ ] **Step 4: Update the catalog type annotation**

In `backend/app/services/status_bar/catalog.py` den Import und die Dataclass anpassen:

```python
from app.schemas.status_bar import PillId


@dataclass(frozen=True)
class PillDefinition:
    id: PillId
    name_key: str                 # i18n key, e.g. "statusBar.pills.power.name"
    default_visibility: str       # "admin" | "all"
    visibility_locked: bool
    silent_when_ok: bool
    href: str
    icon: str                     # lucide icon name; must match the collector's emitted icon
    display_mode_configurable: bool = False  # only True for pills with an admin-chosen display mode
    # Set for plugin-contributed pills only:
    plugin_name: Optional[str] = None
    name_text: Optional[str] = None
    translations: Optional[dict] = None
```

`from typing import Optional` oben ergänzen. Der `CATALOG` bleibt unverändert.

**Falle:** `PillDefinition` ist `@dataclass(frozen=True)`, und `frozen=True`
erzeugt ein `__hash__` aus allen Feldern. Ein `dict` in `translations` macht
die Instanz damit unhashbar — allerdings erst, wenn jemand sie tatsächlich
hasht. Heute wird nur `p.id` als Dict-Key benutzt (`CATALOG_BY_ID`), also ist
das harmlos. Wer später `PillDefinition` in ein Set legt, bekommt einen
`TypeError` an einer sehr unerwarteten Stelle.

- [ ] **Step 5: Replace the old drift test**

In `backend/tests/services/test_status_bar_service.py` den Test in Zeile 92-97 ersetzen:

```python
def test_pill_id_literal_matches_catalog():
    """Drift detection: CORE_PILL_IDS must equal the catalog ids exactly."""
    from app.schemas.status_bar import CORE_PILL_IDS
    from app.services.status_bar.catalog import CATALOG

    assert CORE_PILL_IDS == {p.id for p in CATALOG}
```

- [ ] **Step 6: Add the plugin-side API**

In `backend/app/plugins/base.py` nach `DashboardPanelSpec` einfügen:

```python
class StatusPillSpec(BaseModel):
    """A status-strip pill contributed by a plugin.

    The public pill id is namespaced by the core as
    ``plugin:<plugin_name>:<id>`` — the plugin only picks the suffix.
    """

    id: str = Field(description="Plugin-local suffix, e.g. 'session'")
    icon: str = Field(description="lucide icon name, e.g. 'Gamepad2'")
    href: str = Field(description="Click-through target")
    name_key: str = Field(description="Key into get_translations() for the catalog name")
    name_text: str = Field(description="Literal fallback for the catalog name")
    default_visibility: Literal["admin", "all"] = "admin"
    visibility_locked: bool = False
    silent_when_ok: bool = True
```

Und in `PluginBase` (neben `get_dashboard_panel`):

```python
    def get_status_pills(self) -> List["StatusPillSpec"]:
        """Status-strip pills this plugin contributes. Default: none."""
        return []

    async def collect_status_pill(self, pill_id: str, db: "Session") -> Optional[dict]:
        """Current state of one pill, or None to stay silent.

        *pill_id* is the plugin-local suffix from the spec, not the namespaced
        public id. The returned dict is passed to PillState — supply at least
        ``kind``, ``tone`` and ``label_key``/``label_text``.
        """
        return None
```

`Literal` aus `typing` importieren, falls dort noch nicht vorhanden.

- [ ] **Step 7: Add a public accessor on the manager**

In `backend/app/plugins/manager.py` neben `get_plugin()` einfügen:

```python
    def iter_enabled_plugins(self) -> Iterator[Tuple[str, PluginBase]]:
        """Yield ``(name, plugin)`` for every currently enabled plugin.

        Public accessor so callers stop reaching into ``_enabled``.
        """
        for name in sorted(self._enabled):
            plugin = self.get_plugin(name)
            if plugin is not None:
                yield name, plugin
```

`Iterator` und `Tuple` aus `typing` importieren, falls dort noch nicht vorhanden.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_status_bar_plugin_pills.py tests/services/test_status_bar_service.py tests/api/test_status_bar_routes.py -q --no-cov`
Expected: PASS — die 6 neuen Tests plus die bestehenden Status-Bar-Tests unverändert grün

- [ ] **Step 9: Lint and commit**

```bash
cd backend && python -m ruff check app/schemas/status_bar.py app/services/status_bar/catalog.py app/plugins/base.py app/plugins/manager.py tests/services/test_status_bar_plugin_pills.py
cd .. && git add backend/app/schemas/status_bar.py backend/app/services/status_bar/catalog.py backend/app/plugins/base.py backend/app/plugins/manager.py backend/tests/services/
git commit -m "feat(status-bar): open the pill catalog to plugin contributions"
```

---

### Task 4: StatusBarService mischt Plugin-Pills in den Katalog

**Files:**
- Modify: `backend/app/services/status_bar/service.py`
- Test: `backend/tests/services/test_status_bar_plugin_pills.py` (Teil 2, anhängen)

**Interfaces:**
- Consumes: `StatusPillSpec`, `PluginManager.iter_enabled_plugins()`, `PillDefinition.plugin_name`
- Produces: `StatusBarService._effective_catalog() -> list[PillDefinition]`

- [ ] **Step 1: Write the failing test**

An `backend/tests/services/test_status_bar_plugin_pills.py` anhängen:

```python
import asyncio

from app.plugins.base import StatusPillSpec


class _FakePlugin:
    """Minimal stand-in — the service only needs these two methods."""

    def __init__(self, result=None, hang: bool = False, boom: bool = False):
        self._result, self._hang, self._boom = result, hang, boom

    def get_status_pills(self):
        return [StatusPillSpec(
            id="session", icon="Gamepad2", href="/plugins",
            name_key="pill.name", name_text="Gaming Session",
        )]

    async def collect_status_pill(self, pill_id, db):
        if self._boom:
            raise RuntimeError("collector exploded")
        if self._hang:
            await asyncio.sleep(30)
        return self._result


@pytest.fixture
def with_plugin(monkeypatch):
    """Install a fake enabled plugin into the status bar service."""
    def _install(plugin):
        from app.services.status_bar import service as svc
        monkeypatch.setattr(svc, "iter_enabled_plugins",
                            lambda: [("steam_gaming", plugin)])
    return _install


def test_plugin_pill_appears_in_the_config(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin())

    entries = StatusBarService(db_session).get_config().pills
    entry = next(e for e in entries if e.pill_id == "plugin:steam_gaming:session")

    assert entry.name_text == "Gaming Session"
    assert entry.icon == "Gamepad2"


def test_plugin_pills_start_enabled(db_session, with_plugin):
    """Deliberate deviation: core pills seed disabled, plugin pills do not."""
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin())

    entries = StatusBarService(db_session).get_config().pills
    plugin_entry = next(e for e in entries if e.pill_id.startswith("plugin:"))
    core_entry = next(e for e in entries if e.pill_id == "power")

    assert plugin_entry.enabled is True
    assert core_entry.enabled is False


async def test_plugin_pill_is_rendered_into_the_state(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin(result={
        "kind": "state", "tone": "info",
        "label_key": "pill.session", "label_text": "Gaming Session",
        "value": "Metro Exodus", "icon": "Gamepad2",
    }))

    state = await StatusBarService(db_session).collect_state("admin")
    pill = next(p for p in state.pills if p.id == "plugin:steam_gaming:session")

    assert pill.value == "Metro Exodus"
    assert pill.label_text == "Gaming Session"


async def test_a_silent_plugin_collector_emits_no_pill(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin(result=None))

    state = await StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


async def test_a_throwing_plugin_collector_does_not_break_the_strip(db_session, with_plugin):
    from app.services.status_bar.service import StatusBarService
    with_plugin(_FakePlugin(boom=True))

    state = await StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


async def test_a_hanging_plugin_collector_is_cut_off(db_session, with_plugin, monkeypatch):
    from app.services.status_bar import service as svc
    monkeypatch.setattr(svc, "PLUGIN_COLLECTOR_TIMEOUT_SECONDS", 0.05)
    with_plugin(_FakePlugin(hang=True))

    state = await svc.StatusBarService(db_session).collect_state("admin")

    assert all(not p.id.startswith("plugin:") for p in state.pills)


def test_a_disabled_plugin_drops_its_pill_but_keeps_the_settings(db_session, with_plugin, monkeypatch):
    from app.services.status_bar import service as svc
    with_plugin(_FakePlugin())
    svc.StatusBarService(db_session).get_config()  # seeds the row

    monkeypatch.setattr(svc, "iter_enabled_plugins", lambda: [])
    entries = svc.StatusBarService(db_session).get_config().pills
    assert all(not e.pill_id.startswith("plugin:") for e in entries)

    from app.models.status_bar import StatusBarPillConfig
    row = db_session.query(StatusBarPillConfig).filter(
        StatusBarPillConfig.pill_id == "plugin:steam_gaming:session"
    ).first()
    assert row is not None, "settings must survive a disabled plugin"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_status_bar_plugin_pills.py -q --no-cov`
Expected: FAIL — `AttributeError: module 'app.services.status_bar.service' has no attribute 'iter_enabled_plugins'`

- [ ] **Step 3: Implement the merge**

In `backend/app/services/status_bar/service.py` oben ergänzen:

```python
import asyncio

from app.plugins.base import PluginBase
from app.services.status_bar.catalog import CATALOG, CATALOG_BY_ID, PillDefinition

# A plugin collector that never returns must not stall the whole strip.
PLUGIN_COLLECTOR_TIMEOUT_SECONDS = 2.0


def iter_enabled_plugins() -> list[tuple[str, PluginBase]]:
    """Enabled plugins, or an empty list when the plugin system is unavailable.

    Module-level so tests can patch it.
    """
    try:
        from app.plugins.manager import PluginManager

        return list(PluginManager.get_instance().iter_enabled_plugins())
    except Exception:  # noqa: BLE001 - the strip works without plugins
        logger.debug("plugin pills unavailable", exc_info=True)
        return []
```

Innerhalb von `StatusBarService` ergänzen:

```python
    def _effective_catalog(self) -> list[PillDefinition]:
        """Core catalog plus the pills of every enabled plugin."""
        pills = list(CATALOG)
        for plugin_name, plugin in iter_enabled_plugins():
            try:
                specs = plugin.get_status_pills()
            except Exception:  # noqa: BLE001 - one bad plugin must not hide the rest
                logger.warning("plugin %s failed to declare pills", plugin_name, exc_info=True)
                continue
            for spec in specs:
                pills.append(PillDefinition(
                    id=f"plugin:{plugin_name}:{spec.id}",
                    name_key=spec.name_key,
                    default_visibility=spec.default_visibility,
                    visibility_locked=spec.visibility_locked,
                    silent_when_ok=spec.silent_when_ok,
                    href=spec.href,
                    icon=spec.icon,
                    plugin_name=plugin_name,
                    name_text=spec.name_text,
                    translations=(plugin.get_translations() or None),
                ))
        return pills

    def _plugin_for(self, definition: PillDefinition) -> Optional[PluginBase]:
        for name, plugin in iter_enabled_plugins():
            if name == definition.plugin_name:
                return plugin
        return None
```

`from typing import Optional, cast` sicherstellen.

`_ensure_rows()` bekommt den effektiven Katalog und das abweichende Default:

```python
    def _ensure_rows(self, catalog: list[PillDefinition]) -> dict[str, StatusBarPillConfig]:
        existing = {r.pill_id: r for r in self.db.query(StatusBarPillConfig).all()}
        created = False
        for idx, definition in enumerate(catalog):
            if definition.id not in existing:
                row = StatusBarPillConfig(
                    pill_id=definition.id,
                    # Core pills start hidden and are opted into by the admin.
                    # A plugin pill is the whole point of installing the plugin,
                    # so it starts visible (see design doc).
                    enabled=definition.plugin_name is not None,
                    visibility=definition.default_visibility,
                    sort_order=idx,
                )
                self.db.add(row)
                existing[definition.id] = row
                created = True
        if created:
            self.db.commit()
        return existing
```

`get_config()` und `collect_state()` auf den effektiven Katalog umstellen: beide beginnen mit

```python
        catalog = self._effective_catalog()
        by_id = {d.id: d for d in catalog}
        rows = self._ensure_rows(catalog)
```

In `get_config()` ersetzt `sorted(catalog, key=...)` das bisherige `sorted(CATALOG, ...)`, und der `PillCatalogEntry` bekommt zwei Felder mehr:

```python
                name_text=definition.name_text,
                translations=definition.translations,
```

In `collect_state()` wird `CATALOG_BY_ID` durch `by_id` ersetzt, und der Collector-Aufruf verzweigt:

```python
        for definition, _row in visible:
            if definition.plugin_name is not None:
                partial = await self._collect_plugin_pill(definition)
            else:
                collector = COLLECTORS.get(definition.id)
                if collector is None:
                    continue
                partial = await collector(self.db, role)
            if partial is None:
                continue
            ...
            try:
                pills.append(PillState(
                    id=definition.id,
                    href=definition.href,
                    translations=definition.translations,
                    **partial,
                ))
```

Und die neue Hilfsmethode:

```python
    async def _collect_plugin_pill(self, definition: PillDefinition) -> Optional[dict]:
        """Run a plugin collector under a timeout; never raise."""
        plugin = self._plugin_for(definition)
        if plugin is None:
            return None
        suffix = definition.id.split(":", 2)[2]
        try:
            return await asyncio.wait_for(
                plugin.collect_status_pill(suffix, self.db),
                timeout=PLUGIN_COLLECTOR_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("plugin pill %s timed out", definition.id)
        except Exception:  # noqa: BLE001 - one bad pill must not 5xx the strip
            logger.warning("plugin pill %s failed", definition.id, exc_info=True)
        return None
```

`update_config()` bleibt auf `CATALOG_BY_ID` — Plugin-Pills haben keine `visibility_locked`/`display_mode_configurable`-Sonderregeln, und ein unbekannter `pill_id` wird dort bereits ignoriert.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_status_bar_plugin_pills.py tests/services/test_status_bar_service.py tests/services/test_status_bar_collectors.py tests/api/test_status_bar_routes.py -q --no-cov`
Expected: PASS — 13 neue Tests plus alle bestehenden Status-Bar-Tests grün

- [ ] **Step 5: Lint and commit**

```bash
cd backend && python -m ruff check app/services/status_bar/service.py tests/services/test_status_bar_plugin_pills.py
cd .. && git add backend/app/services/status_bar/service.py backend/tests/services/test_status_bar_plugin_pills.py
git commit -m "feat(status-bar): merge plugin pills into catalog, config and state"
```

---

### Task 5: Das Plugin liefert die Gaming-Pill

**Files:**
- Modify: `backend/app/plugins/installed/steam_gaming/__init__.py`
- Test: `backend/tests/plugins/test_steam_gaming_plugin.py`

**Interfaces:**
- Consumes: `detector.detect_running_app_id()`, `names.resolve_name()`, `StatusPillSpec`, `PluginBase`
- Produces: `SteamGamingPlugin` (von `PluginManager` entdeckt)

- [ ] **Step 1: Write the failing test**

`backend/tests/plugins/test_steam_gaming_plugin.py`:

```python
"""The Steam gaming plugin's status pill."""

import pytest

from app.plugins.installed import steam_gaming as plugin_module
from app.plugins.installed.steam_gaming import SteamGamingPlugin


@pytest.fixture(autouse=True)
def _clear_cache():
    plugin_module._CACHE.clear()
    yield
    plugin_module._CACHE.clear()


@pytest.fixture
def plugin():
    return SteamGamingPlugin()


@pytest.fixture
def prod_mode(monkeypatch):
    """`is_dev_mode` is its own settings FIELD, not derived from nas_mode."""
    monkeypatch.setattr(plugin_module.settings, "is_dev_mode", False)


@pytest.fixture
def dev_mode(monkeypatch):
    monkeypatch.setattr(plugin_module.settings, "is_dev_mode", True)


def test_declares_one_namespaced_pill(plugin):
    specs = plugin.get_status_pills()

    assert len(specs) == 1
    assert specs[0].id == "session"
    assert specs[0].icon == "Gamepad2"


async def test_stays_silent_when_no_game_runs(plugin, monkeypatch, prod_mode):
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: None)

    assert await plugin.collect_status_pill("session", None) is None


async def test_reports_the_game_name_when_resolvable(plugin, monkeypatch, prod_mode):
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: "1449560")
    monkeypatch.setattr(plugin_module, "resolve_name", lambda _id: "Metro Exodus")

    pill = await plugin.collect_status_pill("session", None)

    assert pill["value"] == "Metro Exodus"
    assert pill["label_text"] == "Gaming Session"
    assert pill["tone"] == "info"


async def test_falls_back_to_the_bare_label_for_an_unknown_game(plugin, monkeypatch, prod_mode):
    """Non-Steam shortcuts have no manifest — the pill still shows up."""
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: "3000000000")
    monkeypatch.setattr(plugin_module, "resolve_name", lambda _id: None)

    pill = await plugin.collect_status_pill("session", None)

    assert pill["label_text"] == "Gaming Session"
    assert pill.get("value") is None


async def test_repeated_polls_within_the_ttl_scan_once(plugin, monkeypatch, prod_mode):
    calls = []

    def _counting_detect():
        calls.append(1)
        return "1449560"

    monkeypatch.setattr(plugin_module, "detect_running_app_id", _counting_detect)
    monkeypatch.setattr(plugin_module, "resolve_name", lambda _id: "Metro Exodus")

    clock = {"now": 500.0}
    monkeypatch.setattr(plugin_module, "_monotonic", lambda: clock["now"])

    await plugin.collect_status_pill("session", None)
    await plugin.collect_status_pill("session", None)
    assert len(calls) == 1

    clock["now"] += plugin_module._CACHE_TTL_SECONDS + 0.1
    await plugin.collect_status_pill("session", None)
    assert len(calls) == 2


async def test_dev_mode_shows_a_mock_game(plugin, monkeypatch, dev_mode):
    """Windows dev boxes have no /proc — the strip should still render."""
    monkeypatch.setattr(plugin_module, "detect_running_app_id", lambda: None)

    pill = await plugin.collect_status_pill("session", None)

    assert pill["value"] == "Dev Mode Game"


async def test_an_unknown_pill_id_is_silent(plugin, dev_mode):
    assert await plugin.collect_status_pill("nope", None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_plugin.py -q --no-cov`
Expected: FAIL — `ImportError: cannot import name 'SteamGamingPlugin'`

- [ ] **Step 3: Write the plugin**

`backend/app/plugins/installed/steam_gaming/__init__.py` vollständig ersetzen:

```python
"""Steam gaming plugin: shows a status-strip pill while a game is running.

Detection is a /proc scan (see detector.py); the result is cached for a few
seconds so the status strip's poll — once per logged-in user every 10s across
four production workers — does not re-scan for every request. A per-worker
cache is enough: the pill is an activity indicator, not a ledger, and this
avoids sharing state between workers entirely.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.plugins.base import PluginBase, PluginMetadata, StatusPillSpec
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name

_PILL_ID = "session"
_CACHE_TTL_SECONDS = 3.0
_CACHE: Dict[str, object] = {}


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def _current_game() -> Optional[tuple[str, Optional[str]]]:
    """``(app_id, name)`` of the running game, or None. Cached for a few seconds."""
    now = _monotonic()
    checked_at = _CACHE.get("checked_at")
    if isinstance(checked_at, float) and now - checked_at < _CACHE_TTL_SECONDS:
        return _CACHE.get("game")  # type: ignore[return-value]

    app_id = detect_running_app_id()
    game = (app_id, resolve_name(app_id)) if app_id else None
    _CACHE["checked_at"] = now
    _CACHE["game"] = game
    return game


class SteamGamingPlugin(PluginBase):
    """Surfaces a running Steam session in the topbar status strip."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="steam_gaming",
            display_name="Steam Gaming",
            version="1.0.0",
            description="Shows a status-strip pill while a Steam game is running",
            author="BaluHost",
        )

    def get_status_pills(self) -> List[StatusPillSpec]:
        return [StatusPillSpec(
            id=_PILL_ID,
            icon="Gamepad2",
            href="/plugins",
            name_key="pill_name",
            name_text="Gaming Session",
            default_visibility="admin",
            silent_when_ok=True,
        )]

    async def collect_status_pill(self, pill_id: str, db: Session) -> Optional[dict]:
        if pill_id != _PILL_ID:
            return None

        game = _current_game()
        if game is None:
            if settings.is_dev_mode:
                # No /proc on a Windows dev box — render something anyway.
                game = ("0", "Dev Mode Game")
            else:
                return None

        _app_id, name = game
        return {
            "kind": "state",
            "tone": "info",
            "label_key": "pill_label",
            "label_text": "Gaming Session",
            "value": name,
            "icon": "Gamepad2",
        }

    def get_translations(self) -> Optional[Dict[str, Dict[str, str]]]:
        return {
            "en": {"pill_name": "Gaming Session", "pill_label": "Gaming Session"},
            "de": {"pill_name": "Gaming-Session", "pill_label": "Gaming-Session"},
        }
```

`PluginMetadata` verlangt genau diese fünf Pflichtfelder (`name`, `version`,
`display_name`, `description`, `author`) — alle oben gesetzt. `required_permissions`
bleibt leer: Das Plugin liest nur `/proc` und Steam-Dateien im eigenen Home,
es braucht keine Berechtigung aus dem Permission-Modell.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_steam_gaming_plugin.py -q --no-cov`
Expected: PASS — 7 passed

- [ ] **Step 5: Verify plugin discovery still works**

Run: `cd backend && python -m pytest tests/plugins -q --no-cov`
Expected: PASS — alle Plugin-Tests grün, insbesondere die Discovery-Tests, die `installed/` scannen

- [ ] **Step 6: Lint and commit**

```bash
cd backend && python -m ruff check app/plugins/installed/steam_gaming tests/plugins/test_steam_gaming_plugin.py
cd .. && git add backend/app/plugins/installed/steam_gaming backend/tests/plugins/test_steam_gaming_plugin.py
git commit -m "feat(steam-gaming): contribute the Gaming Session status pill"
```

---

### Task 6: Frontend — Plugin-Texte rendern

**Files:**
- Modify: `client/src/api/statusBar.ts:6-8,16-28,35-44`
- Modify: `client/src/components/topbar/iconMap.ts`
- Modify: `client/src/components/topbar/pillRenderers.tsx:13`
- Modify: `client/src/components/status-bar-config/PillRow.tsx:45`
- Test: `client/src/__tests__/components/topbar/pillRenderers.test.tsx`

**Achtung Pfad:** `vite.config.ts` setzt `include: ['src/__tests__/**/*.test.{ts,tsx}']`.
Ein Test neben der Komponente würde von keinem Runner eingesammelt und wäre
stillschweigend tot (genau der Fehler aus Issue #321). Das Verzeichnis
`client/src/__tests__/components/topbar/` existiert bereits.

**Interfaces:**
- Consumes: `resolvePluginString(translations, key, fallback)` aus `client/src/lib/pluginI18n.ts`
- Produces: nichts für spätere Tasks

- [ ] **Step 1: Write the failing test**

`client/src/__tests__/components/topbar/pillRenderers.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PillRenderer } from '../../../components/topbar/pillRenderers';
import type { PillState } from '../../../api/statusBar';

const base: PillState = {
  id: 'plugin:steam_gaming:session',
  kind: 'state',
  tone: 'info',
  label_key: 'pill_label',
  href: '/plugins',
  icon: 'Gamepad2',
};

describe('PillRenderer with plugin pills', () => {
  it('resolves the label from the plugin translations', () => {
    render(<PillRenderer pill={{
      ...base,
      label_text: 'Gaming Session',
      translations: { en: { pill_label: 'Gaming Session' } },
      value: 'Metro Exodus',
    }} />);

    expect(screen.getByText('Gaming Session')).toBeInTheDocument();
    expect(screen.getByText('Metro Exodus')).toBeInTheDocument();
  });

  it('falls back to label_text when the key is missing from the translations', () => {
    render(<PillRenderer pill={{
      ...base,
      label_text: 'Gaming Session',
      translations: { en: { something_else: 'nope' } },
    }} />);

    expect(screen.getByText('Gaming Session')).toBeInTheDocument();
  });

  it('still uses core i18n for pills without translations', () => {
    render(<PillRenderer pill={{ ...base, id: 'raid', label_key: 'pills.raid.live' }} />);

    // No plugin translations: the i18n key itself is rendered in the test env.
    expect(screen.getByText(/pills\.raid\.live|RAID/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/topbar/pillRenderers.test.tsx`
Expected: FAIL — TypeScript/Runtime-Fehler, weil `label_text` und `translations` im `PillState`-Typ fehlen

- [ ] **Step 3: Widen the API types**

In `client/src/api/statusBar.ts`:

```ts
/** Core pill ids plus `plugin:<name>:<suffix>` — validated server-side. */
export type PillId = string;
```

`PillState` um zwei Felder ergänzen:

```ts
  extra?: Record<string, unknown> | null;
  label_text?: string | null;
  translations?: Record<string, Record<string, string>> | null;
```

`PillCatalogEntry` ebenfalls:

```ts
  display_mode_configurable: boolean;
  name_text?: string | null;
  translations?: Record<string, Record<string, string>> | null;
```

- [ ] **Step 4: Add the icon**

In `client/src/components/topbar/iconMap.ts` `Gamepad2` in beide Listen aufnehmen:

```ts
import {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer,
  Coffee, Clock, Save, Monitor, Gamepad2,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const ICONS: Record<string, LucideIcon> = {
  Zap, Shield, Upload, RefreshCw, HardDrive, Moon, Lock, Thermometer, Coffee, Clock, Save, Monitor,
  Gamepad2,
};
```

- [ ] **Step 5: Branch the renderer**

In `client/src/components/topbar/pillRenderers.tsx` den Import ergänzen und Zeile 13 ersetzen:

```tsx
import { resolvePluginString } from '../../lib/pluginI18n';
```

```tsx
  // Plugin pills carry their own translations; core pills live in the app bundle.
  const label = pill.translations
    ? resolvePluginString(pill.translations, pill.label_key, pill.label_text ?? '')
    : t(pill.label_key, { ...(pill.label_params ?? {}) });
```

- [ ] **Step 6: Branch the config row**

In `client/src/components/status-bar-config/PillRow.tsx` den Import ergänzen und Zeile 45 ersetzen:

```tsx
import { resolvePluginString } from '../../lib/pluginI18n';
```

```tsx
      <span className="flex-1 text-sm text-slate-200">
        {entry.translations
          ? resolvePluginString(entry.translations, entry.name_key, entry.name_text ?? entry.pill_id)
          : t(entry.name_key.replace(/^statusBar\./, ''))}
      </span>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/components/topbar src/__tests__/components/status-bar-config`
Expected: PASS — die 3 neuen Tests plus alle bestehenden Status-Bar-Frontend-Tests

- [ ] **Step 8: Full frontend gates**

Run: `cd client && npx eslint . && npm run build`
Expected: 0 ESLint-Fehler, Build erfolgreich

- [ ] **Step 9: Commit**

```bash
git add client/src/api/statusBar.ts client/src/components/topbar client/src/components/status-bar-config
git commit -m "feat(status-bar): render plugin-provided pill labels client-side"
```

---

### Task 7: Dokumentation und Gesamtverifikation

**Files:**
- Modify: `backend/app/plugins/CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-07-22-status-bar-plugin-pills-steam-gaming.md` (Haken setzen)

**Interfaces:**
- Consumes: alles Vorherige
- Produces: nichts

- [ ] **Step 1: Document the extension point**

In `backend/app/plugins/CLAUDE.md` im Abschnitt „Creating a Plugin" nach Punkt 5 ergänzen:

```markdown
6. Override `get_status_pills()` + `collect_status_pill()` to contribute a
   topbar status-strip pill. The core namespaces the id as
   `plugin:<plugin_name>:<suffix>`, seeds a config row (**enabled by default**,
   unlike core pills) and runs the collector under a 2s timeout — a collector
   that throws or hangs makes its own pill silent, never breaks the strip.
   Labels come from `get_translations()`, resolved client-side via
   `resolvePluginString`, with `name_text`/`label_text` as literal fallbacks.
```

- [ ] **Step 2: Run the full affected backend suites**

Run: `cd backend && python -m pytest tests/plugins tests/services tests/api -q --no-cov`
Expected: PASS — keine Regression in den bestehenden Suites

- [ ] **Step 3: Lint everything touched**

Run: `cd backend && python -m ruff check app tests`
Expected: `All checks passed!`

- [ ] **Step 4: Manual verification in dev mode**

```bash
python start_dev.py
```

Prüfen: Als Admin einloggen → Statusleiste zeigt die Pill „Gaming-Session · Dev Mode Game"
(Dev-Mock, weil Windows kein `/proc` hat). Danach in der Status-Bar-Konfiguration
prüfen, dass die Pill mit lesbarem Namen erscheint, abschaltbar und sortierbar ist.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/CLAUDE.md docs/superpowers/plans/
git commit -m "docs(plugins): document the status-pill extension point"
```

---

## Nach dem letzten Task

PR gegen `main` öffnen. Im PR-Text festhalten:

- dass `registry.vdf`/`RunningAppID` und systemd-Scopes gemessen und verworfen wurden (Links in der Spec),
- dass Plugin-Pills bewusst `enabled=True` starten,
- dass Spiele mit Drittanbieter-Launchern ungetestet sind und die Pill dort stumm bleiben kann.

Teilprojekte 2–4 (Menü-Eintrag, Notification, Feinschliff) bekommen eigene Specs.
