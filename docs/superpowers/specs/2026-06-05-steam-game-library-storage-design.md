# Spielbibliotheken in der Speichernutzung (Steam, erweiterbar)

**Datum:** 2026-06-05
**Status:** Spec — pending implementation plan
**Branch:** `feat/steam-game-library-storage`

## Problem

Die Prod-Box (BaluNode) dient zusätzlich als Linux-Gaming-System. Die große Steam-Bibliothek liegt auf `/mnt/cache-vcl/SteamLibrary` — derselben SSD, die auch den VCL-Cache hält. In der Speichernutzung (Settings → Storage) taucht dieser Platz aktuell unsichtbar im allgemeinen „belegt"-Topf auf; es gibt keine Möglichkeit zu sehen, wie viel Platz Spiele belegen oder welche Spiele wie groß sind.

### Empirischer Befund (auf Prod erhoben, 2026-06-05)

- **Service-User = `sven`** (das Backend läuft unter dem eigenen User, Gruppe `sven`). Voller Lesezugriff auf die Steam-Dateien bestätigt (`namei` zeigt durchgehende `x`/`r`-Rechte). → **Auto-Discovery ist ohne Permission-Workarounds möglich.**
- Zwei Bibliotheken laut `libraryfolders.vdf`:
  - `/home/sven/.local/share/Steam` — klein (Runtime + wenige Apps), Home-Partition.
  - `/mnt/cache-vcl/SteamLibrary` — der große Brocken (~530 GB installiert), auf der VCL-Cache-SSD.
- `libraryfolders.vdf` enthält pro Library bereits einen `apps`-Block (`"<appid>" "<bytes>"`) → Gesamtgröße **und** Größe pro Spiel ohne Verzeichnis-Scan.
- `appmanifest_<appid>.acf` liefert den Spielnamen (`"name"`) und `SizeOnDisk`.

## Goal

In Settings → Storage erscheint eine neue **Karte „Spielbibliotheken"** neben den bestehenden Karten für VCL-Quota und SSD-Cache. Sie zeigt:

- Pro erkannter Bibliothek: Pfad/Mountpoint, Gesamtgröße, Anzahl der Spiele.
- Eine **ausklappbare Drill-down-Liste** der einzelnen Spiele mit Name und Größe (absteigend sortiert).
- Einen klaren Leerzustand, wenn kein Launcher/keine Bibliothek erkannt wird.

Die Erkennung läuft **automatisch** (Steam-Metadaten parsen). Die Architektur ist als **Provider-Interface** angelegt, sodass Epic/Heroic, Lutris, GOG später als zusätzliche Provider andocken können — ohne API-Bruch.

## Non-Goals (v1)

- **Andere Launcher** (Epic/Heroic, Lutris, GOG) — nur die Provider-Naht wird gebaut, nicht die Implementierungen.
- **Manuelle Pfad-Konfiguration im UI** — Auto-Discovery reicht für den vorliegenden Fall; konfigurierbarer Override ist ein späterer Komfort.
- **Verzeichnis-Scan zur Größenbestimmung** — alle Größen kommen aus `libraryfolders.vdf`/`.acf`.
- **Einbau in den `compute_storage_breakdown`-Mountpoint-Donut** (cache/vcl/user_files) — bewusst nicht; die eigene Karte ist der Andockpunkt.
- **Spielverwaltung** (starten, löschen, verschieben) — read-only.
- **Historie/Sampling** der Spielgröße über Zeit.

## Entscheidungen (aus dem Brainstorming)

| Frage | Entscheidung |
|---|---|
| Granularität | Aggregat-Karte **+** Drill-down-Liste pro Spiel |
| Detektion | Auto-Discovery (Steam-Metadaten), Provider-Architektur |
| Launcher-Scope | Steam zuerst, generisch erweiterbar |
| Platzierung | Eigene Karte im Storage-Tab (kein Donut-Segment) |
| Zugriff | Alle eingeloggten User (`get_current_user`) |

## Architektur

```
Settings → Storage  (StorageTab.tsx)
  ├─ System Storage Ring        (bestehend)
  ├─ My Arrays + VCL Quota      (bestehend)
  ├─ SSD Cache                  (bestehend)
  └─ Spielbibliotheken  ← NEU   ──►  GET /api/games/libraries
                                       │
                                       ▼
                         services/game_libraries/service.py
                                       │  iteriert verfügbare Provider
                                       ▼
                         GameLibraryProvider (Protocol)
                                       │
                                       └─ SteamProvider  (vdf.py + .acf parsen)
```

### Backend

Neues Modul `backend/app/services/game_libraries/`:

**`provider.py`** — das erweiterbare Interface:

```python
from typing import Protocol
from app.schemas.games import GameLibrary

class GameLibraryProvider(Protocol):
    id: str            # "steam"
    name: str          # "Steam"
    def is_available(self) -> bool: ...
    def get_libraries(self) -> list[GameLibrary]: ...
```

Eine Registry-Liste `PROVIDERS: list[GameLibraryProvider] = [SteamProvider()]`. Ein weiterer Launcher = eine weitere Klasse in dieser Liste, sonst nichts.

**`vdf.py`** — minimaler Valve-KeyValues-Parser (stdlib only, ~30–40 Zeilen; **kein** `vdf`-PyPI-Paket — gemäß Repo-Regel „keine neuen Deps für kleine Features"). Tokenisiert quoted Strings und `{}`-Blöcke rekursiv zu verschachtelten Dicts. Muss das echte `libraryfolders.vdf`-Sample (siehe Befund) korrekt parsen, inkl. mehrerer Libraries und des `apps`-Blocks.

**`steam.py`** — `SteamProvider`:
- `_find_steam_roots()`: prüft Standardpfade relativ zum Service-User-`$HOME`:
  - `~/.steam/steam`, `~/.steam/root`, `~/.local/share/Steam`
  - Flatpak: `~/.var/app/com.valvesoftware.Steam/data/Steam`
  - Snap: `~/snap/steam/common/.local/share/Steam`
  - Windows (für Dev): `C:\Program Files (x86)\Steam`, `%ProgramFiles%\Steam`
  - **Realpath-Dedup**: `~/.steam/steam` und `~/.local/share/Steam` zeigen oft auf dieselbe Lib → über `os.path.realpath` deduplizieren, damit Spiele nicht doppelt gezählt werden.
- `is_available()`: True, wenn mindestens ein Root mit `steamapps/libraryfolders.vdf` existiert.
- `get_libraries()`: vdf parsen → pro Library-Eintrag:
  - `path`, `device_id = os.stat(path).st_dev`
  - `apps`-Map (appid → size_bytes); `total_bytes = sum(...)`
  - Pro Spiel: Name aus `steamapps/appmanifest_<appid>.acf` (`"name"`-Feld); fehlt die `.acf`, Fallback `f"App {appid}"`. Nur Apps mit vorhandener `.acf` gelten als installiert; reine vdf-Einträge ohne `.acf` werden mit Fallback-Namen geführt (Größe stammt ohnehin aus der vdf).
  - Defensive Fehlerbehandlung pro Library/Datei (eine kaputte `.acf` darf nicht die ganze Antwort kippen) — analog zum `try/except logger.debug`-Muster in `storage_breakdown.py`.

**`service.py`** — `get_game_libraries() -> GameLibrariesResponse`:
- iteriert `PROVIDERS`, ruft bei `is_available()` `get_libraries()` auf, sammelt und aggregiert.
- `available = any(p.is_available() for p in PROVIDERS)`.
- Dev-Mode (`settings.is_dev_mode`) ohne echte Steam-Installation: liefert eine kleine Mock-Library, damit die Windows-Dev-UI etwas rendert. Wenn auf der Dev-Box echtes Steam liegt, gewinnen die echten Daten.

**Mountpoint-Zuordnung:** `device_id` (st_dev) pro Library wird mitgeliefert, sodass das Frontend (oder ein späterer Donut-Einbau) eine Library demselben Gerät wie cache/vcl zuordnen kann. v1 zeigt zusätzlich den rohen `path`; eine Auflösung zu einem Mountpoint-Label ist optional und kann später ergänzt werden.

### Schema (`backend/app/schemas/games.py`)

```python
from pydantic import BaseModel

class GameEntry(BaseModel):
    app_id: str
    name: str
    size_bytes: int

class GameLibrary(BaseModel):
    provider: str          # "steam"
    provider_name: str     # "Steam"
    path: str              # "/mnt/cache-vcl/SteamLibrary"
    device_id: int | None  # st_dev, für Mountpoint-Matching
    total_bytes: int
    game_count: int
    games: list[GameEntry]  # absteigend nach size_bytes sortiert

class GameLibrariesResponse(BaseModel):
    libraries: list[GameLibrary]
    total_bytes: int        # Summe über alle Libraries
    available: bool         # mindestens ein Provider verfügbar
```

### Route (`backend/app/api/routes/games.py`)

```python
@router.get("/libraries", response_model=GameLibrariesResponse)
@user_limiter.limit(get_limit("system_monitor"))
def get_game_libraries(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_user),
) -> GameLibrariesResponse:
    """Erkannte Spielbibliotheken mit Größe pro Spiel."""
    return game_libraries_service.get_game_libraries()
```

Registrierung in `routes/__init__.py`: `api_router.include_router(games.router, prefix="/games", tags=["games"])`. Rate-Limit-Key `system_monitor` (existiert bereits) wiederverwenden — der Endpoint ist read-only und wird beim Öffnen des Storage-Tabs einmal aufgerufen.

### Frontend

**`client/src/api/games.ts`** — Typen (`GameEntry`, `GameLibrary`, `GameLibrariesResponse`) + `getGameLibraries(): Promise<GameLibrariesResponse>` über `apiClient.get('/api/games/libraries')`.

**`client/src/components/settings/GameLibrariesCard.tsx`** — neue Karte:
- Header „Spielbibliotheken" mit `Gamepad2`-Icon (lucide).
- Ladezustand (animate-pulse, wie die anderen Karten); Leerzustand wenn `available === false` oder `libraries.length === 0` („Keine Spielbibliothek erkannt").
- Pro Library: Provider-Badge (z. B. „Steam"), Pfad (truncate), `total_bytes`, `game_count`, und ein Ausklapp-Toggle (Collapse-Muster wie `MemoryTab.tsx`) für die Spielliste.
- Spielliste: `name` links (truncate), `formatBytes(size_bytes)` rechts, tabular-nums, absteigend.
- Styling konsistent mit den bestehenden Karten (`card border-slate-800/60 bg-slate-900/55 ...`), eigener Akzent-Farbton (z. B. cyan/indigo).

**`StorageTab.tsx`** — Karte nach dem SSD-Cache-Block einhängen; Daten via `getGameLibraries()` in einem eigenen `loadGameLibraries()` parallel zu den bestehenden Loads laden (eigener State, Fehler still schlucken wie bei `loadCacheOverview`).

**i18n** — `settings:storage.games.*` (de + en): Titel, „Spiele"/„Games", Leerzustand, „X Spiele", Ausklapp-Label. Beide Locale-Dateien pflegen.

### Performance

`libraryfolders.vdf` ist eine kleine Datei; die ~29 `.acf`-Reads sind triviale Einzeldatei-Opens, einmal pro Storage-Tab-Öffnung (lazy). Kein Verzeichnis-Scan, kein Polling. Kein Caching nötig in v1; falls später ein häufigerer Aufruf entsteht, ist ein kurzer In-Memory-TTL-Cache nachrüstbar.

## Testing (TDD)

**Backend** (`backend/tests/game_libraries/`):
- `test_vdf.py` — Parser gegen das echte `libraryfolders.vdf`-Sample (mehrere Libraries, `apps`-Block); Edge-Cases: leere Datei, fehlende `apps`.
- `test_steam_provider.py` — `SteamProvider.get_libraries()` mit Temp-Fixtures (vdf + ein paar `appmanifest_*.acf`): korrekte `total_bytes`, `game_count`, Namen aus `.acf`, Fallback-Name bei fehlender `.acf`, `device_id` gesetzt, Realpath-Dedup zweier Roots auf dieselbe Lib. `is_available()` true/false.
- `test_service.py` — Aggregation über Provider, `available`-Flag, Dev-Mock-Pfad.
- `test_games_route.py` — `GET /api/games/libraries` mit Auth: 200 + Schema, 401 ohne Token.

**Frontend**:
- `npx tsc --noEmit` grün.
- Optional: kleiner Vitest für `api/games.ts`-Mapping bzw. ein Render-Smoke der Karte (Leerzustand + mit Daten), falls das vorhandene Vitest-Setup das hergibt.

## Betroffene/neue Dateien

**Neu:**
- `backend/app/services/game_libraries/__init__.py`
- `backend/app/services/game_libraries/provider.py`
- `backend/app/services/game_libraries/vdf.py`
- `backend/app/services/game_libraries/steam.py`
- `backend/app/services/game_libraries/service.py`
- `backend/app/schemas/games.py`
- `backend/app/api/routes/games.py`
- `backend/tests/game_libraries/` (Tests + Fixtures)
- `client/src/api/games.ts`
- `client/src/components/settings/GameLibrariesCard.tsx`

**Geändert:**
- `backend/app/api/routes/__init__.py` (Route registrieren)
- `client/src/components/settings/StorageTab.tsx` (Karte einhängen + Load)
- `client/src/i18n/locales/de/settings.json`, `.../en/settings.json` (Strings)
- ggf. `backend/app/services/CLAUDE.md` (neues Submodul dokumentieren)

## Offene Punkte / Risiken

- **Dev-Mock-Form**: genaue Gestalt der Mock-Library im Dev-Mode wird im Plan festgelegt (1 Library, 2–3 Beispielspiele).
- **Mountpoint-Label**: v1 zeigt den rohen Pfad; eine hübsche Mountpoint-Zuordnung über `device_id` ist optionaler Folgeschritt.
- **Nicht-Spiele-Apps** (z. B. „Steam Linux Runtime", Proton): werden als reguläre Apps gelistet. Filtern wäre möglich, ist aber v1 bewusst nicht enthalten (YAGNI); ggf. später per Tool-Appid-Blocklist.
