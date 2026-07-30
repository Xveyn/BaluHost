# Concurrency Probe (S1 / #300)

Temporary instrumentation that measures how badly synchronous DB work blocks
the event loop. The numbers justify the pool and threadpool limits in PR2 —
without them the limits would be a guess.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `CONCURRENCY_PROBE_ENABLED` | `true` | Probe on/off — switches off **both** halves: the reporting task *and* the in-flight middleware on the request hot path |
| `CONCURRENCY_PROBE_INTERVAL_SECONDS` | `60` | Window length. Must be `> 0` (rejected at startup otherwise) |

Both variables are listed in `backend/.env.example`. Changing either requires
a restart of `baluhost-backend`.

## Reading it

Every worker writes one line per window on the `baluhost.concurrency`
logger. In production that line is JSON:

```bash
journalctl -u baluhost-backend --since "-24h" -o cat \
  | jq -c 'select(.logger == "baluhost.concurrency")'
```

> **Local measurements need `LOG_FORMAT=json`.** The dev default is
> `LOG_FORMAT=text`, and the text formatter renders only the interpolated
> message — every `extra` field is dropped. You would see three numbers out of
> twenty and silently lose the rest. Production is unaffected
> (`env.production` sets `LOG_FORMAT=json`).

All fields emitted per window (`build_window_payload()` in
`concurrency_probe.py`):

| Field | Meaning |
|---|---|
| `window_seconds` | Actual window length in seconds (can run slightly over the configured interval) |
| `ticks` | Number of 250ms sampling intervals in this window (~240 at the default configuration) |
| `loop_lag_p50_ms`, `loop_lag_p95_ms`, `loop_lag_max_ms` | **The headline metric.** How long a task waited before it got scheduled. High values = a blocked loop. Has a non-zero floor, see below |
| `req_started`, `req_completed` | Arrival rate = `req_started / window_seconds`. `req_completed` should track `req_started` closely — a growing gap means requests are going unanswered |
| `req_in_flight_now` | Live value at the moment the line was logged (not a window aggregate, unlike every other field here) |
| `req_in_flight_max` | Concurrent requests in the worker — a **lower bound**, see below. Spans the whole request, streaming phase included |
| `req_duration_mean_ms` | **Mean service time over all requests completed in the window** — the input to the sizing formula below. Not restricted to the bounded quantile buffer |
| `req_duration_p50_ms`, `req_duration_p95_ms`, `req_duration_max_ms` | Service-time distribution over the last ≤5000 requests of the window |
| `pool_checkouts` | Connection checkouts in this window — the arrival-rate half of the pool picture. Counted by an engine-level SQLAlchemy listener, so it is complete |
| `pool_in_use_max` | High-water mark of simultaneously checked-out connections. Same accounting, therefore **exact** — not a sample. Overflow use = `max(0, pool_in_use_max - pool_size)` |
| `pool_saturation_events` | Checkouts that took the last free connection (`in_use` reached `pool_size + pool_max_overflow`). Only from that state can the *next* checkout run into `pool_timeout`. `null` when the pool exposes no ceiling — then nothing is claimed |
| `pool_open_max` | Highest observed number of open connections (in use **plus** idle). Point-sampled, see the caveats below |
| `pool_size`, `pool_max_overflow` | Static pool configuration |
| `threadpool_borrowed_max`, `threadpool_waiting_max`, `threadpool_total_tokens` | The anyio threadpool; `waiting > 0` means sync work is queueing up; `total_tokens` is the configured ceiling — the baseline `borrowed_max` is measured against |
| `worker_pid` | Distinguishes the 4 workers |

## What the durations do and do not include

`req_duration_*` is measured from the start of the outermost middleware to the
`http.response.start` ASGI message — status line and headers ready. It
**excludes** everything after that: body transfer for uploads and downloads
(up to the 10 GB limit) and the entire lifetime of a streaming response.

That exclusion is the point. `/api/admin/backend-logs/stream` is an SSE
endpoint over a `while True` loop; an admin with the Logs tab open holds it for
the whole session. Measured to the end of the ASGI call it would contribute a
single sample of several hundred thousand milliseconds — and in a quiet
60-second window on a home NAS (20-40 requests) that one sample *is* the p95.
Sizing a connection pool from it would overshoot by orders of magnitude.

If a request never produces a response at all (the application raised before
the first message), the total elapsed time is recorded instead, so the sample
is not lost.

`req_in_flight_*` deliberately keeps spanning the **whole** call: a streaming
request genuinely is in flight for its entire duration.

## Why `req_in_flight_max` doesn't directly inform sizing

As long as handlers block the loop, new requests queue up **before** accept
and are never counted as "in flight." The observed peak is therefore biased
downward and only useful as a lower bound.

Arrival rate and service time are unbiased. Sizing runs through Little's Law,
which is defined on the **mean** service time — not on a quantile:

```
Concurrency ≈ (req_started / window_seconds) × (req_duration_mean_ms / 1000)
```

This number — not the observed peak — is the basis for `DB_POOL_SIZE` /
`DB_MAX_OVERFLOW` and the anyio token count in PR2. Use
`req_duration_p95_ms` as a separate tail check (does a single slow endpoint
dominate?), never as the input to the formula.

Cross-check the result against `pool_in_use_max` and `pool_checkouts`: those
two come from exact accounting and describe the demand the pool actually saw.

## Caveats you have to read before quoting a number

- **`pool_checkouts`, `pool_in_use_max` and `pool_saturation_events` are
  event-accounted, not sampled.** Two SQLAlchemy engine-level listeners
  (`checkout` / `checkin`) maintain the counters. They run on whatever thread
  performs the checkout, so they record a checkout even while the event loop is
  fully blocked — which is exactly when a non-awaiting `async def` handler
  holds a connection, and exactly when a probe task on the loop could never be
  scheduled to observe it. The listeners cannot raise into the checkout path.
- **`pool_open_max` is point-sampled every 250 ms** and is therefore only a
  lower bound in the other direction: anything shorter than a tick, or anything
  happening while the loop is blocked, is invisible. On top of that it is the
  sum of two non-atomic reads (`checkedout()` + `checkedin()`), so a connection
  returned between the two reads is counted twice — a small systematic *upward*
  bias, opposite in sign to the sampling bias. Treat it as an order of
  magnitude, not as a measurement.
- **`pool_saturation_events: 0` does not prove there were no timeouts.** It
  says that no checkout observed by this worker reached the ceiling. Each of
  the 4 workers has its own pool and its own probe, and the sidecar units
  (monitoring, scheduler, webdav) have pools of their own that this counter
  never sees.
- **The loop lag has a floor above zero.** It is measured as the overshoot of a
  250 ms `asyncio.sleep`, so it inherits timer granularity: on Windows that is
  ~15 ms (the 13.37 ms p95 in the dev verification of this branch is that
  floor, not blocking), on Linux ~1 ms plus the time other already-runnable
  tasks take. Read the PR2 before/after comparison against *this* baseline, not
  against an implied zero.
- **`baluhost_database_connections`** (Prometheus, `/api/metrics`) is not a
  fleet-wide number: it reports checked-out connections in whichever of the 4
  workers happened to serve that scrape, at scrape time, including the
  connection the scrape itself holds. Consecutive scrapes bounce between
  processes.

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
