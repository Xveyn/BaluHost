# Steam-Session-Historie + Dashboard-Panel — Design

**Datum:** 2026-07-24
**Status:** entworfen, abgenommen
**Teilprojekt 4 von 4** — Gesamtschnitt siehe
`docs/superpowers/specs/2026-07-22-status-bar-plugin-pills-steam-gaming-design.md`

## Ziel

Steam-Sessions werden **persistiert** statt nur flüchtig erkannt: wann welches
Spiel lief und wie lange. Das Dashboard zeigt die letzten fünf Sessions als
Plugin-Panel. Nebenher wird die Flankenlogik aus Teilprojekt 3 vollständig —
der direkte Spielwechsel (X→Y ohne Pause), heute bewusst verschluckt, wird
verbucht **und** gemeldet (schließt #462).

Damit endet der Track: Pill (TP1), Menü-Aktion (TP2), Notifications (TP3),
Historie + Panel (TP4).

## Ausgangslage (gemessen, nicht angenommen)

### Was das Plugin heute kann

`backend/app/plugins/installed/steam_gaming/` (444 Zeilen):

- `detector.py` — `/proc`-Scan auf `reaper SteamLaunch AppId=<n>`, dedupliziert,
  niedrigste PID gewinnt.
- `names.py` — AppID → Spielname über `appmanifest_<id>.acf`.
- `launcher.py` — `steam://open/bigpicture`, detached.
- `poller.py` — primary-only Background-Task (30 s), erkennt Flanken
  None→X und X→None und feuert die TP3-Events.
- `__init__.py` — Pill-Spec + Collector, Menüpunkt „Gaming-Modus", Event-Specs.

**Es wird nichts gespeichert.** `SteamSessionPoller._last_app_id` lebt im
Prozess des Primary-Workers; nach jedem Neustart beginnt die Welt neu.

### Dashboard-Panel-Extension-Point

Existiert bereits und braucht keine Erweiterung für die Darstellung:

- `PluginBase.get_dashboard_panel()` → `DashboardPanelSpec`
  (`panel_type` ∈ `gauge | stat | status | chart`).
- `PluginBase.get_dashboard_data(db)` → Daten passend zum Typ
  (`plugins/dashboard_panel.py`).
- Route `GET /api/dashboard/plugin-panel` (`api/routes/dashboard.py`) —
  hängt an `get_current_user`, umschließt `get_dashboard_data()` bereits mit
  try/except und liefert bei Fehler das Panel mit `data=None`.
- Einziger bisheriger Konsument: `tapo_smart_plug`.
- Es kann **immer nur ein** Plugin-Panel aktiv sein
  (`InstalledPlugin.dashboard_panel_enabled`, `plugin_service.py:143`).

Der `status`-Renderer nimmt eine Liste aus `label` / `value` / `tone` —
genau die Form, die eine Session-Liste braucht. **Kein Frontend-Diff.**

### Big Picture vs. Fenster — gemessen, nicht baubar

Der Gesamtschnitt sah für TP4 „Big Picture vs. Fenster" vor, mit dem Zweck, den
Menüpunkt „Gaming-Modus" nicht blind feuern zu lassen, wenn Big Picture schon
läuft. Auf BaluNode gemessen, mit laufendem Steam in beiden Zuständen:

| Signal | Ergebnis |
|---|---|
| `pgrep -a steamwebhelper \| grep -i -e gamepadui -e bigpicture` | leer, auch **während** Big Picture aktiv war |
| `ps -eo args \| grep -o -- '-uimode=[0-9]*'` | `3× -uimode=7` — **identisch** im Fenster- und im Big-Picture-Modus, auch nach 10 s Wartezeit |
| `grep -i -e bigpicture -e gamepad -e tenfoot ~/.steam/registry.vdf` | leer in beiden Zuständen |

`-uimode` beschreibt nur, wie `steamwebhelper` gestartet wurde, nicht den
aktuellen Modus — dieselbe Sorte Sackgasse wie `RunningAppID` in TP1
(ValveSoftware/steam-for-linux#9672). Verbleibender theoretischer Kandidat wäre
das Mitlesen von Steams `console-linux.txt`; ein fremdes Logformat ohne
Stabilitätszusage ist für ein Dauerfeature der falsche Anker. **Big Picture
fällt damit aus TP4 heraus** (siehe Nicht-Ziele).

Nebenbefund von der Box, außerhalb dieses Repos: `/usr/local/bin/steam-bpm-inhibit`
erkennt Big Picture über genau diesen `gamepadui`-String — dieser Zweig kann
nach obiger Messung nie greifen; das Sleep-Inhibit lebt allein vom zweiten
Zweig (`SteamLaunch`, also ein laufendes Spiel).

## Entscheidungen (im Brainstorming getroffen)

- **Persistenz: eigene DB-Tabelle.** Multi-Worker-sicher ohne Zusatzarbeit,
  Aggregation per SQL. Verworfen: JSON unter `.system/` (Aggregation von Hand,
  Datei-Lesen pro Panel-Request); gar nicht persistieren (streicht „Historie").
- **Restart-Policy: `last_seen_at`-Heartbeat.** Jeder Tick schreibt ihn fort;
  eine Session überlebt Deploys nahtlos, eine hängengebliebene wird bei ihrem
  letzten Lebenszeichen geschlossen. Verworfen: beim Start alles Offene mit
  Dauer 0 schließen (verliert jede Session, die ein Deploy überlebt — Deploys
  passieren hier oft); dangling lassen (Aggregate systematisch zu niedrig).
- **Spielwechsel meldet Ende + Start.** Historie und Notifications benutzen
  dieselbe Flankenlogik — eine Wahrheit statt zweier. Schließt #462.
- **Panel ist `admin_only`.** Spielnamen sind eine Information über den
  Box-Besitzer — dieselbe Privatsphäre-Entscheidung wie bei der Pill in TP1.
- **Retention 365 Tage**, im Plugin, ohne Konfigurationsoberfläche.
  Konfigurierbarkeit ist als Folgearbeit festgehalten (siehe unten).
- **Kleinster Oberflächenschnitt:** nur das Dashboard-Panel, keine eigene
  Steam-Seite.

## Nicht-Ziele

- **Big Picture vs. Fenster** — gemessen nicht erkennbar (siehe oben).
- **Auto-Displays-aus nach Sessionende.** Aus dem TP4-Zuschnitt gestrichen.
- **Eigene Steam-Seite.** Pill und Panel zeigen weiterhin auf `/plugins`;
  #451 M-3 (das `href` ist desktop-build- und admin-gegated) bleibt offen.
- **Per-Nutzer-Kategorie-Preference für Plugin-Events.** Aus TP3 vertagt, aber
  Core-Arbeit an den Notifications und mit Steam nur indirekt verwandt —
  bekommt eine eigene Spec.
- **Aggregate wie „Spielzeit pro Spiel/Woche".** Die Daten erlauben es, das
  Panel zeigt es nicht; ohne eigene Seite gibt es keinen Ort dafür.
- **Erkennung außerhalb von Steam** (Lutris, Drittanbieter-Launcher) —
  unverändert aus TP1.

## Architektur

```
backend/app/models/steam_session.py            NEU  Tabelle steam_sessions
backend/alembic/versions/<rev>_…               NEU  Migration
backend/app/plugins/installed/steam_gaming/
  ledger.py                                    NEU  Buchung + Flanken- und Lückenregeln
  poller.py                                    ÄND  Zustand entfällt, ruft den Ledger
  __init__.py                                  ÄND  Panel-Spec, get_dashboard_data, Dev-Mock
backend/app/plugins/base.py                    ÄND  DashboardPanelSpec.admin_only
backend/app/api/routes/dashboard.py            ÄND  Gate: admin_only → is_privileged
backend/app/models/__init__.py                 ÄND  Registrierung (Alembic-Autogenerate)
```

Kein Frontend-Diff.

### Datenmodell

Das Model liegt in `app/models/`, nicht im Plugin — nicht weil die Tabelle zum
Core gehört, sondern weil Alembic-Autogenerate nur sieht, was an
`Base.metadata` hängt. Dasselbe Muster wie `smart_device.py` für Tapo.

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | int, PK | |
| `app_id` | `String(32)`, Index | Steam-AppID |
| `game_name` | `String(200)`, nullable | aufgelöster Name; `None`, wenn kein `appmanifest` lesbar war |
| `started_at` | `DateTime(timezone=True)` | Flanke „Spiel erkannt" |
| `last_seen_at` | `DateTime(timezone=True)` | Heartbeat, jeder Tick |
| `ended_at` | `DateTime(timezone=True)`, nullable | `NULL` = laufende Session |

Index auf `started_at DESC` für die Panel-Abfrage.

**Die Dauer wird nicht gespeichert**, sondern aus `ended_at - started_at`
gerechnet. Ein gespeicherter Wert wäre eine zweite Wahrheit, die beim
Adoptieren einer Session nach einem Restart auseinanderlaufen kann.

**Invariante: höchstens eine offene Session** (`ended_at IS NULL`). Nicht per
DB-Constraint erzwungen — ein partieller Unique-Index wäre PostgreSQL-only und
die Tests laufen auf SQLite — sondern vom Schreiber, der beim Start defensiv
aufräumt.

Die Migration muss auf den echten `alembic heads` aufsetzen, **nicht** auf den
Head der Dev-DB (der Fehler hat schon einmal einen Prod-Deploy zerlegt,
#123 → #124).

### Ledger: die offene Session *ist* der Zustand

`SteamSessionPoller._last_app_id` und das `_initialized`-Flag entfallen
ersatzlos. Der Poller liest seinen Vorzustand aus der DB — eine Wahrheit statt
zweier, und der Restart-Sonderfall löst sich mit auf.

Pro Tick (30 s, primary-only dank #448):

```
app_id = detect_running_app_id()        # wie bisher, in asyncio.to_thread
open   = neueste Session mit ended_at IS NULL
luecke = now - open.last_seen_at        # wie lange war der Poller weg?
```

| offen | erkannt | Buchung | Meldung |
|---|---|---|---|
| — | — | nichts | — |
| — | X | INSERT X (`started_at = now`) | `session_started(X)` |
| X | X | `last_seen_at = now` | — |
| X | — | X schließen | `session_ended(X)` |
| X | Y | X schließen, INSERT Y | `session_ended(X)` + `session_started(Y)` |

Darüber liegen drei Lückenregeln. `_STALE_AFTER_SECONDS = 60` (zwei Ticks),
`_ADOPT_WINDOW_SECONDS = 600`:

1. **`ended_at = now`, wenn der Poller durchgehend da war** (`luecke ≤
   _STALE_AFTER_SECONDS`) — sonst `ended_at = last_seen_at`. War der Prozess
   weg, ist das letzte Lebenszeichen die einzige belastbare Zahl; `now` würde
   die Ausfallzeit als Spielzeit verbuchen.
2. **Nach einer Lücke wird nur gebucht, nie gemeldet.** Ein Deploy soll keine
   „Session beendet"-Push für ein Spiel auslösen, das vor zwei Stunden endete.
   Dieselbe Entscheidung wie TP3s Baseline-Regel, nur aus der DB statt aus
   einem Flag.
3. **Dasselbe Spiel über eine Lücke:** bis `_ADOPT_WINDOW_SECONDS` wird die
   Session weitergeführt (Deploy mitten im Spielen — der Normalfall auf dieser
   Box); darüber wird die alte bei `last_seen_at` geschlossen und eine neue
   eröffnet. Über Nacht aus und morgens dasselbe Spiel wieder gestartet ist
   nicht eine 14-Stunden-Session.

Beim Start räumt der Schreiber zusätzlich auf: **mehrere offene Sessions**
(nach der Invariante unmöglich, aber ein Crash zur Unzeit kann sie erzeugen)
werden bis auf die neueste stillschweigend bei ihrem `last_seen_at`
geschlossen.

**Reihenfolge, verbindlich: erst buchen und committen, dann melden.** Eine
fehlgeschlagene Zustellung darf keine Buchung zurückrollen.

### Retention

Einmal je 24 h löscht derselbe Tick Sessions mit `ended_at` älter als 365 Tage;
die offene Session ist davon nie betroffen. Bewusst **nicht** über
`monitoring/retention_manager.py`: der hängt am `MetricType`-Enum und an
`monitoring_config`-Zeilen — eine Plugin-Tabelle dort einzuhängen koppelt den
Core an ein Plugin. Zehn Zeilen im Plugin statt einer Enum-Erweiterung im Core.

Der Zeitpunkt der letzten Bereinigung lebt im Prozess (kein DB-Feld); ein
Restart führt höchstens zu einem zusätzlichen `DELETE`, das nichts findet.

### Panel

`DashboardPanelSpec` bekommt ein Feld:

```python
admin_only: bool = False
```

Durchgesetzt wird es **im Core**, in `api/routes/dashboard.py`, direkt nach
`plugin.get_dashboard_panel()`:

```python
if spec.admin_only and not is_privileged(current_user):
    return None
```

Warum im Core und nicht über einen Nutzer-Parameter an `get_dashboard_data()`:
keine Signaturänderung, das bestehende Tapo-Panel bleibt unangetastet, und kein
Plugin kann sein eigenes Gate falsch implementieren. Es folgt dem vorhandenen
Muster — `PluginNavItem` hat exakt dieses Feld. Dass `PluginMenuItem` in TP2
bewusst *kein* `admin_only` bekam, ist kein Widerspruch: eine Aktion *führt
etwas aus*, ein Panel *zeigt etwas an*.

Steams Spec: `panel_type="status"`, Titel „Steam Gaming", Icon `gamepad-2`,
`admin_only=True`.

Das Icon braucht **keine** Core-Frontend-Änderung: `PluginDashboardPanel.tsx:167-173`
löst den Namen dynamisch aus lucide auf (kebab-case → PascalCase, Fallback
`Plug`). Bemerkenswert im Vergleich zur Pill, deren `iconMap.ts` eine
geschlossene Core-Map ist — das ist genau die Lücke, die #451 M-2 beschreibt,
und der Panel-Pfad zeigt, dass die dort vorgeschlagene Option (b) im Haus
bereits erprobt ist.

Daten: die fünf neuesten Sessions (`ORDER BY started_at DESC LIMIT 5`); die
laufende steht durch die Sortierung oben.

```
Metro Exodus Enhanced Edition   1h 12m            tone=ok        ← ended_at IS NULL
Cyberpunk 2077                  23.07. · 3h 04m   tone=neutral
Metro Exodus Enhanced Edition   22.07. · 2h 41m   tone=neutral
Factorio                        21.07. · 5h 18m   tone=neutral
Cyberpunk 2077                  20.07. · 1h 02m   tone=neutral
```

`label` ist der Spielname, ersatzweise `AppID <n>`. `value` ist Datum + Dauer.

**Bewusst sprachneutral, keine Wörter.** `StatusItem` hat nur
`label`/`value`/`tone`, keine Key-Felder — der Renderer löst nichts auf. Ein
serverseitig festgetackertes „läuft · 1h 12m" wäre ein neuer Eintrag in #406.
Stattdessen trägt `tone=ok` die Information „läuft"; Datum und Dauer sind in
beiden Sprachen lesbar.

**Leerer Zustand:** noch keine Session verbucht → `get_dashboard_data()` gibt
`None`, das Panel erscheint nicht. Kein Platzhaltertext, der wieder übersetzt
werden müsste.

**Dev-Modus:** der Mock (`("0", "Dev Mode Game")`) lebt heute im
Pill-Collector. Er wandert eine Ebene tiefer in die gemeinsame
Erkennungsfunktion, sodass Pill, Ledger und Panel dieselbe Quelle benutzen —
sonst schreibt der Ledger auf einer Windows-Kiste nie eine Zeile und das Panel
ist lokal nicht testbar.

**Betriebshinweis:** Es kann nur *ein* Plugin-Panel gleichzeitig aktiv sein;
`set_dashboard_panel_enabled()` schaltet beim Einschalten alle anderen ab. Läuft
auf der Box gerade das Tapo-Panel, verdrängt Steam es. Bestehendes Verhalten,
aber hier zum ersten Mal spürbar.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| DB im Tick nicht erreichbar | Rollback, Warnung ins Log, Tick endet; der nächste Tick greift über die Lückenregel — verloren geht höchstens ein Heartbeat |
| `emit_plugin_event()` schlägt fehl | Buchung steht bereits; nur die Meldung fehlt (bestehendes Verhalten aus TP3) |
| `detect_running_app_id()` wirft | Tick loggt und endet; keine Buchung, keine Meldung |
| `appmanifest` fehlt/kaputt | `game_name=None`, Panel zeigt `AppID <n>` |
| Plugin wird deaktiviert, während gespielt wird | Background-Task stoppt, Session bleibt offen; beim Wiedereinschalten schließt die Lückenregel sie bei `last_seen_at` — still |
| Uhr springt rückwärts (NTP) | Dauer wird auf `max(0, …)` geklemmt; eine negative Dauer im Panel wäre schlimmer als eine geschönte Null |
| `get_dashboard_data()` wirft | Route fängt das bereits ab (`dashboard.py:51-57`) und liefert das Panel mit `data=None` |

## Sicherheit

- Kein neuer Subprocess, kein sudo, keine neue sudoers-Regel, keine neue Route.
- Was sich ändert: Spielnamen werden **erstmals dauerhaft gespeichert** statt
  nur flüchtig angezeigt. Deshalb Panel `admin_only` und Retention 365 Tage.
- Die Tabelle enthält nichts, was unter `REDACT_PATTERN`
  (`services/audit/admin_db.py:13`) fiele — kein Secret, kein Token. Die
  Admin-DB-Ansicht zeigt sie im Klartext, was für Admins korrekt ist.
- Der Ledger schreibt nur Werte, die der Detector aus `/proc` und den
  `appmanifest`-Dateien liest; keine Benutzereingabe erreicht die Tabelle.

## Tests

**Ledger** (In-Memory-SQLite, injizierte Uhr):

- alle fünf Zeilen der Flankentabelle;
- frische vs. stale Lücke — `ended_at = now` vs. `ended_at = last_seen_at`;
- nach einer Lücke wird **nichts** gemeldet;
- dasselbe Spiel über 5 min → eine Session; über 30 min → zwei;
- mehrere offene Sessions werden bis auf die neueste geschlossen;
- Retention löscht nur `ended_at < now - 365 d` und lässt die offene Session in
  Ruhe;
- Uhr-Rücksprung ergibt Dauer 0, keine negative Zahl.

**Poller:** meldet genau die Events, die der Ledger zurückgibt — insbesondere
**beide** beim Spielwechsel (#462).

**Panel:** Admin bekommt Daten, Nicht-Admin bekommt `None` (Gate in der Route,
nicht im Plugin); Formatierung für laufende Session, `< 1 h`, `> 1 h`; keine
Sessions → `None`.

**Migration:** `upgrade` und `downgrade` lokal gegen SQLite **und** PostgreSQL
prüfen. CI hat dafür keinen Smoke-Test (#450) — das ist Handarbeit.

## Umfang

```
NEU   backend/app/models/steam_session.py                ~30 Z.
NEU   backend/alembic/versions/<rev>_steam_sessions.py   ~40 Z.
NEU   .../installed/steam_gaming/ledger.py              ~120 Z.
NEU   backend/tests/test_steam_gaming_ledger.py         ~250 Z.
ÄND   .../installed/steam_gaming/poller.py              Zustand entfällt
ÄND   .../installed/steam_gaming/__init__.py            Panel + Dev-Mock
ÄND   backend/app/plugins/base.py                       DashboardPanelSpec.admin_only
ÄND   backend/app/api/routes/dashboard.py               admin_only-Gate
ÄND   backend/app/models/__init__.py                    Registrierung
ÄND   backend/app/plugins/CLAUDE.md                     Panel-Doku
```

## Folgearbeiten

- **Retention konfigurierbar machen** — 365 Tage sind hier fest verdrahtet;
  Issue wird mit dieser Spec angelegt.
- **#462** wird von diesem Teilprojekt geschlossen.
- **#451 M-3** (Pill-`href` auf eine gegatete Route) bleibt offen — ohne eigene
  Steam-Seite gibt es kein besseres Ziel.
- **Per-Nutzer-Kategorie-Preference für Plugin-Events** — eigene Core-Spec.
- Doku-Drift in `backend/app/plugins/CLAUDE.md`: dort steht, der
  Panel-Endpunkt hänge *nicht* an `reconciled_plugin_state` — im Code hängt er
  dran (`api/routes/dashboard.py`). Wird hier mitkorrigiert, weil genau dieser
  Pfad angefasst wird.
