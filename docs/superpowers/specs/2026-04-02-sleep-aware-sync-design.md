# Sleep-Aware Sync Design

**Date:** 2026-04-02
**Status:** Approved
**Scope:** Backend API + Frontend (React Web UI)

## Problem

Admin-set sleep schedules are not respected by sync clients (BaluDesk, BaluApp). When the NAS enters Soft Sleep or True Suspend, automatic sync operations either wake the system (defeating the sleep) or fail silently with connection errors. The admin's power management decisions must dominate over client sync behavior.

## Design Decisions

- **Soft Sleep + automatic sync** → rejected (503), NAS stays asleep
- **Soft Sleep + manual sync** → allowed, auto-wake triggers as before
- **True Suspend** → NAS unreachable, clients use cached schedule to skip sync
- **Sync schedule in sleep window** → rejected at creation time (409)
- **Existing schedules conflicting with later-added sleep window** → not auto-deleted, blocked at runtime by server-side guard

## Components

### 1. Preflight Endpoint

**`GET /api/sync/preflight`** — lightweight endpoint for clients to check sync availability and fetch the sleep schedule.

**Auth:** `get_current_user` (any authenticated user)
**Rate limit:** `sync_operations`
**Auto-wake whitelist:** Yes (must NOT wake the NAS)

**Response schema (`SyncPreflightResponse`):**

```json
{
    "sync_allowed": true,
    "current_sleep_state": "awake",
    "sleep_schedule": {
        "enabled": true,
        "sleep_time": "23:00",
        "wake_time": "06:00",
        "mode": "suspend"
    },
    "next_sleep_at": "2026-04-02T23:00:00Z",
    "next_wake_at": "2026-04-03T06:00:00Z",
    "block_reason": null
}
```

**Fields:**
- `sync_allowed`: `false` when `current_sleep_state != "awake"`
- `sleep_schedule`: `null` if no schedule is active
- `next_sleep_at` / `next_wake_at`: computed from schedule as next occurrence of `sleep_time`/`wake_time` relative to current server time. `null` if schedule is disabled or no schedule exists.
- `block_reason`: `"sleep_active"` | `null`. Set to `"sleep_active"` when `current_sleep_state` is not `awake`.

### 2. Server-Side Guard (FastAPI Dependency)

**New dependency `require_sync_allowed`** — applied to sync endpoints that generate data traffic.

**Mechanism:**
- Reads `X-Sync-Trigger` header from request
  - Values: `auto`, `scheduled`, `manual`
  - Missing header = `manual` (backwards compatibility)
- Checks sleep state via `get_sleep_manager()`

**Decision matrix:**

| Sleep State | Trigger `manual` | Trigger `auto`/`scheduled` |
|---|---|---|
| AWAKE | Allowed | Allowed |
| SOFT_SLEEP | Allowed (auto-wake) | **503** |
| ENTERING_* / WAKING | Allowed | **503** |
| TRUE_SUSPEND | Unreachable | Unreachable |

**503 response body:**

```json
{
    "detail": "Sync blocked: NAS is in sleep mode",
    "sleep_state": "soft_sleep",
    "next_wake_at": "2026-04-03T06:00:00Z",
    "retry_after_seconds": 25200
}
```

**Guarded endpoints:**
- `POST /api/sync/changes`
- `GET /api/sync/state`
- `POST /api/sync/upload/start`, `/chunk`, `/resume`
- `POST /api/sync/report-folders`

**Not guarded (always allowed):**
- `GET /api/sync/preflight`
- `GET /api/sync/status/{device_id}`
- Schedule CRUD (`/schedule/*`)
- Selective sync config

### 3. Sleep Auto-Wake Middleware Update

**File:** `backend/app/middleware/sleep_auto_wake.py`

**Changes:**
1. Add `/api/sync/preflight` to `_WAKE_WHITELIST_PREFIXES`
2. Check `X-Sync-Trigger` header for sync paths: if `auto` or `scheduled`, do NOT trigger auto-wake (let the server-side guard return 503 instead)

**Execution order:** Middleware runs before the route handler. Without this change, automatic syncs would wake the NAS before the guard can reject them.

### 4. Sync Schedule Validation

**Where:**
- `POST /api/sync/schedule/create`
- `PUT /api/sync/schedule/{schedule_id}`

**Logic:**
- Load `SleepConfig` from DB
- If `schedule_enabled = false` → no check, allow everything
- If `schedule_enabled = true` → check if `time_of_day` falls within `[sleep_time, wake_time)`
- Handle overnight windows: e.g., sleep 23:00–06:00 → sync at 02:00 = conflict

**Helper function:**

```python
def is_time_in_sleep_window(sync_time: str, sleep_time: str, wake_time: str) -> bool:
    """Check if sync_time (HH:MM) falls within the sleep window [sleep_time, wake_time)."""
```

**Error response (409 Conflict):**

```json
{
    "detail": "Sync schedule conflicts with sleep window (23:00-06:00). Choose a time outside the sleep window.",
    "sleep_time": "23:00",
    "wake_time": "06:00"
}
```

**No retroactive enforcement:** If an admin adds a sleep window that overlaps existing sync schedules, those schedules are not auto-deleted. The server-side guard (Section 2) blocks them at runtime.

### 5. Frontend Changes

**Scope:** Sync settings area where sync schedules are created/edited.

**Changes:**

1. **Load sleep schedule** — on opening the sync schedule form, call `GET /api/sync/preflight` to get the sleep window (works for all users, not just admins).

2. **Conflict warning** — when the user picks a sync time inside the sleep window:
   - Yellow warning banner below the time picker: *"Dieser Zeitpunkt liegt im Sleep-Fenster (23:00-06:00). Der Sync wird nicht ausgefuehrt."*
   - Submit button disabled
   - Client-side validation using the same `isTimeInSleepWindow` logic

3. **Mark existing schedules** — in the schedule list (`ScheduleList.tsx`): schedules that now fall within a sleep window get a warning icon with tooltip *"Wird blockiert durch Sleep-Schedule"*.

## New Files

- `backend/app/api/deps_sync.py` — `require_sync_allowed` dependency (or add to existing `deps.py`)
- `backend/app/schemas/sync.py` — add `SyncPreflightResponse` schema
- `backend/app/api/routes/sync.py` — add preflight endpoint
- `client/src/lib/sleep-utils.ts` — `isTimeInSleepWindow()` helper

## Modified Files

- `backend/app/middleware/sleep_auto_wake.py` — whitelist + trigger header check
- `backend/app/api/routes/sync.py` — add guard dependency to data endpoints
- `backend/app/api/routes/sync_advanced.py` — add guard dependency to upload/schedule endpoints
- `backend/app/services/sync/scheduler.py` — add sleep window validation
- `client/src/components/sync-settings/ScheduleFormFields.tsx` — conflict warning
- `client/src/components/sync-settings/ScheduleList.tsx` — conflict icons

## Client Integration Guide (BaluDesk + BaluApp)

After backend deployment, both BaluDesk and BaluApp need updates:

1. **Send `X-Sync-Trigger` header** on all sync API calls:
   - `auto` for scheduled/periodic syncs
   - `manual` for user-initiated syncs

2. **Call `GET /api/sync/preflight` periodically** (e.g., every 5 minutes or on app start):
   - Cache `sleep_schedule` locally
   - If `sync_allowed = false`, pause automatic sync
   - Use `next_wake_at` to schedule next retry

3. **Handle 503 responses** on sync endpoints:
   - Parse `retry_after_seconds` from response body
   - Wait and retry after that duration
   - Show user-friendly message: "NAS is sleeping, sync paused until {wake_time}"

4. **Offline schedule awareness:**
   - Cache the last known `sleep_schedule` locally
   - If the NAS is unreachable and the current time falls within the cached sleep window, assume the NAS is sleeping (don't retry aggressively)
   - If the NAS is unreachable outside the sleep window, use normal connection error handling
