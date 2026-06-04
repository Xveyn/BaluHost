# Power/Energy — Custom Date Range (System Monitor → Power)

**Date:** 2026-06-04
**Status:** Draft
**Branch:** `feat/power-energy-date-range`

## Problem

The Power tab in System Monitor (`PowerTab.tsx`) shows cumulative consumption/cost
and instant power, but the time window is limited to three fixed buttons:
**Today / Week / Month**. Users want to view an **arbitrary date range** that can
reach back as far as data exists (e.g. "last 3 months", a past billing period).

The request covers **both** chart modes — *Cumulative* and *Instant* — and the
range must be freely selectable. Where no data exists in the selected window, the
graph should display **0** across that window (not an empty placeholder).

## Non-Goals (Out of Scope)

- No retention or storage-model changes. Per-plugin retention is already solved
  (`retention_days`, `0 = unlimited`, shipped in #154 + Tapo retention commits).
- No rollup / pre-aggregated long-term table.
- No saved range presets, no CSV export.
- No change to the `/stats/*` or `/cost/*` endpoints (only the cumulative pair).

## How Power Data Is Stored (Context)

A single time-series table, **no rollup/aggregate table**:

- **`smart_device_samples`** — `(id, device_id, capability, data_json TEXT, timestamp UTC)`.
- **Live power rows:** `capability = "power_monitor"`,
  `data_json = {current_power, voltage, current_ma, energy_today_wh, is_online}`,
  written by `SmartDevicePoller` every poll (~60 s).
- **Imported history rows:** same table, `data_json` additionally carries
  `{imported_from:"tapo_history", bucket_interval:"hourly"}` — **hourly buckets,
  retention-exempt** (never deleted by cleanup).
- **Aggregation happens on read** in Python: trapezoidal integration for
  cumulative kWh/cost, avg/min/max for instant (`energy.get_cumulative_energy_data`,
  `get_cumulative_energy_total`, `get_period_stats`).
- **Retention:** per-plugin `retention_days` (`0 = unlimited`, default 30),
  daily cleanup via `cleanup_smart_device_samples`; imported rows always kept.

**Consequence:** an arbitrary range is just a wider `timestamp` query window. How
far back *any* data exists = the plugin's retention setting + any imported history.
Empty windows naturally return no rows → zero. No data-model change is required.

## Key Insight: One Response Feeds Both Modes

`getCumulativeEnergy` / `getCumulativeEnergyTotal` return `data_points[]` where each
point already carries **both** `instant_watts` and `cumulative_kwh` / `cumulative_cost`.
The frontend `chartMode` toggle (`'cumulative' | 'instant'`) only selects which series
to plot. Therefore a **single endpoint change** (adding a custom range to the cumulative
pair) covers both Instant and Cumulative automatically.

## Design

### Backend

**`backend/app/services/power/energy.py`**

1. Extract the period→window mapping into a helper:
   ```python
   def _resolve_period_range(period: str, now: datetime) -> tuple[datetime, datetime]:
       # today / week / month → (start, end=now), as today.
   ```
2. `get_cumulative_energy_data(db, device_id, period, cost_per_kwh, *, start=None, end=None)`
   and `get_cumulative_energy_total(db, period, cost_per_kwh, *, start=None, end=None)`:
   - When `start` and `end` are provided (UTC datetimes), use them directly as the
     query window and set the response `period` field to `"custom"`.
   - Otherwise fall back to `_resolve_period_range(period, now)` (unchanged behavior).
3. **Empty range → spanning 0-line.** When an explicit `start`/`end` window yields no
   parsed samples, return **two synthetic boundary points** instead of `[]`:
   ```python
   [{"timestamp": start.isoformat(), "cumulative_kwh": 0.0, "cumulative_cost": 0.0, "instant_watts": 0.0},
    {"timestamp": end.isoformat(),   "cumulative_kwh": 0.0, "cumulative_cost": 0.0, "instant_watts": 0.0}]
   ```
   with `total_kwh = total_cost = 0.0`. This gives the frontend a chart that spans the
   selected window at 0 for **both** modes, with no special-casing in React.
   (Fixed-period empty results keep returning `[]` — unchanged.)

**`backend/app/api/routes/energy.py`**

- `/cumulative/{device_id}` and `/cumulative/total` gain:
  ```python
  start: Optional[datetime] = Query(None, description="UTC ISO start (inclusive)"),
  end:   Optional[datetime] = Query(None, description="UTC ISO end (inclusive)"),
  ```
- Validation (return HTTP 422 on violation):
  - Exactly one of `start`/`end` supplied → error ("both required").
  - `start >= end` → error.
  - `end` in the future → clamp to `now` (not an error).
- Relax the `period` query validator so it is ignored / optional when `start`+`end`
  are present (keep `^(today|week|month)$` for the no-range path).
- Pass `start`/`end` through to the service functions.

The response schema (`CumulativeEnergyResponse`, `CumulativeDataPoint`) is **unchanged**;
`period` is a free string already, so `"custom"` needs no schema change.

### Frontend

**`client/src/api/energy.ts`**

- Extend the two cumulative functions with optional range args; when present, append
  `&start=<iso>&end=<iso>` and omit/ignore `period`:
  ```ts
  getCumulativeEnergy(deviceId, period?, start?: string, end?: string)
  getCumulativeEnergyTotal(period?, start?: string, end?: string)
  ```

**`client/src/components/system-monitor/PowerTab.tsx`**

- Period state widened: `type CumulativePeriod = 'today' | 'week' | 'month' | 'custom'`.
- New state: `customStart: string | null`, `customEnd: string | null` (local `YYYY-MM-DD`).
- **UI:** a **"Custom"** button next to Today/Week/Month. Clicking opens a small popover
  anchored to the button containing two native `<input type="date">` (Von / Bis) and an
  "Anwenden" action. **No new dependency** (native inputs only).
- **Local→UTC conversion** (timezone decision: **local**). On apply:
  ```ts
  const startIso = new Date(`${customStart}T00:00:00`).toISOString();        // local 00:00
  const endLocalNext = new Date(`${customEnd}T00:00:00`); endLocalNext.setDate(endLocalNext.getDate() + 1);
  const endIso = new Date(Math.min(endLocalNext.getTime(), Date.now())).toISOString(); // next-day 00:00, clamped to now
  ```
- Fetch effect: when `cumulativePeriod === 'custom'`, call the API with `start`/`end`;
  otherwise unchanged. The 60 s refresh interval stays (custom ranges also refresh, which
  is harmless; a past closed range simply re-returns the same data).
- **Empty/0 rendering:** because the backend emits two boundary 0-points for an empty
  custom window, `data_points.length > 0` is already satisfied → the existing chart path
  draws a flat 0 line across [start, end] for both modes. The "no data" placeholder branch
  is only reached for the non-custom (fixed-period) empty case.
- **Axis formatting:** extend `formatTimeForRange` / `ChartTimeRange` in
  `client/src/lib/dateUtils.ts` to handle `'custom'`: choose a time label when the span is
  < 2 days, otherwise a date label.

## Data Flow

```
[Custom button] → popover (Von/Bis date inputs) → Anwenden
  → compute startIso/endIso (local→UTC, end clamped to now)
  → setCumulativePeriod('custom'); setCustomStart/End
  → effect: getCumulativeEnergy(id, undefined, startIso, endIso)   (or *Total)
  → GET /api/energy/cumulative/{id}?start=...&end=...
  → energy.get_cumulative_energy_data(..., start, end)
      → query smart_device_samples in [start,end]
      → samples? integrate → data_points  |  none? two 0 boundary points
  → CumulativeEnergyResponse (period="custom")
  → chartMode toggle picks instant_watts vs cumulative_kwh/cost from same points
```

## Error Handling

- One-sided or reversed range → 422 with a clear `detail`; frontend surfaces via the
  existing `getApiErrorMessage` toast path (cumulative fetch currently swallows errors —
  keep that for the auto-refresh, but show a toast on explicit "Anwenden").
- Future `end` is clamped server-side, not rejected.
- Device not found → existing 404 behavior (per-device endpoint only).

## Testing

**Backend (`backend/tests/services/test_energy_service.py`, `tests/api/.../test_energy*.py`):**
- `get_cumulative_energy_data` with explicit `start`/`end` returns points only inside the window.
- Empty custom window → exactly two 0 boundary points + `total_kwh == 0`.
- `get_cumulative_energy_total` with range aggregates across devices.
- Long range includes `imported_from` (retention-exempt) rows.
- Route: one-sided range → 422; `start >= end` → 422; future `end` clamped; `period="custom"` in response.

**Frontend (`client/src/__tests__/`):**
- Custom apply computes start/end and calls the API with range args (local→UTC).
- Empty custom data renders a 0-line chart (boundary points), not the placeholder.
- Mode toggle (Cumulative/Instant) works while a custom range is active.

## Build Order

1. Backend service: `_resolve_period_range` helper + `start`/`end` params + empty-window
   boundary points (TDD: service tests first).
2. Backend routes: query params + validation + clamp (route tests).
3. Frontend API client: range args.
4. `PowerTab`: `'custom'` period, popover with date inputs, local→UTC, fetch wiring.
5. `dateUtils`: `'custom'` axis formatting.
6. i18n keys (Custom, Von, Bis, Anwenden, range labels) — EN + DE.
7. Frontend tests + smoketest (`python start_dev.py`).

## Open Questions

None at spec-writing time. Timezone resolved to **local** (calendar dates interpreted in
the user's local timezone, converted to UTC for the query). Performance of very long
ranges is bounded by the existing 200-point Python downsample.
