# Energy Consumption — Import-Aware, Gap-Capped Integration

**Date:** 2026-06-05
**Status:** Draft
**Branch:** `fix/energy-consumption-gap-integration`
**Issue:** #159 (supersedes/closes #157)

## Problem

The energy calculation in `backend/app/services/power/energy.py` **over-reports consumption**, badly over long ranges. Confirmed against real production data (BaluNode, range 2026-01-01 … 2026-06-05): the UI Total shows **67.7 kWh**, the true value is **~38.4 kWh** (over-reported ~76%). Two compounding bugs:

### Bug 1 — Trapezoidal integration bridges downtime gaps (dominant)

`get_cumulative_energy_data` integrates instantaneous-power samples trapezoidally with **no cap on the inter-sample gap**. When the poller is down (the BaluNode server itself asleep/off), there are no samples; the integration assumes power flowed at the boundary average across the *entire* gap → invents energy.

| Device | bridged (app) | gap-capped | phantom | gap-hours | max gap |
|---|---|---|---|---|---|
| BaluNode | 62.5 kWh | 24.3 | **+38.2** | 3467 h | 169 h |
| Sven PC | 29.8 kWh | 14.1 | **+15.8** | 3466 h | 97 h |

Both devices share one poller (on BaluNode), so gap-hours are nearly identical → the gaps are **server downtime**. **Validation:** the Tapo history-import buckets for those periods carry only ~0.43 / ~0.27 kWh (~1 W avg) — the plug's own measurement confirms the device drew ≈0 while down. The bridged energy is genuinely phantom.

### Bug 2 — Total aggregates by exact-timestamp merge (#157)

`get_cumulative_energy_total` sums `instant_watts` keyed by exact ISO timestamp. Independently-sampled devices almost never share a timestamp, so in the overlap period the code **averages instead of sums** → Total under-counts by ~half the overlap energy.

The two bugs partially cancel (phantom +54 vs merge −25), masking how wrong each is.

## How Power Data Is Stored (context)

One table `smart_device_samples` (`device_id`, `capability`, `data_json` TEXT, `timestamp` UTC). For `power_monitor`:
- **Live samples** (poller, ~every 60 s): `data_json` has `current_power`/`watts`, `is_online`, etc.
- **Imported buckets** (Tapo history import, plugin-specific but generic in storage): `data_json` additionally has `imported_from`, `bucket_interval` (hourly/daily/monthly), and **`bucket_energy_kwh`** (the bucket's own measured energy). `watts` is the bucket's *average* power. Import uses a LIVE_WINS conflict strategy, so imported and live never overlap in time for a device.
- No rollup table — all aggregation is on-read.

## Design

### Constant

```python
GAP_THRESHOLD_MINUTES = 15  # live-sample gap beyond this = downtime (no bridging)
```
Rationale: the poller writes ~every 60 s, so a >15-min gap (≥15 missed writes) is downtime, not a missed beat. Imported buckets are handled by their own energy and are **not** subject to this cap (a 60-min hourly spacing is not a gap).

### `_parse_power_from_sample` — expose import info

Extend the returned dict with two fields (parsed from `data_json`):
- `imported: bool` — `"imported_from" in data`
- `bucket_energy_kwh: Optional[float]` — `data.get("bucket_energy_kwh")`

(All existing fields unchanged.)

### Core: one integration helper

A single internal function computes a device's energy and cumulative curve from its parsed, online, time-sorted samples:

```python
def _integrate_samples(parsed):  # parsed: list of dicts {timestamp, watts, imported, bucket_energy_kwh}
    """Return (data_points, total_wh).
    data_points: [{timestamp, cumulative_kwh, cumulative_cost(later), instant_watts}]
    """
```

Per-interval energy `(prev → cur)`:
1. **`cur.imported` and `cur.bucket_energy_kwh is not None`** → interval energy = `cur.bucket_energy_kwh * 1000` Wh (the bucket's own measured energy; no integration).
2. **else (live, or imported without a stored bucket energy)**:
   - `gap_h = (cur.t − prev.t) / 3600`
   - `gap_h * 60 > GAP_THRESHOLD_MINUTES` → interval energy = **0** (downtime; do not bridge)
   - else → `(prev.watts + cur.watts) / 2 * gap_h`

Accumulate `cumulative_wh`; emit a point per sample with `cumulative_kwh = cumulative_wh/1000` and `instant_watts = cur.watts`. The first sample contributes 0. `total_wh` is the final accumulator.

`get_cumulative_energy_data` uses this helper, then applies the existing 200-point downsample to the data_points (the integration runs at full resolution first, so `total_kwh` is unaffected by downsampling) and adds `cumulative_cost`.

### `get_cumulative_energy_total` — sum per-device curves (fixes #157)

Replace the timestamp-merge with a **carry-forward sum of each device's cumulative curve**:
1. For each power device, compute its full-resolution `(timestamp, cumulative_kwh, instant_watts)` series via the helper.
2. Merge all timestamps (sorted, unique). Walk them, maintaining per device: `last_cum` (last cumulative ≤ t, 0 before its first sample), `last_watts` and `last_watts_ts`.
3. At each t: `combined_cum = Σ last_cum[d]`; `combined_watts = Σ (last_watts[d] if (t − last_watts_ts[d]) ≤ GAP_THRESHOLD else 0)`.
4. Emit combined points; `total_kwh = combined_cum at the last t = Σ device totals` (exact). Downsample to 200.

This makes the Total **exactly** the sum of the (correct) per-device totals, and the Instant-Total reflects only devices currently online (gap → 0).

### `get_period_stats` — consistent energy

`get_period_stats` currently sets `total_energy_kwh = (avg_watts/1000) * period_hours` (avg×duration, also wrong over downtime). Change it to use `_integrate_samples` on the period's parsed samples so the dashboard stat cards (today/week/month) match the cumulative chart. `avg/min/max_watts`, `uptime_percentage`, `downtime_minutes` stay as-is.

## Data Flow

```
samples (live + imported) ─► _parse_power_from_sample (+imported,+bucket_energy_kwh)
  ─► _integrate_samples  (imported→own energy; live→trapezoid, gap>15min→0)
     ├─ get_cumulative_energy_data → per-device total + curve (→ downsample, cost)
     ├─ get_cumulative_energy_total → carry-forward sum of device curves
     └─ get_period_stats → total_energy_kwh
```

## No Migration

Everything is computed on-read; there are no stored aggregates. The fix **retroactively corrects all displayed numbers** (today/week/month/custom, per-device and Total) with no data migration.

## Testing

**Reproduction (TDD, `backend/tests/services/test_energy_service.py`):**
- Two devices, offset live timestamps, a multi-hour sleep gap, and a block of imported hourly buckets. Assert:
  - Per-device: gap energy is **0** (not bridged); imported buckets counted by `bucket_energy_kwh`.
  - A `>15 min` live gap contributes 0; a `≤15 min` gap is trapezoid-integrated.
  - `get_cumulative_energy_total` **equals the sum** of per-device totals (no merge under-count).
  - `get_period_stats.total_energy_kwh` matches the cumulative total for the same range.
- Update existing energy tests whose expected values assumed the old (bridging / avg×hours / merge) math.

## Out of Scope

- **Instant-chart cosmetics during gaps** (a line drawn across a >15-min gap in Instant mode). The energy/cumulative is correct; inserting synthetic 0-watt boundary points for the instant curve is a minor follow-up, not part of this fix.
- **Backfilling real data via Tapo import** — complementary, plugin-specific, user-initiated; the calc fix does not depend on it.
- **Device cumulative-energy-counter approach** — more exact but a larger, Tapo-specific redesign; not needed (gap-cap already matches the imported ground truth).
- No change to retention, storage model, or the custom-range API (#156).

## Expected Result (real data)

Total ≈ **38.4 kWh** (was 67.7); BaluNode ≈ **24.3** (was 62.5); Sven PC ≈ **14.1** (was 29.8).
