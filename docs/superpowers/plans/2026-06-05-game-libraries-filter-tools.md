# Game Libraries: Filter Tools, Fix Sizes, Nicer List — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the existing "Game Libraries" feature: hide Steam tools/runtimes (Proton, Linux Runtime, redist) from the list and totals, read correct per-game sizes from `.acf SizeOnDisk` (fixing 0 B entries), and render each game with a proportional size bar.

**Architecture:** Backend changes are confined to `backend/app/services/game_libraries/steam.py`: a name-heuristic `_is_tool_app()` filter applied in `_build_library`, and a `_read_app_manifest()` that returns both name and authoritative `SizeOnDisk`. Frontend changes are confined to the expanded list in `client/src/components/settings/GameLibrariesCard.tsx`. No schema, route, i18n, or dev-mock changes.

**Tech Stack:** Python/FastAPI, pytest. React 18 + TypeScript + Tailwind.

**Spec:** `docs/superpowers/specs/2026-06-05-game-libraries-filter-tools-design.md`

**Branch:** `feat/game-libraries-filter-tools` (already created off `main`)

**Conventions:**
- Backend tests run from `backend/`: on PowerShell prefix each call with the cd, e.g. `cd backend; python -m pytest tests/game_libraries/test_games_steam_provider.py -v`.
- Frontend type check: `cd client; npx tsc --noEmit`.
- Test env defaults to dev mode (`NAS_MODE=dev`). The `LF will be replaced by CRLF` warning on commit is expected (`core.autocrlf=true`).
- Python in this repo is 3.14, so `tuple[...]` annotations are fine.

---

## Task 1: Backend — filter out Steam tools/runtimes

Add a name-heuristic predicate and apply it in `_build_library` so tools never enter the games list, `total_bytes`, or `game_count`. A library that ends up with zero games is already dropped by the existing `if lib.game_count > 0` guard in `get_libraries()`.

**Files:**
- Modify: `backend/app/services/game_libraries/steam.py`
- Test: `backend/tests/game_libraries/test_games_steam_provider.py`

- [ ] **Step 1: Add the predicate tests**

In `backend/tests/game_libraries/test_games_steam_provider.py`, add `import pytest` at the top (after the existing imports), then append these tests at the end of the file:

```python
@pytest.mark.parametrize("name", [
    "Proton 8.0",
    "Proton Experimental",
    "Proton EasyAntiCheat Runtime",
    "Steam Linux Runtime 3.0 (sniper)",
    "Steamworks Common Redistributables",
    "STEAMWORKS COMMON REDISTRIBUTABLES",  # case-insensitive
])
def test_is_tool_app_true(name):
    assert steam._is_tool_app(name) is True


@pytest.mark.parametrize("name", [
    "Counter-Strike 2",
    "Cyberpunk 2077",
    "App 12345",  # fallback name for missing .acf
])
def test_is_tool_app_false(name):
    assert steam._is_tool_app(name) is False
```

- [ ] **Step 2: Run the predicate tests to verify they fail**

Run: `cd backend; python -m pytest tests/game_libraries/test_games_steam_provider.py -k is_tool_app -v`
Expected: FAIL — `AttributeError: module 'app.services.game_libraries.steam' has no attribute '_is_tool_app'`

- [ ] **Step 3: Implement the predicate**

In `backend/app/services/game_libraries/steam.py`, add the constants and function immediately AFTER the `_CANDIDATE_ROOTS = [ ... ]` list and BEFORE `class SteamProvider:`:

```python
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
```

- [ ] **Step 4: Run the predicate tests to verify they pass**

Run: `cd backend; python -m pytest tests/game_libraries/test_games_steam_provider.py -k is_tool_app -v`
Expected: PASS (9 parametrized cases)

- [ ] **Step 5: Add the filter + drop tests**

Append to `backend/tests/game_libraries/test_games_steam_provider.py`:

```python
def test_get_libraries_filters_tool_apps(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {
        "111": (5000, "Counter-Strike 2"),
        "222": (3000, "Cyberpunk 2077"),
        "900": (1500, "Proton 8.0"),
        "901": (700, "Steam Linux Runtime 3.0 (sniper)"),
        "902": (462, "Steamworks Common Redistributables"),
    })
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1
    lib = libs[0]
    assert [g.name for g in lib.games] == ["Counter-Strike 2", "Cyberpunk 2077"]
    assert lib.game_count == 2
    assert lib.total_bytes == 8000  # tool bytes excluded


def test_get_libraries_drops_tools_only_library(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {
        "900": (1500, "Proton 8.0"),
        "902": (462, "Steamworks Common Redistributables"),
    })
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])
    assert steam.SteamProvider().get_libraries() == []
```

- [ ] **Step 6: Run the filter tests to verify they fail**

Run: `cd backend; python -m pytest tests/game_libraries/test_games_steam_provider.py -k "filters_tool_apps or drops_tools_only" -v`
Expected: FAIL — tools are still present, so `[g.name ...]` includes Proton/runtime entries and the tools-only library is returned (not empty).

- [ ] **Step 7: Apply the filter in `_build_library`**

In `backend/app/services/game_libraries/steam.py`, replace the entire `_build_library` method with this version (reorders to read the name first, then skips tools before building the entry):

```python
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
```

- [ ] **Step 8: Run the full provider suite to verify all pass**

Run: `cd backend; python -m pytest tests/game_libraries/test_games_steam_provider.py -v`
Expected: PASS (all tests, incl. the pre-existing ones and the new filter/drop/predicate tests)

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/game_libraries/steam.py backend/tests/game_libraries/test_games_steam_provider.py
git commit -m "feat(games): filter Proton/runtime tools from libraries"
```

---

## Task 2: Backend — correct sizes from `.acf SizeOnDisk`

Game sizes currently come from the `apps` block of `libraryfolders.vdf`, which is `0` for some installed games (e.g. Cyberpunk 2077). Read the authoritative `SizeOnDisk` from each `appmanifest_*.acf`, falling back to the vdf value only when the manifest is missing or the field is unusable.

**Files:**
- Modify: `backend/app/services/game_libraries/steam.py`
- Test: `backend/tests/game_libraries/test_games_steam_provider.py`

- [ ] **Step 1: Extend the test fixture to allow a separate `.acf` SizeOnDisk**

In `backend/tests/game_libraries/test_games_steam_provider.py`, replace the `_make_library` helper with this version (lets a 3rd tuple element override the `.acf SizeOnDisk` independently of the vdf `apps` size; existing 2-tuple callers are unchanged):

```python
def _make_library(root: Path, apps: dict) -> None:
    """Create a fake Steam root at *root* with the given apps.

    apps maps appid -> (vdf_size, name_or_None) or
    (vdf_size, name_or_None, acf_size_override). The vdf ``apps`` block uses
    vdf_size; the .acf ``SizeOnDisk`` defaults to vdf_size unless a 3rd element
    overrides it. No .acf is written when name is None (simulates a missing
    manifest -> fallback name + vdf size).
    """
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    apps_lines = "\n".join(f'            "{aid}" "{spec[0]}"' for aid, spec in apps.items())
    vdf_text = (
        '"libraryfolders"\n{\n    "0"\n    {\n'
        f'        "path"  "{root.as_posix()}"\n'
        '        "apps"\n        {\n'
        f'{apps_lines}\n'
        '        }\n    }\n}\n'
    )
    (steamapps / "libraryfolders.vdf").write_text(vdf_text, encoding="utf-8")
    for aid, spec in apps.items():
        vdf_size, name = spec[0], spec[1]
        acf_size = spec[2] if len(spec) > 2 else vdf_size
        if name is not None:
            (steamapps / f"appmanifest_{aid}.acf").write_text(
                f'"AppState"\n{{\n    "appid" "{aid}"\n    "name" "{name}"\n    "SizeOnDisk" "{acf_size}"\n}}\n',
                encoding="utf-8",
            )
```

- [ ] **Step 2: Add the size-source tests**

Append to `backend/tests/game_libraries/test_games_steam_provider.py`:

```python
def test_size_prefers_acf_size_on_disk_over_vdf(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    # vdf apps size is 0 (stale tally); real size lives in .acf SizeOnDisk.
    _make_library(root, {"1091500": (0, "Cyberpunk 2077", 99_000_000_000)})
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1
    assert libs[0].games[0].size_bytes == 99_000_000_000
    assert libs[0].total_bytes == 99_000_000_000


def test_size_falls_back_to_vdf_when_no_acf(tmp_path, monkeypatch):
    root = tmp_path / "SteamRoot"
    _make_library(root, {"333": (1234, None)})  # no .acf written
    monkeypatch.setattr(steam, "_CANDIDATE_ROOTS", [str(root)])

    libs = steam.SteamProvider().get_libraries()
    assert len(libs) == 1
    assert libs[0].games[0].size_bytes == 1234
    assert libs[0].games[0].name == "App 333"
```

- [ ] **Step 3: Run the size tests to verify the first fails**

Run: `cd backend; python -m pytest tests/game_libraries/test_games_steam_provider.py -k "size_prefers or size_falls_back" -v`
Expected: `test_size_prefers_acf_size_on_disk_over_vdf` FAILS (size is read from the vdf `0`, so `size_bytes == 0`, not the real size). `test_size_falls_back_to_vdf_when_no_acf` may already pass (current code reads vdf size) — that is fine; it locks in the fallback behavior.

- [ ] **Step 4: Replace `_read_app_name` with `_read_app_manifest`**

In `backend/app/services/game_libraries/steam.py`, replace the entire `_read_app_name` static method with:

```python
    @staticmethod
    def _read_app_manifest(steamapps: Path, app_id: str) -> tuple[Optional[str], Optional[int]]:
        """Return ``(name, size_on_disk_bytes)`` from ``appmanifest_<app_id>.acf``.

        Either element is ``None`` when the manifest is missing or the field is
        absent/unparseable. ``SizeOnDisk`` is Steam's authoritative installed size
        (the vdf ``apps`` tally is sometimes stale/zero).
        """
        acf = steamapps / f"appmanifest_{app_id}.acf"
        try:
            data = vdf.parse(acf.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None, None
        state = data.get("AppState")
        if not isinstance(state, dict):
            return None, None
        raw_name = state.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None
        size: Optional[int] = None
        raw_size = state.get("SizeOnDisk")
        if isinstance(raw_size, str):
            try:
                size = int(raw_size)
            except ValueError:
                size = None
        return name, size
```

- [ ] **Step 5: Update `_build_library` to use the manifest size with vdf fallback**

In `backend/app/services/game_libraries/steam.py`, replace the `_build_library` method (the version from Task 1) with:

```python
    def _build_library(self, lib_path: str, apps: dict) -> GameLibrary:
        steamapps = Path(lib_path) / "steamapps"
        games: List[GameEntry] = []
        total = 0
        for app_id, size_str in apps.items():
            name, acf_size = self._read_app_manifest(steamapps, str(app_id))
            display_name = name or f"App {app_id}"
            if _is_tool_app(display_name):
                continue
            if acf_size is not None and acf_size > 0:
                size = acf_size
            else:
                try:
                    size = int(size_str)
                except (TypeError, ValueError):
                    size = 0
            games.append(GameEntry(app_id=str(app_id), name=display_name, size_bytes=size))
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
```

- [ ] **Step 6: Run the full provider suite to verify all pass**

Run: `cd backend; python -m pytest tests/game_libraries/test_games_steam_provider.py -v`
Expected: PASS (all tests, including the two new size tests and the unchanged filter/predicate/dedup tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/game_libraries/steam.py backend/tests/game_libraries/test_games_steam_provider.py
git commit -m "fix(games): read game size from .acf SizeOnDisk (fixes 0 B entries)"
```

---

## Task 3: Frontend — proportional size bars in the game list

Render each game with a thin proportional bar scaled to the largest game in that library, plus a hover highlight. Only the expanded `<ul>` changes.

**Files:**
- Modify: `client/src/components/settings/GameLibrariesCard.tsx`

- [ ] **Step 1: Compute the per-library max size**

In `client/src/components/settings/GameLibrariesCard.tsx`, inside the `libraries.map((lib, idx) => { ... })` body, add a line immediately after `const open = !!openLibs[key];`:

```tsx
            const open = !!openLibs[key];
            const gamesMax = Math.max(...lib.games.map((g) => g.size_bytes), 1);
```

- [ ] **Step 2: Replace the game list rendering**

In the same file, replace the existing `{open && ( ... )}` block (the `<ul className="mt-3 space-y-1 ...">` and its contents) with:

```tsx
                {open && (
                  <ul className="mt-3 space-y-2 border-t border-slate-700/40 pt-3">
                    {lib.games.map((g) => (
                      <li
                        key={g.app_id}
                        className="rounded px-2 -mx-2 py-1.5 hover:bg-slate-800/30 transition-colors"
                      >
                        <div className="flex justify-between gap-2 text-xs sm:text-sm">
                          <span className="text-slate-300 truncate">{g.name}</span>
                          <span className="text-slate-400 tabular-nums shrink-0">{formatBytes(g.size_bytes)}</span>
                        </div>
                        <div className="mt-1 h-1 rounded-full bg-slate-700/30 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-indigo-500/50"
                            style={{ width: `${Math.max((g.size_bytes / gamesMax) * 100, 1)}%` }}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
```

The dynamic `style={{ width }}` mirrors the existing usage-bar pattern in `StorageTab.tsx`. `Math.max(..., 1)` keeps a sliver visible for very small games.

- [ ] **Step 3: Type-check**

Run: `cd client; npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/settings/GameLibrariesCard.tsx
git commit -m "feat(client): proportional size bars in game library list"
```

---

## Task 4: Final verification

- [ ] **Step 1: Backend — game_libraries suite + neighbors**

Run: `cd backend; python -m pytest tests/game_libraries/ -v`
Expected: all PASS.

Run: `cd backend; python -m pytest tests/ -k "games or mountpoint or storage_breakdown" --no-cov -q`
Expected: PASS (no regressions).

- [ ] **Step 2: Frontend — type check**

Run: `cd client; npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Confirm clean tree**

Run: `git status`
Expected: clean (all changes committed).

- [ ] **Step 4: (Optional) Manual prod check after deploy**

Settings → Storage: the small `/home/sven/.local/share/Steam` library (tools-only) should no longer appear; the `/mnt/cache-vcl/SteamLibrary` list should show no Proton/runtime/redist entries, Cyberpunk 2077 should show a real size (not 0 B), and each game row should have a proportional bar.

---

## Notes for the implementer

- **Two edits to `_build_library`:** Task 1 reorders it to filter tools (size still from vdf); Task 2 rewrites it again to use `_read_app_manifest` (size from `.acf SizeOnDisk`). Apply each task's final version verbatim — don't try to merge them ahead of time.
- **`_read_app_name` is removed in Task 2** (replaced by `_read_app_manifest`). Nothing else references it.
- **Fixture compatibility:** the extended `_make_library` keeps 2-tuple callers working; only the new size test uses a 3-tuple.
- **No scope creep:** do not touch schema, route, i18n, the dev mock, or add a scroll cap to the list.
