# Bluetooth als bundled Plugin — Design

**Datum:** 2026-09-11
**Status:** Genehmigt (Abschnitte 1–4 im Chat abgenommen)
**Branch:** `feat/bluetooth-plugin`
**Basis:** `main` @ `f6917c85`

## Problem

BaluNode ist NAS und KDE-Gaming-Rechner in einem und hängt am Fernseher. Wer
einen Controller, Kopfhörer, eine Maus oder Tastatur verbinden will, muss dafür
bisher an den Desktop und den KDE-Dialog bedienen. Im Repo gibt es keinerlei
Bluetooth-Code.

Gewünscht ist eine Fernbedienung in der Web-App: Geräte sehen, verbinden,
trennen, entfernen und **neu koppeln** — auch Tastaturen, deren Kopplung einen
Code verlangt.

## Ziel

Aus einem Popover in der Topbar heraus:

- gekoppelte Geräte nach Art gruppiert sehen (Controller, Audio, Eingabe),
  inklusive Verbindungszustand und — wo BlueZ ihn liefert — Akkustand;
- verbinden, trennen, Kopplung entfernen, Adapter an/aus;
- nach neuen Geräten suchen und sie koppeln, wobei ein Kopplungscode **im
  Web-UI** angezeigt bzw. bestätigt wird.

Hauptanwendungsfall sind Controller, danach Kopfhörer, Maus und Tastatur.

## Nicht-Ziele

- **Eingehende Kopplungen.** Kopplungswünsche, die ein fremdes Gerät anstößt,
  bleiben bei KDE (BlueDevil). Das Plugin koppelt nur, was es selbst anstößt.
- **BaluNode als Bluetooth-Lautsprecher** (A2DP-Sink), Dateiübertragung (OBEX),
  Tethering (PAN), LE-Audio-Broadcast.
- **Umbenennen** (`Alias`), **Blockieren**, **Profilwahl** (HFP/A2DP),
  **Umschalten zwischen mehreren Adaptern** — nicht in v1.
- **`RequestPasskey`** (Gerät zeigt einen Code, der Rechner tippt ihn ein) und
  **Legacy-Geräte mit fester PIN** („0000") — keines der Zielgeräte braucht das.
- **Eine eigene Plugin-Nav-Seite.** Die Topbar ist der einzige Bedienort.
- **Änderungen an BlueZ-Konfiguration.** `main.conf`, `disable_ertm` und jede
  andere Systemeinstellung werden nie geschrieben.

## Gemessene Ausgangslage

Alles hier ist auf BaluNode gemessen (2026-09-11), nicht angenommen. Wer einen
dieser Punkte ändert, muss das Design neu prüfen.

**System.** Debian 13, Kernel `6.12.74+deb13+1-amd64`, BlueZ `5.82`,
`bluedevil 6.3.4`, `libspa-0.2-bluetooth 1.4.2` (PipeWire). `bluetooth.service`
aktiv.

**Zwei Funkmodule, ein Adapter.** `lsusb` zeigt zwei Bluetooth-Geräte:

```
0b05:1bef  ASUSTek Computer, Inc. Bluetooth Controller
13d3:3571  IMC Networks Bluetooth Radio
```

BlueZ kennt aber nur **einen** Controller, `A0:AD:9F:6F:43:F1` (Hersteller
`0x005d` = Realtek). Der Betreiber nutzt bewusst einen Dongle statt des
Onboard-Moduls, weil der Xbox-Controller mit Kernel und Mainboard-Modul nicht
zuverlässig lief. Das zweite Modul wird vom Kernel nicht als Adapter
hochgezogen. `Modalias usb:v1D6Bp0246` in `bluetoothctl show` ist BlueZ' eigene
DeviceID, nicht die USB-ID.

**Der Dienst erreicht BlueZ ohne Sonderrechte.** `baluhost-backend` läuft als
`User=sven`, `Group=baluhost`. Die Gruppen des **laufenden** Prozesses
(`/proc/<MainPID>/status`) enthalten `106` = `bluetooth`. Die D-Bus-Policy von
BlueZ liegt unter Debian 13 in `/usr/share/dbus-1/system.d/` (nicht `/etc`) und
erlaubt der Gruppe `bluetooth` den Zugriff. Ein `bluetoothctl show` über
`systemd-run -p User=sven` — also ohne Login-Session, wie der Dienst — gelingt.
**Kein sudo, keine sudoers-Regel, kein Wrapper.**

**Gekoppelte Geräte.**

| Gerät | Adresse | Icon | Transport | Hinweis |
|---|---|---|---|---|
| Xbox Wireless Controller | `40:8E:2C:4B:16:92` | `input-gaming` | LE (keine `Class`, `Appearance 964` = HID-Gamepad) | Treiber `xpadneo` |
| JBL TUNE510BT | `C8:2B:6B:35:0D:B3` | `audio-headphones` | BR/EDR (`Class 2360344`) | `LegacyPairing false` |

`Alias` ist beschreibbar, `Blocked` ebenso. `Battery1` und `Input1` hängen nur an
**verbundenen** Geräten; bei der Messung waren beide getrennt. Das wird im Spike
nachgemessen (siehe unten).

**BlueZ-Konfiguration** (nur gelesen, nie geschrieben):
`Experimental = true`, `KernelExperimental = true`, `[GATT] Cache = no`,
`ReconnectAttempts=7`, `ReconnectIntervals=1,2,4,8,16,32,64`, `AutoEnable=true`.
`/sys/module/bluetooth/parameters/disable_ertm` = `Y`.

**Der Adapter wird neu initialisiert.** `dmesg` zeigt zweimal
`Failed to read codec capabilities (-22)` gefolgt von `MGMT ver 1.23` — mutmaßlich
nach einem Aufwachen per `rtcwake`. Adapter-Zustand darf deshalb nicht über
einen Aufruf hinaus zwischengespeichert werden.

**Der Adapter wird mit KDE geteilt.** Zwischen zwei Aufrufen im Abstand weniger
Sekunden sprang `Discovering` von `no` auf `yes`, ohne dass BaluHost beteiligt
war. BlueDevil scannt bei Bedarf selbst.

**`busctl --json` scheitert an `GetManagedObjects`** mit
`Failed to create new json object: Invalid argument`. Ursache: `ManufacturerData`
hat die Signatur `a{qv}` — ein Dictionary mit Ganzzahl-Schlüsseln, das sich nicht
auf ein JSON-Objekt abbilden lässt.

## Drei Fallen, die aus den Messungen folgen

### BlueZ ist nicht zustandslos

`pactl` und `kscreen-doctor` sind einzelne Aufrufe ohne Gedächtnis. Bei BlueZ
sind **Discovery und der Koppel-Agent an die Lebensdauer der D-Bus-Verbindung
gebunden**, die sie gestartet hat. Ein einmaliges `bluetoothctl scan on` beendet
den Scan, sobald der Prozess endet. Zusammen mit vier Uvicorn-Workern ist das der
Kern dieses Designs (siehe *Worker-Modell*).

### Kopplungen hängen am Adapter, nicht am Gerät

BlueZ speichert Bonds unter `/var/lib/bluetooth/<adapter-MAC>/`. Wird das
Onboard-Modul irgendwann doch erkannt (etwa nach einem Kernel-Update), kann es
zum Standard-Adapter werden. Ein Plugin, das „den Standard-Adapter" nimmt, würde
dann Controller und JBL plötzlich als ungekoppelt zeigen und neue Kopplungen auf
das falsche Funkmodul legen.

**Entscheidung: feste Bindung per MAC** (siehe *Adapterwahl*), nie stilles
Umschwenken.

### `ManufacturerData` und Co. gehen nicht durch

Die Rohtypen von BlueZ (`a{qv}`, `a{yv}`, `ay`) sind weder JSON-tauglich noch für
die UI nützlich. **Die API reicht keine BlueZ-Rohdaten durch**; die Modelle
übernehmen ausschließlich die unten genannten Felder. Die Test-Fixture wird
deshalb nicht mit `busctl`, sondern mit einem Mitschnitt-Skript über `dbus-next`
erstellt.

## Architektur

Optionales **bundled** Plugin `bluetooth` (in-process, voll vertrauenswürdig).
Ein externes Sandbox-Plugin liefe als `baluhost-plugin` ohne Gruppe `bluetooth`
und käme nicht an den System-Bus-Dienst `org.bluez`.

```
backend/app/plugins/installed/bluetooth/
├── __init__.py   # BluetoothPlugin(PluginBase), Router, Audit-Helfer, Fehlerabbildung
├── models.py     # Pydantic; Feldnamen sind der API-Vertrag zum Frontend
├── bluez.py      # EINZIGE Stelle mit org.bluez-Kenntnis: Bus, reine Parser, Aufrufe
├── agent.py      # org.bluez.Agent1 als dbus-next ServiceInterface
├── pairing.py    # Koppel-Sitzung: Sperre, SHM-Übergabe, Zustandsautomat
├── backend.py    # BluetoothBackend (Protocol), DevBluetoothBackend, BlueZBackend
└── service.py    # Backend-Wahl, Validierung, Modul-Singleton
```

Jede Datei bleibt unter der 500-Zeilen-Konvention.

**D-Bus-Zugang** folgt dem Vorbild `services/power/core_uptime_rtc_guard.py:38-45`:
`dbus-next` (bereits Abhängigkeit, `backend/pyproject.toml:46`) mit
`try/except ImportError` als Windows-Rückfall,
`MessageBus(bus_type=BusType.SYSTEM).connect()`. Keine neue Abhängigkeit, kein
Subprozess, kein `bluetoothctl`.

**Verworfen: `bluetoothctl`-Aufrufe.** Textausgabe ohne JSON-Modus, Scan nur als
blockierender `--timeout`-Aufruf, Kopplung mit Agent im nicht-interaktiven Modus
unzuverlässig. Ein Mischansatz hätte zwei Werkzeuge im selben Plugin — genau das,
was die `pactl`/`wpctl`-Regel im Audio-Plugin verhindert.

### Worker-Modell

Die Operationen zerfallen nach ihrem Zustandsbedarf in drei Klassen.

**1. Zustandslos — jeder Worker direkt.** Lesen (`GetManagedObjects`), Verbinden,
Trennen, Entfernen, Adapter an/aus. Der BlueZ-Objektbaum ist systemweit, alle
Worker sehen dasselbe. Jeder Worker hält eine eigene, bei Bedarf aufgebaute und
nach Fehlern neu aufgebaute Bus-Verbindung.

**2. Scan — der annehmende Worker.** `POST /scan` startet auf der Verbindung des
annehmenden Workers `SetDiscoveryFilter({"Transport": "auto"})` +
`StartDiscovery()` und beendet die Suche nach **30 s** selbst per
`StopDiscovery()`. Die übrigen Worker sehen die gefundenen Geräte über den
gemeinsamen Objektbaum. Läuft im selben Worker schon ein Scan, antwortet die
Route mit dessen Ende. Parallele Scans aus verschiedenen Workern oder von KDE
zählt BlueZ pro Client — harmlos, keine Absprache nötig.

**3. Koppeln — ein Besitzer, Übergabe über SHM.**

- Der Worker, der `POST /devices/{address}/pair` annimmt, wird **Besitzer**. Er
  startet die Kopplung als `asyncio`-Task (starke Referenz, überlebt das Ende des
  Requests) und antwortet sofort mit `202`.
- **Systemweit höchstens eine Kopplung.** Die Sperre ist eine
  **OS-Dateisperre** (`fcntl.flock`, unter Windows `msvcrt.locking`) auf
  `/tmp/baluhost-bluetooth-pairing.lock` (unter Windows im Verzeichnis aus
  `tempfile.gettempdir()`), gehalten für die gesamte Sitzung. Der
  Kernel gibt sie frei, wenn der Prozess stirbt — **die Sperre braucht kein
  Ablaufdatum und kann nicht verwaisen.**
  - Die Sperrdatei liegt **bewusst nicht** in `/dev/shm/baluhost/`:
    `cleanup_shm()` (`services/monitoring/shm.py:104`) löscht beim Beenden des
    Monitoring-Workers alle Dateien dort. Eine gelöschte, aber noch gesperrte
    Datei ließe einen zweiten Worker eine neue Datei anlegen und sperren — zwei
    gleichzeitige Kopplungen. `/tmp` ist durch `PrivateTmp=true` pro Unit privat,
    aber zwischen den vier Workern derselben Unit geteilt; genau so arbeitet
    schon die Primary-Sperre `/tmp/baluhost-primary.lock`.
- **Hinweg zur UI:** Der Besitzer schreibt den Stand per `write_shm()` nach
  `bluetooth_pairing.json` (atomar, `mkstemp` ⇒ Modus `0600`). Er schreibt bei
  jeder Zustandsänderung und zusätzlich alle 5 s als Lebenszeichen. Leser nutzen
  `read_shm(..., max_age_seconds=15)`: Ist die Datei älter oder fehlt sie, gilt
  die Sitzung als **abgebrochen**.
- **Rückweg zum Besitzer** (nur Zahlenvergleich und Abbruch):
  `POST /pairing/{id}/confirm` bzw. `/cancel` schreibt
  `bluetooth_pairing_answer.json` mit `session_id`, `user_id` und Aktion. Der
  Besitzer fragt alle 250 ms ab, verbraucht die Datei und verwirft Antworten mit
  fremder `session_id`.
- **Gesamt-Timeout 60 s.** Danach `CancelPairing()`, Agent-Antwort `Rejected`.

**Ausfälle enden sicher.** Stirbt der Besitzer, schließt sich seine
D-Bus-Verbindung; BlueZ bricht die Kopplung selbst ab, der Kernel gibt die Sperre
frei, die Sitzungsdatei veraltet. Löscht `cleanup_shm()` die Sitzungsdatei, zeigt
die UI „abgebrochen"; der Besitzer läuft in seinen Timeout. Es bleibt nie etwas
halb gekoppelt oder dauerhaft gesperrt.

### Adapterwahl

Neue Einstellung `bluetooth_adapter_address` in `core/config.py`
(Env `BLUETOOTH_ADAPTER_ADDRESS`), validiert gegen das MAC-Format, Standard leer.

| Einstellung | vorhandene Adapter | Verhalten |
|---|---|---|
| leer | genau einer | dieser wird benutzt |
| leer | mehrere | `available: false`, Hinweis „mehrere Adapter — `BLUETOOTH_ADAPTER_ADDRESS` setzen" |
| gesetzt | darunter der gesetzte | dieser wird benutzt; sind es mehrere, zusätzlich eine Warnung im Zustand |
| gesetzt | der gesetzte fehlt | `available: false`, Hinweis „Adapter … nicht vorhanden" — **kein Rückfall** auf einen anderen |

Auf BaluNode greift heute Zeile 1. Die Einstellung wird erst relevant, wenn das
Onboard-Modul auftaucht — dann fällt das Plugin laut aus, statt still auf das
falsche Funkmodul zu wechseln.

## Datenmodell

```python
DeviceKind = Literal["controller", "audio", "input", "other"]

class BluetoothAdapter(BaseModel):
    address: str
    name: str
    powered: bool
    discovering: bool      # auch True, wenn KDE gerade scannt

class BluetoothDevice(BaseModel):
    address: str           # "40:8E:2C:4B:16:92"
    name: str              # Alias → Name → Adresse
    kind: DeviceKind
    icon: Optional[str]    # BlueZ-Icon, nur zur Symbolwahl im Frontend
    paired: bool
    trusted: bool
    connected: bool
    battery_percent: Optional[int]   # nur wenn Battery1 vorhanden
    rssi: Optional[int]              # nur während/kurz nach einem Scan

class BluetoothState(BaseModel):
    available: bool
    detail: Optional[str]
    warning: Optional[str]           # z.B. zweiter Adapter aufgetaucht
    adapter: Optional[BluetoothAdapter]
    devices: list[BluetoothDevice]
    can_pair_here: bool              # LAN-Prüfung, serverseitig aus der Client-IP
    pairing_active: bool             # irgendeine Kopplung läuft (Sperre belegt)
```

**`kind` aus `Icon`:**

| Icon | kind |
|---|---|
| `input-gaming` | `controller` |
| `audio-*` (`audio-headphones`, `audio-headset`, `audio-card`) | `audio` |
| `input-keyboard`, `input-mouse`, `input-tablet` | `input` |
| alles andere, fehlend | `other` |

Geräte werden nur unter dem gebundenen Adapter gelistet (`Device1.Adapter` ==
Adapter-Pfad).

```python
PairingStage = Literal[
    "connecting",        # Pair() läuft, noch keine Rückfrage
    "display_passkey",   # Code auf dem Gerät eintippen
    "display_pin",       # PIN auf dem Gerät eintippen
    "confirm",           # Zahlenvergleich: Ja/Nein
    "succeeded", "failed", "cancelled",
]

class PairingSession(BaseModel):
    session_id: str
    address: str
    device_name: str
    stage: PairingStage
    code: Optional[str]      # nur für den Initiator ausgeliefert
    entered: Optional[int]   # getippte Ziffern bei display_passkey
    error: Optional[str]     # kuratierter Fehlerschlüssel, nie BlueZ-Rohtext
```

## Koppel-Ablauf

1. `POST /scan` — 30-s-Fenster. `GET /state` listet neu gefundene, ungekoppelte
   Geräte. BlueZ entfernt ungekoppelte Funde nach Ende der Suche von selbst
   wieder (`TemporaryTimeout`); das ist erwünscht.
2. `POST /devices/{address}/pair`. **Vor jedem D-Bus-Aufruf:**
   - Adresse matcht `^([0-9A-F]{2}:){5}[0-9A-F]{2}$` (nach `upper()`), sonst 400;
   - sie steht im **aktuellen** Objektbaum unter dem gebundenen Adapter, sonst 404;
   - das Gerät ist nicht bereits gekoppelt, sonst 409;
   - LAN-Prüfung besteht, sonst 403;
   - die Sperre ist frei, sonst 409.

   Der Objektpfad wird **aus der geprüften Adresse gebaut**
   (`<adapter>/dev_XX_XX_…`). Eine Client-Zeichenkette wird nie zum Pfad.
3. Der Besitzer meldet den Agenten an (`RegisterAgent(path, "KeyboardDisplay")`,
   **ohne** `RequestDefaultAgent`) und ruft `Device1.Pair()`.
4. Bei Erfolg: `Trusted = true` (nötig, damit Controller und Eingabegeräte nach
   dem Aufwachen selbst wieder verbinden), dann `Connect()`, falls nicht
   verbunden.
5. `finally`: `UnregisterAgent`, Endstand schreiben, Sitzungsdatei nach 10 s
   Anzeigezeit löschen, Sperre freigeben.

**Warum ohne `RequestDefaultAgent`:** BlueZ fragt einen Agenten, der nicht
Standard-Agent ist, ausschließlich zu Kopplungen, die **dieselbe D-Bus-Verbindung**
per `Pair()` angestoßen hat. Eingehende Anfragen erreichen weiter BlueDevil. Das
Plugin verdrängt KDE nie.

### Der Agent

Fähigkeit `KeyboardDisplay`: Tastaturen bekommen echten MITM-Schutz per Code,
Geräte ohne Ein-/Ausgabe (Controller, Kopfhörer, Mäuse) koppeln weiter ohne Code.

**Jede Methode prüft zuerst, ob `device` der Objektpfad der laufenden Sitzung
ist. Wenn nicht: `org.bluez.Error.Rejected`.**

| Methode | Anlass | Verhalten |
|---|---|---|
| `DisplayPasskey(dev, passkey, entered)` | moderne Tastatur | `stage=display_passkey`, Code sechsstellig mit führenden Nullen, `entered` fortlaufend |
| `DisplayPinCode(dev, pin)` | seltene Variante | `stage=display_pin` |
| `RequestPinCode(dev)` | Legacy-Tastatur | **nur bei `Icon == input-keyboard`**: sechsstellige PIN aus `secrets`, `stage=display_pin`, PIN an BlueZ zurück. Sonst `Rejected` („Legacy-Gerät mit fester PIN nicht unterstützt") |
| `RequestConfirmation(dev, passkey)` | Zahlenvergleich | `stage=confirm`, wartet auf die Antwortdatei; ohne Antwort bis zum Timeout `Rejected` |
| `RequestAuthorization(dev)` | Just Works mit Rückfrage | annehmen — der Klick auf genau dieses Gerät ist die Zustimmung. **Vom Spike zu bestätigen** |
| `RequestPasskey(dev)` | Gerät zeigt, Rechner tippt | `Rejected` (v1) |
| `AuthorizeService(dev, uuid)` | eingehende Dienstanfrage | immer `Rejected` |
| `Cancel()` | BlueZ bricht ab | `stage=cancelled` |
| `Release()` | Agent abgemeldet | nichts außer Aufräumen |

### Fehlerabbildung

BlueZ-Fehlernamen werden auf kuratierte Schlüssel abgebildet; Rohtext von BlueZ
wird geloggt, aber **nie ausgeliefert**.

| BlueZ | Ergebnis |
|---|---|
| `AuthenticationFailed` | Sitzung `failed`, `error=auth_failed` („Code falsch oder abgelaufen") |
| `AuthenticationCanceled`, `AuthenticationRejected` | `cancelled` |
| `AuthenticationTimeout`, `ConnectionAttemptFailed`, `br-connection-page-timeout` | `failed`, `error=unreachable` („Gerät nicht erreichbar — Kopplungsmodus aktiv?") |
| `AlreadyExists` | als Erfolg behandeln |
| `InProgress` | 409 (auch: KDE koppelt gerade) |
| `NotReady` | 409 („Adapter ist aus") |
| `DoesNotExist`, `UnknownObject` | 404 |
| alles andere | `BadGatewayError` (502, kuratierte Meldung übersteht den 5xx-Scrubber) |

## Routen

Alle unter `/api/plugins/bluetooth/`. Jede Route: `require_power_manage_bluetooth`
(**auch die lesenden** — die Liste verrät Hardware und MAC-Adressen),
`@user_limiter.limit(get_limit("bluetooth"))`, Pydantic-Schema für jeden Rumpf.

| Methode | Pfad | Rumpf / Antwort | LAN-Prüfung |
|---|---|---|---|
| GET | `/state` | → `BluetoothState` | — |
| POST | `/adapter/power` | `{"powered": bool}` | — |
| POST | `/scan` | → `{"until": datetime}` | — |
| POST | `/devices/{address}/connect` | — | — |
| POST | `/devices/{address}/disconnect` | — | — |
| DELETE | `/devices/{address}` | Kopplung entfernen (`Adapter1.RemoveDevice`) | — |
| POST | `/devices/{address}/pair` | → `202 {"session_id"}` | **ja** |
| GET | `/pairing` | → `PairingSession` des Aufrufers oder `null` | — |
| POST | `/pairing/{id}/confirm` | `{"accept": bool}` | **ja** |
| POST | `/pairing/{id}/cancel` | — | — |

`GET /pairing`, `confirm` und `cancel` wirken **nur für den Initiator** der
Sitzung (`user_id` in der Sitzungsdatei). Andere Berechtigte sehen über
`pairing_active` nur, *dass* gekoppelt wird — nie den Code.

Audio-Geräte (A2DP/HFP) tauchen nach dem Verbinden automatisch als Ausgang im
Audio-Plugin auf (PipeWire legt den Sink an). **Die beiden Plugins kennen sich
nicht**; die Kopplung läuft über PipeWire, nicht über Code.

### Eigene Rate-Limit-Kategorie

`core/rate_limiter.py`:

```python
# Bluetooth — Popover-Abfrage alle 3 s, während einer Kopplung jede Sekunde
"bluetooth": "120/minute",
```

Gerechnet: 60 Kopplungs-Abfragen + 20 Zustands-Abfragen pro Minute im
ungünstigsten Fall, plus Luft für Klicks. `admin_operations` (30/min) wäre schon
von der Kopplungs-Abfrage allein aufgebraucht.

## Berechtigung

Neues Recht `can_manage_bluetooth` im Modell `user_power_permissions`
(UI: „Systemberechtigungen"). Vorbild ist `can_control_audio`.

- **Modell** (`models/power_permissions.py`): Spalte `can_manage_bluetooth`,
  `Boolean, nullable=False, default=False, server_default="0"`.
- **Migration:** additiv, kettet an den echten Head **`c3a7f0d51b64`**
  (`python -m alembic heads` am 2026-09-11, genau ein Head) — vor dem Anlegen
  erneut prüfen, nie den Kopf der Dev-Datenbank nehmen.
- **Dienst** (`services/power_permissions.py`): `_ACTION_FIELD_MAP` erhält
  `"manage_bluetooth": "can_manage_bluetooth"`. **Keine Implikation**,
  `_apply_implications` bleibt unberührt. Feld in `get_permissions`,
  `update_permissions` und den `old_values`/`new_values` des Audit-Eintrags.
- **Abhängigkeit** (`api/deps.py`):
  `require_power_manage_bluetooth = _make_power_dependency("manage_bluetooth")`.
- **`my-permissions`** (`api/routes/sleep.py`): `True` für Admins, sonst aus
  `get_permissions`.
- **Frontend:** weiterer Schalter in `PowerPermissionsSection.tsx`, Feld in den
  drei Schnittstellen in `api/powerPermissions.ts`, Beschriftung in
  `admin.json` (de/en).

Admins vergeben das Recht pro User. Standard ist Verweigerung.

## Sicherheit

**Bedrohungsmodell.** Ein Angreifer in Funkreichweite erbeutet ein Web-Konto mit
diesem Recht, koppelt seine eigene Tastatur und tippt in die Desktop-Session von
`sven` — der in der Gruppe `sudo` ist. Ohne das Plugin braucht dieser Angriff
Zugang zum Fernseher; mit dem Plugin genügen Web-Konto und Funkreichweite. Die
folgenden Regeln heben diese Hürde wieder an.

1. **Recht `can_manage_bluetooth`** auf jeder Route, Standard Verweigerung, keine
   Implikation, Admins implizit.
2. **LAN-Prüfung beim Koppeln und Bestätigen**:
   `is_private_or_local_ip(request.client.host)` (`core/network_utils.py`), wie
   bei `can_unlock_session`. Gilt für **alle Rollen, Admins eingeschlossen**.
   Die Prüfung ist sicher, weil `--forwarded-allow-ips=127.0.0.1` den
   `X-Forwarded-For` nur von nginx annimmt. Verbinden, Trennen und Entfernen
   bekannter Geräte bleiben ohne LAN-Prüfung: sie können stören, aber kein neues
   Vertrauen schaffen.
3. **Nur selbst angestoßene Kopplungen.** Das Plugin setzt nie `Discoverable`
   oder `Pairable`, registriert sich nie als Standard-Agent. Eingehende
   Kopplungen bleiben bei KDE.
4. **Der Agent antwortet nur zum Gerät der Sitzung**; alles andere `Rejected`.
5. **Code und PIN**
   - werden nie geloggt und nie ins Audit geschrieben;
   - gehen nur an den Initiator;
   - liegen nur in `bluetooth_pairing.json` (Modus `0600`, Besitzer `sven`) und
     werden nach Sitzungsende gelöscht;
   - PINs stammen aus `secrets`, nie aus `random`.
6. **Eingaben erreichen BlueZ nur nach Abgleich** mit dem aktuellen Objektbaum.
   Objektpfade werden aus validierten Adressen gebaut.
7. **Der UI-Hinweis „Eingabegerät" ist Information, keine Kontrolle.** `Icon` und
   `Class` meldet das Gerät selbst; ein Angreifer-Gerät kann sich als Kopfhörer
   ausgeben und trotzdem ein HID-Profil anbieten. Die tragenden Kontrollen sind
   1–4 und der Code bei Tastaturen.
8. **Audit:** Koppeln (Erfolg/Fehler, Adresse, `kind`), Entfernen, Adapter an/aus.
   Nicht-Admins zusätzlich `delegated_power_action`. Verbinden/Trennen nicht —
   häufig, selbstkorrigierend, ohne Vertrauenswirkung.
9. **Kein Schreibzugriff auf BlueZ-Konfiguration.** `main.conf`,
   `disable_ertm`, Adapter-Name, `Pairable`, `Discoverable` bleiben unberührt.
10. **Keine neuen Systemrechte.** Kein sudo, keine sudoers-Datei, kein neuer
    systemd-Dienst. Keine neuen Geheimnisse, nichts für `REDACT_PATTERN`.

## Frontend

**Neu**
- `client/src/api/bluetooth.ts` — Typen und Aufrufe
- `client/src/components/topbar/BluetoothMenu.tsx` — Symbol mit Popover
- `client/src/components/topbar/BluetoothPairingDialog.tsx` — Koppel-Dialog
- `client/src/i18n/locales/{de,en}/bluetooth.json` — neuer Namespace, in der
  i18n-Konfiguration registrieren

**Geändert**
- `client/src/components/layout/LayoutHeader.tsx` — eine Zeile:
  `{!isPi && bluetoothEnabled && canManageBluetooth && <BluetoothMenu />}`
- `PowerPermissionsSection.tsx`, `api/powerPermissions.ts`, `admin.json` — Recht

### Verhalten

- **Popover:** Adapter-Schalter; gekoppelte Geräte nach `kind` gruppiert mit
  Verbinden/Trennen und Akkustand; Entfernen über ein Menü mit Rückfrage.
- **„Gerät hinzufügen"** startet den Scan mit Countdown und listet ungekoppelte
  Funde. Ist `can_pair_here` falsch, ist der Knopf ausgegraut mit Hinweis
  „Koppeln nur im lokalen Netz". Ist `pairing_active` wahr und die Sitzung nicht
  die eigene: ausgegraut mit „Es wird gerade gekoppelt".
- **Koppel-Dialog** je nach `stage`: Spinner „Gerät in den Kopplungsmodus
  versetzen …" · großer Code mit Fortschrittspunkten (`entered`) · Ja/Nein beim
  Zahlenvergleich · Erfolg / kuratierte Fehlermeldung. Abbrechen jederzeit.
- **Eingabegeräte** tragen im Dialog einen Hinweis, dass sie in die
  Desktop-Session tippen können (Information, siehe Sicherheit Punkt 7).
- **Abfrage:** alle 3 s bei offenem Popover, jede Sekunde bei offenem
  Koppel-Dialog, gar nicht bei geschlossenem Popover. Läuft eine Antwort noch,
  wird die nächste Abfrage übersprungen.
- **`available: false`** zeigt `detail` statt einer leeren Liste.

## Dev-Modus

`DevBluetoothBackend` (bei `NAS_MODE=dev` oder nicht-Linux) hält im Speicher:
Adapter, einen gekoppelten Xbox-Controller (verbunden, Akku 80 %) und einen
gekoppelten, getrennten JBL. Ein Scan fördert drei Geräte zutage, damit jeder
UI-Pfad auf Windows bedienbar ist:

| Dev-Gerät | Ablauf |
|---|---|
| „Dev-Tastatur" | `display_passkey`, `entered` zählt im Sekundentakt hoch |
| „Dev-Maus" | Kopplung ohne Rückfrage |
| „Dev-Telefon" | `confirm` (Zahlenvergleich) |

Die Dev-Kopplung läuft **über dieselbe `pairing.py`** — Sperre und SHM-Dateien
sind echt (`%TEMP%/baluhost-shm/`), nur die Agent-Aufrufe werden simuliert. So ist
die Übergabe zwischen Workern auch in Dev abgedeckt.

## Spike (erste Umsetzungsaufgabe, auf BaluNode)

Zu messen **an der Wirkung, nicht am Exit-Code**:

1. Mit einem Wegwerf-Skript über `dbus-next`, das den Agenten wie geplant
   registriert und **jeden** Agent-Aufruf protokolliert:
   - JBL entfernen und neu koppeln — welche Agent-Methoden ruft BlueZ?
   - Kommt bei Just Works `RequestAuthorization`, oder winkt BlueZ selbst durch?
   - Erscheint parallel ein BlueDevil-Dialog auf dem Fernseher? (Soll: nein.)
2. Dasselbe mit dem Xbox-Controller — **nur wenn gerade nicht gespielt wird**;
   der Controller muss danach ohnehin neu gekoppelt sein.
3. Mitschnitt von `GetManagedObjects` mit **verbundenen** Geräten als Fixture
   (`Battery1`, `Input1`, `Trusted`, `UUIDs` sichtbar). MAC-Adressen konsistent
   anonymisieren, bevor etwas ins Repo kommt.

Ändert der Spike eine Annahme (insbesondere `RequestAuthorization`), wird dieses
Dokument angepasst, bevor weiter implementiert wird.

## Tests

**Backend**
- `bluez.py`-Parser gegen die gemessene Fixture: `kind`-Abbildung, Namensfallback
  Alias → Name → Adresse, fehlendes `Battery1`, Geräte fremder Adapter werden
  ausgefiltert, Rohtypen (`ManufacturerData`) landen nicht im Modell.
- Adapterwahl: alle vier Zeilen der Tabelle.
- Agent: fremdes Gerät → `Rejected` in jeder Methode; `RequestPinCode` nur bei
  `input-keyboard`; `AuthorizeService` und `RequestPasskey` immer `Rejected`;
  unbeantworteter Zahlenvergleich → `Rejected` nach Timeout; PIN kommt aus
  `secrets`.
- Sitzung: Sperre exklusiv; freigegeben nach Sitzungsende und nach Prozessende;
  Code nur an den Initiator; veraltete/fehlende Datei ⇒ `cancelled`; Antwort mit
  fremder `session_id` wird verworfen; Abbruch.
- Routen: 403 ohne Recht; **403 von öffentlicher IP auch als Admin** (pair,
  confirm); 400 bei ungültiger Adresse; 404 bei unbekannter Adresse **ohne dass
  das Backend aufgerufen wird**; 409 bei laufender Kopplung; BlueZ-Rohtext nie in
  der Antwort; Audit-Einträge geschrieben.
- **`caplog`-Prüfung:** Code und PIN tauchen in keinem Log-Eintrag auf.
- UI-Manifest wie bei den Geschwister-Plugins (sonst bleibt die Topbar leer).
- Recht: Feld in `get`/`update`/`my-permissions`, keine Implikation.

Kein Test ruft echtes BlueZ auf; der CI-Runner hat keinen System-Bus mit BlueZ.

**Frontend** (Vitest, läuft in CI)
- `BluetoothMenu`: erscheint nur bei Plugin *und* Recht; Gruppierung; ausgegrauter
  Koppeln-Knopf bei `can_pair_here=false` und fremder Sitzung.
- `BluetoothPairingDialog`: alle `stage`-Zustände, Abbrechen, Ja/Nein.
- **Vertragstest der Platzhalter direkt gegen `bluetooth.json`** (de/en) — der
  react-i18next-Mock erfindet die Interpolation selbst und verdeckt fehlende
  `{{platzhalter}}`.

Vor dem PR: `eslint .` und `npm run build` (nicht nur `tsc --noEmit`).

## Doku

- `backend/app/plugins/installed/bluetooth/CLAUDE.md` (neu, Aufbau wie
  `audio_control`)
- `backend/app/plugins/CLAUDE.md` — Verzeichnisbaum
- Wurzel-`CLAUDE.md` — Quick Reference
- `.claude/rules/architecture.md` — API-Liste
- `.claude/rules/security-agent.md` — Rollenmodell: doppeltes Gate für
  `can_manage_bluetooth` (Recht **und** LAN), analog `can_unlock_session`

## Betrieb

Der Router wird **nur beim Start gemountet**. Nach dem ersten Aktivieren braucht
es einen `baluhost-backend`-Neustart; `GET /api/plugins/bluetooth` zeigt das über
`restart_required`. Auf BaluNode ist sonst nichts zu provisionieren: der
Dienst-User ist bereits in der Gruppe `bluetooth`. Für frische Boxen ergänzt
`deploy/install/modules/10-systemd-services.sh` einen idempotenten Schritt nach
dem Muster der `video`-Gruppe (`:187-194`): **nur wenn** `getent group bluetooth`
existiert (also BlueZ installiert ist), den Dienst-User per `usermod -aG` aufnehmen;
sonst eine Warnung und weiter. Ohne BlueZ meldet das Plugin `available: false`.

## Bekannte Grenzen

- **WireGuard-Clients zählen als lokal,** sofern das VPN-Subnetz privat
  adressiert ist — `is_private_or_local_ip` unterscheidet nicht zwischen LAN und
  VPN. Das entspricht dem Verhalten von `can_unlock_session`. Wer über VPN
  verbunden ist, besitzt bereits einen WireGuard-Schlüssel als zweiten Faktor.
- **Ungekoppelte Funde verschwinden** kurz nach dem Scan (`TemporaryTimeout`).
- **Kopplung setzt voraus, dass das Gerät im Kopplungsmodus ist.** Das Plugin
  kann das nicht auslösen; der Dialog sagt es.
- **Parallel koppelnde KDE-Sitzung** führt zu `InProgress` (409).
- **Nach dem Aufwachen** ist der Adapter frisch initialisiert; Wiederverbinden
  übernimmt BlueZ (`ReconnectAttempts`), nicht das Plugin.
- **`discovering` ist nicht exklusiv** — es zeigt auch KDE-Scans.
- **Gemessen wurde an zwei Geräten** (Xbox-Controller LE, JBL BR/EDR). Maus und
  Tastatur sind durch den Agent-Vertrag abgedeckt, aber nicht am echten Gerät
  gemessen, bis der Betreiber eines koppelt.

## Aufwandsschätzung

| Bereich | Umfang |
|---|---|
| Spike + Fixture auf BaluNode | klein |
| Recht (Modell, Migration, Dienst, deps, `my-permissions`, Toggle) | klein, Muster vorhanden |
| `bluez.py` + Parser + Adapterwahl | mittel |
| `agent.py` + `pairing.py` (Sperre, SHM, Automat) | groß — der eigentliche Kern |
| Routen, Fehlerabbildung, Audit | mittel |
| Topbar-Popover + Koppel-Dialog + i18n | mittel |
| Tests | mittel bis groß |
