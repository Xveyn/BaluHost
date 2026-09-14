# Steam-Spiele aus BaluApp starten — Design

**Datum:** 2026-09-14 (überarbeitet nach Review am selben Tag)
**Status:** Überarbeitet nach drei Reviews (Code-Fakten, Sicherheit, Design)
**Umfang dieser Spec:**
- **PR A — #640:** Steam-Start aus dem Backend über `systemd-run --user` (Vorab-PR, eigenständig verifizierbar)
- **PR B — Feature:** Recht `can_launch_games`, Routen im `steam_gaming`-Plugin, Rechte-Schalter
- **Teil 2 — BaluApp:** eigenes Repo `Xveyn/BaluApp`, eigene Spec; hier nur als Vertrag

## Ziel

Ein Nutzer mit dem Recht `can_launch_games` wählt in BaluApp ein installiertes
Steam-Spiel und startet es auf BaluNode. Der Start schaltet die Bildschirme ein,
entsperrt die Session (sofern der Nutzer das darf), öffnet Big Picture und startet
dann das Spiel. Das bestehende Session-Tracking (Pill, Ledger, Notifications,
Dashboard-Panel) läuft unverändert mit.

**Nicht im Umfang:** Web-UI von BaluHost (außer dem Rechte-Schalter), Spiele ohne
Steam-Client, Nicht-Steam-Spiele, Spielcover, laufendes Spiel beenden.

## Messungen (BaluNode, 2026-09-14, SSH als `sven`)

Alle mit **beobachteter Wirkung** auf dem Bildschirm, nicht nur Exit-Code.

| # | Zustand | Aufruf | Ergebnis |
|---|---|---|---|
| M1 | Steam läuft | `steam steam://rungameid/400` ohne Session-Env | Portal startet; `reaper SteamLaunch AppId=400` sichtbar |
| M2 | Steam gestoppt | derselbe Aufruf ohne `DISPLAY` | `Unable to open X11 display, exiting` — kein Start |
| M3 | Steam gestoppt | mit `DISPLAY=:0` + `XAUTHORITY=/run/user/1000/xauth_*` | Steam startet kalt, Portal sichtbar |
| M4 | Steam gestoppt | `steam://open/bigpicture` und `steam://rungameid/400` direkt nacheinander | Steam, Big Picture und Portal kommen; der zweite Prozess meldet `Steam is already running, exiting (command line was forwarded)` |
| M5 | Steam gestoppt | `env -i HOME=/home/sven XDG_RUNTIME_DIR=/run/user/1000 PATH=/usr/bin:/bin systemd-run --user --collect steam steam://rungameid/400` | Steam startet kalt, Portal sichtbar |

Zusätzlich: `systemctl --user show-environment` enthält `DISPLAY=:0` und
`DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus` (von KDE importiert), aber
**kein** `XAUTHORITY` — M5 funktioniert trotzdem.

Folgerungen:
- `steam://rungameid` ist der Startweg; der `reaper`-Wrapper und damit das Tracking bleiben erhalten.
- Steam wird **im User-Manager** gestartet (M5), nicht als Kindprozess des Backends — siehe PR A.
- Kein Warten auf „Steam bereit" nötig (M4).
- **Offen:** M1–M5 liefen per SSH. Der Service-Kontext (`User=sven`, `PrivateTmp=true`) wird nach dem Deploy von PR A mit beobachteter Wirkung verifiziert, bevor PR B startet.

---

## PR A — Steam-Start über `systemd-run --user` (#640)

### Problem

`launcher._dispatch` startet heute `Popen(["steam", url], env=wayland_session_env())`.
Läuft Steam nicht, wird der Aufruf selbst zum Steam-Client, und der

1. scheitert ohne X11 (M2);
2. **erbt die Backend-Umgebung** — `wayland_session_env()` beginnt mit
   `dict(os.environ)`, und `baluhost-backend.service` lädt `.env.production`
   (`SECRET_KEY`, `TOKEN_SECRET`, `DATABASE_URL`, `VPN_ENCRYPTION_KEY`). Jedes
   Spiel, jeder Crash-Reporter und jedes Anti-Cheat erbt sie;
3. liegt in der **cgroup des Backend-Service** — jeder Deploy-Neustart beendet
   Steam samt laufendem Spiel;
4. läuft unter **`PrivateTmp=true`** der Unit.

Heute verdeckt, weil Steam per `app-steam@autostart.service` dauerhaft läuft.

### Lösung

`launcher._dispatch(url, what)`:

```python
_STEAM_RUN_TIMEOUT_SECONDS = 10
_ENV_ALLOWLIST = ("HOME", "USER", "LOGNAME", "PATH", "LANG",
                  "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")

def _user_manager_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env

argv = ["systemd-run", "--user", "--collect", "--quiet", "steam", url]
subprocess.run(argv, env=_user_manager_env(), timeout=_STEAM_RUN_TIMEOUT_SECONDS,
               stdin=DEVNULL, stdout=DEVNULL, stderr=PIPE, check=False)
```

- **Warum `systemd-run --user`:** Die Unit läuft im User-Manager von `sven` —
  eigene cgroup (überlebt Backend-Neustarts), kein `PrivateTmp`, und sie bekommt
  die **Umgebung des User-Managers**, nicht die des Aufrufers. `DISPLAY` stammt
  von KDE (M5).
- **Allowlist auch für den `systemd-run`-Prozess selbst:** Er ist kurzlebig, aber
  es gibt keinen Grund, ihm Secrets zu geben. `XDG_RUNTIME_DIR` braucht er, um
  den User-Manager zu finden.
- **`run` statt `Popen`:** `systemd-run` kehrt zurück, sobald die transiente Unit
  angelegt ist. Der Returncode ist damit beobachtbar — z. B. „kein User-Manager"
  (niemand angemeldet) → `(False, "steam could not be started")`, Detail
  (`stderr`, gekürzt) nur ins Log. Er sagt weiterhin **nicht**, ob Big Picture
  oder das Spiel erscheint.
- **Kein fester Unit-Name:** Bei laufendem Steam endet die Unit sofort (Befehl
  weitergeleitet); bei Kaltstart lebt sie so lange wie Steam. Ein fester Name
  würde beim zweiten Aufruf mit „unit already exists" scheitern.
- Fehlerfälle: `FileNotFoundError` → `"systemd-run not found"`;
  `TimeoutExpired` → `"steam could not be started"`; Returncode ≠ 0 → dito.
- Dev-Modus: unverändert no-op.
- `services/power/session_env.py` bleibt **unverändert** (Konsumenten
  `desktop_backend`, `desktop_windows`, `audio_control/pactl`,
  `display_output/kscreen` brauchen weiter `WAYLAND_DISPLAY`); `launcher.py`
  importiert es nicht mehr. Docstring „Two callers" in `session_env.py` wird
  auf die tatsächlichen Konsumenten korrigiert.
- `launcher.py`-Modul-Docstring: „detached"-Begründung ersetzen durch die
  User-Manager-Begründung.

### Tests (`backend/tests/plugins/test_steam_gaming_launcher.py`)

- argv ist exakt `["systemd-run", "--user", "--collect", "--quiet", "steam", URL]` für open und close; nie `shell`.
- `env` enthält keine Nicht-Allowlist-Variable: `monkeypatch.setenv("SECRET_KEY", "x")` → nicht im übergebenen `env`.
- `XDG_RUNTIME_DIR` fehlt in `os.environ` → wird aus der uid gesetzt (uid per Monkeypatch; `os.getuid` fehlt auf Windows).
- `timeout=10` wird übergeben; `TimeoutExpired`, `FileNotFoundError`, Returncode 1 → `ok=False`, keine Exception, keine `stderr`-Interna im `detail`.
- Dev-Modus: `subprocess.run` ungerufen.
- Die bestehenden Tests, die `subprocess.Popen` patchen, werden auf `subprocess.run` umgestellt.

### Verifikation nach Deploy (Pflicht, beobachtete Wirkung)

1. `steam -shutdown`, dann im Power-Menü „Gaming Mode" → Steam startet in Big Picture.
2. `sudo systemctl restart baluhost-backend` → Steam läuft weiter (`pgrep -c -x steam` > 0).
3. `cat /proc/$(pgrep -x steam | head -1)/environ | tr '\0' '\n'` enthält kein `SECRET_KEY`.

Erst wenn 1–3 gelten, startet PR B.

---

## PR B — Spielstart-Feature

### Architektur

Routen im bundled Plugin `steam_gaming`. Dort liegen Erkennung, Launcher,
Gaming-Mode-Ablauf und Marker.

**Router in einem bisher router-losen Plugin.** Plugin-Router werden nur beim
Start gemountet (`core/lifespan.py`, `PluginManager.get_router()`). Nach dem
Deploy unkritisch (Neustart, Plugin in Prod aktiv). Wird das Plugin später
erst nach dem Start aktiviert, landen Anfragen im Catch-all-Proxy und bekommen
`404 "Plugin not found"` (`plugins/sandbox/proxy.py:55`), bis das Backend neu
startet; `PluginDetailResponse.restart_required` zeigt das an. Pill, Menü,
Panel und Notifications wirken weiterhin sofort.

### Dateien

**Neu**
- `steam_gaming/routes.py` — Router, `_audit`. **Ohne** `from __future__ import annotations`: hinter `@user_limiter.limit` bricht der Future-Import die Body-Erkennung von slowapi (siehe `bluetooth/__init__.py:7-11`). Eigene Datei, weil `__init__.py` schon ~470 Zeilen hat (#301).
- `steam_gaming/launch.py` — `start_gaming_mode()` (gemeinsamer Ablauf) und `launch_game()`.
- `steam_gaming/library.py` — `list_installed_games()`, `find_installed_game(app_id)`.
- `steam_gaming/models.py` — Pydantic-Modelle der Routen (Name wie in `bluetooth`, `audio_control`, `display_output`); ebenfalls ohne Future-Import.
- `backend/alembic/versions/<rev>_add_can_launch_games_permission.py`
- Tests: `test_steam_gaming_routes.py`, `test_steam_gaming_launch.py`, `test_steam_gaming_library.py`, `test_power_permissions_launch_games.py`

**Geändert**
- `steam_gaming/__init__.py` — `get_router()` importiert `routes` **spät** (vermeidet den Zyklus `__init__` → `routes` → `launch` → `__init__`); `run_menu_action` delegiert an `launch.start_gaming_mode()`.
- `steam_gaming/launcher.py` — `launch_game(app_id)` über `_dispatch`.
- `steam_gaming/detection.py` — `current_app_id(*, dev_stand_in: bool = True)`.
- `services/game_libraries/steam.py` — `_is_tool_app` → öffentlich `is_tool_app` (Alias oder Umbenennung inkl. Aufrufer).
- `models/power_permissions.py`, `schemas/power_permissions.py` (Response, Update, MyResponse), `services/power_permissions.py` (Map, `get_permissions`, Update-Zweig, beide Audit-Dicts, Docstring von `check_permission`), `api/deps.py`, `api/routes/sleep.py` (beide Konstruktionen)
- `core/rate_limiter.py` — zwei Kategorien
- `tests/plugins/test_steam_gaming_plugin.py` — Patch-Ziele umziehen (siehe Tests)
- Frontend: `client/src/api/powerPermissions.ts` (drei Interfaces), `components/user-management/PowerPermissionsSection.tsx` (`FIELD_TO_I18N`, `PERMISSION_TOGGLES`, Icon `Gamepad2`), `i18n/locales/{de,en}/admin.json`
- Doku: `steam_gaming/CLAUDE.md` (Layout-Tabelle, „No router"-Absatz, Gaming-Mode-Abschnitt mit gemeinsamem Helfer und Worst-Case-Laufzeit), `plugins/CLAUDE.md` (Plugin-Liste), `services/CLAUDE.md` / `models/CLAUDE.md` / `api/CLAUDE.md` (Recht und Abhängigkeit), Root-`CLAUDE.md` Quick Reference, `.claude/rules/architecture.md` (API-Liste), `.claude/rules/security-agent.md` (Rollenmodell)

### Berechtigung `can_launch_games`

Nach dem Vorbild `can_manage_bluetooth` (Migration `e7c2a9d41f86`):
- Spalte `Boolean, nullable=False, default=False, server_default="0"`.
- Migration additiv, kettet an den echten Head **`19b0fbf9df31`** (`python -m alembic heads`, 2026-09-14). Vor dem Anlegen erneut prüfen.
- `_ACTION_FIELD_MAP["launch_games"] = "can_launch_games"`; **keine Implikation**, insbesondere nicht `can_unlock_session`.
- `require_power_launch_games = _make_power_dependency("launch_games")`.
- `my-permissions`: `True` für Admins, sonst aus der DB.

**Was das Recht faktisch erlaubt (in `security-agent.md` festzuhalten):** Spiele
starten **und dabei** die Bildschirme einschalten und Big Picture öffnen —
ohne `can_toggle_desktop`. Das ist der Zweck des Features. Entsperren bleibt
bei `can_unlock_session`.

**API-Keys** (`balu_*`, ohne Scopes/TTL) erreichen die Routen wie alle anderen
`require_power_*`-Routen. Bewusst akzeptiert und dokumentiert; die LAN-Prüfung
gilt auch für sie.

### Bibliothek (`library.py`)

Eigene, manifestbasierte Sicht statt `get_game_libraries()`, weil jene
Provider-Fehler verschluckt (`service.py:42`), IDs aus `libraryfolders.vdf`
übernimmt (auch ohne Manifest, als `"App <id>"`) und alle Größen liest.

```python
_APP_ID_RE = re.compile(r"[0-9]{1,10}")      # re.fullmatch — kein \d (Unicode), kein $ (\n)
_NAME_MAX = 200

@dataclass(frozen=True)
class InstalledGame:
    app_id: str
    name: str

class LibraryUnavailable(Exception): ...

def list_installed_games() -> list[InstalledGame]: ...
def find_installed_game(app_id: str) -> Optional[InstalledGame]: ...
```

- Quelle: `game_libraries.steam.find_steamapps_dirs()` (Roots **und** Bibliotheken aus `libraryfolders.vdf`).
- **Installiert = `appmanifest_<id>.acf` existiert** und liefert einen Namen. Kein Manifest → nicht startbar.
- ID aus dem Dateinamen, geprüft mit `_APP_ID_RE.fullmatch`; Name aus dem Manifest, auf 200 Zeichen gekürzt; `is_tool_app(name)` → ausgeschlossen.
- Dedupliziert nach `app_id`, sortiert nach `name.casefold()`.
- `find_installed_game` liest **gezielt eine** Datei pro Bibliothek (`appmanifest_<id>.acf`), kein Verzeichnis-Scan.
- Kein `steamapps`-Verzeichnis gefunden → `LibraryUnavailable` (Route: `503`). Im Dev-Modus stattdessen eine feste Mock-Liste (Cyberpunk 2077 `1091500`, Dota 2 `570`, Counter-Strike 2 `730`).
- `list_installed_games()` hat einen **Per-Worker-Cache mit 30 s TTL** (wie `_CACHE` in `detection`); `find_installed_game` liest immer frisch.
- Alles blockierend → Aufruf nur via `asyncio.to_thread`.

### API

Prefix `/api/plugins/steam_gaming`.

| Methode | Pfad | Antwort | Recht | LAN | Rate-Limit |
|---|---|---|---|---|---|
| GET | `/games` | `GameListResponse` | `require_power_launch_games` | — | `steam_games_read` `60/minute` |
| POST | `/games/{app_id}/launch` | `202 LaunchResponse` | `require_power_launch_games` | **ja** | `steam_launch` `6/minute` |

```python
class LaunchableGame(BaseModel):
    app_id: str
    name: str

class RunningGame(BaseModel):
    app_id: str
    name: Optional[str]

class GameListResponse(BaseModel):
    games: list[LaunchableGame]
    running: Optional[RunningGame]
    can_launch_here: bool              # is_private_or_local_ip(client_host) — Information, keine Kontrolle

class LaunchResponse(BaseModel):
    status: Literal["requested"]
    session_locked: Optional[bool]     # current_lock_state() nach dem Ablauf; None = unbekannt
```

- `running` in **beiden** Routen aus `current_app_id(dev_stand_in=False)` +
  `resolve_game_name()`. Auf Linux identisch mit dem heutigen Verhalten; auf dem
  Windows-Dev-Rechner `None`, sodass GET und POST dasselbe sehen.
- `GET /games` ohne LAN-Prüfung: Lesen schafft kein Vertrauen; hinter dem Recht,
  weil Bibliothek und laufendes Spiel Information über den Box-Besitzer sind.
- Getrennte Rate-Limits, damit das Nachfragen nach einem Start nicht das
  Start-Budget verbraucht.

### Startablauf

**Prüfungen im POST, in dieser Reihenfolge — alle vor jedem Seiteneffekt:**

1. **Recht** — Abhängigkeit (auditiert Ablehnungen selbst).
2. **LAN/VPN** — `is_private_or_local_ip(request.client.host)` für alle Rollen,
   sonst `ForbiddenError("Launching is only allowed from the local network")` +
   Audit `steam_game_launch_denied` (`reason: not_local`).
3. **`app_id`** — `_APP_ID_RE.fullmatch`, sonst `NotFoundError("Game not installed")`.
4. **Bibliothek** — `find_installed_game(app_id)`; `LibraryUnavailable` →
   `ServiceUnavailableError("Game library unavailable")`; `None` →
   `NotFoundError("Game not installed")`.
5. **Laufendes Spiel** — `current_app_id(dev_stand_in=False)` nicht `None` →
   `ConflictError("A game is already running")`.

**Ausführung:**

```python
@dataclass(frozen=True)
class GamingModeStart:
    ok: bool
    failed_step: Optional[Literal["displays", "steam"]]
    detail: str                        # nur fürs Log

async def start_gaming_mode(*, user: Optional[UserPublic], client_host: Optional[str],
                            db) -> GamingModeStart:
    # 1. await get_desktop_service().enable()            — Fehler → ok=False, "displays"
    # 2. if user is not None: await unlock_if_permitted(user=..., client_host=..., db=...)
    #                                                     — Ablehnung ist KEIN Abbruch
    # 3. await to_thread(open_big_picture)                — Fehler → ok=False, "steam"
    # 4. await to_thread(gaming_state.mark_started)
```

- `run_menu_action` übersetzt `GamingModeStart` in die bisherigen Keys
  (`menu_displays_failed`, `menu_steam_failed`, `menu_gaming_mode_started`) und
  behält den `user is None`-Zweig (kein Entsperrversuch).
- Die Route ruft danach 5. `await to_thread(launch_game, game.app_id)` — **mit der
  ID aus dem Bibliothekseintrag**, nicht dem Request-String.
- Danach `session_locked = await current_lock_state()`.

**Kein äußerer Timeout.** `asyncio.wait_for` bricht nur das `await` ab; der Thread
liefe weiter — ein Entsperren ohne Audit (#643) oder ein Spielstart trotz
Fehlerantwort wären die Folge. Stattdessen begrenzen die Schritte sich selbst:

| Schritt | eigenes Limit | Quelle |
|---|---|---|
| Bildschirme | 30 s | `LinuxDesktopBackend._run` (`desktop_backend.py:73`) |
| Entsperren | ~15 s Worst Case | `session_lock` (Poll + loginctl) |
| Big Picture | 10 s | PR A |
| Spiel | 10 s | PR A |
| Sperrstatus | ~3 s | `current_lock_state` |

**Worst Case ≈ 70 s**, typisch < 3 s. nginx lässt `/api/` 300 s zu
(`deploy/install/templates/baluhost-nginx-http.conf:102`). BaluApp setzt für den
POST ein Client-Timeout von ≥ 90 s. Das Senken des `kscreen-doctor`-Timeouts
gehört zu #643, nicht hierher.

**Bildschirme:** `enable()` schaltet die in KWin aktiven Ausgänge ein — die
Auswahl aus dem Display-Output-Plugin.

**Entsperren:** ausschließlich über `unlock_if_permitted()` (eigene Rechte- und
LAN-Prüfung, eigenes Audit). Wer nur `can_launch_games` hat, startet womöglich
hinter dem Sperrbildschirm; `session_locked=true` sagt BaluApp, dass sie einen
Hinweis zeigen soll.

### Fehlerabbildung

Alle Meldungen neutral auf Englisch, wie die `public_message`-Defaults in
`core/exceptions.py`. BaluApp verzweigt nach Statuscode, nicht nach Text.

| Fall | Antwort |
|---|---|
| Kein Recht | `403` (Abhängigkeit) |
| Nicht aus LAN/VPN | `403` |
| `app_id` ungültig / nicht installiert | `404 "Game not installed"` |
| Bibliothek nicht lesbar | `503 "Game library unavailable"` |
| Spiel läuft bereits | `409 "A game is already running"` |
| Bildschirme gehen nicht an | `502 "Displays could not be turned on"` — nichts weiter gestartet |
| Big Picture nicht startbar | `502 "Steam could not be started"` — kein Spiel, kein Marker |
| Nur das Spiel nicht startbar | `502 "Steam could not be started"` — Marker bleibt gesetzt (Big Picture ist offen) |
| Erfolg | `202 {"status": "requested", "session_locked": …}` |

`ServiceError`-Subklassen (nicht `HTTPException(>=500)`), damit die Meldung den
5xx-Scrubber übersteht. Details nur ins Log.

### Audit

- `steam_game_launch` — `event_type="POWER"`, `resource="steam_gaming"`,
  `ip_address=client_host`, `details={"app_id", "failed_step"}`, `success`.
  **Kein Spielname** (stammt aus einer von `sven` beschreibbaren Datei) und
  **kein `detail`** (Interna).
- `steam_game_launch_denied` bei der LAN-Ablehnung, ebenfalls mit IP.
- Nicht-Admins zusätzlich `log_security_event("delegated_power_action", resource="launch_games")`.
- `404`/`409`/`503` werden nicht auditiert: kein Vertrauenseffekt, und wer das
  Recht hat, sieht die Bibliothek ohnehin über `GET`.
- Das Entsperren auditiert `unlock_if_permitted()` selbst.

### Sicherheit

**Bedrohungsmodell.** Ein erbeutetes Konto (oder API-Key) mit `can_launch_games`
startet Spiele: Bildschirme an, Big Picture, ein Spiel. Ärgerlich, aber ohne neues
Vertrauen — solange es nicht entsperrt und nicht aus dem Internet geht.

1. Recht auf beiden Routen, Standard verweigert, keine Implikation.
2. LAN/VPN-Prüfung beim Start für alle Rollen. **Tragend ist die Proxy-Kette:**
   uvicorn vertraut `X-Forwarded-For` nur von `127.0.0.1`, die installierte
   nginx-Vorlage verbindet über `127.0.0.1:8000`. Latente Umgehungen: #641
   (`localhost` in der Referenzkonfig), #642 (Teredo gilt als privat).
3. Entsperren nur mit `can_unlock_session`.
4. Kommandozeile: `fullmatch([0-9]{1,10})` **und** Bibliothekseintrag mit Manifest;
   die URL wird aus der ID des Eintrags gebaut. Listen-Argumente, kein `shell=True`,
   keine Sudoers-Regel. Ziffern-only schließt `steam://rungameid/<id>//<args>` und
   64-Bit-Shortcut-IDs aus.
5. Steam erbt keine Backend-Secrets (PR A).
6. Kein laufendes Spiel wird verdrängt (`409`).
7. Antworten und Audit ohne Interna.

**Akzeptiert (dokumentiert):**
- **Gleichzeitige Starts** (Doppeltipp, zwei Nutzer) passieren beide die
  `409`-Prüfung, weil der `reaper` erst nach Sekunden erscheint. BaluApp sperrt
  den Button bis zur Antwort.
- **„Gaming-Mode beenden" mitten im Start** (zwischen `mark_started` und
  `rungameid`): `close/bigpicture` + `show_desktop` laufen, danach startet das
  Spiel trotzdem. Seltene Überschneidung zweier Admin-/Rechte-Aktionen.
- **Wachhalten:** Scheitert nur das Spiel, hält der gesetzte Marker die Box über
  die Gaming-Präsenz wach — konsistent, weil Big Picture offen ist.
- **API-Keys** siehe Berechtigung.

### Tests

**Refactor:** Die bestehenden Gaming-Mode-Tests patchen Namen im Paket
(`steam_gaming.get_desktop_service`, `.open_big_picture`, `.unlock_if_permitted`;
`test_steam_gaming_plugin.py` u. a. Z. 157, 254, 264, 339, 352, 363, 496, 529, 581,
600, 619). Nach dem Umzug greifen sie ins Leere. Die Patch-Ziele ziehen nach
`app.plugins.installed.steam_gaming.launch.*` um; **die Assertions bleiben
unverändert** — das ist der Beleg, dass sich das Verhalten nicht ändert.

**Routen** (über `TestClient`, nicht per Direktaufruf — nur so fällt die
Future-Import-Falle auf):
- Recht: ohne → `401/403` auf beiden Routen; Nicht-Admin mit Recht → erlaubt.
- LAN: öffentliche IP → `403` **auch für Admins**, Audit mit IP, weder Desktop noch Launcher gerufen; VPN-IP → erlaubt; `client_host=None` → `403`; `GET` liefert `can_launch_here=false` bei öffentlicher IP.
- `app_id`: `abc`, `400%0A`, `٤٠٠`, 11 Ziffern, `400%2F1` → `404`; gültig aber nicht installiert → `404`; Tool (Proton-Manifest) → `404`; Launcher ungerufen, **kein Audit**.
- Bibliothek nicht lesbar → `503`.
- Laufendes Spiel → `409`, nichts gestartet, kein Audit.
- Reihenfolge `displays → unlock → bigpicture → mark_started → rungameid`.
- Bildschirme scheitern → `502`, weder Big Picture noch Spiel; Big Picture scheitert → `502`, kein Spiel, kein Marker; nur Spiel scheitert → `502`, Marker gesetzt.
- Marker bereits gesetzt → Ablauf läuft normal (zweites `open/bigpicture`).
- `launch_game` bekommt die ID aus dem Bibliothekseintrag.
- `session_locked` spiegelt `current_lock_state()` (`True`/`False`/`None`).
- Audit-`details` enthalten weder Name noch Launcher-`detail`.
- Nicht-Admin → zusätzlich `delegated_power_action`.
- Dev-Modus: `current_app_id(dev_stand_in=False)` ist `None`, obwohl `current_app_id()` den Stand-in liefert.

**Bibliothek:** Manifest → Eintrag; kein Manifest → kein Eintrag; Tool-Name → ausgeschlossen; Duplikat in zwei Bibliotheken → einmal; Name > 200 → gekürzt; Dateiname mit Nicht-Ziffern-ID → ignoriert; keine Verzeichnisse → `LibraryUnavailable` (prod) bzw. Mock (dev); Cache: zweiter Aufruf innerhalb der TTL liest nicht erneut.

**Recht:** Map-Eintrag, Round-Trip über `update_permissions`, Audit-Dicts, `my-permissions` (Admin `True`, Nutzer aus DB). Probe: Map-Zeile bzw. Write-Through testweise entfernen → rot.

**Frontend:** `PowerPermissionsSection` rendert den Schalter; Vertragstest gegen `admin.json` (de + en) auf die neuen Schlüssel.

### Deploy & Betrieb

- Migration im normalen Deploy; keine Sudoers-Änderung.
- Recht beim gewünschten Nutzer setzen.
- **Verifikation mit beobachteter Wirkung:**
  1. Aus dem LAN: Spiel starten bei laufendem Steam, dann nach `steam -shutdown`.
  2. **Über Mobilfunk ohne VPN:** `GET /games` → `can_launch_here=false`; `POST` → `403`. Dieser Schritt prüft die Proxy-Kette, auf der die LAN-Prüfung steht.
  3. Über VPN: Start funktioniert.

## Vertrag für Teil 2 (BaluApp)

1. `GET /api/sleep/my-permissions` → `can_launch_games` blendet „Spiele" ein.
2. `GET /api/plugins/steam_gaming/games`:
   - `404` → „Funktion nicht verfügbar" (Router nicht gemountet); `403` → „Keine Berechtigung" (auch deaktiviertes Plugin); `503` → „Spielebibliothek nicht erreichbar".
   - Liste anzeigen, laufendes Spiel hervorheben; Start-Buttons deaktiviert, wenn `running != null` oder `can_launch_here == false` (Hinweis „Nur im Heimnetz oder über VPN").
3. `POST …/games/{app_id}/launch` mit Client-Timeout ≥ 90 s; Button gesperrt bis zur Antwort.
   - `202` → „Wird gestartet"; `session_locked == true` → Hinweis „Bildschirm ist gesperrt". Danach `GET /games` nach ~5 s und ~15 s, bis `running.app_id == app_id`.
   - `404` → „Spiel nicht mehr installiert" + Liste neu laden; `409` → Liste neu laden (zeigt das laufende Spiel); `403` → „Nur im Heimnetz oder über VPN"; `502`/`503` → „Start fehlgeschlagen".
   - **Nach jedem Fehler erst `GET /games`, bevor ein neuer Start möglich ist** — ein Schritt kann nach der Fehlerantwort noch nachwirken.

## Verworfene Alternativen

- **`DISPLAY`/`XAUTHORITY`-Glob in `session_env`** (ursprünglicher #640-Vorschlag) — löst M2, aber Steam erbte weiter Secrets, cgroup und `PrivateTmp`.
- **Core-Route neben `/api/games/libraries`** — der Core müsste Plugin-Interna kennen.
- **Spiele ohne Steam-Client** (native Binary, `umu-run`, `proton run`) — die meisten Titel starten sich über Steam neu; das `reaper`-Tracking entfiele.
- **Menüaktion statt Route** — admin-gegated im Core, keine Parameter.
- **`can_launch_games` impliziert Entsperren** — ein Spielstart-Recht würde still den physischen Desktop öffnen.
- **Äußerer Timeout um den Ablauf** — bricht nur das `await`, nicht den Thread (siehe oben, #643).
- **`get_game_libraries()` als Datenquelle** — verschluckt Fehler, übernimmt IDs ohne Manifest, liest Größen unnötig.
- **Zweite Funktion `running_game_strict()`** — dupliziert die Längenbegrenzung; ein Parameter an `current_app_id()` hält einen Codepfad.
