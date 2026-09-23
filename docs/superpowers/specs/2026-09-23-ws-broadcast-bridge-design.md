# Prozessübergreifende WebSocket-Brücke — Design

**Datum:** 2026-09-23
**Status:** Entwurf
**Basis:** `main` @ `ab51f7c4`
**Issue:** [#685](https://github.com/Xveyn/BaluHost/issues/685) — „WebSocket-Broadcasts
erreichen nur einen von vier Uvicorn-Workern"
**Umfang:** #685 plus drei beim Nachsehen gefundene Befunde, die mitbehoben
werden (Doppel-Primary, fehlende Gesamtobergrenze für Verbindungen,
Pool-Dimensionierung) — Begründung unter „Die Entscheidungen".
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
- **Eine prozessübergreifende Obergrenze *je Nutzer*.** Die wäre nur mit
  gemeinsamem Zustand zu haben — Tabelle plus Migration plus Aufräumen der
  Zeilen abgestürzter Worker, oder Advisory Locks an der Listener-Verbindung.
  Beides steht in keinem Verhältnis zum Risiko. Stattdessen kommt die Grenze,
  die heute völlig fehlt: eine Gesamtobergrenze je Prozess (siehe „Mitbehoben:
  eine Obergrenze, die wirklich bindet").
- **Ein zweiter Dienst für den Notification-WebSocket.** Siehe „Verworfene Wege".

## Die Entscheidungen

| Frage | Entscheidung |
|---|---|
| Transport | `pg_notify` mit der Nachricht in der Nutzlast |
| Wer hört zu? | Jeder API-Prozess, **nicht** hinter `IS_PRIMARY_WORKER` |
| Wer stellt zu? | Ausschließlich der Listener — publizieren stellt nie selbst zu |
| Wer ist Primary? | Nur die Fernkanal-Unit; der lokale Kanal bewirbt sich nicht |
| Was bindet die Verbindungszahl? | Eine Gesamtobergrenze je Prozess, zusätzlich zur Grenze je Nutzer |
| Wie wird der echte Pfad geprüft? | Fake-Bus im Unit-Test, echtes Postgres über ein Verifikationsskript |

Die drei zunächst als Folgearbeiten notierten Befunde sind eingearbeitet, weil
zwei davon code-only zu beheben sind und der erste mit der Brücke zusammenhängt:
ohne ihn würde die Brücke die doppelten Meldungen des Doppel-Primary erst sichtbar
machen (zwei Popups je Ereignis), wo sie heute halb von der Worker-Isolation
verdeckt sind. Die Brücke allein wäre also eine Verbesserung mit einer neuen
Verschlechterung im Gepäck.

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

## Mitbehoben: ein Primary Worker statt zwei

`_try_become_primary()` (`core/lifespan.py:96`) gibt **False** zurück, sobald
`settings.channel == "local"`. Der lokale Kanal bewirbt sich damit nie um die
Rolle; Eigentümer der Hardware-Schleifen ist immer die Fernkanal-Unit.

Warum so und nicht über den Lock-Pfad: `BALUHOST_CHANNEL=local` steht schon im
`Environment=` der Local-Unit und ist am laufenden System belegt
(`systemctl show baluhost-backend-local -p Environment`). Die Änderung ist damit
**code-only** — kein neuer Lock-Pfad unter `/run/baluhost/`, keine Änderung an
einem Unit-Template und deshalb kein einmaliger Operator-Schritt, der eine
installierte Box sonst nicht erreichen würde (#689). Sie ist außerdem
*deterministisch*: ein gemeinsamer Lock würde die Rolle demjenigen geben, der
zuerst startet — und das ist die socket-aktivierte Local-Unit.

Was dadurch in der Local-Unit aufhört: Fan-Control-Regelschleife,
Power-Manager, GPU-Power, SMART-Collector, mDNS-Ankündigung,
Plugin-Hintergrundtasks, der Reconcile-Takt und die beiden Bridge-Loops. Genau
das ist der Zweck — jedes davon lief bisher doppelt.

**Was dadurch nicht aufhört:** die API-Routen des lokalen Kanals. Die
`IS_PRIMARY_WORKER`-Gates in `fan_control.py` schützen Schreibwege und die
Wiederherstellungslogik, nicht das Lesen; der Kommentar an `fan_control.py:442`
sagt ausdrücklich, dass HTTP-Routen „bei vier Workern meist auf einem Sekundär"
landen und deshalb ohne die Rolle funktionieren müssen. Der Tauri-Companion
merkt von der Umstellung nichts.

**Der Preis, benannt:** Ist die Fernkanal-Unit unten, ist niemand Primary — die
Hardware-Schleifen ruhen, bis sie zurück ist (bei `systemctl restart` gut zehn
Sekunden). Heute übernimmt in diesem Fenster die Local-Unit. Der Tausch ist
gewollt: zehn Sekunden ohne Regelung sind harmlos, zwei Prozesse, die
gleichzeitig PWM schreiben, sind es nicht.

Folge für dieses Vorhaben: die im Issue-Umfeld gefundenen Doppelzeilen (vier in
sieben Tagen) entstehen nicht mehr, und die Brücke verteilt keine Doppel-Popups.

## Mitbehoben: eine Obergrenze, die wirklich bindet

`MAX_CONNECTIONS_PER_USER = 5` (`services/websocket_manager.py:17`) gilt je
Prozess, effektiv also bis zu 30 Verbindungen für einen Nutzer. Das ist nicht
das eigentliche Loch. Das eigentliche Loch ist: **es gibt überhaupt keine
Gesamtobergrenze.** Mit N Konten ist die Zahl offener Sockets je Prozess heute
unbeschränkt, und das ist die Zahl, die Speicher kostet.

Deshalb kommt `MAX_CONNECTIONS_TOTAL = 100` je Prozess hinzu, geprüft in
`connect()` vor der Grenze je Nutzer, mit derselben
`ConnectionLimitExceeded`-Ausnahme und demselben `WS_1008`-Abschluss in
`routes/notifications.py`. Sechs Prozesse × 100 ist eine Größe, die die Maschine
trägt; „unbeschränkt" ist keine.

Der Kommentar an `MAX_CONNECTIONS_PER_USER` wird berichtigt: er behauptet heute
eine Grenze, die er nicht durchsetzt. Künftig steht dort, dass sie je Prozess
gilt, wie viele Prozesse es gibt, und dass die bindende Grenze die Gesamtzahl
ist.

## Mitbehoben: Pool-Dimensionierung

`DB_POOL_SIZE=10` und `DB_MAX_OVERFLOW=20` (`core/database.py:_get_pg_pool_config`)
ergeben je Prozess bis zu 30 Verbindungen. Weder das Template `env.production`
noch die installierte `.env.production` setzen diese Schlüssel — es gelten also
die Code-Defaults, und sie gelten für jeden der sechs API-Prozesse plus die
Worker-Skripte: rechnerisch über 180 gegen `max_connections=100`.

Neue Defaults: **`pool_size 5`, `max_overflow 5`**. Das ergibt im schlimmsten
Fall 10 je Prozess, also 60 über sechs Prozesse, plus die sechs
Listener-Verbindungen und die Worker-Skripte — mit Abstand unter 100.
Gemessener Ist-Zustand: `pool_open_max` liegt bei 2–3 je Prozess
(Concurrency-Log), 28 von 100 Verbindungen belegt. Der Kopfraum bleibt also
groß, und weil die Schlüssel Umgebungsvariablen sind, ist eine Anhebung ohne
Code-Änderung möglich, falls `pool_timeout` doch einmal zuschlägt.

Auch das ist code-only: die Defaults greifen, weil niemand sie überschreibt.

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
  Gemessen: 28 von 100 belegt, danach 34. Die neuen Pool-Defaults senken
  gleichzeitig die theoretische Obergrenze von über 180 auf unter 70, die Summe
  geht also nach unten, nicht nach oben.
- **Alle drei mitbehobenen Punkte sind code-only.** Der Kanalvergleich nutzt ein
  `Environment=`, das in der Local-Unit schon steht; die Pool-Defaults greifen,
  weil `.env.production` sie nicht setzt; die Verbindungsobergrenze ist eine
  Konstante. Kein Unit-Template, kein Operator-Schritt.
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
Issue). Löst es nicht: der Emitter läuft weiter im Primary Worker der
Fernkanal-Unit, die Brücke bräuchte man trotzdem — nur mit zwei Prozessen statt
sechs. Zusatzaufwand ohne Ersparnis.

**Gemeinsamer Lock-Pfad unter `/run/baluhost/` für die Primary-Wahl.** Wäre die
naheliegende Lösung des Doppel-Primary und wurde verworfen, weil sie die Rolle
demjenigen gibt, der zuerst startet — das ist die socket-aktivierte Local-Unit,
also gerade der Prozess, der sie nicht haben soll. Der Kanalvergleich ist
deterministisch und braucht keine Änderung an einem Unit-Template.

**Präsenztabelle für die Verbindungsobergrenze.** Bräuchte eine Migration und
ein Aufräumen der Zeilen abgestürzter Worker — Zustand, der nur dann korrekt
ist, wenn ihn jemand pflegt. Siehe „Folgearbeiten".

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

**Für die drei mitbehobenen Punkte:**

- `tests/core/test_primary_worker_channel.py`: `_try_become_primary()` gibt bei
  `settings.channel == "local"` False zurück, **ohne** die Lock-Datei zu
  berühren; bei `remote` bleibt das heutige Verhalten samt
  `BALUHOST_PRIMARY_WORKER=0`-Override; zwei Prozesse mit `remote` ergeben
  weiterhin genau einen Gewinner
- `tests/services/test_websocket_manager.py`: die 101. Verbindung eines Prozesses
  wird mit `ConnectionLimitExceeded` abgewiesen, auch wenn sie von einem Nutzer
  ohne eigene Verbindungen kommt; die Grenze je Nutzer bleibt bei 5 wirksam
- `tests/core/test_database_pool_config.py`: Defaults sind 5/5 und die
  Umgebungsvariablen überschreiben sie weiterhin

**Echter Postgres-Pfad:** `scripts/debug/verify_ws_bus.py` startet zwei
Prozesse gegen die echte Datenbank, publiziert in einem und bestätigt im anderen
die Zustellung samt Laufzeit. Einmal auf der Produktionsbox gefahren, die
Ausgabe kommt in den PR. CI fährt ausschließlich SQLite, also berührt dort kein
Test den `LISTEN`-Pfad — das ist die bewusst in Kauf genommene Lücke, und das
Skript ist ihr Gegengewicht.

**Nach dem Deploy, am lebenden System:**

1. `/api/schedulers/*/run-now` für einen Job auslösen, der eine Meldung erzeugt,
   und prüfen, dass das Tray das Popup zeigt — bei vier Versuchen viermal, nicht
   einmal.
2. `journalctl -u baluhost-backend-local` zeigt für alle Worker
   `Primary worker: False`, `journalctl -u baluhost-backend` genau einmal `True`.
3. Die Verbindungszahl gegen Postgres bleibt nach einer Stunde Betrieb unter 50
   (`select count(*) from pg_stat_activity`).

## Folgearbeiten

**Prozessübergreifende Obergrenze je Nutzer.** Bleibt bewusst ungebaut, siehe
„Nicht-Ziele". Wird sie je gebraucht, ist der Weg mit dem besten Verhältnis
Advisory Locks an der Listener-Verbindung: session-gebunden, also gibt ein
abgestürzter Worker seine Slots von selbst frei — im Gegensatz zu einer
Präsenztabelle, deren Zeilen dann liegen bleiben.
