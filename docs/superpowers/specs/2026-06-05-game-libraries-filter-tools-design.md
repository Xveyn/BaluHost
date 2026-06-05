# Spielbibliotheken: Tools filtern, korrekte Größen, schönere Liste

**Datum:** 2026-06-05
**Status:** Spec — pending implementation plan
**Branch:** `feat/game-libraries-filter-tools`

## Problem

Die in PR #161 eingeführte Spielbibliothek-Anzeige (`backend/app/services/game_libraries/steam.py` + `client/src/components/settings/GameLibrariesCard.tsx`) hat nach dem ersten Live-Test drei Schwächen:

1. **Tools/Runtimes werden als Spiele gelistet:** `Steamworks Common Redistributables`, `Steam Linux Runtime 1.0/2.0/3.0/4.0`, `Proton Experimental/7.0/8.0/9.0/10.0/Hotfix`. Sie verfälschen Liste und Gesamtgröße. Die kleine Home-Library (`/home/sven/.local/share/Steam`) besteht **ausschließlich** aus solchen Tools und sollte komplett verschwinden.
2. **Falsche Größen (0 B):** Manche Spiele (live beobachtet: `Cyberpunk 2077`, appid `1091500`) werden mit `0 B` angezeigt. Ursache: die Größe stammt aus dem `apps`-Block der `libraryfolders.vdf`, der für einzelne Apps `"0"` enthält (Steams Update-Tally, teils stale). Die autoritative Größe steht im `.acf` unter `SizeOnDisk`.
3. **Liste optisch karg:** reine Name/Größe-Zeilen ohne visuelle Proportion.

## Goal

- Tool-/Runtime-Apps verschwinden aus Liste **und** zählen nicht zu `total_bytes`/`game_count`. Reine Tools-Bibliotheken fallen ganz weg.
- Spielgrößen sind korrekt (kein fälschliches 0 B), Quelle ist `.acf SizeOnDisk` mit vdf-Fallback.
- Die ausgeklappte Liste zeigt pro Spiel einen **Proportional-Balken** (skaliert zum größten Spiel der Library) plus Hover-Highlight.

## Non-Goals

- Kein konfigurierbarer Filter / kein Whitelisting einzelner Tools (YAGNI).
- Keine AppID-Blocklist (Name-Heuristik gewählt — zukunftssicher gegen neue Proton-/Runtime-Versionen).
- Keine Änderung an Schema, Route, i18n oder dem Dev-Mock.
- Keine Scroll-/Höhenbegrenzung der Liste (auch lange Listen werden voll ausgeklappt — Status quo).

## Entscheidungen (aus dem Brainstorming)

| Frage | Entscheidung |
|---|---|
| Tool-Erkennung | Name-Heuristik (kein AppID-Blocklist) |
| Tool-Bytes in `total_bytes`/`game_count`? | Nein — Spiele-only Total |
| Reine Tools-Library | Komplett ausblenden (bestehende `game_count > 0`-Logik) |
| Größenquelle | `.acf SizeOnDisk`, Fallback auf vdf-`apps`-Wert |
| Listen-Stil | Proportional-Balken pro Zeile + Hover-Highlight |

---

## Backend (`backend/app/services/game_libraries/steam.py`)

### 1. Tool-Erkennung — neue Hilfsfunktion

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

Deckt ab: `Proton …` (7.0/8.0/9.0/10.0/Experimental/Hotfix/EasyAntiCheat Runtime/BattlEye Runtime), `Steam Linux Runtime …` (1.0 scout/2.0 soldier/3.0 sniper/4.0), exakt `Steamworks Common Redistributables`.

### 2. Größenquelle — `.acf SizeOnDisk` mit vdf-Fallback

`_read_app_name` wird zu `_read_app_manifest`, das Name **und** Größe aus einem `.acf`-Parse liefert:

```python
@staticmethod
def _read_app_manifest(steamapps: Path, app_id: str) -> tuple[Optional[str], Optional[int]]:
    """Return ``(name, size_on_disk_bytes)`` from ``appmanifest_<app_id>.acf``.

    Either element is ``None`` when the manifest is missing or the field is
    absent/unparseable. ``SizeOnDisk`` is Steam's authoritative installed size.
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

### 3. Anwendung — in `_build_library`

Name+Größe aus dem Manifest holen, Tools überspringen, Größe bevorzugt aus `SizeOnDisk` (sonst vdf-Wert):

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

`games`, `total_bytes` und `game_count` enthalten dadurch nur echte Spiele. Die bestehende Zeile `if lib.game_count > 0: libraries.append(lib)` in `get_libraries()` blendet reine Tools-Bibliotheken unverändert ganz aus.

### Bewusste Konsequenzen

- `total_bytes` ist Spiele-only (weicht absichtlich von der reinen `steamapps`-Disk-Belegung ab — gewünscht).
- Apps ohne `.acf` → Fallback-Name `App <id>` (matcht keine Tool-Muster, wird als Spiel geführt) und Größe aus dem vdf-Wert. In der Praxis unkritisch, da installierte Apps immer ein `.acf` haben.
- False-Positive-Risiko der Heuristik gering: kein bekanntes echtes Spiel beginnt mit „Proton"/„Steam Linux Runtime".

---

## Frontend (`client/src/components/settings/GameLibrariesCard.tsx`)

Nur die ausgeklappte Spielliste (`<ul>`) wird umgebaut. Pro Library `maxSize` einmal berechnen:

```tsx
const maxSize = Math.max(...lib.games.map((g) => g.size_bytes), 1);
```

Jede Spielzeile: Name + Größe in einer Zeile, darunter ein dünner Proportional-Balken; Zeile mit Hover-Highlight:

```tsx
{lib.games.map((g) => (
  <li key={g.app_id} className="rounded px-2 -mx-2 py-1.5 hover:bg-slate-800/30 transition-colors">
    <div className="flex justify-between gap-2 text-xs sm:text-sm">
      <span className="text-slate-300 truncate">{g.name}</span>
      <span className="text-slate-400 tabular-nums shrink-0">{formatBytes(g.size_bytes)}</span>
    </div>
    <div className="mt-1 h-1 rounded-full bg-slate-700/30 overflow-hidden">
      <div
        className="h-full rounded-full bg-indigo-500/50"
        style={{ width: `${Math.max((g.size_bytes / maxSize) * 100, 1)}%` }}
      />
    </div>
  </li>
))}
```

Der dynamische `style={{ width }}` folgt dem bestehenden Muster der Usage-Bars in `StorageTab.tsx` (Inline-Width ist dort etabliert). `bg-indigo-500/50` bleibt im Akzent-Ton der Karte. `Math.max(..., 1)` lässt auch sehr kleine Spiele einen sichtbaren Strich behalten; bei `size_bytes === 0` (sollte nach dem Größen-Fix selten sein) ist der Balken minimal.

---

## Tests (TDD)

### Backend — `backend/tests/game_libraries/test_games_steam_provider.py`

`_make_library` muss um `SizeOnDisk` im `.acf` ergänzt/parametrisierbar sein, damit vdf-Größe und `.acf`-Größe **unterschiedlich** sein können (für den 0-B-Fix-Test). Bestehende Tests bleiben grün (Fixtures schreiben `SizeOnDisk == vdf-Größe`).

1. **`test_is_tool_app`** — Predicate direkt: True für `"Proton 8.0"`, `"Proton Experimental"`, `"Proton EasyAntiCheat Runtime"`, `"Steam Linux Runtime 3.0 (sniper)"`, `"STEAMWORKS COMMON REDISTRIBUTABLES"` (Case-insensitive); False für `"Counter-Strike 2"`, `"Cyberpunk 2077"`, `"App 12345"`.
2. **Tool-Filter** — gemischte Library (2 Spiele + 2 Tools): `games` enthält nur die 2 Spiele, `game_count == 2`, `total_bytes == Summe der 2 Spiele` (Tool-Bytes nicht enthalten).
3. **Tools-only-Library wird gedroppt** — Library mit ausschließlich Tools → `get_libraries()` liefert sie nicht.
4. **Größe aus `SizeOnDisk`** — App mit vdf-`apps`-Größe `0`, aber `.acf SizeOnDisk` = echte Größe → `GameEntry.size_bytes` == echte Größe (deckt den Cyberpunk-0-B-Fall ab).
5. **vdf-Fallback ohne `.acf`** — App ohne `.acf` → Name `App <id>`, Größe aus vdf-`apps`-Wert (Verhalten wie bisher).

### Frontend

- `cd client && npx tsc --noEmit` grün. Optional kleiner Render-Smoke der Balken (max-Skalierung, Hover-Klassen vorhanden), falls das Vitest-Setup es hergibt.

## Betroffene Dateien

- Geändert: `backend/app/services/game_libraries/steam.py` (Tool-Predicate + Filter + `.acf SizeOnDisk`-Größe)
- Geändert: `backend/tests/game_libraries/test_games_steam_provider.py` (Fixture-Erweiterung + 5 Tests)
- Geändert: `client/src/components/settings/GameLibrariesCard.tsx` (Proportional-Balken-Liste + Hover)
