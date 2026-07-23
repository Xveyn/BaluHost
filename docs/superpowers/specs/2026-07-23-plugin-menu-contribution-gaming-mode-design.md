# Plugin-Menü-Contribution + Gaming-Modus — Design

**Datum:** 2026-07-23
**Status:** entworfen, abgenommen
**Teilprojekt 2 von 4** — Gesamtschnitt siehe
`docs/superpowers/specs/2026-07-22-status-bar-plugin-pills-steam-gaming-design.md`

## Ziel

Das System-Menü (`PowerMenu`) soll einen Eintrag **„Gaming-Modus"** bekommen:
Displays einschalten und Steams Big Picture öffnen — ein Klick, statt Displays
an, hinsetzen, Steam suchen.

Wie Teilprojekt 1 wird das **nicht** als Core-Feature gebaut, sondern als
Beitrag des `steam_gaming`-Plugins über einen **neuen Extension-Point**:
Plugins können Aktionen ins System-Menü hängen. Der Extension-Point entsteht
wieder zusammen mit seinem ersten Konsumenten — eine API ohne echten Nutzer
bekommt fast immer den falschen Schnitt.

## Ausgangslage

Vorhanden und wiederverwendet, nicht neu gebaut:

- **Displays an/aus** — `DesktopService.enable()/disable()`
  (`services/power/desktop.py`) über `kscreen-doctor --dpms on|off`
  (`services/power/desktop_backend.py:96-100`). Bewusst DPMS statt `systemctl
  stop sddm`: das Stoppen des Display-Managers lässt den Framebuffer alle
  Ausgänge zünden und nagelt die dGPU bei ~78 W fest (gemessen), DPMS lässt sie
  auf ~18 W idlen.
- **Session-Umgebung** — `LinuxDesktopBackend._session_env()`
  (`desktop_backend.py:67-76`) setzt `XDG_RUNTIME_DIR=/run/user/<uid>` und
  `WAYLAND_DISPLAY`, damit ein Kommando die Wayland-Session des angemeldeten
  Users erreicht. Das Backend läuft als derselbe User (`sven`, UID 1000), dem
  die KDE-Session gehört — kein sudo nötig.
- **UI-Manifest** — `GET /api/plugins/ui/manifest` (`routes/plugins.py:124`)
  liefert je aktiviertem Plugin `nav_items` und `translations`; der
  `PluginContext` konsumiert das bereits beim Login.
- **Plugin-Texte im Frontend** — `resolvePluginString(translations, key,
  fallback)` (`lib/pluginI18n.ts`), etabliert für Dashboard-Panels und seit
  Teilprojekt 1 auch für Pills.
- **Berechtigungen** — Displays an/aus ist heute über
  `require_power_toggle_desktop` gegated (Admin **oder** delegierter Nutzer mit
  `can_toggle_desktop`), mit Audit-Eintrag und Notification-Emit
  (`routes/desktop.py:73-109`). Das umgebende `PowerMenu` ist admin-only.

Steam läuft auf der Box dauerhaft über die User-Unit
`app-steam@autostart.service`. „Steam starten" heißt deshalb **nicht** einen
Prozess starten, sondern die laufende Instanz in den Big-Picture-Modus holen.

## Nicht-Ziele

- **Kein „Gaming-Modus beenden".** Zum Ausschalten existiert direkt darüber im
  selben Menü „Desktop deaktivieren". Ein Gegenstück müsste Steam-Prozesse
  beenden dürfen — deutlich größere Angriffsfläche, und die Frage „was passiert
  bei laufendem Spiel" wäre zu beantworten. Automatisches Displays-aus nach
  Session-Ende ist ohnehin Teilprojekt 4.
- **Kein feineres Berechtigungsmodell.** Die Aktion ist admin-only; ein Gate
  analog `can_toggle_desktop` ist später additiv nachrüstbar.
- **Keine Zustandsanzeige im Menüpunkt** (ausgegraut, wenn Displays schon an).
  Ein Einmal-Auslöser, immer sichtbar.
- **Kein Bestätigungsdialog.** Displays einschalten und ein Fenster öffnen ist
  nicht destruktiv; ein Dialog wäre Zeremonie ohne Schutzwirkung.

## Architektur

```
backend/app/plugins/base.py            + PluginMenuItem, MenuActionResult,
                                         get_menu_items(), run_menu_action()
backend/app/schemas/plugin.py          + PluginMenuItemSchema; PluginUIInfo.menu_items
backend/app/plugins/manager.py           menu_items in das UI-Manifest aufnehmen
backend/app/api/routes/plugins.py      + POST /{name}/menu-actions/{action_id}
backend/app/services/power/session_env.py   gemeinsamer Wayland-Session-Env-Helper

backend/app/plugins/installed/steam_gaming/
  __init__.py                          + get_menu_items(), run_menu_action()
  launcher.py                            Big Picture abgekoppelt starten

client/src/api/plugins.ts               Typ PluginMenuItem
client/src/contexts/PluginContext.tsx   pluginMenuItems (flach, sortiert)
client/src/components/PowerMenu.tsx     generisches Rendern + Auslösen
```

### Extension-Point

**Deklaration.** `PluginUIManifest` bekommt `menu_items`:

```python
class PluginMenuItem(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")   # plugin-lokal, z. B. "gaming_mode"
    icon: str                                   # lucide-Name
    label_key: str                              # Schlüssel in get_translations()
    label_text: str                             # Literal-Fallback
    description_key: str | None = None
    description_text: str | None = None
    tone: Literal["neutral", "info", "success", "warning", "danger"] = "neutral"
    order: int = 100
```

**Ausführung.** `PluginBase` bekommt zwei Methoden, spiegelbildlich zu
`get_status_pills()` / `collect_status_pill()`:

```python
def get_menu_items(self) -> List[PluginMenuItem]:
    """Aktionen dieses Plugins im System-Menü. Default: keine."""
    return []

async def run_menu_action(self, action_id: str, db: Session) -> Optional[MenuActionResult]:
    """Aktion ausführen. None = Plugin kennt diese Aktion nicht."""
    return None
```

```python
class MenuActionResult(BaseModel):
    ok: bool
    message_key: str | None = None   # Schlüssel in get_translations()
    message_text: str                # Literal-Fallback, immer gesetzt
```

**Route.** `POST /api/plugins/{name}/menu-actions/{action_id}`,
`get_current_admin`, Ratelimit `admin_operations`, Audit mit
`event_type="PLUGIN"`, Ressource `{plugin}:{action_id}`.

Der Antwortkörper ist das `MenuActionResult` des Plugins
(`{ok, message_key, message_text}`), unverändert durchgereicht. Der
`message_key` wird **nicht** serverseitig aufgelöst: das Frontend hat die
`translations` des Plugins bereits aus dem UI-Manifest und löst über
`resolvePluginString` auf — dieselbe Mechanik wie bei Pill-Labels, und keine
Sprachwahl im Backend.

Sie dispatcht **nicht frei**: die `action_id` muss in den vom Plugin
deklarierten `menu_items` vorkommen, sonst 404 — `run_menu_action()` wird dann
gar nicht erst aufgerufen. Die Ausführung läuft unter Exception-Guard **und**
`asyncio.wait_for(..., PLUGIN_MENU_ACTION_TIMEOUT_SECONDS)`.

**Deaktivierte Plugins blockt die vorhandene `PluginGateMiddleware`, nicht die
Route.** `menu-actions` steht bewusst **nicht** in deren
`_MANAGEMENT_SUFFIXES` — anders als `/toggle` oder `/config` ist eine Aktion
kein Verwaltungszugriff, der auch bei deaktiviertem Plugin funktionieren muss.
Die Middleware prüft die **DB** (den einzigen worker-übergreifenden Zustand)
mit 5-s-TTL-Cache und antwortet 403; ein Deaktivieren wirkt damit binnen
weniger Sekunden auf allen vier Prod-Workern.

**Bekannte Einschränkung in der Gegenrichtung** (Erbstück aus Teilprojekt 1,
Issue #448): `PluginManager._enabled` ist prozess-lokal. Nach einem
*Aktivieren* über die UI kennt nur der behandelnde Worker die Plugin-Instanz;
auf den übrigen liefert `get_plugin()` `None` → 404 auf einen expliziten
Nutzerklick, bis das Backend neu gestartet wird. Die Operator-Note aus
`plugins/CLAUDE.md` (Restart nach Toggle eines beitragenden Plugins) gilt hier
unverändert und wird um Menü-Aktionen ergänzt. Der strukturelle Fix ist
#448-Scope, nicht dieses Teilprojekt.

`PLUGIN_MENU_ACTION_TIMEOUT_SECONDS = 20.0` — großzügiger als die 2 s der
Pill-Collectoren, weil `kscreen-doctor` selbst ein 30-s-Subprocess-Timeout
mitbringt. **Ehrliche Einschränkung:** blockierende Arbeit läuft im Plugin über
`asyncio.to_thread`, und ein `wait_for` kann einen laufenden Thread nicht
abbrechen — es gibt nur die Anfrage frei. Der Thread läuft bis zu seinem
eigenen Subprocess-Timeout weiter. Das ist vertretbar, weil er einen Thread
belegt und nicht den Event-Loop; blockierende Arbeit im Loop wäre der Fehler,
den Teilprojekt 1 beim Collector gefangen hat.

**Wer darf auslösen, entscheidet der Core.** `PluginNavItem` trägt ein
`admin_only`, das das Plugin selbst setzt — für einen Link vertretbar, für eine
Aktion nicht. `PluginMenuItem` hat bewusst **kein** solches Feld: der Core
erzwingt Admin, das Plugin kann das nicht aufweichen. Damit bleibt die
Rollenteilung des Pill-Extension-Points erhalten — das Plugin liefert *was*
passieren soll, nie *wer* es darf.

**Lesepfad ohne neuen Endpunkt.** `menu_items` reisen im vorhandenen
`GET /api/plugins/ui/manifest` mit (`PluginUIInfo.menu_items`, gespiegelt als
`PluginMenuItemSchema` in `schemas/plugin.py`, wie `PluginNavItemSchema` es für
Nav-Items tut). Kein zweiter Fetch, keine zweite Cache-Schicht. Ein
deaktiviertes Plugin fällt aus dem Manifest — der Menüpunkt verschwindet ohne
Aufräumjob.

### Steam-Plugin

```python
PluginMenuItem(
    id="gaming_mode", icon="Gamepad2", tone="info", order=10,
    label_key="menu_gaming_mode", label_text="Gaming Mode",
    description_key="menu_gaming_mode_desc",
    description_text="Turn displays on and open Big Picture",
)
```

`run_menu_action("gaming_mode")` in dieser Reihenfolge:

1. **Displays an** über `get_desktop_service().enable()` — derselbe Pfad wie
   „Desktop aktivieren", kein eigener Displays-Code. Schlägt das fehl, wird
   **abgebrochen**: Big Picture auf schwarzen Schirmen zu öffnen hilft niemandem.
2. **Big Picture** über `steam steam://open/bigpicture`, **abgekoppelt**
   gestartet (`subprocess.Popen`, `start_new_session=True`, kein `wait()`,
   Streams nach `DEVNULL`, Session-Env). Läuft Steam bereits, reicht der Aufruf
   die URL an die Instanz weiter und endet sofort; läuft es nicht, startet er
   Steam — und hängt dann *nicht* als Kindprozess am Backend.

Beide Schritte sind blockierend und laufen deshalb in `asyncio.to_thread`.

**Rückmeldung sagt nur, was belegbar ist.** Erfolg heißt „Gaming-Modus
gestartet", nicht „Big Picture läuft" — der Prozess wird abgekoppelt gestartet,
was er danach tut, wissen wir nicht. Teilerfolg wird als Teilerfolg gemeldet:
Displays an, aber Steam nicht auffindbar → `ok=False` mit genau dieser Aussage.

**Gemeinsamer Session-Env-Helper.** `XDG_RUNTIME_DIR`/`WAYLAND_DISPLAY` haben
jetzt zwei Aufrufer. `_session_env()` wandert aus `LinuxDesktopBackend` in
`services/power/session_env.py`; beide nutzen ihn. Das ist die einzige Änderung
an bestehendem Code.

### Frontend

`PluginContext` flacht `menu_items` aller aktivierten Plugins zu
`pluginMenuItems` auf — mit Plugin-Name und `translations`, sortiert nach
`order`, exakt wie `pluginNavItems` es für Nav-Items tut. `PowerMenu` liest sie
aus `usePlugins()` und rendert sie im Admin-Block **unter** den
Desktop-Einträgen, vor dem Trenner zum Logout — dort, wo „Displays an" schon
heute steht.

- **Label/Beschreibung** über `resolvePluginString(translations, key, text)`.
- **Icon über Allowlist.** Der Icon-Name kommt vom Plugin; ein
  `LucideIcons[name]`-Zugriff wäre ein Komponenten-Lookup aus
  plugin-kontrolliertem String. Stattdessen dieselbe feste Map wie bei den
  Pills, mit generischem Fallback statt Absturz.
- **Sperre während des Laufs.** `kscreen-doctor` braucht einen Moment; ohne
  deaktivierten Button feuert ein Doppelklick die Aktion zweimal.
- **Kein zusätzlicher Status-Refetch nötig.** Das Menü schließt beim Klick,
  und `PowerMenu` lädt den Desktop-Status ohnehin bei jedem Öffnen neu
  (`PowerMenu.tsx:27-36`) — beim nächsten Öffnen steht „Desktop deaktivieren"
  also bereits korrekt da. Bestehendes Verhalten, keine neue Arbeit.
- Toast bei beiden Ausgängen, Text aus `MenuActionResult`.

Im Pi-Build lädt der `PluginContext` gar nicht erst Plugins — es erscheinen
dort automatisch keine Einträge.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Plugin deaktiviert/deinstalliert | Fällt aus dem Manifest → Menüpunkt weg; POST → **403 durch `PluginGateMiddleware`** (DB-basiert, wirkt binnen ~5 s auf allen Workern) |
| Plugin aktiviert, aber Worker kennt es noch nicht | 404 bis zum Backend-Restart (prozess-lokales `_enabled`, #448 — siehe Extension-Point-Abschnitt) |
| `action_id` nicht deklariert | 404, `run_menu_action()` wird nicht aufgerufen |
| Aktion wirft | HTTP 200 mit `ok=false` + generischer Meldung; Details nur ins Log |
| Aktion überschreitet das Timeout | Abgeschnitten, `ok=false` |
| `steam`-Binary fehlt | `ok=false`, „Steam nicht gefunden" |
| Displays-an schlägt fehl | Abbruch vor Schritt 2, `ok=false` |
| Dev-Modus (Windows) | `DevDesktopBackend` no-op, Launcher no-op → Ablauf klickbar ohne Linux |

Ein Fehler im Plugin führt nie zu einem 5xx und nie zu einer Fehlermeldung mit
Server-Interna — dieselbe Regel wie bei den Pill-Collectoren.

## Sicherheit

- Keine neuen Sudoers-Regeln, kein `shell=True`, ausschließlich
  Listen-Argumente. Die einzige URL im Aufruf ist eine Konstante — kein
  Benutzereingabewert erreicht die Kommandozeile.
- Plugin-gelieferte Strings werden nie zu Codepfaden: `action_id` ist
  regexbeschränkt **und** gegen die deklarierte Liste geprüft, das Icon geht
  durch eine Allowlist.
- Admin-Gate, Ratelimit und Audit-Eintrag liegen im Core, nicht im Plugin.
  Der Audit-Eintrag wird **nach** der Ausführung geschrieben, mit
  `success=ok` — auch Timeout und Fehlschlag landen im Trail.
- Der Extension-Point erlaubt Plugins, eine Aktion *anzubieten* — nicht, ihre
  Sichtbarkeit oder Berechtigung zu bestimmen.
- **Bewusst akzeptiert:** `GET /ui/manifest` ist `get_current_user` — auch
  Nicht-Admins erhalten die `menu_items` (statische Labels/Icons) im Payload;
  nur das Rendern ist clientseitig auf den Admin-Block beschränkt. Das ist
  reine Metadaten-Sichtbarkeit ohne dynamische Daten (anders als der
  Spielname in Teilprojekt 1, der serverseitig gefiltert wird); die
  Ausführung selbst ist serverseitig admin-gegated.

## Tests

**Extension-Point (Core).** `PluginMenuItem.id` weist Großbuchstaben, Punkte
und Pfadanteile ab. `menu_items` erscheinen im UI-Manifest nur für aktivierte
Plugins. Route: Nicht-Admin → 403; unbekanntes Plugin → 404; nicht deklarierte
`action_id` → 404 **und** `run_menu_action()` ungerufen; Happy Path → `ok=true`
plus Audit-Eintrag mit `success=true`; werfende Aktion → 200 mit `ok=false`,
keine Interna in der Antwort, Audit mit `success=false`; hängende Aktion wird
vom Timeout abgeschnitten. Middleware: deaktiviertes Plugin → 403 durch
`PluginGateMiddleware` (Test auf Pfad-Matching des neuen Sub-Pfads — er darf
**nicht** als Management-Route durchrutschen).

**Steam-Plugin.** Reihenfolge Displays-vor-Steam; scheiterndes `enable()` →
Launcher **nicht** aufgerufen, `ok=false`; fehlendes `steam`-Binary
(`FileNotFoundError`) → `ok=false` mit der passenden Meldung; unbekannte
`action_id` → `None`.

**Launcher.** Exakt `["steam", "steam://open/bigpicture"]`,
`start_new_session=True`, Streams auf `DEVNULL`, Session-Env gesetzt, keine
Shell, kein `wait()`.

**Session-Env-Helper.** Beide Aufrufer erhalten dieselbe Umgebung — pinnt die
Extraktion gegen ein späteres Auseinanderlaufen.

**Frontend.** Kontext flacht und sortiert `menu_items`; `PowerMenu` rendert
einen Plugin-Eintrag mit aufgelöstem Label, postet beim Klick auf die richtige
URL, zeigt Toast bei Erfolg **und** bei `ok=false`, sperrt den Button während
des Laufs, fällt bei unbekanntem Icon zurück statt zu brechen.

## Offener Messpunkt

Dass `steam steam://open/bigpicture` an der **laufenden** Instanz tatsächlich
Big Picture öffnet, ist Annahme, nicht Messung. Sie gehört als expliziter
Smoketest-Schritt auf die Box, bevor der PR als fertig gilt. Hält sie nicht,
ändert sich eine Zeile im Launcher (etwa `steam -bigpicture` oder ein
`steam`-Aufruf ohne Argument, der nur das Fenster nach vorn holt) — der
Extension-Point bleibt unberührt.

## Risiken

- **Steam ändert das URL-Schema.** Dann bliebe der Menüpunkt wirkungslos,
  ohne Fehler. Der Aufruf ist eine einzelne, benannte Funktion mit Tests; der
  Bruch wäre lokal.
- **`to_thread` ist nicht abbrechbar** (siehe Timeout-Abschnitt). Bei einem
  hängenden `kscreen-doctor` bleibt bis zu 30 s ein Thread belegt. Kein
  Event-Loop-Stillstand, keine Auswirkung auf andere Requests.
- **Erster ausführender Extension-Point.** Bisher durften Plugins Daten
  liefern; hier lösen sie eine Aktion aus. Kompensiert durch Admin-Gate,
  Deklarationszwang für die `action_id`, Timeout, Audit — und dadurch, dass die
  Aktion selbst nur bereits vorhandene, ebenfalls admin-gegatete Funktionalität
  aufruft.
