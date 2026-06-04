# Energy Consumption — Import-Aware, Gap-Capped Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the over-reported energy consumption by integrating power samples import-aware and gap-capped, and computing the Total as the sum of per-device curves (not a timestamp merge).

**Architecture:** All work is in one service file. A small per-interval energy primitive (`_interval_energy_wh`) plus two helpers (`_load_parsed_online_sorted`, `_device_cumulative_series`) become the single source of truth; `get_cumulative_energy_data`, `get_cumulative_energy_total`, and `get_period_stats` all route through them. Everything is computed on-read, so the fix retroactively corrects all displayed numbers with no migration.

**Tech Stack:** Python, SQLAlchemy, pytest.

**Spec:** `docs/superpowers/specs/2026-06-05-energy-consumption-gap-integration-design.md`
**Issue:** #159 (closes #157)

---

## File Structure

- Modify: `backend/app/services/power/energy.py` — constant, parse extension, the integration primitive + helpers, and rewire the three public functions.
- Test (extend): `backend/tests/services/test_energy_service.py`

No new files; the change is cohesive and belongs in the existing energy service.

---

## Task 1: Primitives — constant, parse fields, `_interval_energy_wh`

**Files:**
- Modify: `backend/app/services/power/energy.py` (constant near line 25; `_parse_power_from_sample` return dict ~line 102; new helper after it)
- Test: `backend/tests/services/test_energy_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/services/test_energy_service.py`. Note: `json`, `pytest`, and `datetime, timedelta, timezone` are already imported at the top of this file, as are `SmartDevice`, `SmartDeviceSample`, `get_period_stats`, and `get_cumulative_energy_data`. Add ONLY the new imports below to the top-of-file import block (do not duplicate existing ones):

```python
from app.services.power.energy import _parse_power_from_sample, _interval_energy_wh, GAP_THRESHOLD_MINUTES
```

Then add this test class:

```python
class TestIntervalEnergyPrimitive:
    def test_parse_exposes_import_fields(self):
        live = _parse_power_from_sample(json.dumps({"current_power": 50.0, "is_online": True}))
        assert live["imported"] is False
        assert live["bucket_energy_kwh"] is None

        imp = _parse_power_from_sample(json.dumps({
            "watts": 100.0, "is_online": True,
            "imported_from": "tapo_history", "bucket_energy_kwh": 0.1,
        }))
        assert imp["imported"] is True
        assert imp["bucket_energy_kwh"] == 0.1

    def test_imported_bucket_uses_own_energy(self):
        t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        prev = {"timestamp": t0, "watts": 0.0, "imported": False, "bucket_energy_kwh": None}
        cur = {"timestamp": t0 + timedelta(days=5), "watts": 100.0,
               "imported": True, "bucket_energy_kwh": 0.1}
        # 0.1 kWh regardless of the (huge) gap to prev
        assert _interval_energy_wh(prev, cur) == pytest.approx(100.0)

    def test_live_within_cap_is_integrated(self):
        t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        prev = {"timestamp": t0, "watts": 100.0, "imported": False, "bucket_energy_kwh": None}
        cur = {"timestamp": t0 + timedelta(minutes=10), "watts": 100.0,
               "imported": False, "bucket_energy_kwh": None}
        # 100 W over 10 min = 16.667 Wh
        assert _interval_energy_wh(prev, cur) == pytest.approx(100.0 * (10 / 60))

    def test_live_gap_beyond_cap_is_zero(self):
        t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        prev = {"timestamp": t0, "watts": 200.0, "imported": False, "bucket_energy_kwh": None}
        cur = {"timestamp": t0 + timedelta(hours=2), "watts": 200.0,
               "imported": False, "bucket_energy_kwh": None}
        assert GAP_THRESHOLD_MINUTES == 15
        assert _interval_energy_wh(prev, cur) == 0.0  # downtime, not bridged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestIntervalEnergyPrimitive -v --no-cov`
Expected: FAIL — `cannot import name '_interval_energy_wh'` / `GAP_THRESHOLD_MINUTES`.

- [ ] **Step 3: Add the constant**

In `backend/app/services/power/energy.py`, just below `_POWER_CAPABILITY = "power_monitor"`:

```python
# A live-sample gap longer than this is treated as downtime: the trapezoidal
# integration does NOT bridge it (the poller was down / device asleep, ~0 draw).
# Imported buckets carry their own energy and are exempt from this cap.
GAP_THRESHOLD_MINUTES = 15
```

- [ ] **Step 4: Extend `_parse_power_from_sample`**

In the returned dict of `_parse_power_from_sample` (currently ends with `"is_online": bool(is_online),`), add two fields:

```python
    bucket_energy_kwh = data.get("bucket_energy_kwh")

    return {
        "watts": float(watts),
        "voltage": float(voltage) if voltage is not None else None,
        "current": current_a,
        "energy_today": energy_today_kwh,
        "is_online": bool(is_online),
        "imported": bool(data.get("imported_from")),
        "bucket_energy_kwh": float(bucket_energy_kwh) if bucket_energy_kwh is not None else None,
    }
```

- [ ] **Step 5: Add the `_interval_energy_wh` primitive**

Add after `_parse_power_from_sample`:

```python
def _interval_energy_wh(prev: Dict, cur: Dict) -> float:
    """Energy in Wh attributed to the interval ending at ``cur``.

    - Imported buckets contribute their own measured ``bucket_energy_kwh``
      (no integration, independent of the gap to ``prev``).
    - Live samples are trapezoid-integrated only when the gap to ``prev`` is
      within ``GAP_THRESHOLD_MINUTES``; larger gaps are treated as downtime
      (0 Wh — the poller was down / device asleep, drawing ~0).
    """
    if cur.get("imported") and cur.get("bucket_energy_kwh") is not None:
        return cur["bucket_energy_kwh"] * 1000.0
    gap_h = (cur["timestamp"] - prev["timestamp"]).total_seconds() / 3600.0
    if gap_h * 60.0 > GAP_THRESHOLD_MINUTES:
        return 0.0
    return (prev["watts"] + cur["watts"]) / 2.0 * gap_h
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestIntervalEnergyPrimitive -v --no-cov`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/energy.py backend/tests/services/test_energy_service.py
git commit -m "feat(energy): import-aware, gap-capped interval energy primitive"
```

---

## Task 2: Per-device helpers + rewire `get_cumulative_energy_data`

**Files:**
- Modify: `backend/app/services/power/energy.py` (`get_cumulative_energy_data` ~lines 389-507; add three helpers before it)
- Test: `backend/tests/services/test_energy_service.py`

- [ ] **Step 1: Write the failing reproduction tests**

Add to `backend/tests/services/test_energy_service.py` (no new imports needed — `SmartDeviceSample` and `get_cumulative_energy_data` are already imported at the top). This `_add_sample` module-level helper is reused by Tasks 3 and 4, so define it once here:

```python
def _add_sample(db, device_id, ts, watts=None, *, imported=False, bucket_kwh=None, online=True):
    if imported:
        data = {"watts": watts if watts is not None else 0.0, "is_online": online,
                "imported_from": "tapo_history", "bucket_interval": "hourly",
                "bucket_energy_kwh": bucket_kwh}
    else:
        data = {"current_power": watts if watts is not None else 0.0, "is_online": online}
    db.add(SmartDeviceSample(device_id=device_id, capability="power_monitor",
                             data_json=json.dumps(data), timestamp=ts))


class TestCumulativeGapAndImport:
    def test_long_gap_is_not_bridged(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        # Two live samples 2h apart at 100W; the gap must contribute 0.
        _add_sample(db_session, smart_device.id, now - timedelta(hours=2), 100.0)
        _add_sample(db_session, smart_device.id, now, 100.0)
        db_session.commit()
        res = get_cumulative_energy_data(db_session, smart_device.id, "today", 0.40,
                                         start=now - timedelta(hours=3), end=now)
        assert res["total_kwh"] == pytest.approx(0.0, abs=1e-9)

    def test_short_gap_is_integrated(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        _add_sample(db_session, smart_device.id, now - timedelta(minutes=10), 120.0)
        _add_sample(db_session, smart_device.id, now, 120.0)
        db_session.commit()
        res = get_cumulative_energy_data(db_session, smart_device.id, "today", 0.40,
                                         start=now - timedelta(hours=1), end=now)
        # 120 W over 10 min = 0.02 kWh
        assert res["total_kwh"] == pytest.approx(120.0 * (10 / 60) / 1000, abs=1e-6)

    def test_imported_bucket_counts_own_energy(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        # Two hourly imported buckets (0.1 kWh each); 60-min spacing must NOT be
        # treated as a gap — each counts its own energy → 0.1 kWh total
        # (first sample contributes nothing; the second bucket adds 0.1).
        _add_sample(db_session, smart_device.id, now - timedelta(hours=2),
                    imported=True, bucket_kwh=0.1)
        _add_sample(db_session, smart_device.id, now - timedelta(hours=1),
                    imported=True, bucket_kwh=0.1)
        db_session.commit()
        res = get_cumulative_energy_data(db_session, smart_device.id, "today", 0.40,
                                         start=now - timedelta(hours=3), end=now)
        assert res["total_kwh"] == pytest.approx(0.1, abs=1e-6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestCumulativeGapAndImport -v --no-cov`
Expected: FAIL — `test_long_gap_is_not_bridged` returns ~0.2 (old bridging), `test_imported_bucket_counts_own_energy` returns the trapezoid of avg watts (~0.1 by luck or different), i.e. assertions don't hold under the current integration.

- [ ] **Step 3: Add the three helpers**

In `backend/app/services/power/energy.py`, add just above `get_cumulative_energy_data`:

```python
def _load_parsed_online_sorted(db: Session, device_id: int,
                               start_time: datetime, end_time: datetime) -> List[Dict]:
    """Query power samples in [start, end], parse, keep online, sorted by time."""
    samples = db.query(SmartDeviceSample).filter(
        and_(
            SmartDeviceSample.device_id == device_id,
            SmartDeviceSample.capability == _POWER_CAPABILITY,
            SmartDeviceSample.timestamp >= start_time,
            SmartDeviceSample.timestamp <= end_time,
        )
    ).order_by(SmartDeviceSample.timestamp).all()
    parsed: List[Dict] = []
    for s in samples:
        p = _parse_power_from_sample(s.data_json)
        if p is not None and p["is_online"]:
            parsed.append({"timestamp": s.timestamp, **p})
    return parsed


def _device_cumulative_series(parsed: List[Dict]) -> tuple[List[Dict], float]:
    """Full-resolution cumulative series from online, time-sorted samples.

    Returns (points, total_wh); points are
    {"timestamp": datetime, "cumulative_kwh": float, "instant_watts": float}.
    """
    points: List[Dict] = []
    cumulative_wh = 0.0
    for i, s in enumerate(parsed):
        if i > 0:
            cumulative_wh += _interval_energy_wh(parsed[i - 1], s)
        points.append({
            "timestamp": s["timestamp"],
            "cumulative_kwh": cumulative_wh / 1000.0,
            "instant_watts": s["watts"],
        })
    return points, cumulative_wh


def _downsample(data_points: List[Dict], max_points: int = 200) -> List[Dict]:
    """Evenly thin a list of chart points down to at most max_points."""
    if len(data_points) <= max_points:
        return data_points
    step = len(data_points) // max_points
    out = [data_points[0]]
    for i in range(step, len(data_points) - 1, step):
        out.append(data_points[i])
    out.append(data_points[-1])
    return out
```

- [ ] **Step 4: Rewire `get_cumulative_energy_data` to use the helpers**

In `get_cumulative_energy_data`, replace the inline query+parse block (the `samples = db.query(...)` through the `parsed_samples` build) with a single call:

```python
    parsed_samples = _load_parsed_online_sorted(db, device_id, start_time, end_time)
```

Keep the existing `if not parsed_samples:` empty-handling block unchanged. Then replace the integration loop + downsample + final return (everything from `# Calculate cumulative energy using trapezoidal integration` onward) with:

```python
    series, total_wh = _device_cumulative_series(parsed_samples)
    data_points = [
        {
            "timestamp": p["timestamp"].isoformat(),
            "cumulative_kwh": round(p["cumulative_kwh"], 4),
            "cumulative_cost": round(p["cumulative_kwh"] * cost_per_kwh, 4),
            "instant_watts": round(p["instant_watts"], 1),
        }
        for p in series
    ]
    data_points = _downsample(data_points)

    total_kwh = total_wh / 1000.0
    total_cost = total_kwh * cost_per_kwh
    return {
        "device_id": device_id,
        "device_name": device.name,
        "period": period_label,
        "cost_per_kwh": cost_per_kwh,
        "currency": "EUR",
        "total_kwh": round(total_kwh, 4),
        "total_cost": round(total_cost, 2),
        "data_points": data_points,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestCumulativeGapAndImport tests/services/test_energy_service.py::TestCumulativeCustomRange -v --no-cov`
Expected: PASS (new reproduction tests + the pre-existing custom-range tests still hold — the empty-window path is unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/energy.py backend/tests/services/test_energy_service.py
git commit -m "fix(energy): gap-capped import-aware integration in get_cumulative_energy_data"
```

---

## Task 3: Rewrite `get_cumulative_energy_total` (sum of per-device curves)

**Files:**
- Modify: `backend/app/services/power/energy.py` (`get_cumulative_energy_total`, the whole function body)
- Test: `backend/tests/services/test_energy_service.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/services/test_energy_service.py`. `SmartDevice` is already imported at the top; add only the new function import. The `_add_sample` helper from Task 2 is reused here.

```python
from app.services.power.energy import get_cumulative_energy_total
```

```python
class TestTotalEqualsSumOfDevices:
    def test_total_equals_sum_of_device_totals(self, db_session):
        now = datetime.now(timezone.utc)
        # Two devices with OFFSET live timestamps (never share a timestamp),
        # both 10-min spacing (within cap) at constant power.
        dev_a = SmartDevice(name="A", plugin_name="tapo_smart_plug",
                            device_type_id="tapo_p110", address="10.0.0.1",
                            capabilities=["power_monitor"], is_active=True,
                            is_online=True, created_by_user_id=1)
        dev_b = SmartDevice(name="B", plugin_name="tapo_smart_plug",
                            device_type_id="tapo_p110", address="10.0.0.2",
                            capabilities=["power_monitor"], is_active=True,
                            is_online=True, created_by_user_id=1)
        db_session.add_all([dev_a, dev_b]); db_session.commit()
        for i in range(7):
            _add_sample(db_session, dev_a.id, now - timedelta(minutes=60 - i * 10), 100.0)
            _add_sample(db_session, dev_b.id, now - timedelta(minutes=55 - i * 10), 50.0)
        db_session.commit()

        a = get_cumulative_energy_data(db_session, dev_a.id, "today", 0.40,
                                       start=now - timedelta(hours=2), end=now)
        b = get_cumulative_energy_data(db_session, dev_b.id, "today", 0.40,
                                       start=now - timedelta(hours=2), end=now)
        total = get_cumulative_energy_total(db_session, "today", 0.40,
                                            start=now - timedelta(hours=2), end=now)
        assert total["period"] == "custom"
        # Exact: Total == sum of per-device totals (no timestamp-merge averaging)
        assert total["total_kwh"] == pytest.approx(a["total_kwh"] + b["total_kwh"], abs=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestTotalEqualsSumOfDevices -v --no-cov`
Expected: FAIL — current merge averages interleaved points, so `total_kwh` < `a+b`.

- [ ] **Step 3: Rewrite `get_cumulative_energy_total`**

Replace the entire `get_cumulative_energy_total` function body with:

```python
def get_cumulative_energy_total(
    db: Session,
    period: str,
    cost_per_kwh: float,
    *,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Dict:
    """Aggregate cumulative energy across all active power-monitoring devices.

    Builds each device's full-resolution cumulative curve (import-aware,
    gap-capped) and sums them via carry-forward over the merged timeline, so
    the Total equals the exact sum of per-device totals.
    """
    now = datetime.now(timezone.utc)
    if start is not None and end is not None:
        start_time, end_time, period_label = start, end, "custom"
    else:
        start_time, end_time = _resolve_period_range(period, now)
        period_label = period

    all_devices = db.query(SmartDevice).filter(
        SmartDevice.is_active == True,  # noqa: E712
    ).all()
    power_devices = [
        d for d in all_devices
        if isinstance(d.capabilities, list) and _POWER_CAPABILITY in d.capabilities
    ]

    def _result(total_kwh: float, data_points: List[Dict]) -> Dict:
        return {
            "device_id": 0,
            "device_name": "Total",
            "period": period_label,
            "cost_per_kwh": cost_per_kwh,
            "currency": "EUR",
            "total_kwh": round(total_kwh, 3),
            "total_cost": round(total_kwh * cost_per_kwh, 2),
            "data_points": data_points,
        }

    # Per-device full-resolution series
    device_series: List[List[Dict]] = []
    for d in power_devices:
        parsed = _load_parsed_online_sorted(db, d.id, start_time, end_time)
        series, _ = _device_cumulative_series(parsed)
        if series:
            device_series.append(series)

    if not device_series:
        if start is not None and end is not None:
            return _result(0.0, [
                {"timestamp": start_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
                {"timestamp": end_time.isoformat(), "cumulative_kwh": 0.0,
                 "cumulative_cost": 0.0, "instant_watts": 0.0},
            ])
        return _result(0.0, [])

    # Carry-forward sum across devices over the merged timeline
    threshold = timedelta(minutes=GAP_THRESHOLD_MINUTES)
    all_ts = sorted({p["timestamp"] for s in device_series for p in s})
    n = len(device_series)
    idx = [0] * n
    last_cum = [0.0] * n
    last_w = [0.0] * n
    last_w_ts: List[Optional[datetime]] = [None] * n

    data_points: List[Dict] = []
    for ts in all_ts:
        for k, s in enumerate(device_series):
            while idx[k] < len(s) and s[idx[k]]["timestamp"] <= ts:
                last_cum[k] = s[idx[k]]["cumulative_kwh"]
                last_w[k] = s[idx[k]]["instant_watts"]
                last_w_ts[k] = s[idx[k]]["timestamp"]
                idx[k] += 1
        combined_cum = sum(last_cum)
        combined_w = sum(
            last_w[k] if (last_w_ts[k] is not None and ts - last_w_ts[k] <= threshold) else 0.0
            for k in range(n)
        )
        data_points.append({
            "timestamp": ts.isoformat(),
            "cumulative_kwh": round(combined_cum, 4),
            "cumulative_cost": round(combined_cum * cost_per_kwh, 4),
            "instant_watts": round(combined_w, 1),
        })

    total_kwh = sum(last_cum)  # final cumulative == sum of device totals
    return _result(total_kwh, _downsample(data_points))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestTotalEqualsSumOfDevices tests/services/test_energy_service.py::TestCumulativeTotalCustomRange -v --no-cov`
Expected: PASS (new test + the pre-existing total custom-range tests still hold — empty-window returns 2 boundary points).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/energy.py backend/tests/services/test_energy_service.py
git commit -m "fix(energy): Total = carry-forward sum of per-device curves (closes #157)"
```

---

## Task 4: `get_period_stats` energy via the same integration

**Files:**
- Modify: `backend/app/services/power/energy.py` (`get_period_stats` lines ~157-234)
- Test: `backend/tests/services/test_energy_service.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/services/test_energy_service.py` (no new imports — `get_period_stats` is already imported at the top; `_add_sample` from Task 2 is reused).

```python
class TestPeriodStatsEnergyMatchesIntegration:
    def test_period_total_does_not_bridge_gaps(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        # Two live samples 2h apart at 100W within a 3h window:
        # old avg*hours would report ~0.3 kWh; integration with gap-cap = 0.
        _add_sample(db_session, smart_device.id, now - timedelta(hours=2), 100.0)
        _add_sample(db_session, smart_device.id, now, 100.0)
        db_session.commit()
        stats = get_period_stats(db_session, smart_device.id,
                                 now - timedelta(hours=3), now)
        assert stats is not None
        assert stats.total_energy_kwh == pytest.approx(0.0, abs=1e-6)

    def test_period_total_matches_cumulative(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        for i in range(7):
            _add_sample(db_session, smart_device.id,
                        now - timedelta(minutes=60 - i * 10), 90.0)
        db_session.commit()
        stats = get_period_stats(db_session, smart_device.id,
                                 now - timedelta(hours=2), now)
        cum = get_cumulative_energy_data(db_session, smart_device.id, "today", 0.40,
                                         start=now - timedelta(hours=2), end=now)
        assert stats.total_energy_kwh == pytest.approx(cum["total_kwh"], abs=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestPeriodStatsEnergyMatchesIntegration -v --no-cov`
Expected: FAIL — current `total_energy_kwh = avg_watts * period_hours` bridges the gap (≈0.3) and won't match the cumulative.

- [ ] **Step 3: Rewire `get_period_stats` energy**

Two edits in `get_period_stats`:

(a) Add ordering + keep timestamps on the parsed samples. Change the query `.all()` to ordered, and the parse loop to attach timestamps:

```python
    samples = db.query(SmartDeviceSample).filter(
        and_(
            SmartDeviceSample.device_id == device_id,
            SmartDeviceSample.capability == _POWER_CAPABILITY,
            SmartDeviceSample.timestamp >= start_time,
            SmartDeviceSample.timestamp <= end_time,
        )
    ).order_by(SmartDeviceSample.timestamp).all()

    if not samples:
        return None

    # Parse all samples (keep timestamps for integration)
    parsed = []
    for s in samples:
        p = _parse_power_from_sample(s.data_json)
        if p is not None:
            parsed.append({"timestamp": s.timestamp, **p})

    if not parsed:
        return None

    samples_count = len(parsed)
    online_samples = [p for p in parsed if p["is_online"]]
    offline_samples = [p for p in parsed if not p["is_online"]]
```

(b) Replace the energy computation:

```python
    period_hours = (end_time - start_time).total_seconds() / 3600  # kept for reference/uptime

    _, total_wh = _device_cumulative_series(online_samples)
    total_energy_kwh = total_wh / 1000.0
```

(The `avg/min/max_watts`, `uptime_percentage`, and `downtime_minutes` lines stay as they are — they already operate on `online_samples` / `offline_samples` / `samples_count`. `period_hours` may now be unused by the energy calc; if a linter flags it as unused, delete that line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py::TestPeriodStatsEnergyMatchesIntegration -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/energy.py backend/tests/services/test_energy_service.py
git commit -m "fix(energy): period-stats energy uses gap-capped integration (matches chart)"
```

---

## Task 5: Full-suite verification

**Files:**
- Test: `backend/tests/services/test_energy_service.py` (and any other energy tests)

- [ ] **Step 1: Run the whole energy test file**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py -v --no-cov`
Expected: PASS. The pre-existing `sample_data` fixture uses 5-minute spacing (all gaps ≤ 15 min, all live, no imports), so the new live integration matches the old trapezoidal result and those tests are unaffected. The only changed behavior is for gaps > 15 min, imported buckets, the Total aggregation, and `get_period_stats.total_energy_kwh`.

- [ ] **Step 2: If any legacy assertion fails, reconcile it**

For any failing pre-existing test, read the assertion. If it asserted a value produced by the old bridging/avg×hours/merge math, recompute the expected value by hand from the fixture data using the new rules (imported→own energy; live gap >15 min→0; else trapezoid; Total=sum of devices) and update the literal. Do **not** weaken an assertion to make it pass; correct the expected number.

- [ ] **Step 3: Run the route-level energy tests too**

Run: `cd backend && python -m pytest tests/services/test_energy_service.py tests/api/test_energy_routes.py -q --no-cov`
Expected: PASS (route tests exercise empty-window behavior, which is unchanged).

- [ ] **Step 4: Commit (only if Step 2 changed anything)**

```bash
git add backend/tests/services/test_energy_service.py
git commit -m "test(energy): reconcile legacy expectations with gap-capped integration"
```

---

## Notes / Validation

- Expected production result after the fix (range 2026-01-01 … now): Total ≈ **38.4 kWh** (was 67.7); BaluNode ≈ **24.3** (was 62.5); Sven PC ≈ **14.1** (was 29.8).
- No migration: all numbers are computed on-read, so the correction applies retroactively to every range and view.
- Instant-mode chart cosmetics across a >15-min gap (a line drawn over the gap) are out of scope — the cumulative/energy is correct; synthetic 0-watt boundary points for the instant curve are a possible follow-up.
