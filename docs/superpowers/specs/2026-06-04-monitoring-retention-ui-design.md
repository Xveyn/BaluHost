# Monitoring Retention UI + Smart-Device Sample Retention — Design

**Date:** 2026-06-04
**Branch:** `feat/monitoring-retention-ui` (worktree, based on `origin/main`)
**Status:** Approved design — ready for implementation planning

## Problem

The backend already supports per-metric retention configuration for monitoring
samples (`GET/PUT /api/monitoring/config/retention/{metric}`, admin-only,
validated 1–8760 h), and the frontend API client already ships
`getRetentionConfig`/`updateRetentionConfig` in `client/src/api/monitoring.ts`.
But **no UI calls them** — the retention period is only *displayed* as a badge
in `DatabaseStatsCards.tsx` (route `/admin-db` → Analytics → Stats). Admins
cannot change how long monitoring data is kept without hitting the API directly.

While designing the editor we uncovered a latent data-loss bug around the
`POWER` metric (see below) that must be fixed as part of this work.

## Goals

1. Give admins a UI to configure monitoring data retention per metric type.
2. Cleanly separate the **smart-device sample retention** (plugin-category
   concern) from the monitoring `RetentionManager`, and fix the bug where the
   active cleanup deletes imported Tapo history.

## Non-Goals (YAGNI)

- No configurable UI knob for smart-device / power retention — it stays a fixed
  30-day default (cleanly owned by the smart-device layer, easy to make
  configurable later).
- No changes to how samples are *collected* or *persisted*.
- No new migration to remove the orphan `MonitoringConfig` POWER row (harmless
  dead data).

## Background: the POWER / smart-device bug

- `MetricType.POWER` maps to the `SmartDeviceSample` model
  (`retention_manager.py`). `SmartDeviceSample` (`smart_device_samples`) is a
  **generic** time-series table shared by *all* smart-device plugins
  (`smart_device` is a plugin **category**, not just Tapo).
- The `SmartDevicePoller._persist_samples_to_db` writes **one row per
  capability** per poll. `DeviceCapability` has 5 values:
  `power_monitor`, `switch`, `sensor`, `dimmer`, `color`. So the table holds
  rows for every capability, not just power.
- The **only active cleanup** of this table today is
  `RetentionManager.run_all_cleanup` → `apply_retention_policy(POWER)`, triggered
  periodically by the monitoring orchestrator (`orchestrator.py:288`) and by the
  manual `POST /api/monitoring/cleanup` endpoint (`monitoring.py:769`). It runs a
  raw `DELETE … WHERE timestamp < cutoff` over the **whole** table — including
  rows flagged `imported_from` (manually imported Tapo history that
  `power/energy.py:cleanup_old_samples` is explicitly contracted to preserve and
  is covered by `test_energy_service.py::test_cleanup_preserves_imported_samples`).
- `power/energy.py:cleanup_old_samples` (capability-filtered, preserves imports)
  is **dead wiring** — defined, re-exported, and tested, but never called in
  production.

Net effect: imported power history is silently deleted after 30 days, in
violation of a tested contract; and a naive "delegate POWER to the
power-only cleanup" fix would leave `switch`/`sensor`/`dimmer`/`color` rows
un-cleaned forever (unbounded table growth). The fix therefore must own the
**entire** table while preserving `imported_from`.

`MetricType.POWER` is referenced **only** inside `retention_manager.py` (three
lines), so decoupling it from the monitoring retention machinery is low-risk.

`SmartDevicePoller` runs in the dedicated single **MonitoringWorker** process
(`worker_service.py:105`), so a cleanup triggered from its poll loop runs exactly
once (not once per web worker).

## Design

### A. Decouple POWER from the monitoring RetentionManager

In `backend/app/services/monitoring/retention_manager.py`:

- Remove the `MetricType.POWER` entries from `DEFAULT_RETENTION`, `METRIC_MODELS`
  and `ROW_SIZES`.
- `run_all_cleanup` iterates `METRIC_MODELS.keys()` instead of `for metric_type in
  MetricType`, so POWER is never cleaned by this path.

In `backend/app/api/routes/monitoring.py`:

- `get_retention_config` (`GET /config/retention`) iterates `METRIC_MODELS.keys()`
  instead of the `MetricType` enum, so `power` is no longer returned. The editor
  therefore never sees POWER and needs **no client-side filter**.
- `update_retention_config` (`PUT /config/retention/{metric}`): **needs an
  explicit guard**. `MetricType("power")` still succeeds (POWER remains a valid
  enum member), so the existing `ValueError` catch does **not** reject it — it
  would silently create a dead POWER config row. Add a check that rejects any
  metric not in `METRIC_MODELS` (i.e. `mt not in METRIC_MODELS`) with HTTP 400, so
  `PUT …/power` is rejected like an unmanaged metric.

Consequences (intended):

- `get_database_stats`/`estimate_database_size` already iterate `METRIC_MODELS`,
  so the **Power card disappears from the Analytics → Stats tab**. The
  `smart_device_samples` table size remains visible in the Analytics → **Storage**
  tab (all-tables view), so no DB-size visibility is lost.
- The previously-created `MonitoringConfig` row for POWER (if any) becomes
  harmless dead data; left in place.

### B. Smart-device sample retention (plugin-category-wide)

New module `backend/app/plugins/smart_device/retention.py` (or a method on the
poller) owning the cleanup for the shared `smart_device_samples` table:

```python
SMART_DEVICE_SAMPLE_RETENTION_DAYS = 30  # fixed default; easy to make configurable later

def cleanup_old_smart_device_samples(db: Session, days_to_keep: int = SMART_DEVICE_SAMPLE_RETENTION_DAYS) -> int:
    """Delete smart_device_samples older than cutoff across ALL capabilities,
    preserving manually-imported rows (data_json contains "imported_from")."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    deleted = db.query(SmartDeviceSample).filter(
        SmartDeviceSample.timestamp < cutoff,
        ~SmartDeviceSample.data_json.contains('"imported_from"'),
    ).delete(synchronize_session=False)
    db.commit()
    return deleted
```

- This **replaces** the dead `power/energy.py:cleanup_old_samples`. Its tests in
  `test_energy_service.py` move/adapt to the new function (drop the
  `capability == "power_monitor"` assumption; the import-preservation assertion
  stays and is the key regression guard).
- **Trigger:** a time-based gate inside `SmartDevicePoller._poll_loop`, analogous
  to the existing `_DB_PERSIST_INTERVAL` gate, running roughly once per day. It
  runs in the single MonitoringWorker process. (If the poller is idle because no
  smart-device plugins are installed, there are no new samples to clean — a
  follow-up startup cleanup is unnecessary for the fixed-default scope.)

Net behaviour vs. today: identical ~30-day cleanup of the table, **minus** the
deletion of imported rows. No regression for `switch`/`sensor`/`dimmer`/`color`.

### C. Frontend — new "Retention" Analytics tab

In `client/src/pages/AdminDatabase.tsx`:

- Extend `AnalyticsTabType` with `'retention'`; add a tab entry to `analyticsTabs`
  (icon `Timer` or `Clock`); add `case 'retention': return <RetentionSettings />`
  to `renderAnalyticsContent`.

New component `client/src/components/admin/RetentionSettings.tsx`:

- On mount, calls `getRetentionConfig()` (returns the managed metrics only — no
  `power`, thanks to A): CPU, Memory, Network, Disk-IO, Process, Uptime, GPU.
- Per row: metric icon + label, a **number input in hours**, a live `≈ N Tage`
  hint, and quick **preset chips**: 1 / 7 / 14 / 30 / 90 days
  (= 24 / 168 / 336 / 720 / 2160 h). Shows the default where relevant.
- **Dirty tracking + a single "Speichern" button** that issues
  `updateRetentionConfig(metric, hours)` only for changed rows, then refreshes
  values. Client clamps to 1–8760 h and disables save on invalid input; backend
  validates too (400/422 → toast). Success/error via `react-hot-toast` +
  `handleApiError`.
- Admin-only by placement (the page is admin-gated; backend enforces
  `get_current_admin`).

New shared module `client/src/components/admin/metricConfig.ts`:

- Hoist the metric → `{ labelKey, icon, color }` map currently inline in
  `DatabaseStatsCards.tsx`, and **add `uptime` and `gpu`** (presently missing, so
  they render with a fallback). `DatabaseStatsCards.tsx` imports from this module
  (small refactor); `RetentionSettings.tsx` reuses it.

`client/src/api/monitoring.ts`: no change (functions already exist).

### D. i18n

Add keys to `client/src/i18n/locales/de/admin.json` and `en/admin.json`:
retention tab title, section hint, preset labels, the `≈ {{count}} Tage` hint,
save button, validation message, success/error toasts. Add `uptime`/`gpu` metric
labels under the existing `databaseStats.metrics.*` namespace.

### E. Error handling

- Client: clamp 1–8760, disable save when invalid, toast on API error, keep the
  edited value on failure so the user can correct it.
- Backend: existing `set_retention` `ValueError` (→ 400) and Pydantic validation
  (→ 422) are unchanged; the invalid-metric guard covers `power`.

## Testing

**Backend (pytest):**

- `RetentionManager` no longer knows POWER: `run_all_cleanup` does not touch
  `smart_device_samples`; `GET /config/retention` does not list `power`;
  `PUT /config/retention/power` → 400. (Extend `tests/monitoring/test_collectors.py`
  and `tests/api/test_monitoring_routes.py`.)
- New smart-device retention: deletes rows across all capabilities older than the
  cutoff **but preserves `imported_from`** (move/adapt
  `tests/services/test_energy_service.py` cleanup tests to the new function).
- Poller trigger gate fires on the expected cadence (unit test the gate logic;
  the gate is time-based like `_DB_PERSIST_INTERVAL`).

**Frontend (Vitest):**

- `RetentionSettings` renders the managed metrics and **no `power` row**.
- A preset chip sets the corresponding hours value and the `≈ Tage` hint updates.
- "Speichern" calls `updateRetentionConfig` with the correct `(metric, hours)`
  for each changed row and not for unchanged rows.
- Invalid input (0 or >8760) disables save.

**Manual smoketest:**

1. `python start_dev.py`
2. `/admin-db` → Analytics → **Retention**: set CPU to 24 h, Save, reload —
   value persists.
3. Confirm `power` is not listed in the editor.
4. Analytics → **Storage**: `smart_device_samples` still appears in the
   all-tables view.

## Files Touched

**Backend**
- `app/services/monitoring/retention_manager.py` — drop POWER from maps; iterate `METRIC_MODELS`.
- `app/api/routes/monitoring.py` — iterate `METRIC_MODELS` in `get_retention_config`; confirm `power` rejected by `update_retention_config`.
- `app/plugins/smart_device/retention.py` *(new)* — category-wide cleanup preserving imports.
- `app/plugins/smart_device/poller.py` — time-based cleanup trigger in the poll loop.
- `app/services/power/energy.py` — remove the dead `cleanup_old_samples` (replaced by B).
- Tests: `tests/monitoring/test_collectors.py`, `tests/api/test_monitoring_routes.py`, `tests/services/test_energy_service.py` (+ new smart-device retention tests).

**Frontend**
- `src/pages/AdminDatabase.tsx` — new Retention sub-tab.
- `src/components/admin/RetentionSettings.tsx` *(new)*.
- `src/components/admin/metricConfig.ts` *(new)* + `src/components/admin/DatabaseStatsCards.tsx` (use shared map; add uptime/gpu).
- `src/i18n/locales/{de,en}/admin.json`.
- Frontend tests under `src/__tests__/`.

## Open Questions

None at spec-writing time.
