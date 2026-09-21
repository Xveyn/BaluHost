# Desktop-Tray für KDE Plasma — Design

**Datum:** 2026-09-21
**Status:** Entwurf zur Durchsicht
**Branch:** `feat/desktop-tray`
**Basis:** `main` @ `2ed58e59`

## Problem

BaluNode ist nicht nur Server, sondern auch der Desktop- und Gaming-Rechner,
an dem täglich gearbeitet wird. Trotzdem gibt es auf genau dieser Maschine
keine Stelle, an der man den Zustand der Anlage sieht, ohne die Web-UI zu
öffnen.

Konkret fehlt der Desktop als Benachrichtigungsweg vollständig. Die
Zustellkanäle sind heute `in_app` (WebSocket in einem offenen Browser-Tab) und
`push` (Firebase auf das Handy). Im Backend gibt es keinen einzigen Aufruf von
`org.freedesktop.Notifications` oder `notify-send`. Degradiert nachts ein RAID,
erfährt man es auf dem Telefon oder beim nächsten Öffnen der Web-UI — nicht auf
dem Rechner, an dem man gerade sitzt.

## Ziel

Ein Tray-Icon im Plasma-Panel, das zwei Dinge tut, die eine Web-UI prinzipiell
nicht kann:

1. **Zustand ohne Öffnen zeigen.** Die Farbe des Icons trägt die Information.
2. **Passiv melden.** Kritische Ereignisse erscheinen als Desktop-Meldung.

Dazu kommt ein Anspruch, der über das Tray hinausreicht: Der Bestand muss mit
Web-App und BaluApp **synchron** sein. Was auf dem Handy weggewischt wurde, darf
das Tray nicht erneut melden.

## Nicht-Ziele

- **Service-Steuerung.** Neustarten oder Beenden von Diensten bleibt der
  Companion-App und der Web-UI vorbehalten. Das Tray fasst nichts
  Privilegiertes an und braucht keine sudoers-Erweiterung.
- **Ein zweiter Gesundheitsbegriff.** Es wird kein Aggregat-Endpunkt gebaut und
  keine eigene Schwellwertlogik über RAID, SMART oder Plattenfüllstand gelegt.
- **Ein `desktop_enabled`-Kanal in den Notification-Preferences.** Die
  Kanal-Abstraktion existiert (`is_channel_enabled_for_category`), aber eine
  eigene Spalte samt Migration und Einstellungs-UI lohnt erst bei mehreren
  Nutzern oder mehreren Desktops. Filterung und Stummschalten passieren in v1
  lokal im Tray.
- **Laufende Vorgänge anzeigen** (Backup läuft, Update läuft, Scrub läuft).
  Nur Kritisches, damit eine Meldung eine Meldung bleibt.
- **Mehrere Zielrechner.** Das Tray wird auf dem Deployment-Host installiert —
  also auf der Maschine, die zugleich als PC dient. Technisch hindert nichts
  einen zweiten Rechner (siehe Abschnitt Authentifizierung), aber
  Paketierung und Installation zielen auf diesen einen.

## Grundidee: das Icon ist eine Projektion des Meldungsbestands

Es gibt im Backend **keinen Aggregat-Endpunkt für Systemgesundheit**;
`/api/health` liefert nur `{"status": "ok", version}` — ein Liveness-Ping. Statt
einen solchen Endpunkt zu bauen, leitet das Tray seinen Zustand aus den
**ungelesenen Meldungen** ab.

Das hat drei Konsequenzen, die alle in die gewünschte Richtung zeigen:

- Der Abgleich mit Web und Android ist geschenkt. Auf dem Handy weggewischt →
  Icon wieder grün.
- „Nur Kritisches" deckt sich mit dem, was das Backend ohnehin führt
  (`NotificationType.CRITICAL` / `WARNING`).
- Es entsteht keine zweite Wahrheit über den Systemzustand, die von der Web-UI
  abweichen könnte.

Vier Zustände:

| Zustand | Bedingung |
|---|---|
| **grau** | keine Verbindung zum Backend |
| **grün** | keine ungelesenen Meldungen |
| **gelb** | ungelesene Meldung vom Typ `warning` |
| **rot** | ungelesene Meldung vom Typ `critical` |

## Icon-Material

Verwendet wird das BaluHost-Logo (blaue Katze). Die vorhandenen Dateien taugen
nicht unverändert:

- `client/public/baluhost-logo.svg` ist mit 1,2 MB kein echtes Vektor-Logo,
  sondern ein nachgezeichnetes Bitmap (viewBox 797×803, tausende Pfadpunkte).
- Die PNGs (`client/src/assets/baluhost-logo.png` 256², `client/src-tauri/icons/icon.png`
  1024²) tragen ein dunkles Hintergrundquadrat. Im Panel säße die Katze in
  einem Kasten.

**Zu erstellen:** eine freigestellte Variante, aus dem 1024er abgeleitet,
gerendert in 22/24/32/48 px, abgelegt unter `backend/baluhost_tray/icons/`.

**Die Zustände gehören nicht in die Katze.** Eine rot eingefärbte Katze liest
sich als anderes Logo, nicht als Alarm. Stattdessen ein **Badge unten rechts**:
Katze pur · Katze + gelber Punkt · Katze + roter Punkt · ausgegraute Katze.
Nebeneffekt: Weil die Katze farbig bleibt, funktioniert sie auf hellen wie
dunklen Panels, ohne dass zwei Themen-Varianten gepflegt werden müssen.

## Architektur

Neues Modul `backend/baluhost_tray/`, Konsolenskript `baluhost-tray` neben dem
vorhandenen `baluhost-tui` in derselben `pyproject.toml`.

| Modul | Aufgabe |
|---|---|
| `pairing.py` | Device-Code-Flow: Code anzeigen, pollen, Token ablegen |
| `session.py` | Token laden und erneuern, `BackendClient` stellen, ws-token besorgen |
| `watch.py` | WebSocket verbinden, Backoff, Ereignisse normalisieren |
| `state.py` | Ungelesene Meldungen halten, Icon-Zustand ableiten, Gaming-Warteschlange |
| `notify.py` | `org.freedesktop.Notifications` über `dbus-next` |
| `tray.py` | `QSystemTrayIcon`, Menü, Icon-Darstellung |
| `config.py` | Erweiterung des TUI-Configs um refresh-Token und Einstellungen |

**Unverändert übernommen:** `baluhost_tui.client.BackendClient` (httpx,
Bearer-Token, get/post/put/delete) und `baluhost_tui.config` (Token-Datei unter
`~/.baluhost/` mit `0600`). Der Token-Speicher wird um das refresh-Token
erweitert; heute hält `save_token()` nur einen einzelnen String.

**Prozessmodell:** ein Prozess. Qt-Eventloop im Hauptthread, asyncio für
WebSocket und D-Bus in einem Worker-Thread, Übergabe an die GUI über
Qt-Signale. Bewusst ohne Zusatzabhängigkeit wie `qasync`.

**Schnitt zwischen `state.py` und `tray.py`:** `tray.py` enthält nur
Darstellung, die gesamte Logik sitzt in `state.py`. Das ist der Grund für die
Trennung — so ist alles Prüfbare ohne Qt prüfbar (siehe Tests).

**Menü, bewusst schmal:** BaluHost öffnen · letzte Meldungen (Klick markiert
gelesen) · eine Stunde stumm · Beenden.

## Authentifizierung

Wiederverwendung des vorhandenen **Device-Code-Flows** aus
`app/api/routes/desktop_pairing.py`, der für BaluDesk gebaut wurde und
`platform: linux` bereits kennt.

`baluhost-tray --pair` → `POST /api/desktop/device-code` mit `device_id` aus der
machine-id, Hostname als `device_name` → der 6-stellige Code erscheint als
Desktop-Meldung und im Menü → Polling gemäß dem gelieferten `interval` → bei
`approved` landen `access_token` und `refresh_token` in `~/.baluhost/` mit
`0600`.

Gewählt gegenüber einem API-Key, weil nichts abzutippen ist und die Kopplung
pro Gerät widerrufbar bleibt. Gewählt gegenüber dem Unix-Socket
(`/run/baluhost/local.sock`), weil dieser Kanal konzeptionell der Companion-App
gehört, aktuell `disabled`/`inactive` ist und das Tray fest an eine Maschine
binden würde.

## Datenfluss im Betrieb

1. **Start:** Token laden, `GET /api/notifications` und
   `GET /api/notifications/unread-count` → Anfangszustand → Icon.
2. **Live-Kanal:** `POST /api/notifications/ws-token` (60 s gültig, scoped) →
   WS `/api/notifications/ws?token=…`.
3. **Eingehende Ereignisse:**
   - `notification` (neu) → bei `critical` Desktop-Meldung, bei `warning` nur
     Icon-Farbe
   - `unread_count` → Zähler
   - `notification_state` (**neu**, siehe unten) → Zustandsänderung von anderswo
4. **Ausgehend:** Klick auf eine Meldung im Tray →
   `POST /api/notifications/{id}/read` → Fan-out → Web und Android ziehen nach.

## Backend-Anteil: Fan-out der Zustandsänderungen

Dies ist der Teil mit Nutzen über das Tray hinaus.

**Ausgangslage (verifiziert am 2026-09-21):** Der geräteübergreifende Abgleich
funktioniert heute nur beim Laden. Der Bestand liegt in der
`notifications`-Tabelle, jede Oberfläche, die frisch lädt, sieht denselben
Stand. Neue Meldungen kommen live über den WS-Typ `notification`. Was fehlt,
sind **Zustandsänderungen an bereits offene Clients**:

- `NotificationContext.tsx` lädt einmal beim Mount (Zeile 84-86) und verlässt
  sich danach auf den WebSocket; kein `refetchInterval`, kein Nachladen bei
  Fokuswechsel.
- In `routes/notifications.py` wird der WebSocket-Manager nur für `connect` und
  `disconnect` benutzt.
- `mark_as_read`, `dismiss`, `snooze` und `delete` im `NotificationService`
  senden nichts.
- `WebSocketManager.send_unread_count(user_id, count)` — die Methode, die genau
  diesen Fan-out macht — hat **keinen Produktivaufrufer**; einziger Aufrufer ist
  `tests/services/test_websocket_manager.py:144`.

Bei einem Browser-Tab fällt das kaum auf, weil man ihn schließt und neu öffnet.
Ein Tray steht tagelang offen; dort wäre die Lücke dauerhaft sichtbar — als
Piepen über Erledigtes.

**Änderung:** Nach `mark_as_read`, `dismiss`, `snooze`, `delete`,
`mark_all_as_read` und `dismiss_all` ein Fan-out an alle Verbindungen des
Nutzers:

- `send_unread_count()` (existiert, ungenutzt)
- ein neues `broadcast_typed`-Ereignis `notification_state` mit
  `{"ids": [...], "action": "read" | "dismissed" | "snoozed" | "deleted"}`

Dazu `NotificationContext.tsx` um den neuen Ereignistyp erweitern, damit die
offene Web-UI live nachzieht.

## Gaming-Gate

Der Rechner ist zugleich Gaming-Rig. Meldungen würden über Vollbildspielen
landen. Zwei Ebenen:

**1. KDE.** Zustellung läuft über den Standardweg `org.freedesktop.Notifications`,
also greifen Plasmas eigene „Nicht stören"- und Vollbild-Regeln automatisch.
Dafür ist nichts zu bauen.

**2. BaluHost-eigener Gaming-Zustand.** Gaming läuft über das Plugin
`steam_gaming`. `gaming_state.is_active()` prüft eine Markerdatei unter
`<nas_storage>/.system/…/gaming_mode_active`; `power/gaming_presence.py`
kombiniert sie mit „ein Display ist an" zu `gaming_mode_on_screen()`. Letzteres
ist der richtige Begriff für das Tray, weil ein verwaister Marker aus einer
abgebrochenen Sitzung die Meldungen sonst dauerhaft stummschalten würde.

**Neuer Endpunkt**, in den Routen des Plugins (Plugin-Router hängen unter
`{api_prefix}/plugins/{name}`):

```
GET /api/plugins/steam_gaming/session-state  →  {"gaming_active": bool}
```

**Verhalten im Tray:** Ist `gaming_active`, werden Popups **zurückgehalten, nicht
verworfen**. Das Icon wechselt trotzdem sofort die Farbe. Endet die Sitzung,
werden die zurückgehaltenen Meldungen zugestellt; mehr als drei werden zu einer
Sammelmeldung zusammengefasst.

**Abfragestrategie:** Der Endpunkt wird nur gefragt, wenn es darauf ankommt —
unmittelbar bevor ein Popup gezeigt würde, und danach periodisch (30 s),
solange die Warteschlange nicht leer ist. Im Normalbetrieb also gar nicht.

**Fehlerrichtung:** Das Plugin ist abschaltbar; dann liefert die Route 404.
404, Zeitüberschreitung oder Fehler gelten als **„nicht im Gaming-Modus"**, das
Popup wird also gezeigt. Lieber eine Meldung zu viel als eine verschluckte.

## Fehlerverhalten

1. **Backend nicht erreichbar:** Icon grau, **eine** Meldung, danach Stille bis
   zur Rückkehr — kein Piepen im Minutentakt. Reconnect mit exponentiellem
   Backoff (1 s bis max. 60 s, mit Jitter). Eine „wieder verbunden"-Meldung nur,
   wenn die Unterbrechung länger als zwei Minuten war.
2. **Reihenfolge nach einer Offline-Phase:** erst REST-Snapshot, dann
   gepufferte WS-Ereignisse anwenden. Andersherum entsteht ein Rennen — der
   Socket meldet „gelesen" für eine Meldung, die der Snapshot gleich darauf
   wieder als ungelesen bringt, und das Icon flackert zurück auf rot.
3. **ws-Token abgelaufen** (60 s): wird pro Verbindungsaufbau frisch geholt.
   Scheitert das mit 401 → access-Token per refresh erneuern.
4. **Kopplung verloren** (refresh schlägt fehl, Gerät widerrufen): lokale Token
   löschen, Icon grau, Menüeintrag „Neu koppeln". Kein stilles Weiterprobieren
   im Sekundentakt gegen ein Backend, das uns nicht mehr kennt.
5. **Keine D-Bus-Sitzung oder kein SNI-Host** (Start außerhalb von Plasma): mit
   klarer Meldung beenden statt abstürzen.
6. **Doppelstart:** Einzelinstanz über eine Lock-Datei in `$XDG_RUNTIME_DIR` —
   sitzungsgebunden, nicht in `/tmp`.

## Paketierung und Autostart

- systemd-`--user`-Unit `baluhost-tray.service`,
  `WantedBy=graphical-session.target`, `Restart=on-failure`.
- Kein root, keine sudoers-Erweiterung.
- Ausführung aus dem vorhandenen venv, wie `baluhost-tui`.
- **PyQt6 als `optional-dependencies`-Extra `tray`**, damit der Server die
  GUI-Abhängigkeit nicht mitschleppt. Auf dem Zielrechner liegen Qt6 und PyQt6
  bereits systemweit (KDE Plasma).
- Unit-Vorlage unter `deploy/install/templates/` wie die übrigen Units,
  Installationsschritt im vorhandenen Install-Modul.

## Tests

- **Zustandsableitung** als Tabellen-Test: leer → grün · nur Warnung → gelb ·
  kritisch dabei → rot · offline → grau.
- **Snapshot-vor-WS-Reihenfolge** (Fehlerfall 2) und **Backoff-Berechnung**.
- **Gaming-Warteschlange:** zurückhalten, Sammelmeldung ab vier Einträgen,
  Zustellung bei Sitzungsende, 404 → Popup wird gezeigt.
- **`notify.py` und `watch.py` gegen Doppelgänger** (D-Bus-Stub, WS-Server-Stub)
  — kein echter Bus, kein Plasma in CI.
- **Backend-Fan-out:** `mark_as_read` → alle Verbindungen des Nutzers erhalten
  `notification_state` und `unread_count`. Der Teil, der Web und Android
  berührt, braucht echten Regressionsschutz.
- **Frontend:** Test für den neuen Ereignistyp im `NotificationContext`.
- **Kein GUI-Test.** `tray.py` bleibt dünn; die Logik in `state.py` ist ohne Qt
  prüfbar.

## Annahmen und offene Punkte

- **Nutzt BaluApp den WebSocket?** Liegt im Repo `Xveyn/BaluApp`, hier nicht
  einsehbar. Falls BaluApp nur beim Öffnen lädt, profitiert Android vom Fan-out
  erst, wenn es dort nachgezogen wird. Der Fan-out schadet in diesem Fall
  nicht, er wirkt nur noch nicht.
- **Das Gaming-Gate betrifft ausschließlich kritische Meldungen** — denn nur
  die erzeugen überhaupt ein Popup; Warnungen schlagen sich ohnehin nur in der
  Icon-Farbe nieder. Zurückhalten heißt also: auch Kritisches wartet bis zum
  Sitzungsende. Begründung: Ein degradiertes RAID verlangt keine Reaktion
  innerhalb einer Minute, und das Icon steht die ganze Zeit auf rot. Die
  Gegenposition wäre, das Gate ganz wegzulassen und sich auf Plasmas „Nicht
  stören" zu verlassen — dann entfällt auch der neue Endpunkt.
- **Freigestelltes Icon-Material** muss erstellt werden; ein reiner
  Automatismus aus dem 1,2-MB-SVG wird bei 22 px nicht überzeugen.
