# Display-Output-Steuerung als bundled Plugin — Design

**Datum:** 2026-09-08
**Status:** Entwurf zur Prüfung
**Issue:** [#590](https://github.com/Xveyn/BaluHost/issues/590)
**Vorgänger:** `docs/superpowers/plans/2026-09-08-display-output-control.md` (Diagnose vom
selben Tag, auf BaluNode geschrieben). Dieses Dokument **ersetzt** dessen
Architektur- und Adressierungsentscheidungen; siehe Abschnitt 11.
**Host der Messungen:** BaluNode (Debian 13, KDE Plasma 6 / KWin Wayland, Backend als `User=sven`)

---

## 1. Problem

Die Webapp kann Displays heute nur global an- und ausschalten
(`kscreen-doctor --dpms on|off` über `PowerMenu`). Sie kann nicht sagen, **welche**
Ausgänge es gibt, welcher gewählt ist, oder in welchem Video-Modus er läuft — und
sie kann nichts davon ändern. Wer vom TV (DP-3) auf den Monitor (HDMI-A-1)
wechseln will, braucht heute eine SSH-Sitzung und `deploy/scripts/display-switch`.

## 2. Lösung in einem Satz

Ein bundled Plugin `display_output` enumeriert die KWin-Ausgänge und setzt Auswahl
und Video-Modus über einen einzigen `kscreen-doctor`-Aufruf; bedient wird es über
ein Popover in der Topbar, direkt neben der Audiosteuerung.

## 3. Warum bundled und in-process

Dieselbe Begründung wie bei `audio_control`, und sie ist keine Bequemlichkeit,
sondern die technische Untergrenze:

Das Plugin läuft im Host-Prozess und damit unter derselben UID wie die
Plasma-Session. Nur deshalb erreicht `wayland_session_env()` (`XDG_RUNTIME_DIR` +
`WAYLAND_DISPLAY`) den KWin-Socket. Ein **Sandbox-Plugin** läuft als
`baluhost-plugin` in einer eigenen Netzwerk-Namespace und käme an diesen Socket
**nie** heran.

Belegt am Gegenbeispiel: `kscreen-doctor -j` aus einer SSH-Sitzung ohne diese
Variablen bricht ab — Qt fällt auf das `xcb`-Plugin zurück und findet kein
Display. Der Env-Helfer ist also tragend, nicht dekorativ.

**Kein Kernfeature**, weil nicht jede Installation einen Desktop hat: ein
kopfloses NAS hat keine KWin-Session, und ein Feature, das dort dauerhaft
„nicht verfügbar" meldet, gehört abschaltbar.

## 4. Gemessene Grundlage

`kscreen-doctor -j` auf BaluNode, 35 066 Bytes, 2026-09-08. Fünf Befunde, die den
Entwurf tragen:

### 4.1 Mode-Namen sind mehrdeutig — der zentrale Befund

`libkscreen/src/doctor/doctor.cpp`, `findMode()`:

```cpp
auto name = QStringLiteral("%1x%2@%3")
    .arg(QString::number(mode->size().width()),
         QString::number(mode->size().height()),
         QString::number(qRound(mode->refreshRate())));
if (mode->id() == query || name == query) {
    return mode;
}
```

Der Name entsteht durch **`qRound()`** der Bildwiederholrate. 119,88 und 120,000
werden damit beide zu `3840x2160@120`. Die Kollision steckt im Namensschema, nicht
in den Daten dieses Hosts.

Gemessen auf HDMI-A-1: 55 Modi, **45** verschiedene Namen. Sechs Namen sind
mehrfach belegt (`720x480@60` viermal, `1920x1080@60` und `1280x720@60` je
dreimal, `3840x2160@60`, `640x480@60`, `720x576@50` je zweimal) — zehn Modi
verstecken sich also hinter einem fremden Namen.

Auf DP-3 trifft es den praktisch wichtigen Fall:

```
id 57  "3840x2160@120"  refreshRate 120.000   <- aktuell aktiv
id 58  "3840x2160@120"  refreshRate 119.880
```

`findMode()` gibt beim ersten Treffer zurück und bricht ab. Ein Aufruf über den
Namen setzt also einen der beiden — welchen, entscheidet die Listenreihenfolge.
Ohne Fehlermeldung.

**Zugleich beweist dieselbe Codezeile: die Mode-ID ist ein gültiges Argument**
(`mode->id() == query`). `output.DP-3.mode.57` funktioniert.

### 4.2 Nur angeschlossene Ausgänge werden gelistet

`/sys/class/drm/` kennt `card0-DP-1` und `card0-DP-2`; im JSON tauchen sie
**nicht** auf. `connected` bleibt im Schema, ist praktisch aber immer `true`.
Ein Dev-Backend, das einen `disconnected`-Ausgang liefert, würde einen Zustand
nachbilden, den das echte Backend nie erzeugt.

### 4.3 Feldpräsenz schwankt zwischen Ausgängen

HDMI-A-1 trägt `vrrPolicy`, DP-3 **nicht**. Der Parser greift durchgehend über
`.get()` zu; ein direkter Indexzugriff kippt am zweiten Ausgang.

### 4.4 `currentModeId` und `preferredModes` sind IDs

Beides sind ID-Strings (`"57"`, `["56"]`), keine Namen. Die Auflösung zum
anzeigbaren Modus läuft ohnehin über die ID-Tabelle.

### 4.5 Die Modenliste ist lexikografisch nach ID-String sortiert

`"1", "10", "11", …, "2", "20"`. Ungefiltert ins Dropdown gekippt unbrauchbar.

### 4.6 Zwei geprüfte Nicht-Befunde

- **Die `lit`-Zuordnung trägt.** `card0-DP-3` → `DP-3`, `card0-HDMI-A-1` →
  `HDMI-A-1`. Präfix-Strip (`^card\d+-`) trifft die KWin-Namen exakt.
- **`card0-Writeback-1` ist harmlos.** Gemessen: `status=unknown`,
  `enabled=disabled`. Der Filter in `display_detector.py` verlangt
  `status == "connected"` **und** `enabled == "enabled"`; ein
  Writeback-Connector meldet nie `connected` und wird deshalb nie mitgezählt.
  Notiert, damit der nächste Leser der Regex diese Runde nicht wiederholt.

## 5. Die zwei Ebenen von „an"

Der Kern der Zustandsdarstellung, und die Ursache der bestehenden Verwirrung:

| Ebene | Quelle | Bedeutung |
|---|---|---|
| **KWin** | `kscreen-doctor -j`, Feld `enabled` | die Ausgangs**wahl** |
| **DRM** | sysfs `enabled` je Connector | ob tatsächlich Pixel getrieben werden |

Bei DPMS-off sind **alle** DRM-Connectoren `disabled`, während KWin seine Wahl
behält. Genau dieser Zustand liegt auf BaluNode aktuell vor und lässt
`DesktopTogglePanel` „Gestoppt" melden, obwohl KWin DP-3 für aktiv hält. Kein
Bug — nur zwei Wahrheiten über verschiedene Dinge.

Im Schema heißen sie deshalb **`selected`** (KWin) und **`lit`** (DRM), nicht
zweimal `enabled`. Die Namensgleichheit ist die Ursache der Verwirrung und soll
nicht ins Schema wandern.

`display_detector.py` liefert heute nur eine *Zahl*. Es bekommt
`get_connector_states() -> dict[str, bool]` dazu — derselbe sysfs-Lauf, nur mit
Namen. Der Reader bleibt im Core, weil `desktop_backend` und `steam_gaming` ihn
schon nutzen; zwei sysfs-Leser für dieselbe Frage wären die schlechtere Antwort.

Lässt sich ein KWin-Name keinem Connector zuordnen, ist `lit` **`None`** — nicht
`False`. Eine unbekannte Antwort als „aus" auszugeben wäre eine Falschaussage.

## 6. Architektur

```
plugins/installed/display_output/
  __init__.py   DisplayOutputPlugin, Router, Audit, Fehlerabbildung
  kscreen.py    einziger Ort, der kscreen-doctor kennt: Parser + run_kscreen{,_json}
  backend.py    DisplayBackend-Protocol, DevDisplayBackend, KWinDisplayBackend
  service.py    DisplayService, Singleton, Validierung
  models.py     Pydantic-Modelle (= API-Vertrag zum Frontend)
  CLAUDE.md
```

Spiegelt `audio_control` Datei für Datei. Zwei Fallen von dort werden übernommen:

- **Kein `from __future__ import annotations` in `__init__.py`.** Zusammen mit
  Pydantic v2 und FastAPIs Body-Erkennung durch den `@user_limiter.limit`-Wrapper
  werden aufgeschobene Annotationen zu ForwardRefs; der Request-Body würde als
  Query-Parameter gelesen und jedes `POST` antwortete 422.
- **`get_ui_manifest()` muss überschrieben werden** mit
  `PluginUIManifest(enabled=True)` und leerer `nav_items`-Liste. `PluginBase`
  liefert dort `None`, und `GET /api/plugins/ui/manifest` listet nur Plugins mit
  wahrhaftigem Manifest — genau die Liste, die `usePluginEnabled` liest. Ohne
  Override ist das Plugin im Frontend für immer „aus", ohne Fehler und ohne
  Logzeile. Leere `nav_items` heißt: keine Route, also wird nie ein `bundle.js`
  geholt.

## 7. Adressierung: Ausgang über Namen, Modus über lebende ID

Die Regel in einem Satz: **niemals eine gespeicherte ID, immer eine aus derselben
Enumeration.**

| Was | Wie adressiert | Warum |
|---|---|---|
| Ausgang | Connector-Name (`DP-3`) | stabile Hardware-Identität, deckungsgleich mit DRM |
| Modus | Mode-**ID** aus der aktuellen Enumeration (`57`) | der Name ist nach 4.1 mehrdeutig |

`GET /state` liefert die IDs der laufenden Enumeration. `POST /apply` schickt
`mode_id` **und** `mode_name` zurück. Der Server liest frisch und prüft:

1. `name` steht in der live enumerierten Ausgangsliste — sonst **400**
2. `mode_id` steht in der Modenliste **genau dieses** Ausgangs — sonst **400**
   *(das ist #589 als Testfall)*
3. der Modus hinter `mode_id` trägt noch `mode_name` — sonst **409**

Zwei Randfälle, damit sie nicht offenbleiben: `mode_name` ist **Pflicht, sobald
`mode_id` gesetzt ist** (nur eines von beiden → 400, sonst wäre die Gegenprobe
abschaltbar). Und ein Modus an einem Ausgang mit `selected: false` wird
**ignoriert**, nicht abgelehnt — KWin behält die Modus-Wahl eines abgewählten
Ausgangs ohnehin, und ein 400 dafür wäre eine Schikane gegenüber einer UI, die
schlicht den zuletzt angezeigten Zustand zurückschickt.

Schritt 3 schließt das Fenster zwischen `GET` und `POST`: schiebt sich ein
Hotplug dazwischen und werden IDs neu vergeben, meldet der Server einen Konflikt,
statt still den falschen Modus zu setzen. Dieselbe Haltung, mit der
`audio_control` volatile PipeWire-Indizes behandelt — 404 statt Raten, die UI
lädt neu.

**Abgrenzung zu #589:** dort steht eine ID als **Konstante im Shell-Skript** und
überlebt Neustarts, an denen KWin neu nummeriert. Hier lebt die ID Sekunden und
wird gegengeprüft. Der Unterschied ist nicht die ID, sondern ihre Haltbarkeit.

### 7.1 Modenliste fürs Dropdown

Roh sind 55 Einträge in ID-String-Reihenfolge, mit Dubletten. Der Parser:

1. fasst **exakte** Dubletten zusammen (gleiche Breite, Höhe **und**
   `refreshRate`, etwa HDMI-A-1 id 9 und 10) und behält die kleinste ID.
   Solche Paare unterscheiden sich nur in DRM-Timing-Flags (CEA gegen DMT) —
   ein Unterschied, der sich einem Menschen nicht sinnvoll anzeigen lässt;
2. sortiert absteigend nach Fläche, dann nach `refreshRate`;
3. beschriftet mit zwei Nachkommastellen: `3840×2160 @ 120,00 Hz` neben
   `3840×2160 @ 119,88 Hz`.

Aus 55 Roheinträgen werden so **50** unterscheidbare (fünf exakte Dubletten
fallen weg: je eine bei `1920x1080@60`, `1280x720@60` und `720x576@50`, zwei bei
`720x480@60`), und die Beschriftung ist innerhalb eines Ausgangs eindeutig.
Die Zahlen sind Testgegenstand, nicht Prosa — die Fixture muss sie hergeben.

## 8. API

Alle Routen unter `/api/plugins/display_output/`, beide gegated mit
`Depends(require_power_manage_displays)` und
`@user_limiter.limit(get_limit("display_output"))`:

| Methode | Pfad | Body | Antwort |
|---|---|---|---|
| GET | `/state` | — | `DisplayLayout` |
| POST | `/apply` | `DisplayApplyRequest` | `{"success": bool, "message": str}` |

```python
class DisplayMode(BaseModel):
    id: str                 # lebende KWin-Mode-ID, nur innerhalb dieses Vorgangs gueltig
    name: str               # "3840x2160@120" - NICHT eindeutig, nur zur Gegenpruefung
    width: int
    height: int
    refresh_rate: float     # exakt, ungerundet: 119.88 vs 120.0
    label: str              # "3840x2160 @ 119,88 Hz" - fuer das Dropdown

class DisplayOutput(BaseModel):
    name: str               # "DP-3"
    connected: bool
    selected: bool          # KWin-Ebene
    lit: Optional[bool]     # DRM-Ebene; None = nicht zuordenbar
    current_mode_id: Optional[str]
    preferred_mode_id: Optional[str]
    scale: float            # nur Anzeige, in v1 nicht setzbar
    priority: int
    modes: list[DisplayMode]

class DisplayLayout(BaseModel):
    outputs: list[DisplayOutput]
    displays_powered: bool  # globaler DPMS-Zustand (mindestens ein Connector leuchtet)
    available: bool
    detail: Optional[str]

class DisplayOutputRequest(BaseModel):
    name: str
    selected: bool
    mode_id: Optional[str] = None
    mode_name: Optional[str] = None   # Gegenprobe zu mode_id

class DisplayApplyRequest(BaseModel):
    outputs: list[DisplayOutputRequest]
```

**Neue Limit-Kategorie** `display_output` in `core/rate_limiter.py` bei
**60/minute**: das Popover fragt nur im geöffneten Zustand alle 5 s ab (≈12/min);
`admin_operations` mit 30/min wäre bei zwei offenen Tabs bereits knapp.

**Auch der Lesezugriff ist gegated** — die Ausgangsliste verrät die angeschlossene
Hardware samt EDID-Größenangaben.

## 9. `apply`: ein Aufruf, Whitelist davor

```
kscreen-doctor output.DP-3.enable output.DP-3.mode.57 output.HDMI-A-1.disable
```

`kscreen-doctor` wendet alle Argumente eines Aufrufs gemeinsam an — kein
Teilzustand bei Fehlern. Das ist der Grund, warum `apply` **genau einen**
Unterprozess startet und nicht mehrere.

Vor dem Bau des argv gilt: **kein Zeichen aus dem Request wird zu einem
argv-Element, ohne vorher in der Enumeration gestanden zu haben.** Namen und IDs
werden nicht escaped oder gefiltert, sondern gegen gemessene Werte abgeglichen;
was nicht dort steht, existiert für den Aufruf nicht. Listen-Argumente schließen
Shell-Injektion ohnehin aus — das hier ist der Gurt zum Hosenträger, und er hält
auch dann, wenn `kscreen-doctor` künftig eigene Argument-Syntax dazulernt.

### 9.1 Invariante: nie alle Ausgänge abwählen

Bliebe nach dem `apply` kein verbundener Ausgang `selected`, → **400**. „Nichts
soll leuchten" ist ein legitimer Wunsch, aber der Weg dafür ist der DPMS-Schalter
im `PowerMenu`: reversibel, und er wirft die KWin-Konfiguration nicht weg.

### 9.2 Kein Confirm/Revert-Timer

Der klassische Footgun — Modus gesetzt, Bild schwarz, keine Bedienung mehr —
greift hier nicht: bedient wird über Netz, nicht am betroffenen Schirm. Ein nicht
synchronisierender Modus macht den Schirm dunkel, die Webapp bleibt erreichbar,
der nächste `apply` korrigiert. Ein Rückfall-Timer wäre eine zusätzliche
Zustandsmaschine ohne Nutzen.

### 9.3 Fehlerabbildung

| Fall | Status |
|---|---|
| unbekannter Ausgang, fremde/unbekannte Mode-ID, alles abgewählt | 400 |
| `mode_name` passt nicht mehr zu `mode_id` | 409 |
| `kscreen-doctor` fehlt, Zeitüberschreitung, Session weg | 502 |
| Erfolg | 200 `{"success": true}` |

**stdout/stderr von `kscreen-doctor` erreichen nie den Client** — sie tragen
EDID-Namen und Pfade. Sie werden geloggt; die Antwort trägt eine kuratierte
Meldung.

Audit-Eintrag `display_apply` (event_type `POWER`) mit dem angewendeten
argv-Vektor in `details`, dazu — wie bei `audio_control` — ein
`delegated_power_action`-Sicherheitseintrag, wenn der Aufrufer kein Admin ist.

## 10. Frontend

`client/src/components/topbar/DisplayMenu.tsx`, Monitor-Symbol links neben dem
Lautsprecher. Eingehängt in `layout/LayoutHeader.tsx` neben Zeile 44:

```tsx
{!isPi && displaysEnabled && <DisplayMenu />}
```

`displaysEnabled = usePluginEnabled('display_output')`; zusätzlich prüft die
Komponente clientseitig `can_manage_displays` über `getMyPowerPermissions()` —
exakt das Muster von `AudioMenu.tsx`.

Pro Ausgang eine Zeile: Name · zwei **getrennte** Abzeichen „gewählt" (KWin) und
„leuchtet" / „dunkel — DPMS aus" (DRM) · Mode-Dropdown · Auswahlschalter. Unten
ein „Anwenden", das genau einen `apply` auslöst; danach Refetch.

Übernommen von `AudioMenu`: Abfrage **nur solange das Popover offen ist** (eine
Fernbedienung, die im Hintergrund pollt, kostet Anfragen ohne Gegenwert) und ein
`inFlight`-Wächter, damit sich bei langsamer Verbindung keine Anfragen stauen.

**Bewusst nicht enthalten: der globale DPMS-Schalter.** Er steht zwei Symbole
weiter im `PowerMenu`; ihn zu duplizieren hieße, zwei Komponenten besitzen
denselben Zustand. Ist alles dunkel, zeigt das Popover einen Hinweis dorthin.

Eigener i18n-Namensraum `display` (de/en), wie `audio`.

## 11. Rechte

Neues Power-Recht **`can_manage_displays`**, gebaut wie `can_control_audio`
(2026-08-27, Migration `a7d3c9f18e42`):

- Migration auf `user_power_permissions`, `server_default='0'` — standardmäßig
  verweigert. Sie muss auf den echten `alembic heads` aufsetzen, nicht auf dem
  veralteten Dev-DB-Head; das hat schon einmal einen Prod-Deploy zerlegt.
- `models/power_permissions.py`, `schemas/power_permissions.py` (3 Stellen),
  `services/power_permissions.py` (Map `"manage_displays"` → Spalte, 4 weitere
  Stellen)
- `api/deps.py`: `require_power_manage_displays = _make_power_dependency("manage_displays")`
- `api/routes/sleep.py:364,375` — Admins bekommen es implizit
- Frontend: `api/powerPermissions.ts`, `components/user-management/PowerPermissionsSection.tsx`

Es steht **neben** den Sleep-/Suspend-Ketten und bleibt aus `_apply_implications`
heraus, ebenso wie `can_control_audio`.

## 12. Dev-Modus

`DevDisplayBackend` bildet BaluNode nach — **zwei** Ausgänge, beide `connected`
(nach 4.2 gibt es keine anderen): DP-3 mit 4K-Modi inklusive des Paars
120,000/119,88, HDMI-A-1 mit WQHD-Modi und mehreren namensgleichen 1080p-Modi.
Genau diese Dubletten müssen im Dev-Modus vorkommen, sonst lässt sich die
Beschriftungslogik unter Windows nicht bedienen. `apply` verändert den
In-Memory-Zustand, sodass das Popover ohne KDE vollständig durchspielbar ist.

Auswahl wie bei `AudioService`: Dev-Backend in `NAS_MODE=dev` und auf jeder
Nicht-Linux-Plattform, sonst `KWinDisplayBackend`.

## 13. Nicht-Ziele (v1)

- **Kein VRR, kein HDR.** VRR an HDMI-A-1 verursacht auf diesem Host einen
  Blackout (im display-switch-Plan als `MON_VRR="never"` MUSS vermerkt). Ein
  Schalter, dessen falsche Stellung das Bild killt, gehört nicht in v1.
- **Kein `scale`.** KWin merkt sich die Skalierung je Ausgang (DP-3 steht auf
  2,5, HDMI-A-1 auf 1,0); wer nur den Ausgang wechselt, braucht sie nicht. Ein
  Feld ohne Regler gehört nicht in den Body. `scale` wird angezeigt, nicht gesetzt.
- Kein Positions-/Layout-Editor, kein sddm-Stop, kein NAS-Modus, keine
  Audio-Kopplung, kein Hotplug-Push, kein Profil-System.
- **#589 bleibt unangetastet.** `deploy/scripts/display-switch` bleibt als CLI
  bestehen (es kann sddm starten, was das Backend bewusst nicht tut) und wird
  separat repariert.

## 14. Betriebsfakten

- **Das Plugin bringt einen Router mit.** Router werden nur beim Start gemountet
  (`core/lifespan.py`), also antworten `/api/plugins/display_output/*` nach dem
  Aktivieren 404 bis zum `baluhost-backend`-Neustart.
  `GET /api/plugins/display_output` meldet das als `restart_required`. Die
  bestehenden Displays-an/aus-Knöpfe im `PowerMenu` sind davon nicht betroffen —
  das ist Core-Code.
- Die Migration läuft mit dem Deploy.

## 15. Tests

`backend/tests/plugins/test_display_output_{parser,service,routes,ui_manifest}.py`,
Fixture `backend/tests/plugins/fixtures/kscreen_balunode.json` — ein **gemessener**
Mitschnitt von BaluNode, auf die relevanten Felder gekürzt, nicht erfunden. Die
Dubletten aus 4.1 bleiben in der Fixture; sie sind der Testgegenstand.

| Gegenstand | Zusicherung |
|---|---|
| Parser | Ausgangsnamen, `selected`, `current_mode_id`, vollständige Modenliste; DP-3 ohne `vrrPolicy` kippt ihn nicht (4.3) |
| Dubletten | id 9/10 werden zu einem Eintrag, id 57/58 bleiben zwei; Beschriftungen innerhalb eines Ausgangs eindeutig |
| Sortierung | absteigend nach Fläche, dann Frequenz — nicht die ID-String-Reihenfolge (4.5) |
| Validierung | unbekannter Ausgang → 400; **Mode-ID eines anderen Ausgangs → 400 (#589)**; alle abgewählt → 400; `mode_name` passt nicht → 409 |
| argv-Bau | ein erwarteter Vektor für eine Mehrfach-Änderung, nagelt die Atomizität fest |
| `lit` | Connector-Zuordnung; unbekannter Name → `None`, nicht `False` |
| Routen | 401 ohne Token, 403 ohne `can_manage_displays`, 200 mit |
| Fehler | kein `kscreen-doctor` → 502; stdout/stderr taucht in keiner Antwort auf |
| Dev-Backend | `apply` verändert das nachfolgende `GET` |
| UI-Manifest | `get_ui_manifest()` liefert `enabled=True` (die Falle aus Abschnitt 6) |

Kein Test ruft echtes `kscreen-doctor` auf — der CI-Runner hat keine
Wayland-Session, und auf ihm liefe der Aufruf in denselben xcb-Abbruch wie in
Abschnitt 3.

## 16. Abnahme

Grüne Tests belegen die Logik, nicht das Bild. Die Abnahme ist manuell auf
BaluNode: enumerieren, HDMI-A-1 aktivieren, Modus setzen, zurück auf DP-3 —
mit physischem Blick auf die Schirme. Dabei wird auch die Präfix-Annahme aus
4.6 bestätigt (`lit` muss dem entsprechen, was wirklich leuchtet).

## 17. Was dieses Dokument gegenüber dem Vorgängerplan ändert

| Der Plan sagte | Gemessen / entschieden |
|---|---|
| Core-Feature unter `/api/system/displays` | bundled Plugin unter `/api/plugins/display_output` |
| Eigene Seite „Displays" mit globalem DPMS-Schalter | Topbar-Popover; DPMS bleibt im `PowerMenu` |
| „Modi über `name`, nie über `id`" | Namen sind mehrdeutig (4.1) → lebende ID + Namensabgleich |
| `apply` nimmt `scale` entgegen | `scale` nur Anzeige (13) |
| Dev-Backend mit einem `disconnected` DP-1 | zwei verbundene Ausgänge — anderes liefert KWin nicht (4.2) |
| Rechte offen (admin-only vorgeschlagen) | neues `can_manage_displays` |
| `lit` je Ausgang, Quelle offen | `display_detector.get_connector_states()` im Core |

Richtig bleiben, unverändert übernommen: die Trennung `selected`/`lit`, ein
einziger atomarer `kscreen-doctor`-Aufruf, Whitelist statt Interpolation, die
Invariante „nie alles abwählen", kein Revert-Timer, und die Nicht-Ziele.
