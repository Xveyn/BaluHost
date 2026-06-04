# Monitoring Retention UI + Smart-Device Sample Retention — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give admins a UI to configure monitoring data retention per metric type, and cleanly move smart-device sample retention out of the monitoring `RetentionManager` into the smart-device layer (fixing a data-loss bug that deletes imported Tapo history).

**Architecture:** Backend already exposes `GET/PUT /api/monitoring/config/retention`. We (1) drop `POWER` from the monitoring `RetentionManager` so the generic cleanup no longer touches the shared `smart_device_samples` table, (2) add a category-wide cleanup owned by the smart-device layer (preserves `imported_from`, fixed 30-day default) triggered from the `SmartDevicePoller` loop in the MonitoringWorker process, and (3) wire the existing (unused) frontend API into a new "Retention" tab on `/admin-db`.

**Tech Stack:** Python / FastAPI / SQLAlchemy / pytest (backend); React + TypeScript + Vite / Vitest / react-i18next / react-hot-toast (frontend).

**Spec:** `docs/superpowers/specs/2026-06-04-monitoring-retention-ui-design.md`

**Worktree:** Already created from `origin/main` at `.claude/worktrees/feat+monitoring-retention-ui` (branch `worktree-feat+monitoring-retention-ui`). Run all commands from the worktree root. Backend commands assume `cd backend`; frontend assume `cd client`.

---

## File Structure

**Backend**
- `backend/app/services/monitoring/retention_manager.py` — drop POWER from `DEFAULT_RETENTION`/`METRIC_MODELS`/`ROW_SIZES`; iterate `METRIC_MODELS` in `run_all_cleanup`.
- `backend/app/api/routes/monitoring.py` — iterate `METRIC_MODELS` in `get_retention_config`; reject metrics not in `METRIC_MODELS` in `update_retention_config`.
- `backend/app/plugins/smart_device/retention.py` *(new)* — `cleanup_old_smart_device_samples()` (all capabilities, preserves imports).
- `backend/app/plugins/smart_device/poller.py` — daily cleanup gate in the poll loop.
- `backend/app/services/power/energy.py` — remove the dead `cleanup_old_samples`.
- `backend/app/services/power/__init__.py` — drop the `cleanup_old_samples` import/export.
- Tests: `backend/tests/monitoring/test_collectors.py`, `backend/tests/api/test_monitoring_routes.py`, `backend/tests/plugins/test_smart_device_retention.py` *(new)*, `backend/tests/services/test_energy_service.py` (remove migrated tests).

**Frontend**
- `client/src/components/admin/metricConfig.ts` *(new)* — shared metric → label/icon/color map (incl. `uptime`, `gpu`).
- `client/src/components/admin/DatabaseStatsCards.tsx` — import the shared map.
- `client/src/components/admin/RetentionSettings.tsx` *(new)* — the editor.
- `client/src/pages/AdminDatabase.tsx` — new "Retention" analytics sub-tab.
- `client/src/i18n/locales/de/admin.json`, `client/src/i18n/locales/en/admin.json` — new keys.
- `client/src/__tests__/components/admin/RetentionSettings.test.tsx` *(new)*.

---

## Task 1: Backend — Decouple POWER from the monitoring RetentionManager

**Files:**
- Modify: `backend/app/services/monitoring/retention_manager.py`
- Test: `backend/tests/monitoring/test_collectors.py`

- [ ] **Step 1: Write the failing test**

Append to the retention manager test class in `backend/tests/monitoring/test_collectors.py` (the class containing `test_run_all_cleanup`, around line 417):

```python
    def test_power_not_managed_by_retention_manager(self, db_session):
        """POWER must not be a metric the monitoring RetentionManager owns."""
        from app.services.monitoring.retention_manager import METRIC_MODELS
        from app.models.monitoring import MetricType

        assert MetricType.POWER not in METRIC_MODELS

    def test_run_all_cleanup_leaves_smart_device_samples(self, db_session):
        """run_all_cleanup must not delete smart_device_samples (owned elsewhere)."""
        import json
        from datetime import datetime, timezone, timedelta
        from app.models.smart_device import SmartDevice, SmartDeviceSample
        from app.services.monitoring.retention_manager import RetentionManager

        device = SmartDevice(
            name="Test Plug", plugin_name="tapo_smart_plug",
            device_type_id="tapo_p110", address="192.168.1.50",
            capabilities=["power_monitor"], is_active=True, is_online=True,
            created_by_user_id=1,
        )
        db_session.add(device)
        db_session.commit()
        db_session.refresh(device)

        old = SmartDeviceSample(
            device_id=device.id, capability="power_monitor",
            data_json=json.dumps({"watts": 5.0}),
            timestamp=datetime.now(timezone.utc) - timedelta(days=400),
        )
        db_session.add(old)
        db_session.commit()

        results = RetentionManager().run_all_cleanup(db_session)

        assert "power" not in results
        assert db_session.query(SmartDeviceSample).count() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/monitoring/test_collectors.py -k "power_not_managed or run_all_cleanup_leaves" -v`
Expected: FAIL — `MetricType.POWER` is still in `METRIC_MODELS`; the 400-day smart-device row is deleted.

- [ ] **Step 3: Remove POWER from the RetentionManager maps**

In `backend/app/services/monitoring/retention_manager.py`:

Delete the unused import (line ~26):
```python
from app.models.smart_device import SmartDeviceSample
```

In `DEFAULT_RETENTION`, delete the line:
```python
    MetricType.POWER: 720,     # 30 days
```

In `METRIC_MODELS`, delete the line:
```python
    MetricType.POWER: SmartDeviceSample,
```

In `ROW_SIZES` (inside `estimate_database_size`), delete the line:
```python
            MetricType.POWER: 60,
```

- [ ] **Step 4: Make `run_all_cleanup` iterate managed metrics only**

In the same file, in `run_all_cleanup`, change:
```python
        for metric_type in MetricType:
            deleted = self.apply_retention_policy(db, metric_type)
            results[metric_type.value] = deleted
```
to:
```python
        for metric_type in METRIC_MODELS:
            deleted = self.apply_retention_policy(db, metric_type)
            results[metric_type.value] = deleted
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/monitoring/test_collectors.py -v`
Expected: PASS (new tests plus all existing retention tests — `test_get_database_stats`, `test_run_all_cleanup`, etc. still pass; they don't assert on power).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/monitoring/retention_manager.py backend/tests/monitoring/test_collectors.py
git commit -m "refactor(monitoring): drop POWER from RetentionManager (smart-device samples owned elsewhere)"
```

---

## Task 2: Backend — Route: drop POWER from list, reject it on update

**Files:**
- Modify: `backend/app/api/routes/monitoring.py:635-688`
- Test: `backend/tests/api/test_monitoring_routes.py:210-243`

- [ ] **Step 1: Write the failing tests**

Append to `class TestRetentionConfigEndpoints` in `backend/tests/api/test_monitoring_routes.py` (after `test_update_retention_invalid_metric`, line ~243):

```python
    def test_retention_config_excludes_power(self, client: TestClient, admin_headers: dict):
        """POWER is no longer a monitoring-managed metric and must not be listed."""
        response = client.get("/api/monitoring/config/retention", headers=admin_headers)
        assert response.status_code == 200
        metric_types = {c["metric_type"] for c in response.json()["configs"]}
        assert "power" not in metric_types
        assert "cpu" in metric_types

    def test_update_retention_power_rejected(self, client: TestClient, admin_headers: dict):
        """Updating retention for the unmanaged POWER metric returns 400."""
        response = client.put(
            "/api/monitoring/config/retention/power",
            json={"retention_hours": 48},
            headers=admin_headers,
        )
        assert response.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_monitoring_routes.py -k "excludes_power or power_rejected" -v`
Expected: FAIL — `power` is still listed (the route iterates `MetricType`), and `PUT …/power` succeeds with 200 (`MetricType("power")` is valid).

- [ ] **Step 3: Update `get_retention_config` to iterate managed metrics**

In `backend/app/api/routes/monitoring.py`, add the import near the other monitoring-service imports at the top of the file (find the existing `from app.services.monitoring...` imports and add this line):
```python
from app.services.monitoring.retention_manager import METRIC_MODELS
```

In `get_retention_config`, change:
```python
    for metric_type in MetricType:
        config = orchestrator.retention_manager.get_config(db, metric_type)
```
to:
```python
    for metric_type in METRIC_MODELS:
        config = orchestrator.retention_manager.get_config(db, metric_type)
```

- [ ] **Step 4: Reject unmanaged metrics in `update_retention_config`**

In `update_retention_config`, change:
```python
    try:
        mt = MetricType(metric_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid metric type: {metric_type}")
```
to:
```python
    try:
        mt = MetricType(metric_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid metric type: {metric_type}")

    if mt not in METRIC_MODELS:
        raise HTTPException(status_code=400, detail=f"Metric type not configurable: {metric_type}")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_monitoring_routes.py -v`
Expected: PASS (new tests + existing `test_retention_config_returns_data`, `test_update_retention_invalid_metric`, etc.).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/monitoring.py backend/tests/api/test_monitoring_routes.py
git commit -m "feat(monitoring): retention API excludes POWER and rejects it on update"
```

---

## Task 3: Backend — New smart-device sample retention

**Files:**
- Create: `backend/app/plugins/smart_device/retention.py`
- Test: `backend/tests/plugins/test_smart_device_retention.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/plugins/test_smart_device_retention.py`:

```python
"""Tests for category-wide smart-device sample retention."""
import json
from datetime import datetime, timezone, timedelta

import pytest

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.smart_device.retention import (
    cleanup_old_smart_device_samples,
    SMART_DEVICE_SAMPLE_RETENTION_DAYS,
)


@pytest.fixture
def device(db_session):
    d = SmartDevice(
        name="Test Plug", plugin_name="tapo_smart_plug",
        device_type_id="tapo_p110", address="192.168.1.50",
        capabilities=["power_monitor", "switch"], is_active=True,
        is_online=True, created_by_user_id=1,
    )
    db_session.add(d)
    db_session.commit()
    db_session.refresh(d)
    return d


def _add(db_session, device_id, capability, days_ago, extra=None):
    data = {"v": 1}
    if extra:
        data.update(extra)
    db_session.add(SmartDeviceSample(
        device_id=device_id, capability=capability,
        data_json=json.dumps(data),
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    ))
    db_session.commit()


def test_default_is_30_days():
    assert SMART_DEVICE_SAMPLE_RETENTION_DAYS == 30


def test_deletes_all_capabilities_older_than_cutoff(db_session, device):
    _add(db_session, device.id, "power_monitor", days_ago=60)
    _add(db_session, device.id, "switch", days_ago=60)
    _add(db_session, device.id, "power_monitor", days_ago=1)

    deleted = cleanup_old_smart_device_samples(db_session, days_to_keep=30)

    assert deleted == 2
    assert db_session.query(SmartDeviceSample).count() == 1


def test_preserves_imported_rows(db_session, device):
    _add(db_session, device.id, "power_monitor", days_ago=60)  # live, old -> deleted
    _add(db_session, device.id, "power_monitor", days_ago=60,
         extra={"imported_from": "tapo_history"})              # imported -> kept

    deleted = cleanup_old_smart_device_samples(db_session, days_to_keep=30)

    assert deleted == 1
    remaining = db_session.query(SmartDeviceSample).all()
    assert len(remaining) == 1
    assert json.loads(remaining[0].data_json).get("imported_from") == "tapo_history"


def test_nothing_to_delete(db_session, device):
    _add(db_session, device.id, "switch", days_ago=1)
    assert cleanup_old_smart_device_samples(db_session, days_to_keep=30) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py -v`
Expected: FAIL — `app.plugins.smart_device.retention` does not exist.

- [ ] **Step 3: Implement the cleanup module**

Create `backend/app/plugins/smart_device/retention.py`:

```python
"""Retention for the shared `smart_device_samples` time-series table.

`smart_device_samples` is written by the SmartDevicePoller for EVERY capability
of EVERY smart_device plugin (power_monitor, switch, sensor, dimmer, color), so
retention is a plugin-category concern — not a monitoring "power metric" one.

Rows flagged ``imported_from`` in their JSON (manually imported history, e.g.
Tapo energy history) are preserved regardless of age.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.smart_device import SmartDeviceSample

logger = logging.getLogger(__name__)

# Fixed default; can be made configurable later without changing callers.
SMART_DEVICE_SAMPLE_RETENTION_DAYS = 30


def cleanup_old_smart_device_samples(
    db: Session,
    days_to_keep: int = SMART_DEVICE_SAMPLE_RETENTION_DAYS,
) -> int:
    """Delete smart_device_samples older than the cutoff across ALL capabilities.

    Imported rows (``data_json`` contains ``"imported_from"``) are preserved.

    Returns the number of deleted rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)

    deleted = db.query(SmartDeviceSample).filter(
        SmartDeviceSample.timestamp < cutoff,
        ~SmartDeviceSample.data_json.contains('"imported_from"'),
    ).delete(synchronize_session=False)

    db.commit()
    if deleted:
        logger.info(
            "Cleaned up %d smart_device_samples older than %d days (imported rows preserved)",
            deleted, days_to_keep,
        )
    return deleted
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/smart_device/retention.py backend/tests/plugins/test_smart_device_retention.py
git commit -m "feat(smart-device): category-wide sample retention preserving imported rows"
```

---

## Task 4: Backend — Remove the dead `energy.cleanup_old_samples`

**Files:**
- Modify: `backend/app/services/power/energy.py` (remove `cleanup_old_samples`, ~lines 307-335)
- Modify: `backend/app/services/power/__init__.py` (drop import + `__all__` entry)
- Modify: `backend/tests/services/test_energy_service.py` (remove migrated tests + import)

- [ ] **Step 1: Confirm there are no other callers**

Run: `cd backend && python -c "import app.services.power.energy as e; print(hasattr(e, 'cleanup_old_samples'))"`
Expected: prints `True` (it still exists now). After removal this command will print `False` (Step 5).

- [ ] **Step 2: Remove the function from `energy.py`**

In `backend/app/services/power/energy.py`, delete the entire `cleanup_old_samples` function (the `def cleanup_old_samples(db: Session, days_to_keep: int = 30) -> int:` block and its body, ~lines 307-335). Leave `_POWER_CAPABILITY` and all other functions intact.

- [ ] **Step 3: Drop the export in `power/__init__.py`**

In `backend/app/services/power/__init__.py`:
- In the `from app.services.power.energy import (...)` block, delete the line `    cleanup_old_samples,`.
- In `__all__`, delete the line `    "cleanup_old_samples",`.

- [ ] **Step 4: Remove the migrated tests**

In `backend/tests/services/test_energy_service.py`:
- Remove `cleanup_old_samples` from the imports at the top of the file.
- Delete the three tests now covered by Task 3: `test_cleanup_old_samples`, `test_cleanup_nothing_old`, `test_cleanup_preserves_imported_samples`.

- [ ] **Step 5: Verify removal and run the affected suites**

Run: `cd backend && python -c "import app.services.power.energy as e; print(hasattr(e, 'cleanup_old_samples'))"`
Expected: `False`

Run: `cd backend && python -m pytest tests/services/test_energy_service.py tests/services/ -q`
Expected: PASS (no import errors, no references to the removed function).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/energy.py backend/app/services/power/__init__.py backend/tests/services/test_energy_service.py
git commit -m "refactor(power): remove dead energy.cleanup_old_samples (replaced by smart-device retention)"
```

---

## Task 5: Backend — Trigger the cleanup from the poller loop

**Files:**
- Modify: `backend/app/plugins/smart_device/poller.py`
- Test: `backend/tests/plugins/test_smart_device_retention.py` (append)

- [ ] **Step 1: Write the failing test for the gate**

Append to `backend/tests/plugins/test_smart_device_retention.py`:

```python
def test_poller_cleanup_gate():
    """The poller only runs cleanup once per interval."""
    from app.plugins.smart_device.poller import SmartDevicePoller, _SAMPLE_CLEANUP_INTERVAL

    poller = SmartDevicePoller()
    # Never cleaned -> should run immediately.
    assert poller._should_cleanup_samples(now=0.0) is True
    poller._last_sample_cleanup = 1000.0
    # Too soon.
    assert poller._should_cleanup_samples(now=1000.0 + _SAMPLE_CLEANUP_INTERVAL - 1) is False
    # Interval elapsed.
    assert poller._should_cleanup_samples(now=1000.0 + _SAMPLE_CLEANUP_INTERVAL) is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py::test_poller_cleanup_gate -v`
Expected: FAIL — `_SAMPLE_CLEANUP_INTERVAL` / `_should_cleanup_samples` do not exist.

- [ ] **Step 3: Add the interval constant**

In `backend/app/plugins/smart_device/poller.py`, below the existing `_DB_PERSIST_INTERVAL = 60.0` (line ~26), add:

```python
# How often to clean up old smart_device_samples (seconds).
_SAMPLE_CLEANUP_INTERVAL = 86400.0  # daily
```

- [ ] **Step 4: Add the cleanup-state field**

In `SmartDevicePoller.__init__`, after `self._last_db_persist: Dict[str, float] = {}` (line ~67), add:

```python
        # Timestamp of last smart_device_samples cleanup (0.0 = never)
        self._last_sample_cleanup: float = 0.0
```

- [ ] **Step 5: Add the gate predicate and the cleanup helper**

In `SmartDevicePoller`, add these two methods (e.g. just after `_persist_samples_to_db`):

```python
    def _should_cleanup_samples(self, now: float) -> bool:
        """True when a sample cleanup is due (shared across all plugin loops)."""
        return now - self._last_sample_cleanup >= _SAMPLE_CLEANUP_INTERVAL

    async def _maybe_cleanup_samples(self) -> None:
        """Run the category-wide sample cleanup if the interval has elapsed."""
        if self._db_session_factory is None:
            return
        if not self._should_cleanup_samples(time.time()):
            return
        self._last_sample_cleanup = time.time()
        try:
            from app.plugins.smart_device.retention import cleanup_old_smart_device_samples
            db = self._db_session_factory()
            try:
                cleanup_old_smart_device_samples(db)
            finally:
                db.close()
        except Exception as exc:
            logger.debug("SmartDevicePoller: sample cleanup failed: %s", exc)
```

- [ ] **Step 6: Call the helper from the poll loop**

In `_poll_loop`, immediately after the DB-persist block (after `self._last_db_persist[plugin_name] = time.time()`, line ~313) and before the "Sleep for the remainder" comment, add:

```python
            # Periodically clean up old samples (runs once per interval, globally)
            await self._maybe_cleanup_samples()
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py -v`
Expected: PASS (all Task 3 tests + `test_poller_cleanup_gate`).

- [ ] **Step 8: Commit**

```bash
git add backend/app/plugins/smart_device/poller.py backend/tests/plugins/test_smart_device_retention.py
git commit -m "feat(smart-device): trigger daily sample cleanup from poller loop"
```

---

## Task 6: Frontend — Shared metric config module (+ uptime/gpu)

**Files:**
- Create: `client/src/components/admin/metricConfig.ts`
- Modify: `client/src/components/admin/DatabaseStatsCards.tsx:5,10-17,40`

- [ ] **Step 1: Create the shared module**

Create `client/src/components/admin/metricConfig.ts`:

```ts
import type { ElementType } from 'react'
import { Cpu, MemoryStick, Network, HardDrive, Activity, Zap, Clock, MonitorPlay, Database } from 'lucide-react'

export interface MetricDisplayConfig {
  labelKey: string
  icon: ElementType
  color: string
}

export const METRIC_CONFIG: Record<string, MetricDisplayConfig> = {
  cpu: { labelKey: 'admin:databaseStats.metrics.cpu', icon: Cpu, color: 'blue' },
  memory: { labelKey: 'admin:databaseStats.metrics.memory', icon: MemoryStick, color: 'emerald' },
  network: { labelKey: 'admin:databaseStats.metrics.network', icon: Network, color: 'purple' },
  disk_io: { labelKey: 'admin:databaseStats.metrics.diskIo', icon: HardDrive, color: 'amber' },
  process: { labelKey: 'admin:databaseStats.metrics.process', icon: Activity, color: 'rose' },
  power: { labelKey: 'admin:databaseStats.metrics.power', icon: Zap, color: 'amber' },
  uptime: { labelKey: 'admin:databaseStats.metrics.uptime', icon: Clock, color: 'blue' },
  gpu: { labelKey: 'admin:databaseStats.metrics.gpu', icon: MonitorPlay, color: 'emerald' },
}

export const DEFAULT_METRIC_CONFIG: MetricDisplayConfig = {
  labelKey: '',
  icon: Database,
  color: 'slate',
}
```

- [ ] **Step 2: Use the shared module in `DatabaseStatsCards.tsx`**

In `client/src/components/admin/DatabaseStatsCards.tsx`:

Replace the inline `METRIC_CONFIG` definition (lines 10-17) with an import. At the top with the other imports (near line 5), add:
```ts
import { METRIC_CONFIG, DEFAULT_METRIC_CONFIG } from './metricConfig'
```
Delete the whole `export const METRIC_CONFIG: Record<...> = { ... }` block (lines 10-17).

In `MetricCard`, change the fallback (line 40):
```ts
  const config = METRIC_CONFIG[metricType] || { labelKey: metricType, icon: Database, color: 'slate' }
```
to:
```ts
  const config = METRIC_CONFIG[metricType] || DEFAULT_METRIC_CONFIG
```
(`Database` is still imported at the top from lucide-react and remains used by the skeleton/empty states, so leave that import as-is.)

- [ ] **Step 3: Typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: clean (no errors).

- [ ] **Step 4: Commit**

```bash
git add client/src/components/admin/metricConfig.ts client/src/components/admin/DatabaseStatsCards.tsx
git commit -m "refactor(admin): hoist metric config to shared module, add uptime/gpu"
```

---

## Task 7: Frontend — i18n keys (de + en)

**Files:**
- Modify: `client/src/i18n/locales/de/admin.json`
- Modify: `client/src/i18n/locales/en/admin.json`

- [ ] **Step 1: Add the new Retention tab label + metric labels (EN)**

In `client/src/i18n/locales/en/admin.json`:

In `database.tabs` (lines 134-140), add a `retention` entry after `maintenance`:
```json
    "tabs": {
      "tables": "Tables",
      "stats": "Stats",
      "storage": "Storage",
      "history": "History",
      "maintenance": "Maintenance",
      "retention": "Retention"
    },
```

In `databaseStats.metrics` (lines 261-268), add `uptime` and `gpu` after `power`:
```json
    "metrics": {
      "cpu": "CPU",
      "memory": "Memory",
      "network": "Network",
      "diskIo": "Disk I/O",
      "process": "Process",
      "power": "Power",
      "uptime": "Uptime",
      "gpu": "GPU"
    },
```

Add a new top-level `retentionSettings` block immediately after the `databaseStats` object (after its closing `}` on line ~281, before `"storageAnalysis"`):
```json
  "retentionSettings": {
    "title": "Data Retention",
    "hint": "How long monitoring samples are kept in the database before automatic cleanup.",
    "hours": "h",
    "approxDays": "≈ {{count}} days",
    "presetDays_one": "{{count}} day",
    "presetDays_other": "{{count}} days",
    "save": "Save",
    "saved": "Retention updated",
    "saveFailed": "Failed to update retention",
    "loading": "Loading retention settings...",
    "validation": "Enter a value between 1 and 8760 hours."
  },
```

- [ ] **Step 2: Add the same keys (DE)**

In `client/src/i18n/locales/de/admin.json`:

In `database.tabs` (lines 134-140), add after `maintenance`:
```json
      "retention": "Aufbewahrung"
```
(add a comma to the previous `"maintenance"` line).

In `databaseStats.metrics`, add after `power`:
```json
      "uptime": "Betriebszeit",
      "gpu": "GPU"
```
(add a comma to the previous `"power"` line).

Add the `retentionSettings` block after the `databaseStats` object:
```json
  "retentionSettings": {
    "title": "Datenaufbewahrung",
    "hint": "Wie lange Monitoring-Samples in der Datenbank behalten werden, bevor sie automatisch bereinigt werden.",
    "hours": "h",
    "approxDays": "≈ {{count}} Tage",
    "presetDays_one": "{{count}} Tag",
    "presetDays_other": "{{count}} Tage",
    "save": "Speichern",
    "saved": "Aufbewahrung aktualisiert",
    "saveFailed": "Aufbewahrung konnte nicht aktualisiert werden",
    "loading": "Lade Aufbewahrungseinstellungen...",
    "validation": "Bitte einen Wert zwischen 1 und 8760 Stunden eingeben."
  },
```

- [ ] **Step 3: Validate JSON**

Run: `cd client && node -e "require('./src/i18n/locales/de/admin.json'); require('./src/i18n/locales/en/admin.json'); console.log('ok')"`
Expected: prints `ok` (no JSON syntax errors).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/admin.json client/src/i18n/locales/en/admin.json
git commit -m "i18n(admin): retention settings + uptime/gpu metric labels"
```

---

## Task 8: Frontend — RetentionSettings component

**Files:**
- Create: `client/src/components/admin/RetentionSettings.tsx`
- Test: `client/src/__tests__/components/admin/RetentionSettings.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/admin/RetentionSettings.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../../api/monitoring', () => ({
  getRetentionConfig: vi.fn(),
  updateRetentionConfig: vi.fn(),
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
const stableT = (k: string, opts?: Record<string, unknown>) =>
  opts && 'count' in opts ? `${k}:${String(opts.count)}` : k;
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}));

import RetentionSettings from '../../../components/admin/RetentionSettings';
import * as api from '../../../api/monitoring';

const CONFIGS = {
  configs: [
    { metric_type: 'cpu', retention_hours: 168, db_persist_interval: 12, is_enabled: true, samples_cleaned: 0 },
    { metric_type: 'gpu', retention_hours: 168, db_persist_interval: 12, is_enabled: true, samples_cleaned: 0 },
  ],
};

describe('RetentionSettings', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders one row per managed metric and no power row', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());
    expect(screen.getByTestId('retention-input-gpu')).toBeTruthy();
    expect(screen.queryByTestId('retention-input-power')).toBeNull();
  });

  it('applies a preset value to the input', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());
    fireEvent.click(screen.getByTestId('retention-preset-cpu-720'));
    expect((screen.getByTestId('retention-input-cpu') as HTMLInputElement).value).toBe('720');
  });

  it('saves only the changed metrics', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    (api.updateRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());

    fireEvent.change(screen.getByTestId('retention-input-cpu'), { target: { value: '24' } });
    fireEvent.click(screen.getByTestId('retention-save'));

    await waitFor(() => expect(api.updateRetentionConfig).toHaveBeenCalledTimes(1));
    expect(api.updateRetentionConfig).toHaveBeenCalledWith('cpu', 24);
  });

  it('disables save when the value is out of range', async () => {
    (api.getRetentionConfig as ReturnType<typeof vi.fn>).mockResolvedValue(CONFIGS);
    render(<RetentionSettings />);
    await waitFor(() => expect(screen.getByTestId('retention-input-cpu')).toBeTruthy());
    fireEvent.change(screen.getByTestId('retention-input-cpu'), { target: { value: '99999' } });
    expect((screen.getByTestId('retention-save') as HTMLButtonElement).disabled).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/admin/RetentionSettings.test.tsx`
Expected: FAIL — the component module does not exist.

- [ ] **Step 3: Implement the component**

Create `client/src/components/admin/RetentionSettings.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import toast from 'react-hot-toast'
import { RefreshCw, Save } from 'lucide-react'
import { getRetentionConfig, updateRetentionConfig } from '../../api/monitoring'
import type { RetentionConfig } from '../../api/monitoring'
import { METRIC_CONFIG, DEFAULT_METRIC_CONFIG } from './metricConfig'

const MIN_HOURS = 1
const MAX_HOURS = 8760
const PRESETS = [
  { days: 1, hours: 24 },
  { days: 7, hours: 168 },
  { days: 14, hours: 336 },
  { days: 30, hours: 720 },
  { days: 90, hours: 2160 },
]

const hoursToDays = (hours: number): number => Math.round((hours / 24) * 10) / 10
const isValid = (v: number): boolean => Number.isInteger(v) && v >= MIN_HOURS && v <= MAX_HOURS

export default function RetentionSettings() {
  const { t } = useTranslation('admin')
  const [configs, setConfigs] = useState<RetentionConfig[]>([])
  const [edited, setEdited] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getRetentionConfig()
      setConfigs(data.configs)
      setEdited({})
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load retention config')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const valueFor = (c: RetentionConfig): number =>
    c.metric_type in edited ? edited[c.metric_type] : c.retention_hours

  const setValue = (metric: string, hours: number) =>
    setEdited(prev => ({ ...prev, [metric]: hours }))

  const dirty = useMemo(
    () => configs.filter(c => c.metric_type in edited && edited[c.metric_type] !== c.retention_hours),
    [configs, edited],
  )
  const hasInvalid = useMemo(() => dirty.some(c => !isValid(edited[c.metric_type])), [dirty, edited])

  const handleSave = async () => {
    if (dirty.length === 0 || hasInvalid) return
    setSaving(true)
    try {
      await Promise.all(dirty.map(c => updateRetentionConfig(c.metric_type, edited[c.metric_type])))
      toast.success(t('retentionSettings.saved'))
      await load()
    } catch {
      toast.error(t('retentionSettings.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-3">
        <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
        <span className="text-slate-400 text-sm">{t('retentionSettings.loading')}</span>
      </div>
    )
  }

  if (error) {
    return <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-red-400 text-sm">{error}</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">{t('retentionSettings.title')}</h3>
          <p className="text-xs text-slate-400 mt-1">{t('retentionSettings.hint')}</p>
        </div>
        <button
          data-testid="retention-save"
          onClick={handleSave}
          disabled={saving || dirty.length === 0 || hasInvalid}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 border border-blue-500/40 text-blue-300 hover:bg-blue-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-sm"
        >
          <Save className={`w-4 h-4 ${saving ? 'animate-pulse' : ''}`} />
          {t('retentionSettings.save')}
        </button>
      </div>

      <div className="space-y-3">
        {configs.map(c => {
          const cfg = METRIC_CONFIG[c.metric_type] || DEFAULT_METRIC_CONFIG
          const Icon = cfg.icon
          const value = valueFor(c)
          const invalid = !isValid(value)
          return (
            <div key={c.metric_type} className="card !p-4">
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                <div className="flex items-center gap-2 sm:w-48">
                  <Icon className="w-4 h-4 text-slate-300" />
                  <span className="text-sm font-medium text-white">
                    {cfg.labelKey ? t(cfg.labelKey) : c.metric_type}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    data-testid={`retention-input-${c.metric_type}`}
                    type="number"
                    min={MIN_HOURS}
                    max={MAX_HOURS}
                    value={value}
                    onChange={e => setValue(c.metric_type, Number(e.target.value))}
                    className={`w-28 bg-slate-800/60 border rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none ${invalid ? 'border-red-500/60' : 'border-slate-700/50 focus:border-blue-500/50'}`}
                  />
                  <span className="text-xs text-slate-400">{t('retentionSettings.hours')}</span>
                  <span className="text-xs text-sky-400">
                    {t('retentionSettings.approxDays', { count: hoursToDays(value) })}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {PRESETS.map(p => (
                    <button
                      key={p.days}
                      data-testid={`retention-preset-${c.metric_type}-${p.hours}`}
                      onClick={() => setValue(c.metric_type, p.hours)}
                      className={`px-2 py-1 rounded-md text-xs border transition-colors ${value === p.hours ? 'bg-blue-500/20 border-blue-500/40 text-blue-300' : 'bg-slate-800/60 border-slate-700/50 text-slate-300 hover:bg-slate-700/50'}`}
                    >
                      {t('retentionSettings.presetDays', { count: p.days })}
                    </button>
                  ))}
                </div>
              </div>
              {invalid && <p className="text-xs text-red-400 mt-2">{t('retentionSettings.validation')}</p>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/admin/RetentionSettings.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/admin/RetentionSettings.tsx client/src/__tests__/components/admin/RetentionSettings.test.tsx
git commit -m "feat(admin): RetentionSettings editor component"
```

---

## Task 9: Frontend — Wire the Retention tab into AdminDatabase

**Files:**
- Modify: `client/src/pages/AdminDatabase.tsx:17,20,66-71,472-501`

- [ ] **Step 1: Import the component and the icon**

In `client/src/pages/AdminDatabase.tsx`:

Add the component import after the other admin component imports (near line 17):
```ts
import RetentionSettings from '../components/admin/RetentionSettings'
```
Add `Timer` to the existing `lucide-react` import on line 12 (append it to the destructured list).

- [ ] **Step 2: Extend the tab type and the tab list**

Change the type alias (line 20):
```ts
type AnalyticsTabType = 'stats' | 'storage' | 'history' | 'maintenance'
```
to:
```ts
type AnalyticsTabType = 'stats' | 'storage' | 'history' | 'maintenance' | 'retention'
```

In the `analyticsTabs` array (lines 66-71), add an entry after `maintenance`:
```ts
    { id: 'retention' as AnalyticsTabType, label: t('database.tabs.retention'), icon: Timer },
```

- [ ] **Step 3: Render the component in the analytics switch**

In `renderAnalyticsContent` (lines 472-501), add a case before `default`:
```tsx
      case 'retention':
        return (
          <div className="card">
            <RetentionSettings />
          </div>
        )
```

- [ ] **Step 4: Typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/AdminDatabase.tsx
git commit -m "feat(admin): add Retention sub-tab to the database analytics view"
```

---

## Task 10: Full regression + manual smoketest

**Files:** none (verification gate)

- [ ] **Step 1: Backend test suite**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass. (Windows note: two auth/permission delete tests are known to be flaky only in the full run — if they fail, re-run them standalone to confirm, per project memory; everything else must pass.)

- [ ] **Step 2: Frontend typecheck + unit tests**

Run: `cd client && npx tsc --noEmit`
Expected: clean.

Run: `cd client && npx vitest run`
Expected: all tests pass.

- [ ] **Step 3: Manual smoketest**

Run: `python start_dev.py`
Then:
1. Log in as admin, go to `/admin-db` → **Analytics** → **Retention**.
2. Confirm rows for cpu, memory, network, disk_io, process, uptime, gpu — and **no `power` row**.
3. Set CPU to `24` h (or click the "1 day" preset), confirm the `≈ days` hint updates and "Save" enables.
4. Click **Save** → success toast; reload the page → value persists at 24 h.
5. Go to **Storage** tab → confirm `smart_device_samples` still appears in the all-tables list.

- [ ] **Step 4: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "test(monitoring-retention): regression fixes from smoketest"
```

---

## Notes for the implementer

- **DRY:** the metric → label/icon map lives only in `metricConfig.ts`; both `DatabaseStatsCards` and `RetentionSettings` import it.
- **YAGNI:** smart-device retention is a fixed 30-day default — no config UI/endpoint. The function signature already accepts `days_to_keep` so it can be made configurable later without touching callers.
- **i18n:** add keys to BOTH `de` and `en`; missing keys fall back to German. `presetDays` uses i18next count pluralization (`presetDays_one`/`presetDays_other`); `approxDays` is a single string with `{{count}}` interpolation (no plural forms needed).
- **Pluralization caveat:** the `presetDays` key is referenced as `retentionSettings.presetDays` in code; the JSON provides `presetDays_one`/`presetDays_other` (i18next resolves the base key to the right plural form).
- The orphan `MonitoringConfig` POWER row (if present in an existing DB) is harmless dead data — no migration.
