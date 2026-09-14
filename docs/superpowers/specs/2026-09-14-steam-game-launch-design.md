# Steam-Spiele aus BaluApp starten — Design (Teil 1: BaluHost-Backend)

**Datum:** 2026-09-14
**Status:** Entwurf, wartet auf Review
**Teil 2:** BaluApp (eigenes Repo `Xveyn/BaluApp`, eigene Spec) — hier nur als Vertrag skizziert

## Ziel

Ein Nutzer mit dem Recht `can_launch_games` wählt in BaluApp ein installiertes
Steam-Spiel und startet es auf BaluNode. Der Start schaltet die Bildschirme ein,
entsperrt die Session (sofern der Nutzer das darf), öffnet Big Picture und startet
dann das Spiel. Das bestehende Session-Tracking (Pill, Ledger, Notifications,
Dashboard-Panel) läuft unverändert mit.

**Nicht im Umfang:**
- Web-UI von BaluHost — außer dem Rechte-Schalter, den der Admin zum Vergeben
  braucht. Über die Website bringt der Start keinen Mehrwert.
- Spiele ohne Steam-Client starten (native Binaries, `umu-run`, `proton run`) —
  verworfen, siehe „Verworfene Alternativen".
- Nicht-Steam-Spiele, Spielcover, laufendes Spiel beenden.

## Messungen (BaluNode, 2026-09-14, SSH als `sven`)

Alle Befunde mit **beobachteter Wirkung** auf dem Bildschirm, nicht nur Exit-Code.

| # | Zustand | Aufruf | Ergebnis |
|---|---|---|---|
| M1 | Steam läuft | `steam steam://rungameid/400` ohne Session-Env | Portal startet; `reaper SteamLaunch AppId=400` sichtbar |
| M2 | Steam gestoppt | derselbe Aufruf ohne `DISPLAY` | `Unable to open X11 display, exiting` — kein Start |
| M3 | Steam gestoppt | mit `DISPLAY=:0` + `XAUTHORITY=/run/user/1000/xauth_MSLMAD` | Steam startet kalt, danach Portal sichtbar |
| M4 | Steam gestoppt | `steam://open/bigpicture` und `steam://rungameid/400` direkt nacheinander, beide detached, beide mit X11-Env | Steam startet, Big Picture kommt, Portal startet. Der zweite Prozess meldet `Steam is already running, exiting (command line was forwarded)` |

Folgerungen:
- **`steam://rungameid` ist der Startweg.** Steam kümmert sich um Proton,
  Startoptionen, DRM und Cloud-Saves; der `reaper`-Wrapper bleibt erhalten.
- **Der Kaltstart braucht X11.** Der Steam-Client ist ein X11-Programm (XWayland
  unter KDE). `session_env.py` setzt heute nur `XDG_RUNTIME_DIR`/`WAYLAND_DISPLAY`
  → Issue **#640**, wird hier mitgefixt.
- **Der `xauth_*`-Dateiname ist pro KDE-Login zufällig** — zur Laufzeit suchen.
- **Kein Warten auf „Steam bereit" nötig** (M4): Steam leitet die Befehlszeile
  an den gerade startenden Client weiter.
- Portal läuft auf der Box über erzwungenes Proton 10 — für diesen Startweg
  irrelevant.

## Architektur

Router im bestehenden bundled Plugin `steam_gaming` — nach dem Muster von
`plugins/installed/bluetooth/`. Dort liegen schon Erkennung (`detection.py`),
Launcher (`launcher.py`), Gaming-Mode-Ablauf und Marker (`gaming_state.py`).

**Konsequenz, bewusst in Kauf genommen:** Das Plugin hatte bisher keinen Router
(`CLAUDE.md`: „No router … restart_required is always false"). Plugin-Router
werden nur beim Start gemountet (`core/lifespan.py`). Nach dem Deploy ist das
unkritisch — der Deploy startet das Backend neu und das Plugin ist in Prod
aktiv. Wird es später aus- und wieder eingeschaltet, zeigt
`PluginDetailResponse.restart_required` den nötigen Neustart korrekt an.
Pill, Menü, Panel und Notifications wirken weiterhin sofort.

### Neue und geänderte Dateien

**Neu**
- `backend/app/plugins/installed/steam_gaming/routes.py` — Router, Schemas-Nutzung, Audit-Helfer
- `backend/app/plugins/installed/steam_gaming/launch.py` — gemeinsamer Startablauf (`start_gaming_mode()`) + `launch_game()`
- `backend/app/plugins/installed/steam_gaming/schemas.py` — Pydantic-Modelle der Routen
- `backend/alembic/versions/<rev>_add_can_launch_games_permission.py`
- Tests (siehe „Tests")

**Geändert**
- `steam_gaming/__init__.py` — `get_router()`; `run_menu_action` nutzt `start_gaming_mode()`
- `steam_gaming/launcher.py` — `launch_game(app_id)`
- `steam_gaming/detection.py` — `running_game_strict()` (Erkennung ohne Dev-Stand-in)
- `steam_gaming/CLAUDE.md` — Router-Abschnitt, „No router"-Satz korrigieren
- `services/power/session_env.py` — `DISPLAY` + `XAUTHORITY` (#640)
- `models/power_permissions.py`, `schemas/power_permissions.py`, `services/power_permissions.py`, `api/deps.py`, `api/routes/sleep.py` — neues Recht
- `core/rate_limiter.py` — Kategorie `steam_launch`
- `client/src/api/powerPermissions.ts`, `client/src/components/user-management/PowerPermissionsSection.tsx`, `client/src/i18n/locales/{de,en}/admin.json` — Rechte-Schalter
- `backend/app/plugins/CLAUDE.md`, `.claude/rules/architecture.md` (API-Liste), `.claude/rules/security-agent.md` (Rollenmodell)

## Berechtigung `can_launch_games`

Exakt nach dem Vorbild `can_manage_bluetooth`:

- **Modell:** Spalte `can_launch_games`, `Boolean, nullable=False, default=False, server_default="0"`.
- **Migration:** additiv, kettet an den echten Head **`19b0fbf9df31`**
  (`python -m alembic heads` am 2026-09-14, genau ein Head). Vor dem Anlegen
  erneut prüfen, nie den Kopf der Dev-Datenbank nehmen.
- **Dienst:** `_ACTION_FIELD_MAP["launch_games"] = "can_launch_games"`; Feld in
  `get_permissions`, `update_permissions` und beiden Audit-Dicts. **Keine
  Implikation** — insbesondere impliziert es **nicht** `can_unlock_session`.
- **Abhängigkeit:** `require_power_launch_games = _make_power_dependency("launch_games")`.
- **`my-permissions`:** `True` für Admins, sonst aus `get_permissions` — das Feld
  liest BaluApp, um den Menüpunkt ein- oder auszublenden.
- **Frontend:** Feld in den drei Schnittstellen von `api/powerPermissions.ts`,
  Schalter in `PowerPermissionsSection.tsx` (Icon `Gamepad2`), Texte in `admin.json`.

Standard: verweigert. Admins haben es implizit.

## API

Prefix `/api/plugins/steam_gaming`. Jede Route: `require_power_launch_games`,
`@user_limiter.limit(get_limit("steam_launch"))`.

| Methode | Pfad | Antwort | LAN-Prüfung |
|---|---|---|---|
| GET | `/games` | `GameListResponse` | — |
| POST | `/games/{app_id}/launch` | `202 LaunchResponse` | **ja** |

```python
class LaunchableGame(BaseModel):
    app_id: str
    name: str

class RunningGame(BaseModel):
    app_id: str
    name: Optional[str]

class GameListResponse(BaseModel):
    games: list[LaunchableGame]        # alphabetisch nach name
    running: Optional[RunningGame]     # aus detection.current_app_id()
    can_launch_here: bool              # is_private_or_local_ip(client_host)

class LaunchResponse(BaseModel):
    status: Literal["requested"]
    session_unlocked: bool
```

`can_launch_here` erspart BaluApp einen fehlschlagenden Klick außerhalb des LANs
(gleiches Muster wie `can_pair_here` im Bluetooth-Plugin) — Information, keine
Kontrolle; die Kontrolle bleibt die Prüfung im POST.

**`GET /games` ohne LAN-Prüfung:** Lesen schafft kein neues Vertrauen. Die Liste
steht hinter demselben Recht, weil laufendes Spiel und Bibliothek Information
über den Box-Besitzer sind (vgl. `admin_only` des Steam-Panels).

**Datenquelle:** `game_libraries.service.get_game_libraries()` — Tools (Proton,
Runtime, Redistributables) sind dort bereits gefiltert; im Dev-Modus liefert sie
die Mock-Bibliothek. Blockierende Datei-I/O → `asyncio.to_thread`.

### Rate-Limit-Kategorie

```python
# Steam-Spielstart — BaluApp liest die Liste beim Öffnen und fragt nach einem
# Start ein paar Mal nach, ob das Spiel läuft. Starts selbst sind selten.
"steam_launch": "30/minute",
```

## Startablauf

### Prüfungen im POST, in dieser Reihenfolge

1. **Recht** — `require_power_launch_games`; Ablehnung auditiert die Abhängigkeit selbst.
2. **LAN/VPN** — `is_private_or_local_ip(request.client.host)`, **für alle Rollen**,
   sonst `403` + Audit `steam_game_launch_denied` (`reason: not_local`). Sicher,
   weil `--forwarded-allow-ips=127.0.0.1` `X-Forwarded-For` nur von nginx annimmt
   (siehe `project_lan_gate_channel_vs_ip`).
3. **`app_id`** — Regex `^\d{1,10}$`, sonst `404`. Danach Abgleich gegen die
   installierte Bibliothek aus `get_game_libraries()`: nicht enthalten → `404`.
   Beide Fälle bewusst gleich (`404`, nicht `400`), damit die Antwort nichts über
   die Form unterscheidet. **Die Kommandozeile bekommt nur eine ID, die aus einer
   Manifest-Datei stammt.**
4. **Läuft schon ein Spiel?** — `detection.running_game_strict()` nicht `None` →
   `ConflictError("Es läuft bereits: <name>")` (`409`). So nimmt niemand mit dem
   Recht einem anderen das laufende Spiel weg. `ServiceError` trägt nur eine
   Meldung, keinen strukturierten Body — BaluApp lädt nach einem `409` ohnehin
   `GET /games` neu und hat `running` dann strukturiert. Warum nicht
   `current_app_id()`: siehe „Dev-Modus".

### Ausführung: `launch.start_gaming_mode()` + `launch_game()`

Der bestehende Start in `SteamGamingPlugin.run_menu_action` wird **ohne
Verhaltensänderung** in einen Helfer gezogen, den Menüaktion und Route nutzen:

```python
@dataclass(frozen=True)
class GamingModeStart:
    ok: bool
    failed_step: Optional[Literal["displays", "steam"]]
    detail: str
    session_unlocked: bool

async def start_gaming_mode(*, user, client_host, db) -> GamingModeStart:
    # 1. get_desktop_service().enable()            — Fehler → Abbruch ("displays")
    # 2. unlock_if_permitted(user, client_host, db) — Ablehnung ist KEIN Abbruch
    # 3. to_thread(open_big_picture)                — Fehler → Abbruch ("steam")
    # 4. to_thread(gaming_state.mark_started)
```

`run_menu_action` übersetzt `GamingModeStart` in die bisherigen
`MenuActionResult`-Keys (`menu_displays_failed`, `menu_steam_failed`,
`menu_gaming_mode_started`). Die bestehenden Gaming-Mode-Tests bleiben
**unverändert grün** — das ist der Beleg, dass der Umbau nichts verschiebt.

Die Route ruft danach:

5. `to_thread(launcher.launch_game, app_id)` → `steam steam://rungameid/<app_id>`,
   über denselben `_dispatch` (detached, `start_new_session=True`, Streams nach
   `DEVNULL`, Listen-Argumente, Session-Env).

**Bildschirme:** `enable()` schaltet die Ausgänge ein, die in KWin aktiv sind —
also die Auswahl aus dem Display-Output-Plugin. Keine eigene Ausgangslogik.

**Entsperren:** läuft ausschließlich über `unlock_if_permitted()` mit dessen
eigenen Regeln (`can_unlock_session` **und** LAN) und dessen Audit. Wer nur
`can_launch_games` hat, startet das Spiel womöglich hinter dem Sperrbildschirm —
**bewusst**: ein Recht zum „Spiel starten" darf nicht still den physischen
Desktop öffnen. `LaunchResponse.session_unlocked` sagt BaluApp, ob sie einen
Hinweis zeigen soll.

### Fehlerabbildung

| Fall | Antwort |
|---|---|
| Kein Recht | `403` (Abhängigkeit, auditiert) |
| Nicht aus LAN/VPN | `403`, Audit `steam_game_launch_denied` |
| `app_id` ungültig oder nicht installiert | `404` |
| Spiel läuft bereits | `409 ConflictError` mit Spielname in der Meldung |
| Ablauf überschreitet `STEAM_LAUNCH_TIMEOUT_SECONDS` | `502 BadGatewayError` „Zeitüberschreitung beim Start" |
| Bildschirme gehen nicht an | `502 BadGatewayError` „Bildschirme konnten nicht eingeschaltet werden", Spiel **nicht** gestartet |
| Big Picture / Spiel: `steam` nicht startbar | `502 BadGatewayError` „Steam konnte nicht gestartet werden" |
| Erfolg | `202 {"status": "requested", "session_unlocked": …}` |

`BadGatewayError` (ein `ServiceError`), damit die kuratierte Meldung den globalen
5xx-Scrubber übersteht — gleiche Begründung wie beim Marketplace-Index. Details
(`detail` aus Launcher/kscreen-doctor) nur ins Log, nie in die Antwort.

**Scheitert nur Schritt 5** (Big Picture ist schon offen, Marker gesetzt): `502`.
Der Marker bleibt gesetzt — Big Picture ist ja tatsächlich offen, das Power-Menü
bietet korrekt „Gaming-Mode beenden" an.

**„requested", nicht „läuft":** Der Prozess ist detached; was danach passiert,
ist von hier nicht beobachtbar. Ob das Spiel läuft, zeigt `GET /games` über
`running`, sobald der `reaper`-Prozess erscheint.

### Timeout

Die Route läuft nicht durch den Menüaktions-Dispatch und hat damit dessen 20-s-
Timeout nicht. Sie bekommt einen eigenen `asyncio.wait_for` um die Schritte 1–5
mit `STEAM_LAUNCH_TIMEOUT_SECONDS = 20` → bei Überschreitung `502`
(`core/exceptions.py` hat keine 504-Klasse; eine neue anzulegen lohnt für diesen
einen Fall nicht, und für BaluApp ist beides „Start fehlgeschlagen"). Alle
blockierenden Schritte laufen in `asyncio.to_thread`, sonst griffe der Timeout nicht.

## Session-Umgebung (#640)

```python
def wayland_session_env(uid: Optional[int] = None) -> dict:
    resolved = uid if uid is not None else os.getuid()
    runtime_dir = f"/run/user/{resolved}"
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", runtime_dir)
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    env.setdefault("DISPLAY", ":0")
    xauth = _find_xauthority(env["XDG_RUNTIME_DIR"])
    if xauth is not None:
        env.setdefault("XAUTHORITY", xauth)
    return env
```

- `_find_xauthority(runtime_dir)`: Glob `xauth_*`, bei mehreren die mit der
  jüngsten `mtime`, `OSError` → `None`. Kein Treffer → Variable weglassen.
- Alles per `setdefault`: eine explizite Umgebung gewinnt weiterhin.
- Zweiter Konsument ist `desktop_backend.py` (`kscreen-doctor`) — die
  zusätzlichen Variablen sind dort harmlos; dessen Tests laufen unverändert mit.
- Nebenwirkung, gewollt: der Gaming-Mode aus dem Power-Menü funktioniert damit
  auch bei gestopptem Steam.

## Audit

Nach dem Bluetooth-Muster (`_audit` in `routes.py`):

- `steam_game_launch` — `event_type="POWER"`, `resource="steam_gaming"`,
  `details={"app_id", "name", "failed_step"}`, `success` = Ergebnis.
  `404`/`409` werden **nicht** auditiert (kein Vertrauenseffekt, häufig bei
  veralteter App-Liste); `403` aus der LAN-Prüfung schon.
- Nicht-Admins zusätzlich `log_security_event("delegated_power_action",
  resource="launch_games")`.
- Das Entsperren auditiert `unlock_if_permitted()` selbst.

## Dev-Modus (Windows)

- Bibliothek: Mock aus `get_game_libraries()` (Cyberpunk 2077, Dota 2, CS2).
- Bildschirme: `DevDesktopBackend` no-op; Launcher: `_dispatch` no-op.
- **Laufendes Spiel:** `detection.current_app_id()` liefert im Dev-Modus immer
  `DEV_APP_ID` — damit würde jeder Start mit `409` beantwortet. Die Routen nutzen
  deshalb eine eigene Funktion `detection.running_game_strict()`: dieselbe
  `/proc`-Erkennung und dieselbe Längenbegrenzung wie `current_app_id()`, aber
  **ohne** Dev-Stand-in. Auf Linux sind beide identisch; auf dem Windows-Dev-Rechner
  liefert sie `None`, und der Ablauf ist lokal durchklickbar. Pill, Ledger und
  Panel behalten ihren Stand-in unverändert.

## Sicherheit

**Bedrohungsmodell.** Ein erbeutetes Konto mit `can_launch_games` startet Spiele
auf dem Gaming-PC: Bildschirme gehen an, Big Picture öffnet sich, ein Spiel
läuft. Ärgerlich, aber ohne neues Vertrauen — solange es **nicht** entsperrt und
**nicht** aus dem Internet geht.

1. Recht `can_launch_games` auf beiden Routen, Standard verweigert, keine
   Implikation.
2. LAN/VPN-Prüfung beim Start für alle Rollen, abgelehnte Versuche auditiert.
3. Entsperren nur mit `can_unlock_session` über `unlock_if_permitted()`.
4. Keine Benutzereingabe erreicht die Kommandozeile ungeprüft: `app_id` ist
   regexbeschränkt **und** muss in der installierten Bibliothek stehen; die URL
   ist `f"steam://rungameid/{app_id}"` mit dieser geprüften ID; Listen-Argumente,
   kein `shell=True`, keine Sudoers-Regel.
5. Kein laufendes Spiel wird verdrängt (`409`).
6. Antworten ohne Server-Interna; Details nur ins Log.

**Akzeptiert:** Zwei Starts im selben Augenblick (Doppeltipp, zwei Nutzer)
passieren beide die `409`-Prüfung, weil der `reaper`-Prozess erst nach einigen
Sekunden erscheint. Steam behandelt den zweiten Aufruf selbst. BaluApp sperrt
den Button während des Starts; eine workerübergreifende Sperre wäre für diesen
Fall unverhältnismäßig.

## Tests

`backend/tests/plugins/test_steam_gaming_routes.py`, `…_launch.py`,
`backend/tests/test_session_env.py` (erweitert),
`backend/tests/test_power_permissions_launch_games.py`.

- **Recht:** beide Routen ohne Recht → `401/403`; Nicht-Admin mit Recht → erlaubt;
  Map-Eintrag, Round-Trip über `update_permissions`, Feld in `my-permissions`
  (Admin `True`, Nutzer aus DB). Probe: Map-Zeile bzw. Write-Through testweise
  entfernen → Tests werden rot.
- **LAN:** öffentliche IP → `403` **auch für Admins**, Audit geschrieben,
  **kein** Aufruf von Desktop/Launcher; VPN-IP → erlaubt; `client_host=None` → `403`.
- **`app_id`:** `abc`, `1; rm`, 11 Ziffern → `404`; gültige, aber nicht installierte
  ID → `404`; Tool-ID (Proton) → `404`. Launcher in allen Fällen ungerufen.
- **`409`:** laufendes Spiel → `409` mit Spielname in `detail`, nichts gestartet.
- **Timeout:** hängender Schritt → `502`, Route kehrt nach dem Timeout zurück.
- **Dev-Modus:** `running_game_strict()` liefert ohne `/proc` `None`, obwohl
  `current_app_id()` den Stand-in liefert.
- **Reihenfolge:** `displays → unlock → bigpicture → mark_started → rungameid`.
- **Fehlerpfade:** Bildschirme scheitern → `502`, weder Big Picture noch Spiel;
  Big Picture scheitert → `502`, kein Spiel, kein Marker; nur Spiel scheitert →
  `502`, Marker gesetzt; abgelehntes Entsperren → `202` mit `session_unlocked=false`.
- **Launcher:** `launch_game("400")` → `Popen(["steam", "steam://rungameid/400"], …)`,
  `start_new_session=True`, `DEVNULL`, kein `shell`; Dev-Modus spawnt nichts.
- **Session-Env:** `DISPLAY` gesetzt; `xauth_*` im temporären Runtime-Dir →
  `XAUTHORITY`; mehrere → jüngste; keine → Variable fehlt; explizite Env wird
  nicht überschrieben.
- **Refactor-Beleg:** `test_steam_gaming_plugin.py` bleibt **unverändert** grün.
- **Frontend:** `PowerPermissionsSection` rendert den neuen Schalter; Vertragstest,
  dass die `admin.json`-Schlüssel in `de` und `en` existieren
  (siehe `project_i18n_mock_hides_placeholder_gap`).

## Vertrag für Teil 2 (BaluApp)

Nur als Skizze, die eigene Spec entsteht im BaluApp-Repo:

1. `GET /api/system/sleep/my-permissions` → `can_launch_games` blendet „Spiele" ein.
2. `GET /api/plugins/steam_gaming/games` → Liste, laufendes Spiel hervorgehoben,
   Start-Button deaktiviert, wenn `running != null` oder `can_launch_here == false`.
3. `POST …/games/{app_id}/launch` → Button gesperrt während des Starts; danach
   `GET /games` nach ~5 s und ~15 s erneut, bis `running.app_id == app_id`.
4. Texte: `403` „Nur im Heimnetz oder über VPN", `404` „Spiel nicht mehr
   installiert", `409` „Es läuft bereits *X*" + Liste neu laden, `502` „Start fehlgeschlagen",
   `session_unlocked=false` → Hinweis „Bildschirm ist gesperrt".
5. `403` durch deaktiviertes Plugin (`PluginGateMiddleware`) wie „kein Recht" behandeln.

## Deploy & Betrieb

- Migration läuft im normalen Deploy. Keine Sudoers-Änderung, kein
  `SYNC_PERMISSIONS=1` nötig.
- Nach dem Deploy: Recht beim gewünschten Nutzer setzen; Verifikation an der Box
  mit **beobachteter Wirkung** — einmal bei laufendem Steam, einmal nach
  `steam -shutdown`.

## Verworfene Alternativen

- **Core-Route neben `/api/games/libraries`** — der Core müsste Plugin-Interna
  (Erkennung, Gaming-Mode, Marker) kennen; beim Session-Verlauf schon einmal
  ausgeschlossen.
- **Spiele ohne Steam-Client** (native Binary, `umu-run`, `proton run`) — die
  meisten Titel rufen `SteamAPI_RestartAppIfNecessary` und starten sich über
  Steam neu oder beenden sich; Steamworks-Titel brauchen Steam ohnehin. Außerdem
  entfiele die `reaper`-Erkennung und damit das ganze Session-Tracking.
- **Menüaktion statt Route** — Menüaktionen sind im Core admin-gegated
  (`PluginMenuItem` hat bewusst kein `admin_only`) und kennen keine Parameter
  wie `app_id`.
- **`can_launch_games` impliziert Entsperren** — ein Spielstart-Recht würde still
  den physischen Desktop öffnen; die doppelte Prüfung von `can_unlock_session`
  existiert genau dagegen.
- **Warten auf „Steam bereit" beim Kaltstart** — M4 zeigt, dass Steam die
  Befehlszeile weiterleitet.
