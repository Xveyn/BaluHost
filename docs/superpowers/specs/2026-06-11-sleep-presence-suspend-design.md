# Presence-Aware Suspend — Design

**Date:** 2026-06-11
**Issue:** #214 — feat(sleep): presence-aware suspend — don't suspend while a user is active in the web/mobile app
**Branch:** `feat/sleep-presence-suspend-214` (created from `origin/main` eee18852, 2026-06-11)

## Problem

The sleep/idle subsystem has no notion of an actively-present user. A logged-in user
viewing the UI generates little HTTP traffic, falls below the idle thresholds, and the
system soft-sleeps and then escalates to true suspend — making the server unreachable
while the user is sitting in front of it. Additionally, on the production host (KDE
desktop) PowerDevil or logind `IdleAction` can suspend the box independently of
BaluHost's own idle heuristic; the existing logind block-sleep inhibitor only covers
core-uptime windows and the always-awake override.

## Decisions (settled during brainstorming)

1. **Guard scope:** Presence blocks the two automatic true-suspend paths — auto-escalation
   (`_escalation_monitor`) and scheduled suspend (`_schedule_check_loop`,
   `schedule_mode == "suspend"`). Manual suspend is never blocked. Soft sleep (entry and
   scheduled soft sleep) is never blocked — it wakes quickly and keeps the box reachable.
2. **Modes:** Both modes ship in v1, default `active`:
   - `active` (active interaction): client sends heartbeats only while the tab/app is
     focused/visible; presence expires after a configurable timeout. A forgotten
     background tab does not keep the server awake.
   - `session` (any open session): client sends heartbeats while the tab is open,
     regardless of visibility. Power-user option; a forgotten tab blocks suspend.
   The mode difference is implemented **purely client-side** — the backend tracker,
   timeout, and queries are identical for both modes.
3. **Client scope:** Backend + web frontend in this repo. BaluApp (Android) gets a
   follow-up issue in its own repo; the heartbeat API will already exist. No
   mobile-`last_seen` bridge.
4. **OS inhibitor:** Active presence also holds the logind block-sleep inhibitor
   (third hold condition in `_reconcile_sleep_inhibitor`), so OS-driven suspends
   (PowerDevil, logind idle, manual `systemctl suspend`) are blocked too. The block
   lock only prevents kernel suspend, so soft sleep is unaffected.
5. **Multi-worker state:** DB table, following the `power_demands` precedent from the
   power-manager multi-worker fix (any worker writes, primary reads). Heartbeats land
   on any of the 4 Uvicorn workers; the sleep loops run only on the primary worker
   (`start_sleep_manager(monitoring=...)`).

## Architecture

```
Web client (per tab)                     Backend (any worker)         Backend (primary worker)
┌─────────────────────┐  POST /api/      ┌──────────────────┐  DB    ┌─────────────────────────┐
│ usePresenceHeartbeat │ sleep/presence  │ presence router   │ ────▶ │ SleepManagerService     │
│  active: visible only│ ───────────────▶│  → record_        │ upsert│  _escalation_monitor    │
│  session: while open │ ◀─────────────── │    heartbeat()    │       │  _schedule_check_loop   │
└─────────────────────┘  mode+interval   └──────────────────┘       │  enter_true_suspend     │
                                                                     │  _reconcile_sleep_      │
                              presence_sessions table  ◀──── reads ──│    inhibitor            │
                                                                     └─────────────────────────┘
```

## Components

### 1. Data model (`backend/app/models/sleep.py`)

New table `presence_sessions`:

| Column | Type | Notes |
|---|---|---|
| `client_id` | String(64), PK | client-generated UUID per tab/device |
| `user_id` | Integer, FK `users.id`, indexed | |
| `client_type` | String(20) | `web` \| `mobile` \| `desktop` |
| `last_heartbeat_at` | DateTime(timezone=True), indexed | |
| `created_at` | DateTime(timezone=True), server_default now | |

New columns on `sleep_config` (singleton row id=1):

| Column | Type | Default |
|---|---|---|
| `presence_enabled` | Boolean | `True` |
| `presence_mode` | String(20) | `"active"` (`active` \| `session`) |
| `presence_timeout_minutes` | Integer | `3` |

Alembic migration must chain onto the real `alembic heads` (multi-head pitfall, PR #123).

### 2. Presence tracker (`backend/app/services/power/presence.py`)

Module-level functions, fresh `SessionLocal()` per call (established service pattern):

- `record_heartbeat(user_id, client_id, client_type) -> None` — upsert by `client_id`
- `is_anyone_present(timeout_minutes) -> bool` — `EXISTS(last_heartbeat_at > now - timeout)`
- `get_present_sessions(timeout_minutes) -> list[...]` — for the status block
- `cleanup_expired() -> int` — delete rows older than 24 h; called from the primary's
  `_schedule_check_loop` tick

### 3. Heartbeat endpoint (`backend/app/api/routes/sleep.py`)

`POST /api/sleep/presence`

- `Depends(deps.get_current_user)`, rate-limited via `@limiter.limit(get_limit(...))`
- Pydantic request: `{client_id: str, client_type: "web"|"mobile"|"desktop"}`
- Response: `{present: true, mode, heartbeat_interval_seconds, timeout_minutes}` —
  clients self-configure from the response; no separate config read needed.

Two mandatory exclusions so the heartbeat does not sabotage the sleep system:

1. **Auto-wake whitelist:** the heartbeat path must NOT wake the system from soft sleep
   (`middleware/sleep_auto_wake.py` already has a whitelist mechanism, used by the sync
   preflight endpoint).
2. **HTTP-RPM exclusion:** heartbeat requests must NOT count toward
   `http_requests_per_minute` (idle metric), otherwise presence would indirectly block
   soft sleep, which stays allowed by design.

### 4. Sleep integration (`backend/app/services/power/sleep.py`)

New helper `SleepManagerService._is_user_present(config) -> bool`:
returns `False` when `presence_enabled` is off; otherwise queries the tracker with
`config.presence_timeout_minutes`. On DB error: log warning and return `False`
(fail toward energy saving — a DB outage must not permanently block suspend; the
inhibitor re-converges on the next successful tick).

Guard points (presence is the third suppressor next to always-awake and core-uptime):

| Site | Behavior |
|---|---|
| `_escalation_monitor` | third skip — escalation deferred, soft sleep persists |
| `_schedule_check_loop` | only the `schedule_mode == "suspend"` path is suppressed (logged like the core-uptime suppression); scheduled soft sleep proceeds |
| `enter_true_suspend` | central guard for all **non-MANUAL** triggers (defense in depth, same pattern as the existing inhibitor-held check). MANUAL always proceeds |
| `_reconcile_sleep_inhibitor` | hold condition becomes `core_active or aa_active or presence_active`; reconciled every 60 s tick. Manual suspend releases the lock the same way it does today for a core-uptime hold (exact mechanism verified during plan writing) |
| `_idle_detection_loop` | **untouched** — presence does not affect the path into soft sleep |

### 5. Status visibility

Extend `SleepStatusResponse` with:

```
presence: {
  enabled: bool,
  mode: "active" | "session",
  anyone_present: bool,
  active_session_count: int,
  suppressing_suspend: bool,
}
```

The Sleep page shows presence as a suppressor badge analogous to core-uptime
(e.g. "Suspend blockiert: 1 aktive Sitzung").

### 6. Web heartbeat hook (`client/src/hooks/usePresenceHeartbeat.ts`)

Mounted once in the authenticated layout:

- Generates `client_id` (UUID) once per tab, stored in `sessionStorage`
- `active` mode: heartbeat every 45 s only while `document.visibilityState === 'visible'`;
  on `visibilitychange` → visible, send immediately
- `session` mode: heartbeat on the interval regardless of visibility while the tab is
  open and the user is logged in
- Mode and interval come from the heartbeat response (self-configuring)
- Errors are swallowed silently (best-effort; must never disturb the UI)
- No heartbeat when logged out; logout stops the timer

### 7. Config UI (Sleep page)

New card "Anwesenheitserkennung": master toggle (`presence_enabled`), mode selector
(active interaction / open session, with trade-off explanation), timeout in minutes.
i18n strings in de + en namespaces.

## Defaults

| Setting | Default | Rationale |
|---|---|---|
| `presence_enabled` | `true` | protects against the worst failure mode; costs nothing when no sessions exist |
| `presence_mode` | `active` | energy savings stay intact; forgotten tabs don't block suspend |
| `presence_timeout_minutes` | `3` | ≈ 4 missed beats at 45 s interval |
| heartbeat interval | 45 s | served to clients via the heartbeat response |

## Error handling & edge cases

- **Tracker DB error in sleep loop:** return `False` (no block), log warning — see §4.
- **Restart:** old rows may still be fresh after a backend restart; harmless, at most
  one timeout window of suspend delay. Timestamps are UTC.
- **Multiple users:** `EXISTS` query — any present user blocks suspend.
- **Dev mode:** identical behavior on SQLite; no special path.
- **Rate limiting:** heartbeat endpoint gets its own rate-limit key sized for
  1 request / 45 s / client with headroom.

## Testing

- **Service unit tests:** upsert behavior, expiry boundaries, `is_anyone_present`
  with/without fresh rows, cleanup.
- **Route tests:** auth required, validation, response shape; heartbeat does not wake
  from soft sleep (whitelist); heartbeat excluded from HTTP-RPM.
- **Sleep integration tests** (style of `test_sleep_core_uptime_integration.py`):
  escalation skipped while present; scheduled suspend suppressed, scheduled soft sleep
  not; `enter_true_suspend` blocks non-MANUAL while present, MANUAL proceeds;
  inhibitor reconcile holds on presence and releases after expiry;
  `presence_enabled=False` disables everything.
- **Frontend (Vitest):** hook sends only while visible (`active`), always (`session`),
  stops on logout. Run the suite locally before the PR (CI `frontend-build` runs
  `npx vitest run`).

## Out of scope / follow-ups

- **BaluApp (Android):** follow-up issue in the BaluApp repo — foreground heartbeat
  against `POST /api/sleep/presence`.
- **BaluDesk:** optional later.
- No change to soft-sleep entry behavior, idle thresholds, or core-uptime semantics.
