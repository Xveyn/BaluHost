# Spielbibliotheken: Proton/Runtime-Tools herausfiltern

**Datum:** 2026-06-05
**Status:** Spec — pending implementation plan
**Branch:** `feat/game-libraries-filter-tools`

## Problem

Die in PR #161 eingeführte Spielbibliothek-Anzeige (`backend/app/services/game_libraries/steam.py`) listet **alle** Apps aus `libraryfolders.vdf` als „Spiele" — inklusive Steam-Tools und -Runtimes, die keine Spiele sind: `Steamworks Common Redistributables`, `Steam Linux Runtime 1.0/2.0/3.0`, `Proton Experimental/7.0/8.0/…`. Diese verfälschen sowohl die Spielliste als auch die ausgewiesene Bibliotheks-Gesamtgröße.

## Goal

Tool-/Runtime-Apps werden aus der Spielbibliothek-Anzeige entfernt: sie erscheinen nicht in der Spielliste und zählen nicht zu `total_bytes` / `game_count`. Eine Bibliothek, die nach dem Filtern keine echten Spiele mehr enthält, verschwindet komplett (greift über die bestehende `game_count > 0`-Logik).

## Non-Goals

- Kein konfigurierbarer Filter / keine UI zum Whitelisten einzelner Tools (YAGNI).
- Keine AppID-Blocklist (Name-Heuristik gewählt — zukunftssicher gegen neue Proton-/Runtime-Versionen).
- Keine Änderung an Schema, Route, Frontend, i18n oder dem Dev-Mock.

## Entscheidungen (aus dem Brainstorming)

| Frage | Entscheidung |
|---|---|
| Erkennung | Name-Heuristik (kein AppID-Blocklist) |
| Tool-Bytes in `total_bytes`/`game_count`? | Nein — Spiele-only Total |

## Ansatz

Reiner Backend-Change, ausschließlich in `backend/app/services/game_libraries/steam.py`.

### Erkennung — neue Hilfsfunktion

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

Deckt ab:
- `Proton …` → `Proton 7.0`, `Proton 8.0`, `Proton Experimental`, `Proton Hotfix`, `Proton EasyAntiCheat Runtime`, `Proton BattlEye Runtime`
- `Steam Linux Runtime …` → `1.0 (scout)`, `2.0 (soldier)`, `3.0 (sniper)`
- exakt `Steamworks Common Redistributables`

### Anwendung — in `_build_library`

Im Schleifenkörper über `apps.items()` zuerst den Namen ermitteln (wie bisher), dann Tool-Apps überspringen — **bevor** ein `GameEntry` erzeugt und `total` aufaddiert wird:

```python
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
```

Dadurch enthalten `games`, `total_bytes` (= `total`) und `game_count` (= `len(games)`) nur echte Spiele. Die bestehende Zeile `if lib.game_count > 0: libraries.append(lib)` in `get_libraries()` sorgt unverändert dafür, dass eine reine Tools-Bibliothek (z. B. die kleine Home-Lib, die nur Redist/Runtime/Proton enthält) ganz wegfällt.

### Bewusste Konsequenzen

- `total_bytes` weicht absichtlich von der reinen `steamapps/common`-Disk-Belegung ab (Spiele-only, gewünscht).
- Apps **ohne** `.acf` erhalten den Fallback-Namen `App <id>`, der keine Tool-Muster matcht → werden weiter als Spiel geführt. Tools haben in der Praxis immer ein `.acf` mit erkennbarem Namen, daher unkritisch.
- False-Positive-Risiko gering: kein bekanntes echtes Spiel beginnt mit „Proton" oder „Steam Linux Runtime".

## Tests (TDD)

Ergänzung in `backend/tests/game_libraries/test_games_steam_provider.py`:

1. **Predicate-Test** `test_is_tool_app`:
   - True für `"Proton 8.0"`, `"Proton Experimental"`, `"Proton EasyAntiCheat Runtime"`, `"Steam Linux Runtime 3.0 (sniper)"`, `"Steamworks Common Redistributables"` (auch in abweichender Groß/Kleinschreibung).
   - False für echte Spielnamen (`"Counter-Strike 2"`, `"Cyberpunk 2077"`) und für den Fallback `"App 12345"`.
2. **Provider-Filter-Test** mit gemischter Fixture (2 echte Spiele + 2 Tools in einer Library):
   - `games` enthält nur die 2 echten Spiele (keine Tool-Namen).
   - `game_count == 2`, `total_bytes == Summe der 2 Spiele` (Tool-Bytes nicht enthalten).
3. **Tools-only-Library wird gedroppt** (eine Library, deren Apps ausschließlich Tools sind → `get_libraries()` liefert sie nicht zurück).

## Betroffene Dateien

- Geändert: `backend/app/services/game_libraries/steam.py` (Hilfsfunktion + Filter in `_build_library`)
- Geändert: `backend/tests/game_libraries/test_games_steam_provider.py` (3 Tests ergänzt)
