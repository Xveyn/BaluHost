# Plan: Display-Output-Steuerung in der BaluHost-Webapp

**Datum:** 2026-09-08
**Host:** BaluNode (Debian 13, KDE Plasma 6 / KWin Wayland, Backend als `User=sven`)
**Status:** Plan — noch nicht umgesetzt, keine Code-Änderung erfolgt.
**Teilweise überholt:** die Architektur- (Core statt Plugin) und
Adressierungsentscheidungen (Modus über `name`) dieses Dokuments wurden durch
Messungen widerlegt bzw. neu entschieden. Maßgeblich ist
`docs/superpowers/specs/2026-09-08-display-output-plugin-design.md`, Abschnitt 17
listet jede Abweichung. Dieses Dokument bleibt als Diagnose-Grundlage erhalten.
**Verwandt:** #589 (stale Mode-IDs in `deploy/scripts/display-switch`),
`/home/sven/docs/superpowers/specs/2026-05-09-display-switch-design.md`,
`/home/sven/docs/superpowers/specs/2026-05-20-display-switch-nas-mode-design.md`

---

## 1. Ziel

Die Webapp soll die angeschlossenen Displays erkennen und den Ausgang anpassen
können: pro DRM-/KWin-Connector aktivieren/deaktivieren und den Video-Mode
(Auflösung + Bildwiederholrate) wählen. Generische Output-Verwaltung, keine
festen Profile.

## 2. Status quo (Diagnose vom 2026-09-08)

### 2.1 Was schon existiert

| Baustein | Datei | Kann heute |
|---|---|---|
| DRM-Connector-Zähler | `backend/app/services/power/gpu/display_detector.py` | zählt aktive Connectoren aus sysfs — **nur eine Zahl**, keine Namen, keine Modi |
| DPMS-Backend | `backend/app/services/power/desktop_backend.py` | `kscreen-doctor --dpms on\|off` über `wayland_session_env()` |
| Service-Factory | `backend/app/services/power/desktop.py` | dev-/linux-Backend-Auswahl, Singleton |
| Routes | `backend/app/api/routes/desktop.py` | `/api/system/sleep/desktop/{status,enable,disable,unlock}` |
| Frontend | `client/src/components/power/DesktopTogglePanel.tsx` | Ein/Aus-Button auf der Sleep-Seite |
| Audio | `backend/app/plugins/installed/audio_control/pactl.py` | Sinks auflisten, Default-Sink setzen |

Der Weg **Backend → KWin ist damit schon offen und erprobt**: der Dienst läuft
als `User=sven`, also derselbe User wie die Plasma-Session, und
`wayland_session_env()` ergänzt `XDG_RUNTIME_DIR` + `WAYLAND_DISPLAY`.

**Es fehlt genau die Mitte:** Output-Enumeration (Name, connected, enabled,
Modenliste) und ein Endpoint zum Setzen.

### 2.2 Live-Zustand BaluNode

```
card0-DP-1        disconnected
card0-DP-2        disconnected
card0-DP-3        connected   DRM enabled=disabled   KWin enabled=true,  priority 1, 3840x2160@120
card0-HDMI-A-1    connected   DRM enabled=disabled   KWin enabled=false, priority 0, 2560x1440@144
```

Tools vorhanden: `kscreen-doctor`, `xrandr`, `wayland-info`. Nicht vorhanden:
`ddcutil`, `wlr-randr` (für KWin auch nicht nötig).

### 2.3 Das zentrale Zustands-Problem: zwei Ebenen von „an"

- **KWin-Ebene** (`kscreen-doctor`) = die Ausgangs*wahl*. DP-3 enabled,
  HDMI-A-1 disabled.
- **DRM-Ebene** (sysfs `enabled`) = ob tatsächlich Pixel getrieben werden.
  Bei DPMS-off sind **alle** Connectoren `disabled`.

Deshalb meldet `DesktopTogglePanel` gerade „Gestoppt", während KWin DP-3 für
aktiv hält. Das ist kein Bug, sondern der Zustand, den `display-switch status`
`mode=ambiguous` nennt. Jede neue UI muss beide Ebenen **getrennt** anzeigen,
sonst behauptet sie „DP-3 aktiv" und „Displays aus" gleichzeitig.

### 2.4 `kscreen-doctor -j` — tatsächliche Struktur

Verifiziert auf BaluNode. Pro Output:

```
name, id, connected, enabled, currentModeId, preferredModes[],
priority, scale, rotation, pos{x,y}, size{w,h}, sizeMM{w,h},
type, vrrPolicy, hdr, wcg, sdr-brightness, overscan,
clones[], replicationSource, followPreferredMode,
modes[ { id, name, refreshRate, size{width,height} } ]
```

**Wichtigster Befund:** jedes Mode-Objekt trägt schon ein `name` wie
`"2560x1440@144"`. Das ist der stabile Schlüssel. `kscreen-doctor` akzeptiert
ihn direkt (`output.DP-3.mode.3840x2160@120`, per `--help` bestätigt).
Mode-**IDs** sind dagegen global über alle Outputs vergeben und instabil — genau
der Defekt in #589. **Die Implementierung adressiert Modi ausschließlich über
`name`, niemals über `id`.**

> **Nachtrag 2026-09-08 (widerlegt).** Der vollständige `-j`-Mitschnitt zeigt,
> dass `name` **nicht eindeutig** ist: `libkscreen`'s `findMode()` bildet ihn mit
> `qRound(refreshRate)`, weshalb 119,88 und 120,000 beide `3840x2160@120` heißen
> (DP-3, id 57/58), und HDMI-A-1 sechs mehrfach belegte Namen trägt. Dieselbe
> Codestelle belegt zudem, dass die Mode-ID sehr wohl ein gültiges Argument ist.
> Die Nachfolge-Spec adressiert Modi deshalb über die **lebende** ID plus
> Namensabgleich. Siehe Spec Abschnitt 4.1 und 7.

### 2.5 Das bestehende `display-switch`-Skript

`deploy/scripts/display-switch` (byte-identisch mit `~/.local/bin/display-switch`),
Branch `feat/display-switch-desktop-guard` ist in `main`. Kann `tv`, `monitor`,
`status`, `__test`; schaltet Display **und** Audio-Sink und startet vorher sddm.
`nas` aus Spec 2026-05-20 ist nicht implementiert; `/etc/sudoers.d/display-switch`
existiert nicht. `tv`/`monitor` brechen aktuell wegen #589 ab.

Das Skript bleibt als CLI unabhängig bestehen. Dieses Feature ersetzt es nicht.

---

## 3. Nicht-Ziele (YAGNI)

- **Kein VRR und kein HDR in der UI.** Auf diesem Host verursacht VRR an
  HDMI-A-1 einen Blackout (dokumentiert als `MON_VRR="never"` MUSS im
  display-switch-Plan). Ein Schalter, dessen falsche Stellung das Bild killt,
  gehört nicht in v1.
- **Kein Positions-Editor / kein Layout-Arrangement.** Mehrere gleichzeitig
  aktive Outputs werden unterstützt, aber die Anordnung bleibt KWins Sache.
- **Kein Stoppen von sddm / kein NAS-Modus.** Bewusst: laut
  `desktop_backend.py` lichtet der fbcon nach `systemctl stop sddm` alle
  Outputs und nagelt die dGPU bei ~78 W.
- **Keine Audio-Kopplung in v1.** Siehe offene Punkte.
- **Kein Hotplug-Push / kein WebSocket.** Polling wie beim bestehenden Panel.
- **Kein Profil-/Preset-System.** Explizit verworfen zugunsten generischer
  Verwaltung.

---

## 4. Getroffene Entscheidungen

| Frage | Entscheidung |
|---|---|
| Bedienmodell | Generische Output-Verwaltung — alle Connectoren enumeriert, je Output enable/disable + Mode-Auswahl |
| Ausführung | `kscreen-doctor` direkt aus Python, analog `LinuxDesktopBackend`. Kein Aufruf von `display-switch`, kein sudo |
| UI-Zustandsmodell | Eine neue Seite „Displays": globaler DPMS-Schalter **plus** pro Output die KWin-Wahl. Das bestehende `DesktopTogglePanel` auf der Sleep-Seite bleibt unverändert als Schnellzugriff |

---

## 5. Architektur

Spiegelt exakt das vorhandene Desktop-Toggle-Muster — Backends getrennt von der
Service-Fassade, Singleton-Factory, dev-/linux-Auswahl über
`settings.is_dev_mode`.

```
routes/display.py
   └─ services/power/display.py          DisplayService  (Fassade, Singleton)
        ├─ DevDisplayBackend             In-Memory, zwei Fake-Outputs
        └─ LinuxDisplayBackend           kscreen-doctor -j / kscreen-doctor output.*
             ├─ wayland_session_env()            (vorhanden, wiederverwendet)
             └─ display_detector.get_…_count()   (vorhanden, für die DRM-Ebene)
```

Ein `apply` ist **ein einziger** `kscreen-doctor`-Aufruf mit allen Argumenten —
das Tool wendet atomar an („all settings are applied in a single command").
Kein Teilzustand bei Fehlern.

### 5.1 Dateien

| Pfad | Verantwortung | Status |
|---|---|---|
| `backend/app/schemas/display.py` | `DisplayMode`, `DisplayOutput`, `DisplayLayout`, `DisplayApplyRequest` | neu |
| `backend/app/services/power/display_backend.py` | Protocol + `DevDisplayBackend` + `LinuxDisplayBackend` (inkl. JSON-Parser) | neu |
| `backend/app/services/power/display.py` | `DisplayService`, `get_display_service()`, Validierung | neu |
| `backend/app/api/routes/display.py` | `GET /`, `POST /apply` | neu |
| `backend/app/api/routes/__init__.py` | Router unter `/system/displays` registrieren | Änderung |
| `backend/tests/services/test_display_backend.py` | Parser gegen Fixture, Validierung | neu |
| `backend/tests/api/test_display_routes.py` | Auth-/Admin-Gate, Fehlerabbildung | neu |
| `backend/tests/fixtures/kscreen_baluNode.json` | echter `kscreen-doctor -j`-Mitschnitt | neu |
| `client/src/api/display.ts` | API-Client | neu |
| `client/src/components/power/DisplayOutputsPanel.tsx` | Output-Liste + Apply | neu |
| `client/src/pages/DisplaysPage.tsx` | Seite, bindet Panel + DPMS-Schalter | neu |
| `client/src/i18n/locales/{de,en}/power.json` | Strings im bestehenden `power`-Namespace | Änderung |

Fixture erzeugen: `XDG_RUNTIME_DIR=/run/user/1000 kscreen-doctor -j`.

### 5.2 Schemas (Skizze)

```python
class DisplayMode(BaseModel):
    name: str          # "3840x2160@120" — der stabile Schluessel
    width: int
    height: int
    refresh_rate: float

class DisplayOutput(BaseModel):
    name: str                      # "DP-3"
    connected: bool
    selected: bool                 # KWin-Ebene (kscreen "enabled")
    lit: bool                      # DRM-Ebene (sysfs "enabled") -> DPMS
    current_mode: Optional[str]
    preferred_mode: Optional[str]
    scale: float
    priority: int
    modes: list[DisplayMode]

class DisplayLayout(BaseModel):
    outputs: list[DisplayOutput]
    displays_powered: bool         # globaler DPMS-Zustand
    detail: Optional[str]
```

`selected` / `lit` statt zweimal `enabled` — die Namensgleichheit ist die
Ursache der Verwirrung aus 2.3 und soll nicht ins Schema wandern.

### 5.3 API

- `GET /api/system/displays` → `DisplayLayout`. Jeder authentifizierte User.
- `POST /api/system/displays/apply` → `{success, message}`. Body:
  `{"outputs": [{"name": "DP-3", "selected": true, "mode": "3840x2160@120", "scale": 2.5}, ...]}`

Registrierung unter Prefix `/system/displays`, Tag `displays`.

---

## 6. Sicherheit & Validierung

Gegen `.claude/rules/security-agent.md` geprüft:

- **Auth:** `GET` → `Depends(get_current_user)`. `POST /apply` →
  `Depends(get_current_admin)` (siehe offene Punkte).
- **Rate-Limit:** `@user_limiter.limit(get_limit("admin_operations"))` auf beiden
  Routen, wie in `routes/desktop.py`.
- **Pydantic-Schema** für den Body, kein rohes `dict`.
- **Audit:** `get_audit_logger_db().log_event(event_type="POWER",
  action="display_apply", …)` mit dem angewendeten Argument-Vektor in `details`.
- **Subprocess:** `subprocess.run()` mit Argument-Liste, `shell=False`, Timeout.
  Kein `sudo`.
- **Whitelist statt Interpolation — die eigentliche Schutzmaßnahme:** Jeder
  `name` aus dem Request muss gegen die **live enumerierten** Output-Namen
  matchen, jeder `mode` gegen die Modenliste **genau dieses** Outputs. Was nicht
  in der Enumeration steht, wird nie zu einem Argument. Damit kann kein
  benutzerkontrollierter String in den argv wandern, selbst wenn
  `kscreen-doctor` künftig eigene Argument-Syntax dazulernt.
- **`scale`** auf 0.5–3.0 begrenzt; alles andere → 400.

### 6.1 Invariante: nie alle Outputs abwählen

Ein `apply`, nach dem kein einzelner verbundener Output mehr `selected` wäre,
wird mit 400 abgelehnt. Begründung: „nichts soll leuchten" ist legitim, aber der
richtige Weg dafür ist der **DPMS-Schalter** — der lässt die KWin-Wahl intact
und ist reversibel. Alle Outputs abzuwählen wirft dagegen die Konfiguration weg.

### 6.2 Warum kein Confirm/Revert-Timer

Der klassische Footgun („Mode gesetzt, Bild schwarz, keine Maus mehr") greift
hier nicht: die Bedienoberfläche ist die Webapp über Netzwerk, nicht der
betroffene Desktop. Ein nicht synchronisierender Mode macht den Schirm schwarz,
die Webapp bleibt erreichbar, der nächste `apply` korrigiert. Ein
15-Sekunden-Rückfall-Timer wäre zusätzliche Zustandsmaschine ohne Nutzen → YAGNI.

---

## 7. Dev-Mode

`DevDisplayBackend` mit zwei Fake-Outputs, die BaluNode nachbilden (DP-3 mit
4K-Modi, HDMI-A-1 mit WQHD-Modi) plus einem `disconnected` DP-1. In-Memory-State,
damit das Frontend unter Windows ohne KDE vollständig bedienbar ist — gleiches
Muster wie `DevDesktopBackend`.

---

## 8. Tests

- **Parser** gegen `kscreen_baluNode.json`: Output-Namen, `selected`,
  `current_mode` als `name` (nicht `id`) aufgelöst, Modenliste vollständig.
- **Validierung:** unbekannter Output → 400; Mode eines *anderen* Outputs → 400
  (das ist #589 als Testfall); alle Outputs abwählen → 400; `scale` außerhalb
  Bereich → 400.
- **Kommando-Bau:** ein erwarteter argv-Vektor für eine Mehrfach-Änderung,
  damit die Atomizität (ein Aufruf) festgenagelt ist.
- **Routen:** 401 ohne Token, 403 für Non-Admin auf `apply`, `GET` für User ok.
- **DevBackend:** `apply` verändert den nachfolgenden `GET`.

Keine Tests, die echtes `kscreen-doctor` aufrufen — der CI-Runner hat keine
Wayland-Session.

---

## 9. Offene Punkte (vor Umsetzung entscheiden)

1. **Rechte-Modell.** Vorschlag: `apply` admin-only über
   `Depends(get_current_admin)`. Das vermeidet eine Alembic-Migration plus
   Erweiterung von `power_permissions.py`, Admin-UI und Mobile-Schema.
   Alternative: neues `can_manage_displays` analog `can_toggle_desktop`, falls
   delegierte User das dürfen sollen.
2. **Audio-Kopplung.** `display-switch` zieht beim Output-Wechsel den
   PipeWire-Default-Sink mit (TV → HDMI-Sink, Monitor → BT oder S/PDIF). Das
   `audio_control`-Plugin kapselt dieselbe Mechanik schon in `pactl.py`. Soll
   `apply` das mitmachen? Vorschlag: **v1 nein** — Display und Audio bleiben
   getrennt bedienbar; Kopplung wäre eine eigene, bewusst entschiedene Funktion.
3. **Verhältnis zu `display-switch`.** Bleibt das Skript dauerhaft als CLI
   (dann #589 fixen) oder wird es nach diesem Feature zurückgebaut? Vorschlag:
   bleibt — es deckt den Fall „vom Sofa ohne Webapp" ab und kann sddm starten,
   was das Backend bewusst nicht tut.
4. **Eigene Seite oder Unterbereich?** Entschieden ist „neue Seite Displays".
   Offen bleibt, ob sie im Menü unter Power/System einsortiert wird oder
   eigenständig.

---

## 10. Tasks

- [ ] **T1** Fixture `backend/tests/fixtures/kscreen_baluNode.json` von BaluNode ziehen und einchecken
- [ ] **T2** `backend/app/schemas/display.py` — Schemas nach 5.2, `selected`/`lit` getrennt
- [ ] **T3** Parser-Tests gegen die Fixture schreiben (rot)
- [ ] **T4** `display_backend.py` — `LinuxDisplayBackend.list_outputs()`: `kscreen-doctor -j` parsen, Modi über `name`, DRM-Ebene über `display_detector` ergänzen (grün)
- [ ] **T5** Validierungs-Tests nach Abschnitt 8 schreiben (rot)
- [ ] **T6** `display.py` — `DisplayService` mit Whitelist-Validierung und Invariante 6.1 (grün)
- [ ] **T7** Kommando-Bau-Test: ein argv-Vektor für Mehrfach-Änderung (rot → grün)
- [ ] **T8** `LinuxDisplayBackend.apply()` — ein `kscreen-doctor`-Aufruf, Timeout, Fehler als `(False, message)`
- [ ] **T9** `DevDisplayBackend` nach Abschnitt 7 + Test
- [ ] **T10** Routen-Tests (401/403/200) schreiben (rot)
- [ ] **T11** `routes/display.py` + Registrierung unter `/system/displays`, Rate-Limit, Audit (grün)
- [ ] **T12** `client/src/api/display.ts` — typisierter Client
- [ ] **T13** `DisplayOutputsPanel.tsx` — Output-Liste, Mode-Dropdown, Apply; Muster von `DesktopTogglePanel.tsx`
- [ ] **T14** `DisplaysPage.tsx` — DPMS-Schalter oben, Panel darunter; Route + Menüeintrag
- [ ] **T15** i18n de/en im `power`-Namespace
- [ ] **T16** Verifikation auf BaluNode: enumerieren, HDMI-A-1 aktivieren, Mode setzen, zurück auf DP-3
- [ ] **T17** `backend/app/services/CLAUDE.md` und `client/src/pages/CLAUDE.md` nachziehen

T16 ist der eigentliche Abnahmetest und braucht physischen Blick auf die
Schirme — bis dahin sagt kein grüner Test, dass das Bild wirklich kommt.
