# Status-Bar-Plugin-Pills + Steam-Gaming-Plugin — Design

**Datum:** 2026-07-22
**Status:** entworfen, abgenommen
**Teilprojekt 1 von 4** (siehe [Gesamtschnitt](#gesamtschnitt))

## Ziel

BaluNode ist zugleich NAS und Gaming-Rechner. Die Web-UI soll anzeigen, wenn
gerade gespielt wird, und Steam bequem startbar machen. Umgesetzt als
**bundled Plugin** — nicht als Core-Feature.

Dieses Teilprojekt liefert die Anzeige: eine Status-Leisten-Pill „Gaming
Session", beigesteuert von einem Plugin über einen **neuen Extension-Point**.

## Gesamtschnitt

Der Wunsch berührt drei Core-Systeme, die heute keine Plugin-Erweiterung
zulassen. Statt eines Großumbaus wird in vier Teilprojekten geliefert, jedes
mit eigener Spec, eigenem Plan und eigener Abnahme:

| # | Teilprojekt | Inhalt |
|---|---|---|
| **1** | **Pill-Extension-Point + Steam-Plugin** | *dieses Dokument* |
| 2 | Menü-Contribution | `PluginUIManifest` + `menu_items`; „Gaming-Modus" (Displays an + Steam) im System-Menü |
| 3 | Notification-Registry | `EventType`-Enum → offene Registry; Plugin-Events in die Zustellung |
| 4 | Feinschliff | Big Picture vs. Fenster, Auto-Displays-aus nach Sessionende, Dashboard-Panel mit Historie |

Der Extension-Point wird bewusst **zusammen mit seinem ersten Konsumenten**
gebaut. Eine API ohne echten Nutzer zu entwerfen produziert fast zwangsläufig
den falschen Schnitt.

## Ausgangslage (gemessen, nicht angenommen)

Alle Angaben stammen aus Messungen auf der Prod-Box (BaluNode), nicht aus
Dokumentation oder Vermutung.

### Prozess- und Session-Modell

- Der Backend-Dienst läuft als **`sven` (UID 1000)** — demselben User, dem die
  KDE-Wayland-Session auf `seat0` gehört (`Active=yes`). Einen `baluhost`-User
  gibt es auf der Box nicht.
- Damit ist der Zugriff auf Steam-Prozesse und `~`-Pfade **ohne sudo** möglich.
  `services/power/desktop_backend.py` nutzt bereits denselben Umstand
  (`XDG_RUNTIME_DIR=/run/user/1000` + `WAYLAND_DISPLAY`), um `kscreen-doctor`
  in die Session zu schicken — der Präzedenzfall für Teilprojekt 2.
- Steam ist **nativ** installiert (`/usr/bin/steam`, kein Flatpak/Snap) und
  läuft dauerhaft über die User-Unit `app-steam@autostart.service`.

### Erkennungssignale

Gemessen mit laufendem Spiel (Metro Exodus Enhanced Edition, AppID 1449560):

```
591737  4367    /bin/sh -c mangohud …/steam-launch-wrapper -- …/reaper SteamLaunch AppId=1449560 -- …
591762  591737  …/ubuntu12_32/reaper SteamLaunch AppId=1449560 -- … Proton 10.0/proton … MetroExodus.exe
```

- ✅ **`reaper SteamLaunch AppId=<n>`** — trägt die AppID in der Kommandozeile.
  Gilt für native wie für Proton-Titel; der Spielbaum hängt vollständig unter
  `steam(4367)`.
- ⚠️ **Doppeltreffer:** Durch den `mangohud`-Wrapper erscheint dieselbe AppID in
  zwei Prozessen. Die Erkennung **muss nach AppID deduplizieren**.
- ❌ **`registry.vdf` / `RunningAppID`** ist unbrauchbar. Modernes Steam setzt
  den Wert nicht mehr (konstant `0`); auf der Box liefert die Abfrage auch im
  laufenden Spiel nichts. Offener Valve-Bug:
  [steam-for-linux#9672](https://github.com/ValveSoftware/steam-for-linux/issues/9672).
- ❌ **Keine systemd-Scope pro Spiel.** `systemctl --user --type=scope` zeigt nur
  `init.scope`; unter `app-*` existiert lediglich die Steam-Autostart-Unit.

### Vorhandener Code

- `services/game_libraries/` — findet Steam-Roots über `libraryfolders.vdf`,
  liest `appmanifest_<id>.acf`, filtert Proton/Runtimes. Rein lesend, nur
  Metadaten. **Die Root-Erkennung und der VDF-Parser werden wiederverwendet.**
  Die Bibliothek der Box liegt unter `/mnt/cache-vcl/SteamLibrary` und wird
  von dieser Logik bereits korrekt aufgelöst.
- `services/status_bar/` — katalog-getriebene Pills (`catalog.py`,
  `collectors.py`, `service.py`), Config je Pill in der DB.
- `lib/pluginI18n.ts` — `resolvePluginString(translations, key, fallback)`, das
  etablierte Muster für Plugin-Texte im Frontend.

## Nicht-Ziele

- Menü-Eintrag, Notification, Session-Dauer, Dashboard-Panel → Teilprojekte 2–4.
- Fallback für Spiele mit Drittanbieter-Launcher (Ubisoft Connect, EA App).
  Solche Titel starten das Spiel aus einer zweiten Launcher-Schicht, wobei
  Steam den Prozess verlieren kann — dann verschwindet auch der `reaper`.
  Ungemessen, weil kein solches Spiel installiert ist. Der Detector wird so
  geschnitten, dass ein zweites Signal ergänzbar ist, **ohne** ihn umzubauen.
- Erkennung von Spielen außerhalb von Steam (Lutris, native Installationen).

## Architektur

```
backend/app/plugins/installed/steam_gaming/
  __init__.py     SteamGamingPlugin: Metadaten, Pill-Spec, Collector, de/en
  detector.py     /proc-Scan → RunningGame | None  (+ TTL-Cache)
  names.py        AppID → Spielname über appmanifest_<id>.acf

backend/app/plugins/base.py          + get_status_pills(), collect_status_pill()
backend/app/schemas/status_bar.py    PILL_IDS → validierter String; PillState erweitert
backend/app/services/status_bar/service.py   effektiver Katalog = Core + Plugins

client/src/components/topbar/…       Renderer-Zweig für Plugin-Texte
client/src/components/status-bar-config/…    Plugin-Pills in der Admin-Liste
```

### Erkennung

```python
@dataclass(frozen=True)
class RunningGame:
    app_id: str
    name: str | None
```

Ablauf:

1. Über `/proc/*/cmdline` iterieren, Nullbytes zu Leerzeichen normalisieren.
2. `SteamLaunch AppId=(\d+)` matchen und alle Treffer sammeln.
3. **Nach AppID deduplizieren.** Der `mangohud`-Wrapper erzeugt zwei Prozesse
   mit derselben AppID — ohne Dedupe zählt dasselbe Spiel doppelt.
4. Bleiben danach **mehrere verschiedene** AppIDs übrig (zwei parallel laufende
   Spiele), gewinnt die mit der niedrigsten PID, also das zuerst gestartete
   Spiel. Bewusste Vereinfachung: Die Pill zeigt eine Session, nicht eine
   Liste. Der Detector gibt die vollständige Liste zurück, damit spätere
   Teilprojekte ohne Umbau darauf zugreifen können.
5. Namen über `names.resolve(app_id)` auflösen; schlägt das fehl, bleibt
   `name=None` und die Pill zeigt nur das Label.

Nicht lesbare oder währenddessen verschwindende `/proc`-Einträge werden
übersprungen (`ProcessLookupError`, `PermissionError`, `FileNotFoundError`) —
im laufenden System sterben Prozesse zwischen `listdir` und `read`.

**Ausführungsort:** direkt im Collector, mit **3 s TTL-Cache pro Worker**.
Begründung:

- Kein Background-Task, damit kein Zustand über die vier Prod-Worker geteilt
  werden muss (weder SHM noch DB noch Primary-Worker-Sonderfall).
- Die Statusleiste pollt alle 10 s pro angemeldetem Nutzer; der Cache verhindert,
  dass mehrere gleichzeitige Requests denselben Scan mehrfach fahren.
- Der Scan kostet wenige Millisekunden (einige hundert `cmdline`-Reads).
- Maximale Staleness 3 s — für eine Anwesenheitsanzeige irrelevant.

Ein Poller wird erst für die Notification in Teilprojekt 3 gebraucht (Flanken­
erkennung Start/Ende); der läuft dann primary-only.

Die Namensauflösung cached AppID → Name **unbegrenzt** (ein Spielname ändert
sich nicht) und negative Ergebnisse für 60 s (ein `appmanifest` kann während
einer laufenden Installation auftauchen).

### Extension-Point

```python
# plugins/base.py
def get_status_pills(self) -> List[StatusPillSpec]:
    """Status-Leisten-Pills dieses Plugins. Default: keine."""
    return []

async def collect_status_pill(self, pill_id: str, db: Session) -> Optional[dict]:
    """Aktueller Zustand einer Pill, oder None um still zu bleiben."""
    return None
```

```python
class StatusPillSpec(BaseModel):
    id: str                      # plugin-lokales Suffix, z. B. "session"
    icon: str                    # lucide-Name, z. B. "Gamepad2"
    href: str
    default_visibility: Literal["admin", "all"] = "admin"
    visibility_locked: bool = False
    silent_when_ok: bool = True
    name_key: str                # Schlüssel in get_translations() für den Katalognamen
    name_text: str               # Literal-Fallback für dieselbe Bezeichnung
```

**ID-Namespace.** Die öffentliche ID lautet `plugin:<plugin_name>:<suffix>`,
gebildet vom Core, nicht vom Plugin. `PILL_IDS` wird von `Literal[...]` zu
einem validierten String: entweder eine bekannte Core-ID oder das
`plugin:`-Schema. Damit sind Kollisionen mit Core-IDs ausgeschlossen und
bestehende Core-IDs bleiben unverändert gültig.

**Effektiver Katalog.** `StatusBarService` bildet `CATALOG` + Pills aller
**aktivierten** Plugins. `_ensure_rows()` legt für Plugin-Pills dieselben
Config-Rows an wie für Core-Pills, `collect_state()` verteilt an den
Core-Collector oder an `plugin.collect_status_pill()`.

**Verwaiste Rows lösen sich von selbst.** `collect_state()` filtert bereits
heute auf „ID im Katalog". Ein deaktiviertes oder deinstalliertes Plugin
verschwindet damit aus der Leiste; seine Einstellungen (an/aus, Reihenfolge,
Sichtbarkeit) bleiben in der DB erhalten und gelten wieder, sobald das Plugin
zurückkommt. Es ist kein Aufräumjob nötig.

**Abweichung von der Core-Konvention:** Core-Pills werden mit `enabled=False`
angelegt und müssen vom Admin aktiviert werden. **Plugin-Pills starten mit
`enabled=True`** — wer ein Plugin installiert, dessen Zweck die Anzeige ist,
soll die Anzeige nicht erst suchen müssen. Bewusste Entscheidung, im Code zu
dokumentieren.

**Texte.** `PillState` bekommt zwei optionale Felder:

- `label_text: str | None` — bereits lesbarer Literal-Fallback
- `translations: dict | None` — die Übersetzungen des Plugins für diese Pill

Das Frontend verzweigt: sind `translations` gesetzt, wird
`resolvePluginString(translations, label_key, label_text)` benutzt (Muster von
`PluginDashboardPanel`), sonst wie bisher `t(label_key)`. Der Spielname geht in
das **vorhandene** `value`-Feld, das schon für reine Daten (`"72°C"`) gedacht
ist und nicht übersetzt wird.

Dieselben zwei Felder braucht auch `PillCatalogEntry`: Die Admin-Konfiguration
listet Pills mit ihrem Namen (`name_key`), und für Plugin-Pills liegt dieser
Name ebenfalls nicht im Core-Bundle. `PillCatalogEntry` bekommt daher
`name_text` und `translations` und wird im Konfigurations-UI über denselben
Zweig aufgelöst.

**Isolation.** Plugin-Collectoren laufen im vorhandenen `_safe`-Wrapper
**plus** `asyncio.wait_for(..., timeout=2.0)`. Core-Collectoren haben heute
kein Timeout; für einen öffentlichen Extension-Point ist eins nötig, sonst legt
ein blockierender Collector die gesamte Leiste lahm. Zeitüberschreitung und
Exception führen beide dazu, dass die Pill stumm bleibt — nie zu einem 5xx.

### Pill-Verhalten

| Zustand | Anzeige |
|---|---|
| Kein Spiel | Pill unsichtbar (`silent_when_ok=True`) |
| Spiel erkannt, Name aufgelöst | `🎮 Gaming Session · Metro Exodus Enhanced Edition` |
| Spiel erkannt, Name unbekannt | `🎮 Gaming Session` |

Icon `Gamepad2`, Ton `info`, Sichtbarkeit `admin` (Vorgabe, vom Admin
änderbar). `href` zeigt vorerst auf die **Plugin-Verwaltung**; eine dedizierte
Steam-Seite ist für Teilprojekt 4 angedacht, dann wandert das Ziel dorthin.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| `/proc` nicht lesbar (Windows-Dev) | Detector liefert `None`; im Dev-Modus greift ein Mock |
| Prozess verschwindet während des Scans | Eintrag überspringen |
| `appmanifest` fehlt/kaputt | `name=None`, Pill zeigt nur das Label |
| Plugin-Collector wirft | Pill stumm, Warnung im Log mit Pill-ID |
| Plugin-Collector hängt | Nach 2 s abgebrochen, Pill stumm |
| Plugin deaktiviert | Pill fällt aus dem Katalog, Config-Row bleibt |

## Sicherheit

- Kein sudo, keine neuen Sudoers-Regeln, kein Subprocess. Es wird ausschließlich
  `/proc` gelesen — und dort nur, was dem eigenen User gehört.
- Keine Pfade aus Benutzereingaben; Steam-Roots stammen aus der bestehenden,
  fest kodierten Kandidatenliste.
- Die Pill ist standardmäßig `admin`-sichtbar. Der Spielname ist eine Information
  über den Box-Besitzer und soll nicht ungefragt für alle Nutzer erscheinen.
- Der Extension-Point erlaubt Plugins nur, **Daten zu liefern**; Icon, `href` und
  Sichtbarkeit bleiben über den Katalog admin-kontrolliert.

## Tests

**Detector** (gegen einen injizierten `/proc`-Reader, kein echtes Dateisystem):
Fund mit AppID, Dedupe der mangohud-Doppeltreffer, kein Spiel, kaputte/leere
cmdline, verschwindender Prozess. TTL-Cache: zweiter Aufruf innerhalb des
Fensters scannt nicht erneut, danach schon.

**Namensauflösung:** `appmanifest` vorhanden → Name; fehlend → `None`;
Negativ-Cache läuft ab.

**Extension-Point:** Plugin-Pill erscheint in Config *und* State; ID-Namespace
kollidiert nicht mit Core-IDs; werfender Collector lässt die übrigen Pills
unberührt; hängender Collector wird nach 2 s abgeschnitten; deaktiviertes
Plugin → Pill weg, Config-Row überlebt und gilt nach Reaktivierung wieder;
Plugin-Pills starten mit `enabled=True`, Core-Pills weiterhin mit `False`.

**Frontend:** Renderer nimmt `resolvePluginString`, wenn `translations` da sind,
sonst `t()`; Plugin-Pills erscheinen in der Admin-Konfigurationsliste.

## Risiken

- **Drittanbieter-Launcher** (siehe Nicht-Ziele) — ungemessen. Auswirkung: Die
  Pill bliebe bei solchen Titeln stumm. Kein Datenverlust, kein Fehlverhalten.
- **Steam ändert den `reaper`-Aufruf.** Dann bricht die Erkennung still. Der
  Detector ist eine einzelne, klar benannte Funktion mit Tests — der Bruch wäre
  lokal und schnell zu korrigieren. Ein zweites Signal ist nachrüstbar.
- **`PILL_IDS` von `Literal` zu String** lockert eine Typprüfung. Kompensiert
  durch einen Validator, der nur Core-IDs und das `plugin:`-Schema zulässt.
