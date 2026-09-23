# Prozessübergreifende WebSocket-Brücke — Design

**Datum:** 2026-09-23
**Status:** Entwurf
**Basis:** `main` @ `ab51f7c4`
**Issue:** [#685](https://github.com/Xveyn/BaluHost/issues/685) — „WebSocket-Broadcasts
erreichen nur einen von vier Uvicorn-Workern"
**Vorläufer:** `2026-09-21-desktop-tray-design.md` — das Tray ist der Verbraucher,
für den dieser Mangel weh tut; die dortige Milderung bleibt bestehen.

## Problem

`WebSocketManager` hält seine Verbindungen in einem prozesslokalen `dict`
(`services/websocket_manager.py:37`) hinter einem Modul-Singleton (`:364`). Ein
Broadcast erreicht damit nur die Sockets *seines* Prozesses. Eine Brücke zwischen
den Prozessen gibt es nicht — alle Aufrufstellen arbeiten in-memory.

Am laufenden Produktionssystem (2026-09-23) nachgesehen, ist die Lage schlechter
als im Issue beschrieben:

| Prozessgruppe | Anzahl | Rolle |
|---|---|---|
| `baluhost-backend` (TCP :8000) | 4 Worker | Web-UI, Tray (`main.py:18` zeigt per Default hierhin) |
| `baluhost-backend-local` (UDS) | 2 Worker | Tauri-Companion über `/run/baluhost/local.sock` |
| `monitoring_worker`, `scheduler_worker` | 2 Prozesse | eigenständige Dienste, emittieren Meldungen |
| `webdav_worker` | 1 Prozess | emittiert nichts, kein Emitter initialisiert |

**Es sind sechs API-Prozesse, nicht vier.** Und weil `baluhost-backend.service`
`PrivateTmp=true` setzt, die Local-Unit aber nicht, sieht jede Unit ein eigenes
`/tmp/baluhost-primary.lock` — es gibt **zwei** Primary Worker gleichzeitig (live
belegt: PID 1339281 und PID 1338770, beide mit `Primary worker: True`). Beide
fahren Fan-Control, Power-Manager, SMART-Collector, mDNS und
`notifications.events`.

Dazu ein zweiter, härterer Befund: `EventEmitter.set_event_loop()` wird
ausschließlich in `core/lifespan.py:553` gerufen. `monitoring_worker` und
`scheduler_worker` rufen zwar `init_event_emitter(SessionLocal)`
(`monitoring_worker.py:42`, `scheduler_worker.py:47`), binden den Loop aber nie —
also bricht `_broadcast_sync()` dort sofort ab („No app loop bound"). Meldungen,
die im `monitoring_worker` entstehen — Temperaturschwellen, Plattenplatz — und
die des `scheduler_worker` erzeugen deshalb **überhaupt keinen** WebSocket-Frame.
Nicht 25 %, sondern null.

Das Fehlerbild ist die teure Sorte: das Tray-Icon wird rot, weil der
REST-Schnappschuss über jeden Worker korrekt antwortet, aber die Desktop-Meldung
bleibt aus. Nach einem Neustart des Trays geht es plötzlich.

## Ziel

Ein Broadcast, der in irgendeinem BaluHost-Prozess entsteht, erreicht **jede**
WebSocket-Verbindung, für die er bestimmt ist — unabhängig davon, in welchem
Prozess sie hängt.

## Nicht-Ziele

- **Haltbarkeit über Verbindungsabrisse hinweg.** Wer nicht zuhört, wenn
  gesendet wird, bekommt es nicht nachgeliefert. Alles hier ist flüchtiger
  Live-Zustand, der sich in 1–3 s erneuert; für kritische Meldungen ist der
  REST-Neuabgleich des Trays das Netz. Eine Outbox-Tabelle wurde dafür erwogen
  und verworfen (siehe „Verworfene Wege").
- **Den Doppel-Primary beheben.** Eigener Befund, eigenes Issue. Er erzeugt echte
  Doppelzeilen, aber selten: in der Produktions-DB über sieben Tage **vier**
  Zeilen (zwei Ereignisse, beide „Temperatur erhöht: gpu:edge"), gegenüber 362
  Meldungen insgesamt. Die weit häufigeren Paare aus `user_id=NULL` und
  `user_id=2` sind der normale Fan-out an Admins plus geroutete Nutzer, keine
  Doppelung. **Nebenwirkung, die benannt sein muss:** mit der Brücke werden diese
  zwei Ereignisse pro Woche als zwei Popups sichtbar statt als eines. Die
  doppelten Zeilen stehen heute schon in der Web-UI-Liste.
- **`MAX_CONNECTIONS_PER_USER` prozessübergreifend durchsetzen.** Die Obergrenze
  von 5 gilt je Prozess, effektiv also 6×. Eigener Befund, eigenes Issue.
- **Die Pool-Dimensionierung anfassen.** `pool_size 10 + max_overflow 20` je
  Prozess ergibt rechnerisch 180 mögliche Verbindungen gegen `max_connections=100`.
  Real sind 2–3 je Prozess offen (`pool_open_max` im Concurrency-Log), aktuell 28
  von 100 belegt. Notiert, nicht angefasst.
- **Ein zweiter Dienst für den Notification-WebSocket.** Siehe „Verworfene Wege".

## Die vier Entscheidungen

| Frage | Entscheidung |
|---|---|
| Transport | `pg_notify` mit der Nachricht in der Nutzlast |
| Wer hört zu? | Jeder API-Prozess, **nicht** hinter `IS_PRIMARY_WORKER` |
| Wer stellt zu? | Ausschließlich der Listener — publizieren stellt nie selbst zu |
| Wie wird der echte Pfad geprüft? | Fake-Bus im Unit-Test, echtes Postgres über ein Verifikationsskript |

## Architektur

```
 monitoring_worker ──┐                    ┌──> backend W1 ─> eigene Sockets
 scheduler_worker ───┤                    ├──> backend W2 ─> eigene Sockets
                     ├─ pg_notify ──> PG ─┤    …
 backend  W1..W4 ────┤   'baluhost_ws'    ├──> local W1 ───> eigene Sockets
 backend-local W1,W2 ┘                    └──> local W2 ───> eigene Sockets

 links: publizieren (6 + 2 Prozesse)   rechts: zuhören (die 6 API-Prozesse)
```

Postgres ist bereits die einzige Komponente, die alle diese Prozesse gemeinsam
und dauerhaft sehen — unabhängig davon, zu welcher systemd-Unit sie gehören. Das
ist der Grund für die Wahl, nicht die Bequemlichkeit: eine Brücke, die an einer
Unit hängt, würde die andere nicht erreichen.

### Neu: `app/services/ws_bus.py`

Ein Umschlag trägt genau die Adressierung, die der Manager heute über fünf
Methoden verstreut:

```python
@dataclass(frozen=True)
class WsEnvelope:
    kind: Literal["user", "admins", "all"]
    msg_type: str
    payload: Any
    user_id: int | None = None    # nur kind="user"
    admins_only: bool = False     # nur kind="all"
```

`msg_type` ist der Typ, der auf dem Draht landet: `notification`,
`unread_count`, `notification_state`, `smart_device_update`,
`dashboard_panel_update`. Die Zuordnung der bestehenden Methoden:

| Methode | `kind` | `msg_type` | Nutzlast |
|---|---|---|---|
| `broadcast_to_user(uid, msg)` | `user` | `notification` | `msg` |
| `broadcast_to_admins(msg)` | `admins` | `notification` | `msg` |
| `broadcast_typed(t, p, admins_only)` | `all` | `t` | `p` |
| `send_unread_count(uid, n)` | `user` | `unread_count` | `{"count": n}` |
| `send_notification_state(uid, ids, a)` | `user` | `notification_state` | `{"ids": ids, "action": a}` |

Zwei Implementierungen hinter einem `Protocol` mit `publish(env)`,
`start(deliver)` und `stop()`:

**`PostgresWsBus`** — `publish()` serialisiert nach JSON und feuert
`SELECT pg_notify('baluhost_ws', …)` über die bestehende SQLAlchemy-Engine,
gekapselt in `asyncio.to_thread`: psycopg2 ist synchron und darf den Event-Loop
nicht anhalten. Kein eigener Verbindungslebenszyklus für das Senden — der Pool
kann das schon.

Der Listener ist eine **eigene** psycopg2-Verbindung *außerhalb* des Pools (eine
gepoolte Verbindung müsste für immer ausgecheckt bleiben, was den Pool
belügt): Autocommit, `LISTEN baluhost_ws`, am Loop über
`loop.add_reader(conn.fileno(), …)`. Im Callback `conn.poll()`, `conn.notifies`
leeren, Umschläge in eine `asyncio.Queue` legen; ein Consumer-Task stellt
sequenziell zu. Die Queue statt `create_task` je Nachricht, aus zwei Gründen:
die Reihenfolge bleibt erhalten, und ein Ausbruch an Nachrichten kann keine
unbegrenzte Menge Tasks erzeugen. Läuft die Queue (maxsize 1000) über, fällt das
älteste Element heraus, mit WARNING.

**`LocalWsBus`** — `publish()` ruft `deliver()` direkt. Das ist der
Dev-/SQLite-Pfad und derselbe Code, gegen den die Tests laufen.

Auswahl per `DATABASE_URL.startswith("postgresql")` aus `core/database.py`,
Singleton wie `get_websocket_manager()`.

### `WebSocketManager`: Senden und Zustellen trennen

Heute macht jede der fünf Methoden beides — Empfänger bestimmen *und* auf Sockets
schreiben. Künftig:

- **`deliver_local(env) -> int`** ist die einzige Stelle, die
  `_user_connections` anfasst. Sie behält die bestehende Aufräumlogik für tote
  Sockets unverändert und setzt die drei `kind`-Regeln um:
  - `user` → alle Verbindungen dieses `user_id`
  - `admins` → über `_admin_users`, und nur Verbindungen mit `conn.is_admin`
    (genau die heutige Semantik von `broadcast_to_admins`, inklusive der in
    `broadcast_typed` dokumentierten Abgrenzung zu `is_privileged()`)
  - `all` → alle Verbindungen, bei `admins_only` ohne die nicht-administrativen
- Die fünf öffentlichen Methoden behalten ihre Signaturen, bauen nur noch den
  Umschlag und geben ihn an den Bus.
- **Der Rückgabetyp wird `None`.** Heute liefern sie die Zahl erreichter Sockets.
  Der publizierende Prozess kann das nach der Umstellung nicht mehr wissen, und
  ein Wert, der in Produktion immer 0 wäre, ist eine Falle für den nächsten
  Leser. Keine Aufrufstelle im App-Code nutzt ihn; elf Zusicherungen in
  `tests/services/test_websocket_manager.py` prüfen künftig `deliver_local()`.
- `is_user_connected()`, `get_connection_count()` und
  `get_connected_user_ids()` bleiben, werden aber im Docstring als **lokale**
  Auskunft markiert: sie kennen nur die Verbindungen dieses Prozesses.

**Genau ein Zustellpfad.** `publish()` stellt nie selbst zu; zugestellt wird nur
aus dem Listener. `NOTIFY` geht an jede Sitzung, die `LISTEN` auf dem Kanal
ausgeführt hat — die der publizierende Prozess ebenfalls hält, auf einer eigenen
Verbindung neben dem Pool. Er bekommt seine eigene Nachricht also über denselben
Weg wie alle anderen: kein Sonderfall, keine Doppelzustellung.

**Eine Ausnahme, mit Absicht:** solange der Listener getrennt ist (also im
Reconnect-Backoff), stellt `publish()` zusätzlich lokal zu. Ein Doppelrisiko
entsteht nicht, weil in der Lücke nichts nachgespielt wird, und die Clients
dieses Prozesses verstummen nicht völlig. `LocalWsBus` ist strukturell derselbe
Fall.

### Anbindung in `lifespan`

Der Bus startet **in jedem Worker**, nicht hinter `IS_PRIMARY_WORKER` — das ist
der ganze Punkt der Änderung. Damit greift er auch in den zwei Workern der
Local-Unit. Zustellziel ist
`lambda env: get_websocket_manager().deliver_local(env)`.

Gestoppt wird in `_shutdown()`: erst `loop.remove_reader`, dann Verbindung
schließen, dann Consumer-Task abbrechen.

**Reconnect:** Bricht die Listener-Verbindung (`OperationalError`,
`conn.closed`), wird der Reader abgemeldet und mit exponentiellem Backoff samt
Jitter neu verbunden, gefolgt von einem neuen `LISTEN`. Der Verlust wird als
WARNING, die Rückkehr als INFO geloggt — damit im Journal ablesbar ist, wie lang
die Lücke war.

### Die zwei emittierenden Worker-Skripte

`monitoring_worker` und `scheduler_worker` bekommen den Bus im
**Publish-Modus** und den fehlenden `set_event_loop()`-Aufruf. Damit erreichen
Temperatur- und Plattenplatz-Meldungen erstmals überhaupt einen Client.

Der fehlende `set_event_loop()`-Aufruf ist streng genommen ein eigener Mangel,
gehört aber zur selben Ursache — „keine Brücke zwischen den Prozessen" — und
ohne diesen Schritt wäre der Fix nur halb: die Brücke stünde, und die lautesten
Meldungen liefen weiter daran vorbei.

Publish-Modus heißt: kein Listener, kein `add_reader`, keine zusätzliche
Verbindung — diese Prozesse halten keine WebSocket-Verbindungen, es gibt dort
nichts zuzustellen. Die lokale Ersatzzustellung aus dem Abschnitt darüber
entfällt damit ebenfalls (sie träfe auf null Sockets).

`webdav_worker` bleibt unberührt: er initialisiert keinen EventEmitter und
emittiert nichts.

### Aufrufstellen

Nur eine Änderung: in `api/routes/_notification_fanout.py:46` fällt

```python
if not manager.is_user_connected(user_id):
    return
```

weg. Der Worker, der ein „gelesen" verarbeitet, kennt die Tray-Verbindung im
Nachbarprozess nicht und würde sonst abbrechen, **bevor** er publiziert. Das ist
ein zweiter, unabhängiger Grund, warum der Zustandsabgleich zwischen Geräten
heute scheitert. Die `COUNT`-Abfrage für den Ungelesen-Zähler läuft damit
unbedingt; sie hängt an einer Nutzeraktion, das ist bezahlbar.

Alle übrigen Broadcast-Aufrufstellen bleiben unverändert — `service.py`,
`events.py`, `dashboard_panel_bridge.py`, `lifespan.py` und
`routes/notifications.py` rufen weiter dieselben Methoden mit denselben
Argumenten.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Nutzlast > 7500 Byte serialisiert | WARNING mit `msg_type` und Größe, Nachricht verworfen |
| Nutzlast nicht JSON-serialisierbar | WARNING, verworfen |
| `pg_notify` schlägt fehl (DB weg) | WARNING, verworfen — nie eine Ausnahme zum Aufrufer |
| Unbekanntes `kind` / kaputtes JSON auf dem Kanal | WARNING, verworfen |
| Queue voll | ältestes Element heraus, WARNING |
| Einzelner Socket wirft beim Senden | unverändert: Verbindung aufräumen, weiter |

Zum Größendeckel: `pg_notify` begrenzt die Nutzlast auf 8000 Byte, wir wachen bei
7500. Gemessen an den heutigen Nachrichten ist das reichlich —
Notification-Zeilen sind wenige hundert Byte und durch die DB-Spalten begrenzt,
Panel-Nutzlasten sind `StatusPanelData` mit ≤5 Zeilen oder ein `GaugePanelData`.
Garantiert ist es aber nicht, weil `get_dashboard_data()` plugin-definiert ist.
Deshalb wacht der Deckel überhaupt: ein Plugin, dessen Panel ausufert, wird laut
statt still. Für die beiden Bridge-Typen ist das Verwerfen selbstheilend — der
nächste Tick sendet 1–3 s später den vollen Zustand.

Kein Aufrufer bekommt je eine Ausnahme zu sehen. Das ist die heutige Zusage und
sie bleibt: wenn der Broadcast versagt, ist die DB-Zeile längst geschrieben.

## Betrieb

- **Kein Alembic-Schritt, keine neue Abhängigkeit, keine Änderung an
  Unit-Templates.** `ci-deploy.sh` reicht zum Ausrollen. Das ist bewusst so
  gewählt: Unit-Templates erreichen eine installierte Box nicht von selbst
  (#689).
- **Sechs zusätzliche dauerhafte Postgres-Verbindungen** (eine je API-Prozess).
  Gemessen: 28 von 100 belegt, danach 34.
- **Während des Deploys** starten die beiden Units nicht gleichzeitig. In diesem
  Fenster kann ein alter Prozess noch lokal-only publizieren, während ein neuer
  schon am Bus hängt. Effekt: einzelne Frames überqueren die Grenze nicht,
  solange der Neustart läuft. Kein Sonderfall im Code.
- **Ein Kanal je Datenbank.** Zwei BaluHost-Installationen auf derselben DB
  würden sich gegenseitig Frames zustellen. Existiert nicht und ist
  nicht vorgesehen; Dev fährt SQLite und damit `LocalWsBus`.

## Verworfene Wege

**Outbox-Tabelle + `NOTIFY` als leere Türklingel.** Hätte kein Größenlimit,
wäre haltbar und könnte nach einem Reconnect über `id > last_seen` nachholen.
Kostet dafür eine Alembic-Migration, einen Aufbewahrungsjob, ein `SELECT` je
Aufwachen — und bringt die klassische Outbox-Falle mit: Sequenz-Ids werden nicht
zwingend in Commit-Reihenfolge sichtbar, ein Leser mit einer Hochwassermarke
überspringt also gelegentlich eine Zeile, was zusätzlich Dedupe über gesehene
Ids verlangt. Für flüchtigen Live-Zustand, der sich alle 1–3 s erneuert, ist das
zu viel Maschinerie.

**Eigener Single-Worker-Prozess für den Notification-WebSocket** (Variante 2 im
Issue). Löst es nicht: die Emitter laufen weiter in den Primary Workern der
anderen Units, die Brücke bräuchte man trotzdem — nur mit zwei Prozessen statt
sechs. Zusatzaufwand ohne Ersparnis.

**Broadcast über die Datenbank pollen** (Variante 3 im Issue). Latenz und Last
für nichts, wo `LISTEN` schon da ist.

**Unix-Socket-Fanout.** Bräuchte einen Broker-Prozess mit eigenem
Lebenszyklus — und er müsste beide systemd-Units überspannen, was den Broker zu
einem dritten Dienst macht. Postgres ist dieser Broker schon, mit Aufsicht.

**Redis.** Neue Infrastruktur für ein Problem, das die vorhandene löst.

## Verifikation

**Unit-Tests** (`tests/services/test_ws_bus.py`,
`tests/services/test_websocket_manager.py`) gegen `LocalWsBus` und einen
`FakeBus`:

- Umschlag-Rundlauf über JSON, inklusive `user_id=None` und `admins_only`
- Umschlagbau je öffentlicher Methode (die fünf Zeilen der Zuordnungstabelle)
- `deliver_local()` je `kind`: Zielauswahl, `admins_only`, Aufräumen toter Sockets
- Größendeckel: >7500 Byte → verworfen + WARNING
- Nicht serialisierbare Nutzlast → verworfen
- Unbekanntes `kind`, kaputtes JSON → verworfen, kein Absturz des Consumers
- Queue-Überlauf verwirft das älteste Element
- Reconnect: nach simuliertem Verbindungsabriss wird neu verbunden und erneut
  `LISTEN` gesetzt; währenddessen stellt `publish()` lokal zu
- SQLite/Dev: `get_ws_bus()` liefert `LocalWsBus`
- `tests/api/test_notification_fanout.py`: publiziert auch ohne lokale Verbindung

**Echter Postgres-Pfad:** `scripts/debug/verify_ws_bus.py` startet zwei
Prozesse gegen die echte Datenbank, publiziert in einem und bestätigt im anderen
die Zustellung samt Laufzeit. Einmal auf der Produktionsbox gefahren, die
Ausgabe kommt in den PR. CI fährt ausschließlich SQLite, also berührt dort kein
Test den `LISTEN`-Pfad — das ist die bewusst in Kauf genommene Lücke, und das
Skript ist ihr Gegengewicht.

**Nach dem Deploy, am lebenden System:** `/api/schedulers/*/run-now` für einen
Job auslösen, der eine Meldung erzeugt, und prüfen, dass das Tray das Popup
zeigt — bei vier Versuchen viermal, nicht einmal.

## Folgearbeiten (eigene Issues)

1. **Doppel-Primary über zwei systemd-Units.** `PrivateTmp=true` in der
   TCP-Unit, nicht gesetzt in der Local-Unit → zwei Lock-Namensräume, zwei
   Primary Worker, doppelte Hardware-Loops (Fan-Control schreibt PWM aus zwei
   Prozessen). Fix wäre ein gemeinsamer Lock-Pfad unter `/run/baluhost/`.
2. **`MAX_CONNECTIONS_PER_USER` gilt je Prozess** (`websocket_manager.py:17`),
   effektiv 6× — der DoS-Deckel ist weicher als sein Kommentar behauptet.
3. **Pool-Dimensionierung gegen `max_connections`** — rechnerisch 180 gegen 100,
   real unkritisch. Notiz, kein Alarm.
