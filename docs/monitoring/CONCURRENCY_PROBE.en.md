# Concurrency Probe (S1 / #300)

Temporary instrumentation that measures how badly synchronous DB work blocks
the event loop. The numbers justify the pool and threadpool limits in PR2 —
without them the limits would be a guess.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `CONCURRENCY_PROBE_ENABLED` | `true` | Probe on/off |
| `CONCURRENCY_PROBE_INTERVAL_SECONDS` | `60` | Window length |

## Reading it

Every worker writes one line per window on the `baluhost.concurrency`
logger. In production that line is JSON:

```bash
journalctl -u baluhost-backend --since "-24h" -o cat \
  | jq -c 'select(.logger == "baluhost.concurrency")'
```

All fields emitted per window (`build_window_payload()` in
`concurrency_probe.py`):

| Field | Meaning |
|---|---|
| `window_seconds` | Actual window length in seconds (can run slightly over the configured interval) |
| `ticks` | Number of 250ms sampling intervals in this window (~240 at the default configuration) |
| `loop_lag_p50_ms`, `loop_lag_p95_ms`, `loop_lag_max_ms` | **The headline metric.** How long a task waited before it got scheduled. High values = a blocked loop |
| `req_started`, `req_completed` | Arrival rate = `req_started / window_seconds`. `req_completed` should track `req_started` closely — a growing gap means requests are going unanswered |
| `req_in_flight_now` | Live value at the moment the line was logged (not a window aggregate, unlike every other field here) |
| `req_in_flight_max` | Concurrent requests in the worker — a **lower bound**, see below |
| `req_duration_p50_ms`, `req_duration_p95_ms`, `req_duration_max_ms` | Service time |
| `pool_checked_out_max`, `pool_overflow_max`, `pool_open_max`, `pool_size`, `pool_max_overflow` | DB pool utilization and its ceiling |
| `pool_saturated_ticks` | Ticks in which the pool was fully exhausted. `0` proves that no checkout could have timed out in this window |
| `threadpool_borrowed_max`, `threadpool_waiting_max`, `threadpool_total_tokens` | The anyio threadpool; `waiting > 0` means sync work is queueing up; `total_tokens` is the configured ceiling — the baseline `borrowed_max` is measured against |
| `worker_pid` | Distinguishes the 4 workers |

## Why `req_in_flight_max` doesn't directly inform sizing

As long as handlers block the loop, new requests queue up **before** accept
and are never counted as "in flight." The observed peak is therefore biased
downward and only useful as a lower bound.

Arrival rate and service time are unbiased. Sizing runs through Little's Law:

```
Concurrency ≈ (req_started / window_seconds) × (req_duration_p95_ms / 1000)
```

This number — not the observed peak — is the basis for `DB_POOL_SIZE` /
`DB_MAX_OVERFLOW` and the anyio token count in PR2.

## Capacity limit that must hold

```
4 workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW) + sidecar demand < max_connections
```

Currently: 4 × (10 + 20) = 120 possible connections against an untuned
PostgreSQL `max_connections` of 100. Three other systemd units (monitoring,
scheduler, webdav) have their own pools.

The 4 workers come from `baluhost-backend.service` (`--workers 4`). The
`baluhost-backend-local.service` template (`--workers 2`, local Unix-socket
channel) already exists but is not part of the current automated deploy
(`deploy/install/modules/10-systemd-services.sh` only installs and enables
`baluhost-backend`, `baluhost-scheduler`, `baluhost-webdav`,
`baluhost-monitoring`) — if it's ever wired in, this arithmetic needs
revisiting.

## Teardown

The probe is meant as a diagnostic, not permanent operation. Decide after
the before/after comparison in PR2: keep it (then fold it into the regular
monitoring docs) or remove it.
