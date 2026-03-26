# Uptime Sleep-State Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show soft-sleep and true-suspend periods in the uptime status bars using data from the existing `SleepStateLog` database table.

**Architecture:** Extend the uptime history API to include sleep events alongside uptime samples. The frontend overlays sleep events onto the existing status bar buckets, coloring them by state (green=online, indigo=soft_sleep, purple=suspended). Soft sleep counts as 100% uptime; only true suspend reduces the uptime percentage.

**Tech Stack:** Python/FastAPI (backend schemas + route), React/TypeScript (frontend components), i18next (translations)

---

### Task 1: Backend — Add `SleepEventSchema` and extend `UptimeHistoryResponse`

**Files:**
- Modify: `backend/app/schemas/monitoring.py:237-241`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/api/test_monitoring_routes.py`:

```python
class TestUptimeSleepEvents:
    """Tests for sleep events in uptime history."""

    def test_uptime_history_includes_sleep_events_field(self, client: TestClient, user_headers: dict):
        """Test that uptime history response contains sleep_events field."""
        response = client.get(
            "/api/monitoring/uptime/history",
            params={"time_range": "1h"},
            headers=user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "sleep_events" in data
        assert isinstance(data["sleep_events"], list)

    def test_uptime_history_sleep_events_have_correct_fields(self, client: TestClient, user_headers: dict, db_session):
        """Test that sleep events contain all required fields."""
        from app.models.sleep import SleepStateLog

        # Insert a test sleep event
        log_entry = SleepStateLog(
            previous_state="awake",
            new_state="soft_sleep",
            reason="test",
            triggered_by="manual",
            duration_seconds=120.0,
        )
        db_session.add(log_entry)
        db_session.commit()

        response = client.get(
            "/api/monitoring/uptime/history",
            params={"time_range": "1h"},
            headers=user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sleep_events"]) >= 1

        event = data["sleep_events"][0]
        assert "timestamp" in event
        assert event["previous_state"] == "awake"
        assert event["new_state"] == "soft_sleep"
        assert "duration_seconds" in event
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_monitoring_routes.py::TestUptimeSleepEvents -v`
Expected: FAIL — `sleep_events` key not in response

- [ ] **Step 3: Add `SleepEventSchema` and extend `UptimeHistoryResponse`**

In `backend/app/schemas/monitoring.py`, add `SleepEventSchema` right after `UptimeSampleSchema` (after line 117), and update `UptimeHistoryResponse`:

```python
class SleepEventSchema(BaseModel):
    """A sleep state transition for uptime overlay."""
    timestamp: datetime
    previous_state: str
    new_state: str
    duration_seconds: Optional[float] = None
```

Update `UptimeHistoryResponse` (line 237-241) to:

```python
class UptimeHistoryResponse(BaseModel):
    """Uptime history response."""
    samples: List[UptimeSampleSchema]
    sleep_events: List[SleepEventSchema] = []
    sample_count: int
    source: str
```

- [ ] **Step 4: Query `SleepStateLog` in the uptime history endpoint**

In `backend/app/api/routes/monitoring.py`, update `get_uptime_history()`. Add the import at the top of the file (near line 48):

```python
from app.models.sleep import SleepStateLog
```

Then, before the `return UptimeHistoryResponse(...)` at line 598, add:

```python
    # Query sleep state events for the time range
    range_start = datetime.now(timezone.utc) - duration

    # Get the most recent event before range start to know initial state
    initial_event = db.query(SleepStateLog).filter(
        SleepStateLog.timestamp < range_start
    ).order_by(SleepStateLog.timestamp.desc()).first()

    sleep_rows = db.query(SleepStateLog).filter(
        SleepStateLog.timestamp >= range_start
    ).order_by(SleepStateLog.timestamp.asc()).all()

    # Build sleep events list (include initial event if it exists)
    all_sleep_rows = ([initial_event] if initial_event else []) + list(sleep_rows)
    sleep_events = [
        SleepEventSchema(
            timestamp=row.timestamp,
            previous_state=row.previous_state,
            new_state=row.new_state,
            duration_seconds=row.duration_seconds,
        )
        for row in all_sleep_rows
    ]
```

Update the return statement to include `sleep_events`:

```python
    return UptimeHistoryResponse(
        samples=samples,
        sleep_events=sleep_events,
        sample_count=len(samples),
        source=source_str,
    )
```

Also add `SleepEventSchema` to the imports from `app.schemas.monitoring` at the top of the file (line 36):

```python
from app.schemas.monitoring import (
    ...
    SleepEventSchema,
    ...
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_monitoring_routes.py::TestUptimeSleepEvents -v`
Expected: PASS

- [ ] **Step 6: Run existing monitoring tests to check for regressions**

Run: `cd backend && python -m pytest tests/api/test_monitoring_routes.py -v`
Expected: All PASS — existing tests should still pass because `sleep_events` defaults to `[]`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/monitoring.py backend/app/api/routes/monitoring.py backend/tests/api/test_monitoring_routes.py
git commit -m "feat(monitoring): add sleep events to uptime history API"
```

---

### Task 2: Frontend — Add `SleepEvent` type and update API response

**Files:**
- Modify: `client/src/api/monitoring.ts:69-75,159-163`

- [ ] **Step 1: Add `SleepEvent` interface**

In `client/src/api/monitoring.ts`, add after the `UptimeSample` interface (after line 75):

```typescript
export type SleepState = 'awake' | 'soft_sleep' | 'true_suspend';

export interface SleepEvent {
  timestamp: string;
  previous_state: SleepState;
  new_state: SleepState;
  duration_seconds?: number;
}
```

- [ ] **Step 2: Update `UptimeHistoryResponse` interface**

In `client/src/api/monitoring.ts`, change `UptimeHistoryResponse` (lines 159-163) to:

```typescript
export interface UptimeHistoryResponse {
  samples: UptimeSample[];
  sleep_events: SleepEvent[];
  sample_count: number;
  source: string;
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/api/monitoring.ts
git commit -m "feat(monitoring): add SleepEvent type to frontend API client"
```

---

### Task 3: Frontend — Add i18n keys for sleep states

**Files:**
- Modify: `client/src/i18n/locales/en/system.json:48-49`

- [ ] **Step 1: Add translation keys**

In `client/src/i18n/locales/en/system.json`, add the following keys inside the `"uptime"` object, right before the closing `}` of the uptime section (after line 48, `"slotUptime": "Uptime: {{percent}}%"`):

```json
      "slotUptime": "Uptime: {{percent}}%",
      "softSleep": "Soft Sleep",
      "suspended": "Suspended",
      "slotSoftSleep": "Soft Sleep",
      "slotSuspended": "Suspended (WoL)",
      "sleepDuration": "Duration: {{duration}}"
```

Note: the existing `"slotUptime"` line needs a comma added at the end.

- [ ] **Step 2: Commit**

```bash
git add client/src/i18n/locales/en/system.json
git commit -m "feat(i18n): add uptime sleep state translation keys"
```

---

### Task 4: Frontend — Sleep state overlay in `UptimeStatusBar`

**Files:**
- Modify: `client/src/components/system-monitor/UptimeStatusBar.tsx`

This is the core change. The component gains a `sleepEvents` prop and uses it to determine each bucket's dominant sleep state.

- [ ] **Step 1: Update imports and types**

In `UptimeStatusBar.tsx`, update the import line (line 10) to include `SleepEvent`:

```typescript
import type { TimeRange, UptimeSample, SleepEvent } from '../../api/monitoring';
```

Update the `UptimeTimeslot` interface (lines 13-20) to include `'soft_sleep' | 'suspended'`:

```typescript
interface UptimeTimeslot {
  startTime: Date;
  endTime: Date;
  sampleCount: number;
  uptimePercent: number;
  status: 'online' | 'offline' | 'partial' | 'no-data' | 'soft_sleep' | 'suspended';
  restartCount: number;
}
```

Update `UptimeStatusBarProps` (lines 22-27) to add the new prop:

```typescript
interface UptimeStatusBarProps {
  samples: UptimeSample[];
  sleepEvents?: SleepEvent[];
  timeRange: TimeRange;
  label: string;
  uptimeField: 'server_uptime_seconds' | 'system_uptime_seconds';
}
```

- [ ] **Step 2: Update the color function**

Replace the `getSlotColor` function (lines 43-51) with:

```typescript
function getSlotColor(slot: UptimeTimeslot): string {
  if (slot.status === 'no-data') return '#334155';
  if (slot.status === 'soft_sleep') return '#6366f1';
  if (slot.status === 'suspended') return '#7c3aed';
  if (slot.uptimePercent === 100) return '#22c55e';
  if (slot.uptimePercent >= 95) return '#84cc16';
  if (slot.uptimePercent >= 75) return '#eab308';
  if (slot.uptimePercent >= 50) return '#f97316';
  if (slot.uptimePercent > 0) return '#ef4444';
  return '#dc2626';
}
```

- [ ] **Step 3: Add sleep state resolution helper**

Add this helper function after `getSlotColor`, before the component function:

```typescript
/**
 * Build a timeline of sleep states from events.
 * Returns a function that, given a time range, returns the dominant state
 * and the fraction of time spent in true_suspend.
 */
function buildSleepTimeline(events: SleepEvent[]) {
  // Parse and sort events chronologically
  const parsed = events
    .map(e => ({ time: parseUtcTimestamp(e.timestamp).getTime(), state: e.new_state }))
    .sort((a, b) => a.time - b.time);

  return function getSlotSleepState(
    bucketStart: number,
    bucketEnd: number,
  ): { dominant: 'awake' | 'soft_sleep' | 'true_suspend'; suspendFraction: number } {
    if (parsed.length === 0) {
      return { dominant: 'awake', suspendFraction: 0 };
    }

    const bucketDuration = bucketEnd - bucketStart;

    // Determine state at bucket start:
    // Find the last event at or before bucketStart
    let stateAtStart: 'awake' | 'soft_sleep' | 'true_suspend' = 'awake';
    for (let i = parsed.length - 1; i >= 0; i--) {
      if (parsed[i].time <= bucketStart) {
        stateAtStart = parsed[i].state as typeof stateAtStart;
        break;
      }
    }

    // Find events within this bucket
    const bucketEvents = parsed.filter(e => e.time > bucketStart && e.time < bucketEnd);

    if (bucketEvents.length === 0) {
      // Entire bucket is in stateAtStart
      return {
        dominant: stateAtStart,
        suspendFraction: stateAtStart === 'true_suspend' ? 1 : 0,
      };
    }

    // Calculate time in each state
    const timeIn: Record<string, number> = { awake: 0, soft_sleep: 0, true_suspend: 0 };
    let currentState = stateAtStart;
    let currentTime = bucketStart;

    for (const event of bucketEvents) {
      timeIn[currentState] += event.time - currentTime;
      currentState = event.state as typeof stateAtStart;
      currentTime = event.time;
    }
    // Remaining time after last event
    timeIn[currentState] += bucketEnd - currentTime;

    // Determine dominant non-awake state (longest), or awake if no sleep
    const suspendFraction = timeIn.true_suspend / bucketDuration;
    let dominant: 'awake' | 'soft_sleep' | 'true_suspend' = 'awake';

    if (timeIn.true_suspend > 0 && timeIn.true_suspend >= timeIn.soft_sleep) {
      dominant = 'true_suspend';
    } else if (timeIn.soft_sleep > 0 && timeIn.soft_sleep > timeIn.true_suspend) {
      dominant = 'soft_sleep';
    }

    return { dominant, suspendFraction };
  };
}
```

- [ ] **Step 4: Integrate sleep state into the bucket loop**

Update the component function signature (line 62) to destructure the new prop:

```typescript
export function UptimeStatusBar({ samples, sleepEvents = [], timeRange, label, uptimeField }: UptimeStatusBarProps) {
```

In the `useMemo` for `timeslots` (line 66), add `sleepEvents` to the dependency array and integrate the sleep timeline. Replace the entire `useMemo` block (lines 66-153) with:

```typescript
  const timeslots = useMemo<UptimeTimeslot[]>(() => {
    const clientNow = Date.now();
    const bucketDuration = config.durationMs / config.segments;
    const getSleepState = buildSleepTimeline(sleepEvents);

    // Parse all samples
    const allParsed = samples
      .map(s => ({ ...s, _time: parseUtcTimestamp(s.timestamp).getTime() }))
      .sort((a, b) => a._time - b._time);

    // Use the latest sample timestamp as reference for "now" if available.
    const now = allParsed.length > 0
      ? Math.max(clientNow, allParsed[allParsed.length - 1]._time)
      : clientNow;
    const rangeStart = now - config.durationMs;

    const parsed = allParsed.filter(s => s._time >= rangeStart && s._time <= now);

    const slots: UptimeTimeslot[] = [];

    for (let i = 0; i < config.segments; i++) {
      const bucketStart = rangeStart + i * bucketDuration;
      const bucketEnd = bucketStart + bucketDuration;

      // Samples in this bucket
      const bucketSamples = parsed.filter(s => s._time >= bucketStart && s._time < bucketEnd);

      // Get sleep state for this bucket
      const { dominant: sleepDominant, suspendFraction } = getSleepState(bucketStart, bucketEnd);

      if (bucketSamples.length === 0) {
        // No samples — check if we know sleep state
        if (sleepDominant === 'true_suspend') {
          slots.push({
            startTime: new Date(bucketStart),
            endTime: new Date(bucketEnd),
            sampleCount: 0,
            uptimePercent: 0,
            status: 'suspended',
            restartCount: 0,
          });
        } else if (sleepDominant === 'soft_sleep') {
          slots.push({
            startTime: new Date(bucketStart),
            endTime: new Date(bucketEnd),
            sampleCount: 0,
            uptimePercent: 100,
            status: 'soft_sleep',
            restartCount: 0,
          });
        } else {
          slots.push({
            startTime: new Date(bucketStart),
            endTime: new Date(bucketEnd),
            sampleCount: 0,
            uptimePercent: 0,
            status: 'no-data',
            restartCount: 0,
          });
        }
        continue;
      }

      // Detect restarts: uptime field drops between consecutive samples
      let restartCount = 0;
      for (let j = 1; j < bucketSamples.length; j++) {
        if (bucketSamples[j][uptimeField] < bucketSamples[j - 1][uptimeField]) {
          restartCount++;
        }
      }

      // Also check against the last sample from the previous bucket
      if (i > 0 && slots[i - 1].status !== 'no-data') {
        const prevBucketSamples = parsed.filter(s => {
          const prevStart = rangeStart + (i - 1) * bucketDuration;
          const prevEnd = prevStart + bucketDuration;
          return s._time >= prevStart && s._time < prevEnd;
        });
        if (prevBucketSamples.length > 0) {
          const lastPrev = prevBucketSamples[prevBucketSamples.length - 1];
          if (bucketSamples[0][uptimeField] < lastPrev[uptimeField]) {
            restartCount++;
          }
        }
      }

      // Determine status based on sleep state + restarts
      let status: UptimeTimeslot['status'];
      let uptimePercent: number;

      if (sleepDominant === 'true_suspend') {
        // Has samples but also spent time suspended
        status = 'suspended';
        uptimePercent = Math.round((1 - suspendFraction) * 100);
      } else if (sleepDominant === 'soft_sleep') {
        status = restartCount > 0 ? 'partial' : 'soft_sleep';
        uptimePercent = 100; // soft sleep is still uptime
      } else if (restartCount > 0) {
        // Coverage-based calculation for restarts
        const firstSampleTime = bucketSamples[0]._time;
        const lastSampleTime = bucketSamples[bucketSamples.length - 1]._time;
        const coverage = bucketSamples.length === 1
          ? Math.min(1, bucketSamples.length / 3)
          : Math.min(1, (lastSampleTime - firstSampleTime) / bucketDuration + 0.1);
        const rawPercent = Math.max(0, Math.round((1 - restartCount * 0.2) * coverage * 100));
        uptimePercent = Math.min(100, Math.max(0, rawPercent));
        status = 'partial';
      } else {
        uptimePercent = 100;
        status = 'online';
      }

      slots.push({
        startTime: new Date(bucketStart),
        endTime: new Date(bucketEnd),
        sampleCount: bucketSamples.length,
        uptimePercent,
        status,
        restartCount,
      });
    }

    return slots;
  }, [samples, sleepEvents, config, uptimeField]);
```

- [ ] **Step 5: Update the tooltip to show sleep state labels**

Replace the tooltip content block (lines 205-218 in the original) inside the `{timeslots.map}`. The full tooltip `<div>` inner content becomes:

```tsx
              <p className="text-slate-300 font-medium">
                {formatSlotTime(slot.startTime)}
              </p>
              <p className="text-slate-400">
                → {formatSlotTime(slot.endTime)}
              </p>
              {slot.status === 'no-data' ? (
                <p className="text-slate-500 mt-1">{t('monitor.uptime.noDataSlot')}</p>
              ) : slot.status === 'soft_sleep' ? (
                <p className="text-indigo-400 mt-1">{t('monitor.uptime.slotSoftSleep')}</p>
              ) : slot.status === 'suspended' ? (
                <>
                  <p className="text-purple-400 mt-1">{t('monitor.uptime.slotSuspended')}</p>
                  <p className="text-white text-[10px]">
                    {t('monitor.uptime.slotUptime', { percent: slot.uptimePercent })}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-white mt-1">
                    {t('monitor.uptime.slotUptime', { percent: slot.uptimePercent })}
                  </p>
                  {slot.restartCount > 0 && (
                    <p className="text-amber-400">
                      {t('monitor.uptime.restartDetected', { count: slot.restartCount })}
                    </p>
                  )}
                </>
              )}
```

- [ ] **Step 6: Commit**

```bash
git add client/src/components/system-monitor/UptimeStatusBar.tsx
git commit -m "feat(monitoring): add sleep state overlay to UptimeStatusBar"
```

---

### Task 5: Frontend — Wire sleep events through `UptimeTab`

**Files:**
- Modify: `client/src/components/system-monitor/UptimeTab.tsx`

- [ ] **Step 1: Update imports and state**

In `UptimeTab.tsx`, add `SleepEvent` to the imports (line 8-14):

```typescript
import type { TimeRange, SleepEvent } from '../../api/monitoring';
import {
  getUptimeCurrent,
  getUptimeHistory,
  type CurrentUptimeResponse,
  type UptimeSample,
} from '../../api/monitoring';
```

Add `Moon` to the lucide imports (line 7):

```typescript
import { AlertTriangle, CheckCircle, Moon } from 'lucide-react';
```

Add sleep events state (after line 37):

```typescript
  const [sleepEvents, setSleepEvents] = useState<SleepEvent[]>([]);
```

- [ ] **Step 2: Store sleep events from API response**

In the `fetchData` callback (line 49), update to also store sleep events:

```typescript
      setCurrent(currentData);
      setHistory(historyData.samples);
      setSleepEvents(historyData.sleep_events ?? []);
      setError(null);
```

- [ ] **Step 3: Pass `sleepEvents` to `UptimeStatusBar` components**

Update the two `UptimeStatusBar` usages (lines 130-141) to pass the new prop:

```tsx
        <UptimeStatusBar
          samples={history}
          sleepEvents={sleepEvents}
          timeRange={timeRange}
          label={t('monitor.uptime.serverLabel')}
          uptimeField="server_uptime_seconds"
        />
        <UptimeStatusBar
          samples={history}
          sleepEvents={sleepEvents}
          timeRange={timeRange}
          label={t('monitor.uptime.systemLabel')}
          uptimeField="system_uptime_seconds"
        />
```

- [ ] **Step 4: Add sleep events to the incidents section**

Compute suspend events from sleep events. Add this `useMemo` after the `restarts` memo (after line 100):

```typescript
  // Extract suspend events from sleep events
  const suspendEvents = useMemo(() => {
    return sleepEvents.filter(e => e.new_state === 'true_suspend');
  }, [sleepEvents]);

  const softSleepEvents = useMemo(() => {
    return sleepEvents.filter(e => e.new_state === 'soft_sleep');
  }, [sleepEvents]);

  const hasIncidents = restarts.length > 0 || suspendEvents.length > 0;
```

Update the incidents header condition (line 147) to use `hasIncidents`:

```tsx
          {hasIncidents ? (
```

Update the "no incidents" condition (line 154) to use `hasIncidents`:

```tsx
        {!hasIncidents ? (
```

After the restarts map block (after line 183 closing `</div>`), but inside the incidents `<div>`, add the suspend events and soft sleep events:

```tsx
            {suspendEvents.map((event, idx) => (
              <div
                key={`suspend-${idx}`}
                className="card border-purple-500/20 bg-purple-500/5 p-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <Moon className="w-4 h-4 text-purple-400 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-white">
                      {formatDateTime(event.timestamp)}
                    </p>
                    {event.duration_seconds && (
                      <p className="text-xs text-slate-400">
                        {t('monitor.uptime.sleepDuration', { duration: formatUptime(event.duration_seconds) })}
                      </p>
                    )}
                  </div>
                </div>
                <div className="rounded-full bg-purple-500/20 px-2 py-1">
                  <span className="text-xs text-purple-400">{t('monitor.uptime.suspended')}</span>
                </div>
              </div>
            ))}
            {softSleepEvents.map((event, idx) => (
              <div
                key={`sleep-${idx}`}
                className="card border-indigo-500/20 bg-indigo-500/5 p-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <Moon className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-white">
                      {formatDateTime(event.timestamp)}
                    </p>
                    {event.duration_seconds && (
                      <p className="text-xs text-slate-400">
                        {t('monitor.uptime.sleepDuration', { duration: formatUptime(event.duration_seconds) })}
                      </p>
                    )}
                  </div>
                </div>
                <div className="rounded-full bg-indigo-500/20 px-2 py-1">
                  <span className="text-xs text-indigo-400">{t('monitor.uptime.softSleep')}</span>
                </div>
              </div>
            ))}
```

Note: The existing code structure wraps restarts in `<div className="space-y-2">`. The suspend and soft sleep event blocks go inside this same wrapper, after the restarts map. The full else-branch of the incidents section (lines 159-183) becomes:

```tsx
          <div className="space-y-2">
            {restarts.map((restart, idx) => (
              /* ... existing restart code unchanged ... */
            ))}
            {suspendEvents.map((event, idx) => (
              /* ... suspend event code from above ... */
            ))}
            {softSleepEvents.map((event, idx) => (
              /* ... soft sleep event code from above ... */
            ))}
          </div>
```

- [ ] **Step 5: Commit**

```bash
git add client/src/components/system-monitor/UptimeTab.tsx
git commit -m "feat(monitoring): wire sleep events into UptimeTab with incidents display"
```

---

### Task 6: Verify end-to-end + final commit

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/api/test_monitoring_routes.py -v`
Expected: All PASS

- [ ] **Step 2: Check frontend builds**

Run: `cd client && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 3: Visual verification (dev mode)**

Run: `python start_dev.py`
Open `http://localhost:5173` → System Monitor → Uptime tab
Verify: bars render correctly, no console errors. Since there are no sleep events in dev mode, bars should look the same as before (all green or grey for no-data).

- [ ] **Step 4: Final combined commit (if not already committed per task)**

If any uncommitted changes remain:

```bash
git add -A
git commit -m "feat(monitoring): complete uptime sleep-state tracking"
```
