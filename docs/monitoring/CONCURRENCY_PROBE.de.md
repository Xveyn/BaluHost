# Concurrency-Probe (S1 / #300)

Temporäre Instrumentierung, die misst, wie stark synchrone DB-Arbeit den
Event-Loop blockiert. Die Zahlen begründen die Pool- und Threadpool-Grenzen
in PR2 — ohne sie wären die Grenzen geraten.

## Konfiguration

| Env-Variable | Default | Bedeutung |
|---|---|---|
| `CONCURRENCY_PROBE_ENABLED` | `true` | Probe an/aus — schaltet **beide** Hälften ab: den Reporting-Task *und* die In-Flight-Middleware auf dem heißen Request-Pfad |
| `CONCURRENCY_PROBE_INTERVAL_SECONDS` | `60` | Fensterlänge. Muss `> 0` sein (sonst Abbruch beim Start) |

Beide Variablen stehen in `backend/.env.example`. Eine Änderung erfordert
einen Neustart von `baluhost-backend`.

## Auslesen

Jeder Worker schreibt pro Fenster eine Zeile auf dem Logger
`baluhost.concurrency`. In Produktion ist das JSON:

```bash
journalctl -u baluhost-backend --since "-24h" -o cat \
  | jq -c 'select(.logger == "baluhost.concurrency")'
```

> **Lokal messen geht nur mit `LOG_FORMAT=json`.** Der Dev-Default ist
> `LOG_FORMAT=text`, und der Text-Formatter gibt ausschließlich die
> interpolierte Nachricht aus — sämtliche `extra`-Felder fallen weg. Man sähe
> drei von zwanzig Zahlen und verlöre den Rest unbemerkt. Produktion ist nicht
> betroffen (`env.production` setzt `LOG_FORMAT=json`).

Alle vom Fenster emittierten Felder (`build_window_payload()` in
`concurrency_probe.py`):

| Feld | Bedeutung |
|---|---|
| `window_seconds` | Tatsächliche Fensterlänge in Sekunden (kann leicht über dem konfigurierten Intervall liegen) |
| `ticks` | Anzahl der 250-ms-Messintervalle in diesem Fenster (bei Standard-Konfiguration ~240) |
| `loop_lag_p50_ms`, `loop_lag_p95_ms`, `loop_lag_max_ms` | **Leitkennzahl.** Wie lange ein Task nicht drankam. Hohe Werte = blockierter Loop. Hat einen Boden über null, siehe unten |
| `req_started`, `req_completed` | Ankunftsrate = `req_started / window_seconds`. `req_completed` sollte sich `req_started` annähern — eine wachsende Lücke bedeutet unbeantwortete Requests |
| `req_in_flight_now` | Live-Wert zum Zeitpunkt der Log-Zeile (kein Fenster-Aggregat, im Gegensatz zu allen anderen Feldern hier) |
| `req_in_flight_max` | Gleichzeitige Requests im Worker — **untere Schranke**, siehe unten. Umfasst den ganzen Request, Streaming-Phase eingeschlossen |
| `req_duration_mean_ms` | **Mittlere Bedienzeit über alle im Fenster abgeschlossenen Requests** — der Eingabewert der Auslegungsformel unten. Nicht auf den gedeckelten Quantil-Puffer beschränkt |
| `req_duration_p50_ms`, `req_duration_p95_ms`, `req_duration_max_ms` | Verteilung der Bedienzeit über die letzten ≤5000 Requests des Fensters |
| `pool_checkouts` | Connection-Checkouts in diesem Fenster — die Ankunftsraten-Hälfte des Pool-Bildes. Von einem Engine-Listener gezählt und damit vollständig |
| `pool_in_use_max` | High-Water-Mark gleichzeitig entnommener Verbindungen. Gleiche Buchführung, also **exakt** — kein Sample. Overflow-Nutzung = `max(0, pool_in_use_max - pool_size)` |
| `pool_saturation_events` | Checkouts, die die letzte freie Verbindung genommen haben (`in_use` erreichte `pool_size + pool_max_overflow`). Nur aus diesem Zustand heraus kann der *nächste* Checkout in `pool_timeout` laufen. `null`, wenn der Pool keine Obergrenze kennt — dann wird nichts behauptet |
| `pool_open_max` | Höchster beobachteter Stand offener Verbindungen (belegt **plus** leerlaufend). Punktuell gesampelt, siehe Vorbehalte unten |
| `pool_size`, `pool_max_overflow` | Statische Pool-Konfiguration |
| `threadpool_borrowed_max`, `threadpool_waiting_max`, `threadpool_total_tokens` | anyio-Threadpool; `waiting > 0` heißt, sync Arbeit staut sich; `total_tokens` ist die konfigurierte Obergrenze — die Vergleichsbasis für `borrowed_max` |
| `worker_pid` | Unterscheidet die 4 Worker |

## Was die Dauern enthalten — und was nicht

`req_duration_*` wird vom Eintritt in die äußerste Middleware bis zur
ASGI-Nachricht `http.response.start` gemessen — Statuszeile und Header stehen.
**Nicht** enthalten ist alles danach: die Body-Übertragung bei Up- und
Downloads (bis zur 10-GB-Grenze) und die gesamte Lebensdauer einer
Streaming-Response.

Genau darum geht es. `/api/admin/backend-logs/stream` ist ein SSE-Endpoint über
eine `while True`-Schleife; ein Admin mit offenem Logs-Tab hält ihn die ganze
Sitzung. Bis zum Ende des ASGI-Aufrufs gemessen, lieferte er einen einzelnen
Messwert von mehreren hunderttausend Millisekunden — und in einem ruhigen
60-Sekunden-Fenster auf einem Heim-NAS (20-40 Requests) **ist** dieser eine
Wert das p95. Ein daraus ausgelegter Connection-Pool läge um Größenordnungen
daneben.

Kommt es gar nicht zu einer Response (die Anwendung wirft vor der ersten
Nachricht), wird ersatzweise die Gesamtdauer erfasst — die Messung geht nicht
verloren.

`req_in_flight_*` umfasst dagegen bewusst weiterhin den **ganzen** Aufruf: ein
laufender Stream ist tatsächlich die ganze Zeit in flight.

## Warum `req_in_flight_max` nicht direkt für die Auslegung taugt

Solange die Handler den Loop blockieren, stauen sich neue Requests **vor** dem
Accept und werden nicht als „in flight" gezählt. Der Peak ist deshalb nach
unten verzerrt und nur als untere Schranke brauchbar.

Unverzerrt sind Ankunftsrate und Bedienzeit. Die Auslegung läuft über
Little's Law — und das ist auf der **mittleren** Bedienzeit definiert, nicht
auf einem Quantil:

```
Nebenläufigkeit ≈ (req_started / window_seconds) × (req_duration_mean_ms / 1000)
```

Diese Zahl — nicht der beobachtete Peak — ist die Grundlage für
`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` und die anyio-Token-Zahl in PR2.
`req_duration_p95_ms` dient als separate Ausreißer-Prüfung (dominiert ein
einzelner langsamer Endpoint?), nie als Eingabe der Formel.

Zur Gegenprobe `pool_in_use_max` und `pool_checkouts` heranziehen: beide
stammen aus exakter Buchführung und beschreiben die Nachfrage, die der Pool
tatsächlich gesehen hat.

## Vorbehalte, die man vor dem Zitieren einer Zahl gelesen haben muss

- **`pool_checkouts`, `pool_in_use_max` und `pool_saturation_events` sind
  event-gebucht, nicht gesampelt.** Zwei SQLAlchemy-Listener auf Engine-Ebene
  (`checkout` / `checkin`) führen die Zähler. Sie laufen in dem Thread, der den
  Checkout ausführt, und erfassen ihn deshalb auch bei vollständig blockiertem
  Event-Loop — also genau dann, wenn ein nicht-awaitender `async def` Handler
  eine Verbindung hält und ein Probe-Task auf dem Loop gar nicht drankäme, um
  es zu sehen. Die Listener können nicht in den Checkout-Pfad hinein werfen.
- **`pool_open_max` wird alle 250 ms punktuell gesampelt** und ist damit in die
  andere Richtung nur eine untere Schranke: Was kürzer als ein Tick ist oder
  während einer Loop-Blockade passiert, bleibt unsichtbar. Zusätzlich ist der
  Wert die Summe zweier nicht-atomarer Lesevorgänge (`checkedout()` +
  `checkedin()`) — eine dazwischen zurückgegebene Verbindung zählt doppelt, ein
  kleiner systematischer *Aufwärts*-Bias, dem Sampling-Bias entgegengesetzt.
  Als Größenordnung lesen, nicht als Messwert.
- **`pool_saturation_events: 0` beweist nicht, dass es keine Timeouts gab.** Es
  besagt, dass kein von diesem Worker gesehener Checkout die Obergrenze
  erreicht hat. Jeder der 4 Worker hat einen eigenen Pool und eine eigene
  Probe, und die Sidecar-Units (monitoring, scheduler, webdav) haben eigene
  Pools, die dieser Zähler nie sieht.
- **Der Loop-Lag hat einen Boden über null.** Gemessen wird die Überschreitung
  eines 250-ms-`asyncio.sleep`, der Wert erbt also die Timer-Granularität: unter
  Windows ~15 ms (die 13,37 ms p95 aus der Dev-Verifikation dieses Branches
  sind dieser Boden, keine Blockade), unter Linux ~1 ms plus die Laufzeit
  anderer bereits lauffähiger Tasks. Den Vorher-/Nachher-Vergleich in PR2 gegen
  *diese* Basis lesen, nicht gegen eine implizite Null.
- **`baluhost_database_connections`** (Prometheus, `/api/metrics`) ist keine
  flottenweite Zahl: gemeldet werden die entnommenen Verbindungen desjenigen
  der 4 Worker, der den Scrape bedient hat, zum Zeitpunkt des Scrapes,
  einschließlich der Verbindung, die der Scrape selbst hält. Aufeinander
  folgende Scrapes springen zwischen Prozessen.

## Kapazitätsgrenze, die eingehalten werden muss

```
4 Worker × (DB_POOL_SIZE + DB_MAX_OVERFLOW) + Sidecar-Bedarf < max_connections
```

Aktuell: 4 × (10 + 20) = 120 mögliche Verbindungen gegen ein ungetuntes
PostgreSQL-`max_connections` von 100. Drei weitere systemd-Units
(monitoring, scheduler, webdav) haben eigene Pools.

Die 4 Worker stammen aus `baluhost-backend.service` (`--workers 4`). Das
Template `baluhost-backend-local.service` (`--workers 2`, lokaler
Unix-Socket-Kanal) existiert bereits, ist aber nicht Teil des aktuellen
automatisierten Deploys (`deploy/install/modules/10-systemd-services.sh`
installiert und aktiviert nur `baluhost-backend`, `baluhost-scheduler`,
`baluhost-webdav`, `baluhost-monitoring`) — sollte es künftig eingebunden
werden, muss die Rechnung oben neu bewertet werden.

## Abbau

Die Probe ist als Diagnose gedacht, nicht als Dauerbetrieb. Nach dem
Nachher-Vergleich in PR2 entscheiden: behalten (dann in die reguläre
Monitoring-Doku überführen) oder entfernen.
