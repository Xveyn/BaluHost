# Power/Energy Custom Date Range — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a freely selectable date range (calendar behind a "Custom" button) to the System Monitor → Power tab, covering both Cumulative and Instant chart modes, for single devices and the Total aggregate; empty windows render a flat 0 line.

**Architecture:** Backend gains optional `start`/`end` (UTC ISO) params on the two cumulative energy endpoints; the service layer computes on an arbitrary `(start, end)` window and emits two synthetic 0 boundary points for empty windows. Frontend adds a `'custom'` period with a native-`<input type="date">` popover, converts the locally-picked dates to UTC, and reuses the existing chart (both modes read the same `data_points`). No retention or storage-model changes.

**Tech Stack:** FastAPI + SQLAlchemy (backend), pytest; React + TypeScript + Recharts (frontend), vitest + React Testing Library; i18next (de/en).

**Spec:** `docs/superpowers/specs/2026-06-04-power-energy-custom-date-range-design.md`

---

## File Structure

**Backend**
- Modify: `backend/app/services/power/energy.py` — add `_resolve_period_range()` helper; add keyword-only `start`/`end` to `get_cumulative_energy_data()` and `get_cumulative_energy_total()`; emit 0 boundary points for empty explicit windows.
- Modify: `backend/app/api/routes/energy.py` — add `start`/`end` query params + `_validate_range()` helper to `/cumulative/{device_id}` and `/cumulative/total`; drop the `period` regex so a custom call isn't rejected.
- Test (extend): `backend/tests/services/test_energy_service.py`
- Test (create): `backend/tests/api/test_energy_routes.py`

**Frontend**
- Modify: `client/src/api/energy.ts` — optional `start`/`end` on `getCumulativeEnergy()` / `getCumulativeEnergyTotal()`.
- Modify: `client/src/lib/dateUtils.ts` — add `'custom'` to `ChartTimeRange` + axis format; add pure `localRangeToUtcIso()` helper.
- Modify: `client/src/components/system-monitor/PowerTab.tsx` — `'custom'` period, popover with date inputs, fetch wiring, axis range.
- Modify: `client/src/i18n/locales/de/system.json` and `client/src/i18n/locales/en/system.json` — keys under `monitor.power`.
- Test (create): `client/src/__tests__/api/energy.test.ts`
- Test (create): `client/src/__tests__/lib/dateUtils.customRange.test.ts`

---

## Task 1: Service — `_resolve_period_range()` helper + range on `get_cumulative_energy_data()`

**Files:**
- Modify: `backend/app/services/power/energy.py:367-469`
- Test: `backend/tests/services/test_energy_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/test_energy_service.py` (after the existing cumulative tests):

```python
class TestCumulativeCustomRange:
    def test_explicit_range_filters_window(self, db_session, smart_device, sample_data):
        # sample_data has 10 samples at now, now-5m, ... now-45m
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=12)  # captures samples at 0,5,10 min ago
        result = get_cumulative_energy_data(
            db_session, smart_device.id, "today", 0.40, start=start, end=now,
        )
        assert result is not None
        assert result["period"] == "custom"
        # Only samples within [start, now] are counted (3 of them: 0,5,10 min ago)
        assert len(result["data_points"]) == 3

    def test_empty_range_returns_two_zero_boundary_points(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=400)
        end = now - timedelta(days=399)  # no samples exist here
        result = get_cumulative_energy_data(
            db_session, smart_device.id, "today", 0.40, start=start, end=end,
        )
        assert result is not None
        assert result["period"] == "custom"
        assert result["total_kwh"] == 0.0
        assert result["total_cost"] == 0.0
        assert len(result["data_points"]) == 2
        assert result["data_points"][0]["instant_watts"] == 0.0
        assert result["data_points"][0]["cumulative_kwh"] == 0.0
        assert result["data_points"][0]["timestamp"] == start.isoformat()
        assert result["data_points"][1]["timestamp"] == end.isoformat()

    def test_no_range_keeps_period_label(self, db_session, smart_device, sample_data):
        result = get_cumulative_energy_data(db_session, smart_device.id, "today", 0.40)
        assert result["period"] == "today"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestCumulativeCustomRange -v`
Expected: FAIL — `get_cumulative_energy_data()` got an unexpected keyword argument `start`.

- [ ] **Step 3: Add the `_resolve_period_range()` helper**

In `backend/app/services/power/energy.py`, add above `get_cumulative_energy_data` (before line 367):

```python
def _resolve_period_range(period: str, now: datetime) -> tuple[datetime, datetime]:
    """Map a named period to a (start, end=now) window."""
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:  # month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now
```

- [ ] **Step 4: Add `start`/`end` to `get_cumulative_energy_data()`**

Change the signature (line 367) to:

```python
def get_cumulative_energy_data(
    db: Session,
    device_id: int,
    period: str,
    cost_per_kwh: float,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Optional[Dict]:
```

Replace the period-mapping block (currently lines 389-397, `now = ...` through the `else:` branch) with:

```python
    now = datetime.now(timezone.utc)
    if start is not None and end is not None:
        start_time, end_time = start, end
        period_label = "custom"
    else:
        start_time, end_time = _resolve_period_range(period, now)
        period_label = period
```

Change the sample query upper bound (was `SmartDeviceSample.timestamp <= now`) to `<= end_time`.

Replace the empty-samples early return (currently lines 414-424) with:

```python
    if not parsed_samples:
        if start is not None and end is not None:
            zero_points = [
                {"timestamp": start_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
                {"timestamp": end_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
            ]
            return {
                "device_id": device_id, "device_name": device.name,
                "period": period_label, "cost_per_kwh": cost_per_kwh,
                "currency": "EUR", "total_kwh": 0.0, "total_cost": 0.0,
                "data_points": zero_points,
            }
        return {
            "device_id": device_id, "device_name": device.name,
            "period": period_label, "cost_per_kwh": cost_per_kwh,
            "currency": "EUR", "total_kwh": 0.0, "total_cost": 0.0,
            "data_points": [],
        }
```

In the final success `return` dict (currently line 460-469), change `"period": period,` to `"period": period_label,`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py -v`
Expected: PASS (the new `TestCumulativeCustomRange` class and all pre-existing tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/energy.py backend/tests/services/test_energy_service.py
git commit -m "feat(energy): arbitrary start/end window in get_cumulative_energy_data"
```

---

## Task 2: Service — range on `get_cumulative_energy_total()`

**Files:**
- Modify: `backend/app/services/power/energy.py:472-587`
- Test: `backend/tests/services/test_energy_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/test_energy_service.py`:

```python
class TestCumulativeTotalCustomRange:
    def test_total_explicit_range(self, db_session, smart_device, sample_data):
        from app.services.power.energy import get_cumulative_energy_total
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=12)
        result = get_cumulative_energy_total(db_session, "today", 0.40, start=start, end=now)
        assert result["period"] == "custom"
        assert result["device_name"] == "Total"
        assert len(result["data_points"]) >= 1

    def test_total_empty_range_zero_boundaries(self, db_session, smart_device):
        from app.services.power.energy import get_cumulative_energy_total
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=400)
        end = now - timedelta(days=399)
        result = get_cumulative_energy_total(db_session, "today", 0.40, start=start, end=end)
        assert result["period"] == "custom"
        assert result["total_kwh"] == 0.0
        assert len(result["data_points"]) == 2
        assert result["data_points"][0]["timestamp"] == start.isoformat()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestCumulativeTotalCustomRange -v`
Expected: FAIL — unexpected keyword argument `start`.

- [ ] **Step 3: Add `start`/`end` to `get_cumulative_energy_total()`**

Change the signature (line 472) to:

```python
def get_cumulative_energy_total(
    db: Session,
    period: str,
    cost_per_kwh: float,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict:
```

Set `period_label` once **immediately after the `power_devices = [...]` list comprehension and before the `empty_result = {` dict** (so `empty_result` can use it):

```python
    period_label = "custom" if (start is not None and end is not None) else period
```

In the `empty_result` dict (currently `"period": period,`), change it to `"period": period_label,`.

Pass the range through to the per-device call (the line `device_data = get_cumulative_energy_data(db, device.id, period, cost_per_kwh)`):

```python
        device_data = get_cumulative_energy_data(
            db, device.id, period, cost_per_kwh, start=start, end=end,
        )
```

Before the existing `if not watts_by_ts: return empty_result`, insert the boundary-point branch so an explicit empty window spans 0:

```python
    if not watts_by_ts and start is not None and end is not None:
        return {
            "device_id": 0, "device_name": "Total", "period": period_label,
            "cost_per_kwh": cost_per_kwh, "currency": "EUR",
            "total_kwh": 0.0, "total_cost": 0.0,
            "data_points": [
                {"timestamp": start.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
                {"timestamp": end.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
            ],
        }
```

In the final success `return` dict, change `"period": period,` to `"period": period_label,`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/energy.py backend/tests/services/test_energy_service.py
git commit -m "feat(energy): arbitrary start/end window in get_cumulative_energy_total"
```

---

## Task 3: Routes — `start`/`end` query params + validation

**Files:**
- Modify: `backend/app/api/routes/energy.py` (imports at top; `/cumulative/{device_id}` lines 393-443; `/cumulative/total` lines 355-390)
- Test: `backend/tests/api/test_energy_routes.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_energy_routes.py`:

```python
"""API integration tests for energy cumulative custom-range params."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models.smart_device import SmartDevice


@pytest.fixture
def power_device(db_session) -> SmartDevice:
    device = SmartDevice(
        name="Route Test Plug", plugin_name="tapo_smart_plug",
        device_type_id="tapo_p110", address="192.168.1.50",
        capabilities=["power_monitor"], is_active=True, is_online=True,
        created_by_user_id=1,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


class TestCumulativeRangeParams:
    def test_requires_auth(self, client: TestClient, power_device):
        r = client.get(f"/api/energy/cumulative/{power_device.id}?period=today")
        assert r.status_code == 401

    def test_one_sided_range_rejected(self, client: TestClient, user_headers, power_device):
        start = datetime.now(timezone.utc).isoformat()
        r = client.get(
            f"/api/energy/cumulative/{power_device.id}?start={start}",
            headers=user_headers,
        )
        assert r.status_code == 422

    def test_reversed_range_rejected(self, client: TestClient, user_headers, power_device):
        now = datetime.now(timezone.utc)
        start = now.isoformat()
        end = (now - timedelta(days=1)).isoformat()
        r = client.get(
            f"/api/energy/cumulative/{power_device.id}?start={start}&end={end}",
            headers=user_headers,
        )
        assert r.status_code == 422

    def test_valid_empty_range_returns_custom(self, client: TestClient, user_headers, power_device):
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=400)).isoformat()
        end = (now - timedelta(days=399)).isoformat()
        r = client.get(
            f"/api/energy/cumulative/{power_device.id}?start={start}&end={end}",
            headers=user_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["period"] == "custom"
        assert body["total_kwh"] == 0.0
        assert len(body["data_points"]) == 2

    def test_total_valid_empty_range(self, client: TestClient, user_headers, power_device):
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=400)).isoformat()
        end = (now - timedelta(days=399)).isoformat()
        r = client.get(
            f"/api/energy/cumulative/total?start={start}&end={end}",
            headers=user_headers,
        )
        assert r.status_code == 200
        assert r.json()["period"] == "custom"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_energy_routes.py -v`
Expected: FAIL — currently `start`/`end` are unknown query params (ignored), so `period` stays `"today"` and 422 cases return 200.

- [ ] **Step 3: Add imports + validation helper**

In `backend/app/api/routes/energy.py`, extend the stdlib import at the top (after the module docstring, near line 8):

```python
from datetime import datetime, timezone
```

Add the helper just below `router = APIRouter()` (line 28):

```python
def _validate_range(
    start: Optional[datetime], end: Optional[datetime]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Validate/normalize a custom range. Returns (None, None) when absent."""
    if start is None and end is None:
        return None, None
    if start is None or end is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both 'start' and 'end' are required for a custom range",
        )
    # Treat naive datetimes as UTC (frontend sends '...Z', but be defensive)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'start' must be before 'end'",
        )
    now = datetime.now(timezone.utc)
    if end > now:
        end = now
    return start, end
```

- [ ] **Step 4: Wire range params into `/cumulative/{device_id}`**

In `get_cumulative_energy` (line 393), change the `period` param to drop the regex and add `start`/`end`:

```python
    period: str = Query("today"),
    start: Optional[datetime] = Query(None, description="UTC ISO start (inclusive)"),
    end: Optional[datetime] = Query(None, description="UTC ISO end (inclusive)"),
```

At the start of the function body (before fetching the price config), validate and pass through:

```python
    start_dt, end_dt = _validate_range(start, end)
```

Change the service call to:

```python
    data = energy_stats.get_cumulative_energy_data(
        db=db, device_id=device_id, period=period,
        cost_per_kwh=price_config.cost_per_kwh, start=start_dt, end=end_dt,
    )
```

- [ ] **Step 5: Wire range params into `/cumulative/total`**

In `get_cumulative_energy_total` (route, line 355), change the `period` param and add `start`/`end`:

```python
    period: str = Query("today"),
    start: Optional[datetime] = Query(None, description="UTC ISO start (inclusive)"),
    end: Optional[datetime] = Query(None, description="UTC ISO end (inclusive)"),
```

In the body:

```python
    start_dt, end_dt = _validate_range(start, end)
    price_config = energy_stats.get_energy_price_config(db)
    cost_per_kwh = price_config.cost_per_kwh
    result = energy_stats.get_cumulative_energy_total(
        db, period, cost_per_kwh, start=start_dt, end=end_dt,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_energy_routes.py tests/services/test_energy_service.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/energy.py backend/tests/api/test_energy_routes.py
git commit -m "feat(energy): custom start/end query params on cumulative endpoints"
```

---

## Task 4: Frontend API client — range args

**Files:**
- Modify: `client/src/api/energy.ts:139-156`
- Test: `client/src/__tests__/api/energy.test.ts` (create)

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/api/energy.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getCumulativeEnergy, getCumulativeEnergyTotal } from '../../api/energy';

describe('energy cumulative API — custom range', () => {
  beforeEach(() => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { data_points: [] } });
  });

  it('sends period when no range given', async () => {
    await getCumulativeEnergy(5, 'week');
    expect(apiClient.get).toHaveBeenCalledWith('/api/energy/cumulative/5?period=week');
  });

  it('sends start/end (not period) when range given', async () => {
    await getCumulativeEnergy(5, 'today', '2026-06-01T00:00:00.000Z', '2026-06-04T00:00:00.000Z');
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/energy/cumulative/5?start=2026-06-01T00%3A00%3A00.000Z&end=2026-06-04T00%3A00%3A00.000Z',
    );
  });

  it('total sends start/end when range given', async () => {
    await getCumulativeEnergyTotal('today', '2026-06-01T00:00:00.000Z', '2026-06-04T00:00:00.000Z');
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/energy/cumulative/total?start=2026-06-01T00%3A00%3A00.000Z&end=2026-06-04T00%3A00%3A00.000Z',
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/api/energy.test.ts`
Expected: FAIL — current functions ignore start/end and always append `?period=...`.

- [ ] **Step 3: Update the two functions**

Replace `getCumulativeEnergy` and `getCumulativeEnergyTotal` in `client/src/api/energy.ts` (lines 139-156) with:

```ts
export async function getCumulativeEnergy(
  deviceId: number,
  period: 'today' | 'week' | 'month' = 'today',
  start?: string,
  end?: string,
): Promise<CumulativeEnergyResponse> {
  const params = new URLSearchParams();
  if (start && end) {
    params.set('start', start);
    params.set('end', end);
  } else {
    params.set('period', period);
  }
  const response = await apiClient.get<CumulativeEnergyResponse>(
    `/api/energy/cumulative/${deviceId}?${params.toString()}`,
  );
  return response.data;
}

export async function getCumulativeEnergyTotal(
  period: 'today' | 'week' | 'month' = 'today',
  start?: string,
  end?: string,
): Promise<CumulativeEnergyResponse> {
  const params = new URLSearchParams();
  if (start && end) {
    params.set('start', start);
    params.set('end', end);
  } else {
    params.set('period', period);
  }
  const response = await apiClient.get<CumulativeEnergyResponse>(
    `/api/energy/cumulative/total?${params.toString()}`,
  );
  return response.data;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/api/energy.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/api/energy.ts client/src/__tests__/api/energy.test.ts
git commit -m "feat(energy-api): optional start/end range args on cumulative client"
```

---

## Task 5: dateUtils — `'custom'` axis format + `localRangeToUtcIso()` helper

**Files:**
- Modify: `client/src/lib/dateUtils.ts:68-107`
- Test: `client/src/__tests__/lib/dateUtils.customRange.test.ts` (create)

- [ ] **Step 1: Write the failing tests**

Create `client/src/__tests__/lib/dateUtils.customRange.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { localRangeToUtcIso, formatTimeForRange } from '../../lib/dateUtils';

describe('localRangeToUtcIso', () => {
  it('maps local start 00:00 and inclusive end day to UTC, clamps end to now', () => {
    // nowMs far in the future so no clamping occurs
    const nowMs = new Date('2030-01-01T00:00:00Z').getTime();
    const { startIso, endIso } = localRangeToUtcIso('2026-06-01', '2026-06-03', nowMs);
    // Start is local midnight of Jun 1; end is local midnight of Jun 4 (exclusive upper bound)
    expect(new Date(startIso).getTime()).toBe(new Date('2026-06-01T00:00:00').getTime());
    expect(new Date(endIso).getTime()).toBe(new Date('2026-06-04T00:00:00').getTime());
  });

  it('clamps end to now when the range reaches today', () => {
    const nowMs = new Date('2026-06-03T12:34:00').getTime();
    const { endIso } = localRangeToUtcIso('2026-06-01', '2026-06-03', nowMs);
    expect(new Date(endIso).getTime()).toBe(nowMs);
  });
});

describe('formatTimeForRange custom', () => {
  it('formats custom timestamps with locale-aware day/month order (de: day before month)', () => {
    // Pass a LOCAL Date to avoid timezone-dependent day shifts in CI.
    const local = new Date(2026, 5, 4, 12, 30); // 2026-06-04 12:30 local (month is 0-based)
    const out = formatTimeForRange(local, 'custom', 'de');
    expect(out).toMatch(/\d{2}:\d{2}/);            // time present
    expect(out).toContain('04');                    // day
    expect(out).toContain('06');                    // month
    expect(out.indexOf('04')).toBeLessThan(out.indexOf('06')); // de order day.month
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/__tests__/lib/dateUtils.customRange.test.ts`
Expected: FAIL — `localRangeToUtcIso` is not exported; `'custom'` is not a valid `ChartTimeRange`.

- [ ] **Step 3: Extend `ChartTimeRange` + `formatTimeForRange`**

In `client/src/lib/dateUtils.ts`, change the type (line 68):

```ts
export type ChartTimeRange = '10m' | '1h' | '24h' | '7d' | 'today' | 'week' | 'month' | 'custom';
```

Add a `case 'custom'` in the `switch` of `formatTimeForRange` (before the closing brace at line 106):

```ts
    case 'custom':
      return date.toLocaleString(locale, {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      });
```

- [ ] **Step 4: Add `localRangeToUtcIso()` helper**

Append to `client/src/lib/dateUtils.ts`:

```ts
/**
 * Convert a locally-picked date range (YYYY-MM-DD strings from <input type="date">)
 * to absolute UTC ISO instants for the energy API.
 *
 * - `startIso` = local 00:00 of `startDate`.
 * - `endIso`   = local 00:00 of the day AFTER `endDate` (inclusive end day),
 *               clamped to `nowMs` so the window never reaches into the future.
 *
 * @param startDate - 'YYYY-MM-DD' (local)
 * @param endDate   - 'YYYY-MM-DD' (local)
 * @param nowMs     - current epoch ms (injected for testability)
 */
export function localRangeToUtcIso(
  startDate: string,
  endDate: string,
  nowMs: number,
): { startIso: string; endIso: string } {
  const start = new Date(`${startDate}T00:00:00`); // parsed as local time
  const endNext = new Date(`${endDate}T00:00:00`);
  endNext.setDate(endNext.getDate() + 1); // inclusive end day -> exclusive next midnight
  const endMs = Math.min(endNext.getTime(), nowMs);
  return { startIso: start.toISOString(), endIso: new Date(endMs).toISOString() };
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/lib/dateUtils.customRange.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/lib/dateUtils.ts client/src/__tests__/lib/dateUtils.customRange.test.ts
git commit -m "feat(dateUtils): custom chart range format + localRangeToUtcIso helper"
```

---

## Task 6: i18n keys (de + en)

**Files:**
- Modify: `client/src/i18n/locales/en/system.json` (object `monitor.power`)
- Modify: `client/src/i18n/locales/de/system.json` (object `monitor.power`)

- [ ] **Step 1: Add EN keys**

In `client/src/i18n/locales/en/system.json`, inside the `monitor.power` object (alongside the existing `periodToday`/`periodWeek`/`periodMonth` keys), add:

```json
"periodCustom": "Custom",
"customFrom": "From",
"customTo": "To",
"customApply": "Apply",
"customInvalidRange": "Start date must be on or before end date"
```

- [ ] **Step 2: Add DE keys**

In `client/src/i18n/locales/de/system.json`, inside the `monitor.power` object, add:

```json
"periodCustom": "Benutzerdefiniert",
"customFrom": "Von",
"customTo": "Bis",
"customApply": "Anwenden",
"customInvalidRange": "Startdatum muss vor oder gleich dem Enddatum liegen"
```

- [ ] **Step 3: Verify JSON is valid**

Run: `cd client && node -e "require('./src/i18n/locales/en/system.json'); require('./src/i18n/locales/de/system.json'); console.log('ok')"`
Expected: prints `ok` (no JSON parse error).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/en/system.json client/src/i18n/locales/de/system.json
git commit -m "i18n(power): custom date range labels (en/de)"
```

---

## Task 7: PowerTab — Custom period, date popover, fetch wiring

**Files:**
- Modify: `client/src/components/system-monitor/PowerTab.tsx` (type at line 38; state at 55-60; fetch effect 98-120; selector block 360-394; chart axis 462-474)

- [ ] **Step 1: Widen the period type and add state**

Change line 38:

```tsx
type CumulativePeriod = 'today' | 'week' | 'month' | 'custom';
```

After the existing cumulative state (line 60), add:

```tsx
  // Custom range (applied values drive fetching; drafts live in the popover)
  const [customStart, setCustomStart] = useState<string | null>(null);
  const [customEnd, setCustomEnd] = useState<string | null>(null);
  const [showRangePicker, setShowRangePicker] = useState(false);
  const [draftStart, setDraftStart] = useState('');
  const [draftEnd, setDraftEnd] = useState('');
```

Add the helper import to the existing `dateUtils` import (line 21-22):

```tsx
import { formatTimeForRange, parseUtcTimestamp, localRangeToUtcIso } from '../../lib/dateUtils';
```

- [ ] **Step 2: Wire the fetch effect for custom ranges**

Replace the body of the cumulative fetch `useEffect` (lines 99-120) so it skips fetching for an incomplete custom range and sends start/end otherwise:

```tsx
  useEffect(() => {
    const isCustom = cumulativePeriod === 'custom';
    if (isCustom && (!customStart || !customEnd)) {
      return; // nothing applied yet
    }
    const fetchCumulative = async () => {
      setCumulativeLoading(true);
      try {
        const start = isCustom ? customStart! : undefined;
        const end = isCustom ? customEnd! : undefined;
        const period = (isCustom ? 'today' : cumulativePeriod) as 'today' | 'week' | 'month';
        const data = selectedDeviceId === null
          ? await getCumulativeEnergyTotal(period, start, end)
          : await getCumulativeEnergy(selectedDeviceId, period, start, end);
        setCumulativeData(data);
      } catch {
        // Non-critical: cumulative data will remain null
      } finally {
        setCumulativeLoading(false);
      }
    };

    fetchCumulative();
    const interval = setInterval(fetchCumulative, 60000);
    return () => clearInterval(interval);
  }, [selectedDeviceId, cumulativePeriod, customStart, customEnd]);
```

- [ ] **Step 3: Add the Custom button + popover to the period selector**

In the period selector block (after the `today/week/month` `.map(...)` closes at line 392, still inside the `<div className="flex gap-1 sm:gap-2 flex-wrap">`), add:

```tsx
            <div className="relative">
              <button
                onClick={() => {
                  setDraftStart(customStart ?? '');
                  setDraftEnd(customEnd ?? '');
                  setShowRangePicker((v) => !v);
                }}
                className={`px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors ${
                  cumulativePeriod === 'custom'
                    ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700 border border-transparent'
                }`}
              >
                {t('monitor.power.periodCustom')}
              </button>
              {showRangePicker && (
                <div className="absolute right-0 z-20 mt-2 w-64 rounded-lg border border-slate-700 bg-slate-900 p-3 shadow-xl">
                  <label className="block text-xs text-slate-400 mb-1">{t('monitor.power.customFrom')}</label>
                  <input
                    type="date"
                    value={draftStart}
                    max={draftEnd || undefined}
                    onChange={(e) => setDraftStart(e.target.value)}
                    className="w-full mb-2 px-2 py-1 text-sm bg-slate-800 border border-slate-700 rounded text-white focus:border-blue-500 focus:outline-none"
                  />
                  <label className="block text-xs text-slate-400 mb-1">{t('monitor.power.customTo')}</label>
                  <input
                    type="date"
                    value={draftEnd}
                    min={draftStart || undefined}
                    onChange={(e) => setDraftEnd(e.target.value)}
                    className="w-full mb-3 px-2 py-1 text-sm bg-slate-800 border border-slate-700 rounded text-white focus:border-blue-500 focus:outline-none"
                  />
                  <button
                    onClick={() => {
                      if (!draftStart || !draftEnd || draftStart > draftEnd) {
                        toast.error(t('monitor.power.customInvalidRange'));
                        return;
                      }
                      const { startIso, endIso } = localRangeToUtcIso(draftStart, draftEnd, Date.now());
                      setCustomStart(startIso);
                      setCustomEnd(endIso);
                      setCumulativePeriod('custom');
                      setShowRangePicker(false);
                    }}
                    className="w-full px-2 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded"
                  >
                    {t('monitor.power.customApply')}
                  </button>
                </div>
              )}
            </div>
```

- [ ] **Step 4: Use a `'custom'`-aware axis range in the chart**

The chart maps points with `formatTimeForRange(dp.timestamp, cumulativePeriod as ChartTimeRange, i18n.language)` (line 473). Because `ChartTimeRange` now includes `'custom'` and `CumulativePeriod` is a subset of it, the existing cast already resolves correctly — no change needed there. Verify the two other `formatTimeForRange(..., cumulativePeriod as ChartTimeRange, ...)` call sites in the instant-mode chart branch use the same cast (they do); leave them unchanged.

- [ ] **Step 5: Build the frontend to verify types compile**

Run: `cd client && npx tsc --noEmit`
Expected: no type errors related to `PowerTab.tsx` / `CumulativePeriod` / `ChartTimeRange`.

- [ ] **Step 6: Run the full frontend test + lint for touched files**

Run: `cd client && npx vitest run src/__tests__/api/energy.test.ts src/__tests__/lib/dateUtils.customRange.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add client/src/components/system-monitor/PowerTab.tsx
git commit -m "feat(power-tab): custom date range picker for cumulative + instant charts"
```

---

## Task 8: Manual smoketest

- [ ] **Step 1: Start dev environment**

Run: `python start_dev.py`
Open `http://localhost:5173` → log in (`admin` / `DevMode2024`) → System Monitor → Power tab.

- [ ] **Step 2: Verify Custom range — both modes**

1. Click **Custom** → popover opens with two date inputs (rendered in browser locale: DE `TT.MM.JJJJ`, EN `MM/DD/YYYY`).
2. Pick a range covering today and a few past days → **Anwenden**.
3. Chart updates; toggle **Cumulative** ↔ **Instant** — both honor the same range.
4. Pick a far-past range with no data → chart shows a flat **0 line** spanning the range (not the "no data" placeholder), totals show 0.
5. Pick start > end → toast `customInvalidRange`, no fetch.

- [ ] **Step 3: Final full test run**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py tests/api/test_energy_routes.py -v`
Expected: PASS.

Run: `cd client && npx vitest run src/__tests__/api/energy.test.ts src/__tests__/lib/dateUtils.customRange.test.ts`
Expected: PASS.

---

## Notes / Known Costs

- Very long custom ranges over 5-minute live data load all rows then downsample to 200 points in Python (existing `max_points` cap bounds the response). Acceptable; no rollup table in scope.
- The 60 s auto-refresh also re-fetches a closed past range; harmless (same data returned).
- Empty custom windows render exactly two 0 boundary points, so the "Data Points" stat shows 2 for empty ranges — expected.
