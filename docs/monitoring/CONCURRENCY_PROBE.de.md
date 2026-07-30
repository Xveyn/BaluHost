# Concurrency-Probe (S1 / #300)

Temporäre Instrumentierung, die misst, wie stark synchrone DB-Arbeit den
Event-Loop blockiert. Die Zahlen begründen die Pool- und Threadpool-Grenzen
in PR2 — ohne sie wären die Grenzen geraten.

## Konfiguration

| Env-Variable | Default | Bedeutung |
|---|---|---|
| `CONCURRENCY_PROBE_ENABLED` | `true` | Probe an/aus |
| `CONCURRENCY_PROBE_INTERVAL_SECONDS` | `60` | Fensterlänge |

## Auslesen

Jeder Worker schreibt pro Fenster eine Zeile auf dem Logger
`baluhost.concurrency`. In Produktion ist das JSON:

```bash
journalctl -u baluhost-backend --since "-24h" -o cat \
  | jq -c 'select(.logger == "baluhost.concurrency")'
```

Alle vom Fenster emittierten Felder (`build_window_payload()` in
`concurrency_probe.py`):

| Feld | Bedeutung |
|---|---|
| `window_seconds` | Tatsächliche Fensterlänge in Sekunden (kann leicht über dem konfigurierten Intervall liegen) |
| `ticks` | Anzahl der 250-ms-Messintervalle in diesem Fenster (bei Standard-Konfiguration ~240) |
| `loop_lag_p50_ms`, `loop_lag_p95_ms`, `loop_lag_max_ms` | **Leitkennzahl.** Wie lange ein Task nicht drankam. Hohe Werte = blockierter Loop |
| `req_started`, `req_completed` | Ankunftsrate = `req_started / window_seconds`. `req_completed` sollte sich `req_started` annähern — eine wachsende Lücke bedeutet unbeantwortete Requests |
| `req_in_flight_now` | Live-Wert zum Zeitpunkt der Log-Zeile (kein Fenster-Aggregat, im Gegensatz zu allen anderen Feldern hier) |
| `req_in_flight_max` | Gleichzeitige Requests im Worker — **untere Schranke**, siehe unten |
| `req_duration_p50_ms`, `req_duration_p95_ms`, `req_duration_max_ms` | Bedienzeit |
| `pool_checked_out_max`, `pool_overflow_max`, `pool_open_max`, `pool_size`, `pool_max_overflow` | DB-Pool-Auslastung und Obergrenze |
| `pool_saturated_ticks` | Ticks, in denen der Pool voll ausgeschöpft war. `0` beweist, dass in diesem Fenster kein Checkout-Timeout möglich war |
| `threadpool_borrowed_max`, `threadpool_waiting_max`, `threadpool_total_tokens` | anyio-Threadpool; `waiting > 0` heißt, sync Arbeit staut sich; `total_tokens` ist die konfigurierte Obergrenze — die Vergleichsbasis für `borrowed_max` |
| `worker_pid` | Unterscheidet die 4 Worker |

## Warum `req_in_flight_max` nicht direkt für die Auslegung taugt

Solange die Handler den Loop blockieren, stauen sich neue Requests **vor** dem
Accept und werden nicht als „in flight" gezählt. Der Peak ist deshalb nach
unten verzerrt und nur als untere Schranke brauchbar.

Unverzerrt sind Ankunftsrate und Bedienzeit. Die Auslegung läuft über
Little's Law:

```
Nebenläufigkeit ≈ (req_started / window_seconds) × (req_duration_p95_ms / 1000)
```

Diese Zahl — nicht der beobachtete Peak — ist die Grundlage für
`DB_POOL_SIZE` / `DB_MAX_OVERFLOW` und die anyio-Token-Zahl in PR2.

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
