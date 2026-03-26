# Uptime Sleep-State Tracking

**Date:** 2026-03-26
**Status:** Approved

## Problem

The uptime monitoring page shows 100% green bars even when the NAS was in soft sleep or true suspend (WoL). Sleep/suspend periods are invisible because:

1. `time.time()` advances during suspend, so `server_uptime_seconds` and `system_uptime_seconds` never drop — no restart is detected.
2. The frontend treats any bucket with samples and no restart as 100% online.
3. The synthetic history fallback generates perfect coverage, hiding gaps.

## Solution

Overlay sleep events from the existing `SleepStateLog` database table onto the uptime status bars. No changes to the uptime sample collection — sleep state comes from the sleep manager's own log.

## Color Scheme

| Status | Color | Hex | Uptime-% | Meaning |
|--------|-------|-----|----------|---------|
| Online | Green | `#22c55e` | 100% | Fully operational |
| Soft Sleep | Indigo | `#6366f1` | 100% | Reachable, services reduced |
| Suspended | Purple | `#7c3aed` | 0% | Unreachable, needs WoL |
| No Data | Slate | `#334155` | excluded | No samples collected |

Soft sleep counts as uptime (server is reachable). Only true suspend reduces the uptime percentage.

## Backend Changes

### 1. New Schema: `SleepEventSchema`

File: `backend/app/schemas/monitoring.py`

```python
class SleepEventSchema(BaseModel):
    """A sleep state transition for uptime overlay."""
    timestamp: datetime
    previous_state: str   # "awake" | "soft_sleep" | "true_suspend"
    new_state: str
    duration_seconds: Optional[float] = None
```

### 2. Extend `UptimeHistoryResponse`

File: `backend/app/schemas/monitoring.py`

```python
class UptimeHistoryResponse(BaseModel):
    samples: List[UptimeSampleSchema]
    sleep_events: List[SleepEventSchema] = []  # NEW
    sample_count: int
    source: str
```

### 3. Query `SleepStateLog` in Uptime History Endpoint

File: `backend/app/api/routes/monitoring.py`

In `get_uptime_history()`, after fetching uptime samples, also query `SleepStateLog` for the same time range:

```python
from app.models.sleep import SleepStateLog

sleep_rows = db.query(SleepStateLog).filter(
    SleepStateLog.timestamp >= start
).order_by(SleepStateLog.timestamp.asc()).all()

sleep_events = [
    SleepEventSchema(
        timestamp=row.timestamp,
        previous_state=row.previous_state,
        new_state=row.new_state,
        duration_seconds=row.duration_seconds,
    )
    for row in sleep_rows
]
```

Also query events just before the range to establish the initial state at range start (the most recent event before `start`).

### 4. No Changes to UptimeCollector

The sample collection logic stays unchanged. Sleep state information is orthogonal — it comes from `SleepStateLog`, not from uptime samples.

## Frontend Changes

### 1. New Types

File: `client/src/api/monitoring.ts`

```typescript
export interface SleepEvent {
  timestamp: string;
  previous_state: 'awake' | 'soft_sleep' | 'true_suspend';
  new_state: 'awake' | 'soft_sleep' | 'true_suspend';
  duration_seconds?: number;
}

export interface UptimeHistoryResponse {
  samples: UptimeSample[];
  sleep_events: SleepEvent[];  // NEW
  sample_count: number;
  source: string;
}
```

### 2. UptimeStatusBar: Sleep State Overlay

File: `client/src/components/system-monitor/UptimeStatusBar.tsx`

**New prop:** `sleepEvents: SleepEvent[]`

**Bucket state resolution:** For each time bucket, determine the dominant sleep state:

1. Walk through `sleepEvents` chronologically to build a timeline of states.
2. For each bucket, calculate the proportion of time in each state (awake / soft_sleep / true_suspend).
3. Determine bucket status:
   - If any `true_suspend` time exists: calculate awake+soft_sleep proportion as uptime-%, set status to `suspended` or `partial`.
   - If only `soft_sleep`: status = `soft_sleep`, uptime = 100%.
   - If only `awake`: status = `online`, uptime = 100%.
4. Color the bucket using the dominant (longest) non-awake state, or green if fully awake.

**New `UptimeTimeslot.status` values:** Add `'soft_sleep'` and `'suspended'` to the existing `'online' | 'offline' | 'partial' | 'no-data'` union.

**Color mapping additions:**
```typescript
if (slot.status === 'soft_sleep') return '#6366f1';   // indigo
if (slot.status === 'suspended') return '#7c3aed';     // purple
```

**Tooltip:** Show the sleep state name and duration within the slot.

### 3. UptimeTab: Sleep Events in Incidents

File: `client/src/components/system-monitor/UptimeTab.tsx`

Extend the incidents section to show sleep/suspend events alongside restarts:

- Extract `soft_sleep` and `true_suspend` entries from `sleep_events`.
- Show soft sleep entries with an indigo badge ("Soft Sleep").
- Show suspend entries with a purple badge ("Suspended").
- Include duration if available.

### 4. i18n Keys

File: `client/src/i18n/locales/en/system.json` (uptime section)

```json
"softSleep": "Soft Sleep",
"suspended": "Suspended",
"sleepEvent": "Sleep event",
"suspendEvent": "Suspend event",
"slotSoftSleep": "Soft Sleep",
"slotSuspended": "Suspended (WoL)"
```

## Data Flow

```
SleepManagerService
  └─ _log_state_change()
       └─ SleepStateLog (DB table)

GET /api/monitoring/uptime/history
  ├─ UptimeCollector samples (memory/DB)
  └─ SleepStateLog query (DB)
       └─ Combined response { samples, sleep_events }

UptimeTab (frontend)
  ├─ UptimeStatusBar (samples + sleep_events → colored bars)
  └─ Incidents section (restarts + sleep events)
```

## Edge Cases

1. **Range starts mid-sleep:** Query one event before range start to know the initial state.
2. **No sleep events:** Bar works exactly as before (all green if samples exist).
3. **Sleep manager not running:** `sleep_events` is empty — graceful fallback.
4. **Overlapping states (entering_suspend):** Treat `entering_suspend` as `soft_sleep` since the system is still reachable during that brief transition.
5. **Synthetic history fallback:** When synthetic uptime samples are generated, still query real `SleepStateLog` events — they are independent.

## Files to Modify

### Backend
- `backend/app/schemas/monitoring.py` — Add `SleepEventSchema`, extend `UptimeHistoryResponse`
- `backend/app/api/routes/monitoring.py` — Query `SleepStateLog` in `get_uptime_history()`

### Frontend
- `client/src/api/monitoring.ts` — Add `SleepEvent` type, update `UptimeHistoryResponse`
- `client/src/components/system-monitor/UptimeStatusBar.tsx` — Sleep state overlay logic + colors
- `client/src/components/system-monitor/UptimeTab.tsx` — Pass `sleepEvents`, show in incidents
- `client/src/i18n/locales/en/system.json` — New translation keys
