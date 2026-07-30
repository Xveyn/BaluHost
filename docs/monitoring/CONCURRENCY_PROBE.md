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

Die interessanten Felder:

| Feld | Bedeutung |
|---|---|
| `loop_lag_p95_ms`, `loop_lag_max_ms` | **Leitkennzahl.** Wie lange ein Task nicht drankam. Hohe Werte = blockierter Loop |
| `req_in_flight_max` | Gleichzeitige Requests im Worker — **untere Schranke**, siehe unten |
| `req_started`, `window_seconds` | Ankunftsrate = `req_started / window_seconds` |
| `req_duration_p95_ms` | Bedienzeit |
| `pool_checked_out_max`, `pool_open_max`, `pool_size`, `pool_max_overflow` | DB-Pool-Auslastung und Obergrenze |
| `pool_saturated_ticks` | Ticks, in denen der Pool voll ausgeschöpft war. `0` beweist, dass in diesem Fenster kein Checkout-Timeout möglich war |
| `threadpool_borrowed_max`, `threadpool_waiting_max` | anyio-Threadpool; `waiting > 0` heißt, sync Arbeit staut sich |
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

## Abbau

Die Probe ist als Diagnose gedacht, nicht als Dauerbetrieb. Nach dem
Nachher-Vergleich in PR2 entscheiden: behalten (dann in die reguläre
Monitoring-Doku überführen) oder entfernen.
