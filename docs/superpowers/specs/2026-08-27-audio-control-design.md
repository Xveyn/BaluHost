# Audiosteuerung als bundled Plugin — Design

**Datum:** 2026-08-27
**Status:** Genehmigt
**Branch:** `feat/audio-control`
**Basis:** `main` @ `999df93c`

## Problem

BaluNode ist NAS und KDE-Gaming-Rechner in einem und hängt an Fernseher bzw.
Boxen. Wer die Lautstärke ändern, das Ausgabegerät wechseln oder eine einzelne
Anwendung leiser stellen will, muss dafür bisher physisch an den Desktop. Es gibt
keinerlei Audio-Code im Repo.

Gewünscht ist eine Fernbedienung in der Web-App: erreichbar vom Handy oder
Laptop, ohne Umweg über eine Unterseite.

## Ziel

Master-Pegel und Mute setzen, zwischen Ausgabegeräten umschalten und laufende
Streams einzeln regeln — bedienbar aus einem Popover in der Topbar, direkt neben
Benachrichtigungen und Power-Menü.

## Nicht-Ziele

- **Eingänge/Mikrofone (Sources).** Bewusst ausgeschlossen; verdoppelt die
  Backend-Fläche ohne Nutzen für den Fernbedienungs-Fall.
- **Audio-Wiedergabe durch BaluHost selbst.** Wir steuern fremde Streams, wir
  erzeugen keine.
- **Audio-Streaming zu anderen Geräten.**
- **Equalizer, Balance, Kanal-Einzelregelung, Latenz-Einstellungen.**
- **Eine eigene Plugin-Nav-Seite.** Die Topbar ist der einzige Bedienort.

## Gemessene Ausgangslage

Alle folgenden Punkte sind auf der Produktionsmaschine gemessen, nicht
angenommen. Sie tragen das Design; wer sie ändert, muss das Design neu prüfen.

**Der Dienst kommt ohne Sonderrechte an PipeWire.**
`/etc/systemd/system/baluhost-backend.service` läuft mit `User=sven`,
`Group=sven` und enthält **keine einzige Härtungs-Direktive** (kein
`PrivateUsers`, `ProtectHome`, `ProtectSystem`). Die Desktop-Session läuft unter
derselben UID 1000, der Socket liegt auf `/run/user/1000/pulse/native`.

Der Beweis ist ein Lauf mit vollständig leerer Umgebung:

```
env -i XDG_RUNTIME_DIR=/run/user/1000 /usr/bin/wpctl status
```

Das listet Geräte und Pegel korrekt auf. `DBUS_SESSION_BUS_ADDRESS` wird **nicht**
benötigt. Damit reicht exakt die Umgebung, die `services/power/session_env.py`
ohnehin herstellt — **kein Sudo, keine Sudoers-Regel, kein Helfer-Prozess.**

**Werkzeuge:** `wpctl`, `pactl`, `pw-dump`, `pw-cli` liegen in `/usr/bin`.
PipeWire 1.4.2 mit Pulse-Kompatibilität.

**`pactl -f json` liefert gültiges JSON.** Gemessen an einem echten Firefox-Stream:

```json
[{"index":789,"client":"788","sink":61,"corked":false,"mute":false,
  "volume":{"front-left":{"value":36305,"value_percent":"55%","db":"-15.39 dB"},
            "front-right":{"value":36305,"value_percent":"55%","db":"-15.39 dB"}},
  "properties":{"application.name":"Firefox",
                "application.process.binary":"firefox-esr",
                "media.name":"(10) Caller Broke Into a Smoke Shop … — YouTube",
                "media.class":"Stream/Output/Audio"}}]
```

**Geräte:** zwei angeschlossene Sinks — die APU über S/PDIF
(`alsa_output.pci-0000_0e_00.6.iec958-stereo`) und die dGPU über HDMI
(`alsa_output.pci-0000_03_00.1.hdmi-stereo-extra1`). Zusätzlich ist unter *Default
Configured Devices* ein **Bluetooth-Gerät** hinterlegt
(`bluez_output.C8_2B_6B_35_0D_B3.1`), das meist **nicht verbunden** ist.

## Zwei Fallen, die aus den Messungen folgen

### `pactl` und `wpctl` haben getrennte ID-Räume

Derselbe physische Ausgang trägt bei `pactl` die Nummer 61 und bei `wpctl` die
Nummer 35. Werden beide Werkzeuge gemischt, entstehen Verwechslungen, die erst im
Betrieb auffallen und schwer zu finden sind.

**Entscheidung: ausschließlich `pactl`.** Es deckt Geräte, Streams,
Standardgerät, Pegel und Mute in einem Befehlssatz ab und kann JSON ausgeben.
`wpctl` gibt nur menschenlesbaren Baum-Text aus. `wpctl`, `pw-cli` und `pw-dump`
kommen im Produktionscode **nicht** vor.

### „Standardgerät" bedeutet zwei verschiedene Dinge

Das *konfigurierte* Standardgerät ist eine überdauernde Präferenz und kann auf
ein Gerät zeigen, das gerade nicht existiert — auf BaluNode ist das der Regelfall
(Bluetooth). Das *aktive* Standardgerät ist das, worüber gerade wirklich Ton
läuft.

**Wir arbeiten ausschließlich mit dem aktiven.** `pactl get-default-sink` liefert
genau das: den tatsächlich wirksamen Ausgang, mit der Rückfalllogik von PipeWire
bereits angewendet. Die konfigurierte Präferenz zeigt nur `wpctl` — und `wpctl`
ist oben ausgeschlossen worden. Sie hier trotzdem anzuzeigen, hieße das Werkzeug
zu wechseln, um dem Nutzer ein Gerät zu präsentieren, das er weder hört noch
auswählen kann.

Daraus folgt: `AudioState` führt **kein** Feld für die konfigurierte Präferenz.
Die Geräteliste enthält nur vorhandene Geräte, und ein abwesendes
Bluetooth-Gerät fällt dadurch von selbst heraus, statt eine Sonderbehandlung zu
brauchen. Liefert `get-default-sink` einen Namen, der in der Sink-Liste fehlt —
etwa während eines Gerätewechsels — trägt schlicht kein Eintrag `is_default`.
Das ist ein zulässiger Zwischenzustand, kein Fehler.

## Architektur

Optionales **bundled** Plugin. Bundled Plugins laufen laut
`backend/app/plugins/CLAUDE.md` im Host-Prozess und voll vertrauenswürdig — nur
*externe* Marketplace-Plugins werden als `baluhost-plugin` in einer
Netzwerk-Namespace isoliert. Ein externes Plugin käme nicht an
`/run/user/1000/pulse/native` (Modus 0700, gehört `sven`); ein bundled Plugin
schon. Diese Unterscheidung ist die Voraussetzung des ganzen Entwurfs.

```
backend/app/plugins/installed/audio_control/
├── __init__.py   # AudioControlPlugin(PluginBase): metadata, get_router()
├── models.py     # Pydantic: AudioSink, AudioStream, AudioState
├── pactl.py      # einzige Stelle mit Subprozess- und JSON-Kenntnis
├── backend.py    # AudioBackend (Protocol) + DevAudioBackend + PipeWireAudioBackend
└── service.py    # Orchestrierung, Fehlerübersetzung
```

Die Zweiteilung in Protocol plus Dev-/Linux-Implementierung spiegelt
`services/power/desktop_backend.py`. Jede Datei bleibt deutlich unter der
500-Zeilen-Konvention.

### Verantwortlichkeiten

| Einheit | Aufgabe | Abhängigkeiten |
|---|---|---|
| `pactl.py` | `pactl` aufrufen, JSON parsen, normalisieren | `subprocess`, `session_env` |
| `backend.py` | Protokoll und die zwei Implementierungen | `pactl.py`, `models.py` |
| `service.py` | Backend wählen, Fehler übersetzen | `backend.py` |
| `__init__.py` | Plugin-Metadaten, Routen | `service.py` |

`pactl.py` ist die einzige Datei, die weiß, dass es `pactl` überhaupt gibt.
Ein späterer Wechsel auf eine PipeWire-Bibliothek berührt nur sie.

## Datenmodell

```python
class AudioSink(BaseModel):
    id: int              # pactl-Index
    name: str            # z.B. "alsa_output.pci-0000_0e_00.6.iec958-stereo"
    description: str     # z.B. "Ryzen HD Audio Controller Digitales Stereo (IEC958)"
    volume_percent: int  # 0-150
    muted: bool
    is_default: bool     # das AKTIVE Standardgerät

class AudioStream(BaseModel):
    id: int              # pactl-Index des Sink-Inputs
    sink_id: int
    application: str     # application.name, Fallback node.name, Fallback "Unbekannt"
    binary: Optional[str]  # application.process.binary, für die Icon-Zuordnung
    title: Optional[str]   # media.name — siehe Datenschutz
    volume_percent: int
    muted: bool
    corked: bool         # pausiert

class AudioState(BaseModel):
    sinks: list[AudioSink]
    streams: list[AudioStream]
    available: bool      # False, wenn PipeWire nicht erreichbar ist
    detail: Optional[str]
```

### Normalisierungen (aus der gemessenen Ausgabe)

- `value_percent` ist ein **String** (`"55%"`) — Prozentzeichen abschneiden, zu
  `int`. Nicht parsbar → `0` und Warnung im Log, nie eine Ausnahme nach oben.
- `client` ist ein **String** (`"788"`), `index` und `sink` sind **Zahlen**.
  Nicht auf einheitliche Typen verlassen.
- Der Pegel kommt **pro Kanal**. Gelesen wird das Maximum über alle Kanäle,
  gesetzt wird für alle Kanäle gleich. Das verwirft eine bestehende Balance —
  akzeptiert, weil die UI keine Balance anbietet.
- Streams werden auf `media.class == "Stream/Output/Audio"` gefiltert;
  Aufnahme-Streams gehören nicht in den Ausgabe-Mixer.
- Fehlt `application.name`, greift `node.name`, dann ein neutraler Platzhalter.

## Der `pactl`-Vertrag

Jeder Aufruf: Listen-Argumente (nie Zeichenketten), Timeout 5 s, Umgebung aus
`wayland_session_env()`, kein `shell=True`.

**Lesen**

| Zweck | Befehl |
|---|---|
| Geräte | `pactl -f json list sinks` |
| Streams | `pactl -f json list sink-inputs` |
| aktives Standardgerät | `pactl get-default-sink` |

**Schreiben**

| Zweck | Befehl |
|---|---|
| Gerätepegel | `pactl set-sink-volume <id> <n>%` |
| Gerät stumm | `pactl set-sink-mute <id> 0` bzw. `1` |
| Standardgerät | `pactl set-default-sink <name>` |
| Streampegel | `pactl set-sink-input-volume <id> <n>%` |
| Stream stumm | `pactl set-sink-input-mute <id> 0` bzw. `1` |

Alle IDs werden vor dem Einsetzen als `int` validiert; der Gerätename für
`set-default-sink` muss aus der zuvor gelesenen Sink-Liste stammen — es wird
niemals eine vom Client gelieferte Zeichenkette durchgereicht.

Der Pegel wird serverseitig auf **0–150 %** begrenzt. 150 % erlaubt die
Übersteuerung, die PipeWire ohnehin zulässt; ohne Deckel könnte ein Aufrufer
1000 % setzen und die Boxen beschädigen.

## Routen

Alle unter `/api/plugins/audio_control/`.

| Methode | Pfad | Zweck |
|---|---|---|
| `GET` | `/state` | Geräte, Streams und Standardgerät in einer Antwort |
| `PUT` | `/sinks/{id}/volume` | `{ "percent": 0-150 }` |
| `PUT` | `/sinks/{id}/mute` | `{ "muted": bool }` |
| `PUT` | `/default-sink` | `{ "name": str }` |
| `PUT` | `/streams/{id}/volume` | `{ "percent": 0-150 }` |
| `PUT` | `/streams/{id}/mute` | `{ "muted": bool }` |

`GET /state` liefert bewusst alles auf einmal, damit das Popover mit **einem**
Rundlauf aufgeht statt mit dreien.

Jede Route: Pydantic-Schema für den Rumpf (nie rohes `dict`), Rate-Limit über
`@user_limiter.limit(get_limit("audio_control"))`, und `require_power_control_audio`
als Abhängigkeit — **auch das `GET`** (Begründung unten).

### Eigene Rate-Limit-Kategorie

`core/rate_limiter.py` bekommt einen neuen Eintrag:

```python
# Audio control — Popover-Abfrage alle 2s plus entprellte Schieberegler
"audio_control": "240/minute",
```

Die naheliegende Kategorie `admin_operations` (30/Minute) wäre **falsch und
würde das Feature unbenutzbar machen**: die 2-Sekunden-Abfrage allein verbraucht
30 Anfragen pro Minute, also das gesamte Kontingent, bevor ein einziger Regler
bewegt wurde. Gerechnet mit 30 Abfragen plus etwa 15 Schreibvorgängen je
Regler-Bewegung liegen 240/Minute komfortabel darüber, ohne die Route als
Verstärker für Missbrauch zu öffnen. Zum Vergleich: `status_polling` steht bei
60/Minute für einen 10-Sekunden-Takt.

Lesen und Schreiben teilen sich bewusst eine Kategorie — getrennte Kontingente
brächten hier keinen Schutz, nur zwei Zahlen zum Pflegen. Der Wert ist wie alle
anderen zur Laufzeit über die Rate-Limit-Konfiguration übersteuerbar.

Ein 404 auf einen unbekannten Index ist ein Normalfall, kein Fehler: Streams
verschwinden, sobald die Wiedergabe endet. Die UI behandelt ihn als „Liste ist
veraltet, neu laden".

## Datenschutz: `media.name`

Die gemessene Stream-Eigenschaft `media.name` enthielt den vollen Titel des
gerade laufenden YouTube-Videos. Die Stream-Liste ist damit **kein reiner
Steuerungs-Endpunkt, sondern ein Auskunfts-Endpunkt über das Desktop-Verhalten
des angemeldeten Benutzers.**

Zwei Konsequenzen:

1. **Der Lesepfad wird genauso streng gegated wie der Schreibpfad.** `GET /state`
   liegt hinter `require_power_control_audio`, nicht hinter `get_current_user`.
   Wer die Lautstärke regeln darf, sieht zwangsläufig auch die Titel — deshalb
   ist es eine bewusst zu vergebende Berechtigung und keine Selbstverständlichkeit.
2. **Die UI zeigt standardmäßig nur den Anwendungsnamen** („Firefox"). Der Titel
   wird als `title`-Attribut geliefert und erscheint nur im Tooltip. Der Mixer
   bleibt bedienbar, ohne dass ein Blick auf den Bildschirm verrät, was läuft.

## Berechtigung

Neues Recht `can_control_audio`, eingereiht in das bestehende Modell aus
`user_power_permissions` (UI-Name „Systemberechtigungen"). Vorbild ist
`can_toggle_desktop`.

- **Modell** (`models/power_permissions.py`): Spalte `can_control_audio` an
  `UserPowerPermission`, `Boolean, nullable=False, default=False, server_default="0"`
  — identisch zu den sechs bestehenden Rechten.
- **Migration:** additiv, mit Server-Default. Sie kettet an den echten Head
  **`16ea14ef13bb`** (per `python -m alembic heads` ermittelt, genau ein Head),
  **nicht** an den Kopf der Dev-Datenbank. Ein Verstoß dagegen hat hier schon
  einmal einen Produktions-Deploy mit mehreren Heads zerlegt.
- **Dienst** (`services/power_permissions.py`): `_ACTION_FIELD_MAP` erhält
  `"control_audio": "can_control_audio"`. Keine Implikation — das Recht steht
  unabhängig neben den Sleep-/Suspend-Ketten, `_apply_implications` bleibt
  unberührt. Feld in `get_permissions`, `update_permissions` sowie in den
  `old_values`/`new_values` des Audit-Eintrags ergänzen.
- **Abhängigkeit** (`api/deps.py`):
  `require_power_control_audio = _make_power_dependency("control_audio")`.
  Die Fabrik existiert bereits und erledigt Admin-Kurzschluss, Prüfung und den
  `authorization_failure`-Audit-Eintrag.
- **`my-permissions`** (`api/routes/sleep.py`): Feld ergänzen — `True` für
  Admins, sonst aus `get_permissions`.

Standard ist Verweigerung: Wer keine Zeile in der Tabelle hat, hat das Recht nicht.

## Audit-Logging

**Protokolliert werden Gerätewechsel und Mute. Pegeländerungen nicht.**

Ein Schieberegler erzeugt selbst mit Entprellung Dutzende Schreibvorgänge pro
Bedienung. Würde jeder davon protokolliert, ersetzte das Rauschen genau die
Einträge, wegen derer man ins Audit-Log schaut. Ein Pegel ist außerdem trivial
beobachtbar und selbstkorrigierend — ein Gerätewechsel oder eine Stummschaltung
dagegen ist ein Zustandssprung, den man später erklären können will.

Ruft ein Nicht-Admin eine Schreibroute auf, wird zusätzlich
`delegated_power_action` als Sicherheitsereignis vermerkt — wie in
`routes/desktop.py`.

## Frontend

**Neu**
- `client/src/api/audioControl.ts` — Typen und Aufrufe
- `client/src/components/topbar/AudioMenu.tsx` — Lautsprecher-Symbol mit Popover
- `client/src/i18n/locales/{de,en}/audio.json`

**Geändert**
- `client/src/components/layout/LayoutHeader.tsx` — eine Zeile
- `client/src/components/user-management/PowerPermissionsSection.tsx` — siebter Toggle
- `client/src/api/powerPermissions.ts` — Feld in den drei Schnittstellen
- `client/src/i18n/locales/{de,en}/admin.json` — Beschriftung des Toggles

### Einhängen

```tsx
{!isPi && audioEnabled && canControlAudio && <AudioMenu />}
```

`audioEnabled` kommt aus `usePluginEnabled('audio_control')`
(`contexts/PluginContext.tsx`), `canControlAudio` aus `my-permissions`. Beide
Bedingungen sind nötig: die erste blendet das Feature aus, wenn das Plugin
abgeschaltet ist, die zweite, wenn der Benutzer das Recht nicht hat. Ohne die
zweite sähe jeder ein Symbol, das nur 403 liefert.

Das ist der einzige Eingriff in Core-UI. Ein Plugin-`ui/bundle.js` rendert in
einem Sandbox-iframe auf einer eigenen Nav-Seite und kann sich technisch nicht in
die Topbar einhängen — deshalb dieser Weg statt eines reinen Plugin-Bundles.

### Verhalten

- **Abfrage nur bei offenem Popover**, im 2-Sekunden-Takt. Geschlossen wird gar
  nicht abgefragt: eine Fernbedienung, die im Hintergrund dauerhaft pollt, kostet
  Strom und Anfragen ohne Gegenwert.
- **Schieberegler entprellt (200 ms) mit optimistischer Anzeige.** Der Regler
  folgt sofort dem Finger, die Anfrage geht verzögert raus. Ohne das wäre die
  Bedienung entweder ruckelig oder würde die Route fluten.
- **Läuft eine Antwort noch, wird die nächste Abfrage übersprungen**, damit sich
  bei langsamer Verbindung keine Anfragen stauen.
- **Pausierte Streams (`corked`) werden gedämpft dargestellt, nicht versteckt** —
  ein pausiertes Video verschwände sonst mitten in der Bedienung aus der Liste.
- **Ist `available: false`**, zeigt das Popover einen kurzen Hinweis statt leerer
  Regler. Das passiert, wenn die Desktop-Session nicht läuft — auf einer Kiste,
  die schlafen gelegt wird, ein Normalfall.
- **Ist die Stream-Liste leer**, erscheint ein Hinweis „gerade spielt nichts".
  Auch das ist häufig: bei zwei von drei Messungen lief kein einziger Stream.

## Dev-Modus

`DevAudioBackend` hält zwei erfundene Geräte und zwei Streams im Speicher und
verändert sie bei Schreibzugriffen. Ohne das ist das Feature auf dem
Windows-Entwicklungsrechner nicht bedienbar, und das Frontend wäre nur gegen die
Produktionsmaschine testbar.

Die Auswahl folgt `desktop.py`: Dev-Backend bei `NAS_MODE=dev` oder auf
Nicht-Linux-Systemen, sonst das PipeWire-Backend.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| `pactl` fehlt | `available: false` plus Hinweis; keine Ausnahme |
| PipeWire nicht erreichbar | dito |
| Timeout (5 s) | Fehler protokolliert, `available: false` |
| Ungültiges JSON | Fehler protokolliert, leere Listen |
| Unbekannte ID beim Schreiben | 404, UI lädt neu |
| Pegel außerhalb 0–150 | 422 aus der Pydantic-Prüfung |

Grundsatz: Ein defekter Audio-Stack darf die Topbar nicht beschädigen. Jeder
Fehler endet in einem sauberen Zustand mit `available: false`, nie in einem 500er
und nie in einer kaputten Kopfzeile.

Fehlermeldungen an den Client bleiben allgemein; `pactl`-Ausgaben werden
protokolliert, aber nicht ausgeliefert — sie enthalten Gerätenamen und Pfade.

## Tests

**Backend**
- `pactl.py`: Parser gegen die **echte, hier gemessene JSON-Ausgabe** als Fixture.
  Zusätzlich die Randfälle: Prozent-String, fehlendes `application.name`,
  gemischte Typen bei `client`/`index`, leere Stream-Liste, konfiguriertes
  Standardgerät, das in der Sink-Liste fehlt, und ungültiges JSON.
- `DevAudioBackend`: Schreiben verändert den gelesenen Zustand.
- Routen: 403 ohne Recht, 200 als Admin, 200 als berechtigter Nicht-Admin,
  422 bei Pegel außerhalb des Bereichs, 404 bei unbekannter ID.
- Rechte: GET/PUT über `can_control_audio`, Feld in `my-permissions`,
  Audit-Werte enthalten das neue Feld.

**Frontend** (Vitest — die Suite ist real und läuft in CI)
- `AudioMenu`: erscheint nur bei Plugin *und* Recht; Entprellung feuert einmal
  statt pro Pixel; leere Stream-Liste zeigt den Hinweis; `available: false`
  zeigt den Hinweis.
- `audioControl.ts`: Aufrufformen.

Vor dem PR laufen `eslint .` und `npm run build` — der CI-Job prüft beides, und
`tsc -b` deckt mehr ab als `tsc --noEmit`.

## Sicherheit

- **Keine neuen Rechte auf dem System.** Kein Sudo, keine Sudoers-Datei, kein
  neuer Systemd-Dienst, kein Netzwerkzugang. Das Backend nutzt einen Socket, an
  den es als `sven` ohnehin darf.
- **Kein `shell=True`, ausschließlich Listen-Argumente.** IDs sind `int`,
  Gerätenamen stammen aus der zuvor gelesenen Liste. Es gibt keinen Pfad, auf dem
  eine Client-Zeichenkette in eine Befehlszeile gelangt.
- **Lese- und Schreibpfad gleich streng gegated** — wegen `media.name`.
- **Standard ist Verweigerung**; ohne Zeile in der Tabelle kein Zugriff.
- **Keine neuen Geheimnisse**, nichts für `REDACT_PATTERN`.
- Die Fläche ist auf den Ton der lokalen Desktop-Session begrenzt. Der
  schlimmste Missbrauch durch einen berechtigten Nutzer ist unangenehm laut —
  deshalb der 150-%-Deckel — oder ein stummer Desktop.

## Betrieb

Ein Plugin mit eigenem Router wird laut `plugins/CLAUDE.md` **nur beim Start
gemountet**. Der erste Einsatz braucht deshalb einen `baluhost-backend`-Neustart,
bevor die Endpunkte existieren; `GET /api/plugins/audio_control` weist über
`restart_required` darauf hin. Spätere An-/Abschaltungen wirken ohne Neustart.

Alle vier Uvicorn-Worker lesen den Zustand direkt aus PipeWire. Es gibt keinen
zwischengespeicherten Zustand und damit **kein Problem mit mehreren Workern** —
anders als bei Funktionen, die auf gemeinsamen Speicher angewiesen sind.

## Bekannte Grenzen

- **Bluetooth-Geräte kommen und gehen.** Ein konfiguriertes, aber abwesendes
  Standardgerät wird ignoriert. Ein Gerät zu *verbinden* ist nicht Teil des
  Umfangs — die Steuerung regelt, was da ist.
- **Streams sind flüchtig.** Zwischen Anzeige und Klick kann ein Stream
  verschwinden. Deshalb ist 404 ein Normalfall.
- **Ohne Desktop-Session gibt es keinen Ton zu regeln.** Läuft die Session
  nicht, meldet das Feature ehrlich `available: false`.
- **Balance geht beim Setzen verloren** (siehe Normalisierungen).
- **Der Mixer wurde an genau einem Stream gemessen** (Firefox). Andere
  Anwendungen — insbesondere Spiele über Proton — können ihre Eigenschaften
  anders befüllen. Der Parser fällt deshalb gestaffelt zurück
  (`application.name` → `node.name` → Platzhalter), statt ein Feld
  vorauszusetzen.

## Aufwandsschätzung

| Bereich | Umfang |
|---|---|
| Plugin-Backend (5 Dateien) | mittel |
| Recht (Modell, Migration, Dienst, Abhängigkeit, `my-permissions`) | klein, Muster vorhanden |
| Topbar-Komponente samt Popover | mittel |
| Systemberechtigungen-Toggle plus Übersetzungen | klein |
| Tests | mittel |
