# Desktop-Tray für KDE Plasma — Design

**Datum:** 2026-09-21
**Status:** Überarbeitet nach kritischem Review (2 vorbestehende Backend-Defekte, 6 Entwurfsfehler)
**Branch:** `feat/desktop-tray`
**Basis:** `main` @ `e143b21f`

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

**Beim Entwurf kam heraus, dass es noch schlechter steht.** `emit_sync`
(`services/notifications/events.py:603`) schreibt die Notification und ruft
danach nur `_send_push_sync()` — nie `create()`, nie `dispatch()`, also nie
einen Broadcast. Genau die kritischen Hardware-Ereignisse laufen über diesen
Pfad: `emit_raid_degraded_sync`, `emit_smart_failure_sync`,
`emit_temperature_critical_sync`, `emit_disk_space_critical_sync`. Auch die
offene Web-UI erfährt davon heute nichts. Das ist kein Tray-Problem, aber ohne
Behebung wäre das Tray bei genau diesen Ereignissen blind.

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
- **Eine Meldungsliste im Menü.** Ursprünglich vorgesehen, beim Planen
  verworfen: Eine Liste zu rendern und Klicks darauf zu behandeln macht aus
  `tray.py` eine kleine Anwendung und hebelt den Schnitt aus, der die Logik
  ohne Qt prüfbar hält. Ein Klick auf das Icon öffnet die Web-UI, die diese
  Liste bereits hat.
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

**Was grün nicht heißt.** Es heißt „nichts Ungelesenes", nicht „Anlage gesund".
`mark_as_read` setzt nur `is_read`; wer eine RAID-Meldung liest, während das
Array degradiert bleibt, sieht ein grünes Icon. Der Tooltip benennt deshalb
Ungelesenes und verspricht keinen Gesundheitszustand. Wer eine echte
Zustandsachse will, braucht eine zweite Quelle — das ist bewusst nicht Teil
dieser Runde.

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
| `watch.py` | Snapshot laden, Ereignisse normalisieren, Backoff berechnen |
| `loop.py` | Wiederanlauf, Takt, Gaming-Gate, Zustellung — alles Entscheidbare |
| `announce.py` | Verbindungsmeldungen, Stummschaltung |
| `state.py` | Ungelesene Meldungen halten, Icon-Zustand ableiten, Warteschlange |
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

**Menü, bewusst schmal:** BaluHost öffnen · eine Stunde stumm · neu koppeln ·
Beenden. Keine Meldungsliste (siehe Nicht-Ziele) und keine Service-Steuerung —
letztere bleibt bei Companion-App und Web-UI.

Weil die Liste entfällt, hat das Tray **keinen ausgehenden Pfad**: Es markiert
nichts als gelesen. Das ist Absicht — es zeigt und meldet, es bedient nicht.

## Authentifizierung

Wiederverwendung des vorhandenen **Device-Code-Flows** aus
`app/api/routes/desktop_pairing.py`, der für BaluDesk gebaut wurde und
`platform: linux` bereits kennt.

`baluhost-tray --pair` → `POST /api/desktop-pairing/device-code` mit `device_id`
aus der machine-id, Hostname als `device_name` → der 6-stellige Code erscheint
auf der Konsole → Polling gemäß dem gelieferten `interval` → bei `approved`
landen `access_token` und `refresh_token` in `~/.baluhost/tray-tokens.json` mit
`0600`.

Der Router trägt `prefix="/desktop-pairing"`; `/api/desktop/…` ist nicht
gebunden. Die Poll-Route ist auf 12 Anfragen pro Minute begrenzt, deshalb
schläft der Flow `interval + 1`.

Gewählt gegenüber einem API-Key, weil nichts abzutippen ist und die Kopplung
pro Gerät widerrufbar wird — *wird*, nicht *ist*: Heute verwirft
`poll_device_code` den jti des Refresh-Tokens und hinterlegt es nie, weshalb
`/auth/refresh` es als widerrufen ablehnt und `revoke_device_tokens()` nichts
zu widerrufen hat. Die Kopplung stirbt mit dem Access-Token. Das wird im Plan
als eigener Task behoben und betrifft BaluDesk ebenso.

**Zum Umfang des Tokens:** Die Kopplung gibt ein vollwertiges Nutzer-Token
heraus, nicht ein auf Benachrichtigungen beschränktes. Das Tray hält damit mehr
Rechte, als es braucht. Die Zusage „fasst nichts Privilegiertes an" bezieht sich
auf Betriebssystemrechte, nicht auf die API. Ein scoped Token wäre die bessere
Lösung — das Muster existiert (`create_ws_token`, `create_sse_token`) — und ist
hier bewusst zurückgestellt. Gewählt gegenüber dem Unix-Socket
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
4. **Alle 10 Minuten ein Neuabgleich per REST.** Keine Notlösung, sondern die
   Korrekturinstanz für drei Dinge, die ein Ereignisstrom nicht leisten kann:
   abgelaufene Snoozes (siehe unten), in der Verbindungslücke verpasste Frames
   und Drift des Zählers.
5. **Ausgehend: nichts.** Ohne Meldungsliste markiert das Tray nichts als
   gelesen. Der Fan-out nützt ihm, er wird von ihm nicht ausgelöst.

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

**Änderung:** Nach `mark_as_read`, `dismiss`, `snooze`, `delete_permanently`,
`mark_all_as_read`, `dismiss_all`, `restore` und `empty_trash` — **acht**
Routen, nicht sechs — ein Fan-out an alle Verbindungen des Nutzers. `restore`
und `empty_trash` ändern den Zähler zwar nicht (Papierkorb-Zeilen sind nie
ungelesen, weil `dismiss` immer `is_read=True` mitsetzt), wohl aber die Liste
in Web-UI und BaluApp — und zugesagt ist Bestandsgleichheit, nicht
Zählergleichheit.

Die Sammelaktionen tragen **keine IDs**: `mark_all_as_read` kennt einen
optionalen Kategoriefilter, „alles gelesen" wäre bei gesetzter Kategorie
falsch. Sie bedeuten „neu laden"; der Client rät nicht, er fragt.

- `send_unread_count()` (existiert, ungenutzt)
- ein neues Ereignis `notification_state` mit
  `{"ids": [...], "action": "read" | "dismissed" | "snoozed" | "deleted"}`

**Ort des Fan-outs: die Route-Ebene, nicht der Service.** Die Zustandsmethoden
des `NotificationService` sind synchron (`def` mit `Session`), der Versand ist
`async`. Ein Fan-out im Service müsste aus synchronem Code heraus einen Task
auf einer fremden Eventloop starten — fragil und schwer testbar. Die
Route-Handler sind bereits `async`; dort wird nach dem Service-Aufruf ein
gemeinsamer Helfer gerufen, damit die sechs Stellen nicht auseinanderlaufen.

`broadcast_to_user()` ist für diesen Zweck **nicht** verwendbar: Es setzt
`"type": "notification"` fest. Für den Fan-out kommt eine eigene Methode
`send_notification_state()` dazu, symmetrisch zu `send_unread_count()`.

Dazu `NotificationContext.tsx` um den neuen Ereignistyp erweitern, damit die
offene Web-UI live nachzieht.

## Snooze — warum der Neuabgleich nötig ist

`NotificationService.snooze()` setzt nur `snoozed_until` und lässt
`is_read=False`. `get_unread_count()` und `get_user_notifications()` filtern
gesnoozte Zeilen heraus, solange die Frist läuft. **Einen Job, der den Ablauf
bemerkt, gibt es nicht** — `notifications/scheduler.py` kennt nur
`check_and_send_warnings` und `_run_trash_cleanup`. Die Zeile taucht einfach
wieder in Abfragen auf, sobald jemand fragt.

Behandelte das Tray `snoozed` wie „gelesen" und verließe sich auf Ereignisse,
wäre eine Snooze faktisch ein „für immer weg": Icon grün bis zum nächsten
Neustart, obwohl das RAID weiter degradiert ist. Der Zehn-Minuten-Neuabgleich
ist der einzige Weg zurück auf rot — deshalb steht er im Datenfluss und nicht
in einer Fußnote.

## Gaming-Gate

Der Rechner ist zugleich Gaming-Rig. Meldungen würden über Vollbildspielen
landen. Zwei Ebenen:

**1. KDE.** Zustellung läuft über den Standardweg `org.freedesktop.Notifications`,
also greifen Plasmas eigene „Nicht stören"- und Vollbild-Regeln automatisch.
Dafür ist nichts zu bauen.

**2. BaluHost-eigener Gaming-Zustand.** Gaming läuft über das Plugin
`steam_gaming`. Die naheliegende Quelle `gaming_mode_on_screen()` ist die
**falsche**: Ihr Marker bedeutet laut `steam_gaming/CLAUDE.md:30` „Marker file
recording that *we* started gaming mode" und wird nur von
`launch.start_gaming_mode()` gesetzt. Ein Spiel, das direkt in Steam
angeklickt wird, setzt ihn nicht — der Normalfall also. Ein Gate darauf wäre
fast immer offen.

Richtig ist `game_is_running()` (`gaming_presence.py:80`), dieselbe Quelle, die
Pill, Ledger und Panel benutzen, mit dem Marker als zweitem Pfad für Big
Picture:

```
(game_is_running() or marker gesetzt) and displays_on()
```

Die Display-Bedingung bleibt: Sie ist es, die einen verwaisten Marker aus einer
abgebrochenen Sitzung von selbst verfallen lässt.

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
3. **Drei Fehlerklassen, nicht eine.** Ein 401 kostet einen Refresh und einen
   neuen Versuch. Ein 429 oder 5xx kostet einen Backoff — und *nur* das: Die
   ws-Token-Route ist auf 30 Anfragen pro Minute begrenzt, und ein Backoff, der
   bei einer Sekunde beginnt, brennt das Kontingent in einer halben Minute
   durch. Ein Ratelimit darf niemals eine Entkopplung auslösen.
4. **Kopplung verloren** (Refresh mit 401 abgelehnt, Gerät widerrufen): lokale
   Token löschen, Icon grau, eine Meldung, Menüeintrag „Neu koppeln". Die
   Schleife endet sichtbar, statt den Worker-Thread still sterben zu lassen.
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
- **`packages.find` und `package-data` müssen erweitert werden.** Heute sammelt
  `pyproject.toml` nur `["app*", "baluhost_tui*"]`; ohne `baluhost_tray*` wäre
  das Konsolenskript installiert, das Modul nicht, und die Unit begänne mit
  `ModuleNotFoundError`. Ohne `package-data` fehlten die Icons im Wheel.
- **`ConditionPathExists` auf die Token-Datei.** Ohne Kopplung soll die Unit gar
  nicht starten — sonst startet `Restart=on-failure` sie im Zehnsekundentakt neu,
  bis sie auf `failed` steht.
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

## Zwei Vorbedingungen aus dem Review

Beim kritischen Review des Entwurfs kamen zwei vorbestehende Defekte heraus,
ohne die das Tray nicht funktionieren *kann*. Beide gehören in dieselbe Runde,
haben aber eigenständigen Wert:

1. **`emit_sync` broadcastet nicht** (siehe Problem). Ohne Behebung bliebe das
   Icon bei RAID-Degradation, SMART-Ausfall, kritischer Temperatur und voller
   Platte grün — also bei allem, wofür es gebaut wird.
2. **Das Refresh-Token der Gerätekopplung wird nie hinterlegt** (siehe
   Authentifizierung). Ohne Behebung entkoppelt sich das Tray nach Ablauf des
   Access-Tokens selbst.

Beide nützen Web-App und BaluApp unabhängig vom Tray.

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
- **Wer ist der Desktop-Benutzer?** Der Installer kennt `BALUHOST_USER` — das
  angelegte Dienstkonto, nicht zwingend der Mensch, der sich in Plasma anmeldet.
  Eine User-Unit im Home des Dienstkontos startet in keiner Desktop-Sitzung. Der
  Zielbenutzer wird deshalb getrennt bestimmt und im Zweifel erfragt, statt
  geraten.
- **Es gibt keinen periodischen RAID-Health-Poll.** `emit_raid_degraded_sync`
  wird nur aus `degrade()` gerufen, also wenn BaluHost selbst ein Device
  ausfallen lässt. Eine spontan degradierende Platte erzeugt heute also
  überhaupt keine Meldung — weder im Tray noch auf dem Handy. Das ist ein
  eigener Backend-Befund, der über diese Runde hinausgeht, und der Grund, warum
  die manuelle Abnahme mit `simulate_failure` oder einer manuell erzeugten
  Meldung arbeiten muss.
- **Systemmeldungen und mehrere Admins.** `is_read` ist eine einzige Spalte, und
  `_user_filter(is_admin=True)` schließt `user_id IS NULL` ein. Liest Admin A
  eine Systemmeldung, sinkt der Zähler von Admin B, ohne dass B etwas erfährt —
  der Fan-out adressiert nur eine `user_id`. Im Ein-Admin-Betrieb folgenlos.
