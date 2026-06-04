# Per-Plugin Smart-Device Retention Config (Tapo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins configure smart-device sample retention per smart_device plugin (starting with Tapo) under Plugins — with quick presets, a free custom value (1–365 days), and an "unlimited / never delete" option (0).

**Architecture:** Add `retention_days` to the Tapo plugin's existing config schema (`0`=unlimited, presets/unlimited expressed via `x-` schema extensions). Refactor the branch's whole-table smart-device cleanup into a per-plugin function the poller calls with each plugin's configured value. Extend the generic schema-driven plugin settings form to render number/retention fields.

**Tech Stack:** Python / FastAPI / SQLAlchemy / pytest (backend); React + TS / Vite / Vitest / react-i18next (frontend).

**Spec:** `docs/superpowers/specs/2026-06-04-plugin-retention-config-design.md`

**Branch:** This stacks on the smart-device retention already on `feat/monitoring-retention-ui` (same branch / PR #154). Run all commands from the worktree root `D:\Programme (x86)\Baluhost\.claude\worktrees\feat+monitoring-retention-ui`. Backend: `cd backend && python -m pytest ...`. Frontend: `cd client && npx vitest run ...` / `npx tsc --noEmit`.

**Depends on (already on this branch):**
- `backend/app/plugins/smart_device/retention.py` — `cleanup_old_smart_device_samples(db, days_to_keep)` + `SMART_DEVICE_SAMPLE_RETENTION_DAYS = 30`.
- `backend/app/plugins/smart_device/poller.py` — `_maybe_cleanup_samples`, `_should_cleanup_samples`, `_last_sample_cleanup`, `_SAMPLE_CLEANUP_INTERVAL`, `self._plugins` (dict `plugin_name → instance`), `self._db_session_factory`.
- `backend/tests/plugins/test_smart_device_retention.py` — `device` fixture (`plugin_name="tapo_smart_plug"`), `_add(db, device_id, capability, days_ago, extra=None)` helper, and the existing cleanup tests + `test_poller_cleanup_gate`.

---

## File Structure

**Backend**
- `backend/app/plugins/installed/tapo_smart_plug/__init__.py` — add `retention_days` to `TapoPluginConfig`; add its i18n label to `get_translations()`.
- `backend/app/plugins/smart_device/retention.py` — replace whole-table cleanup with per-plugin `cleanup_smart_device_samples(db, plugin_name, days_to_keep)`.
- `backend/app/plugins/smart_device/poller.py` — `_retention_days_for_plugin()` + `_maybe_cleanup_samples()` iterates plugins using their configured retention.
- `backend/tests/plugins/test_smart_device_retention.py` — update existing tests to the per-plugin signature; add scope + unlimited + poller-config tests.
- `backend/tests/plugins/test_tapo_plugin_config.py` *(new)* — `TapoPluginConfig.retention_days` validation.

**Frontend**
- `client/src/components/plugins/PluginSettingsSection.tsx` — number/retention renderer (presets + unlimited via `x-` extensions).
- `client/src/i18n/locales/{de,en}/plugins.json` — generic `settings.*` strings (days unit, unlimited, presetDays).
- `client/src/__tests__/components/plugins/PluginSettingsSection.test.tsx` *(new)*.

---

## Task 1: Backend — Tapo `retention_days` config field + label

**Files:**
- Modify: `backend/app/plugins/installed/tapo_smart_plug/__init__.py`
- Test: `backend/tests/plugins/test_tapo_plugin_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/plugins/test_tapo_plugin_config.py`:

```python
"""Validation tests for the Tapo plugin config schema."""
import pytest
from pydantic import ValidationError

from app.plugins.installed.tapo_smart_plug import TapoPluginConfig


def test_default_retention_is_30():
    assert TapoPluginConfig().retention_days == 30


@pytest.mark.parametrize("value", [0, 1, 30, 365])
def test_accepts_valid_retention(value):
    assert TapoPluginConfig(retention_days=value).retention_days == value


@pytest.mark.parametrize("value", [-1, 366, 1000])
def test_rejects_out_of_range(value):
    with pytest.raises(ValidationError):
        TapoPluginConfig(retention_days=value)


def test_schema_exposes_presets_and_unlimited():
    schema = TapoPluginConfig.model_json_schema()
    prop = schema["properties"]["retention_days"]
    assert prop["x-presets"] == [7, 30, 90, 180]
    assert prop["x-unlimited-value"] == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_tapo_plugin_config.py -v`
Expected: FAIL — `retention_days` does not exist / `x-presets` missing.

- [ ] **Step 3: Add the field to `TapoPluginConfig`**

In `backend/app/plugins/installed/tapo_smart_plug/__init__.py`, the class currently is:

```python
class TapoPluginConfig(BaseModel):
    """Configuration schema for the Tapo Smart Plug plugin."""

    panel_devices: List[int] = Field(
        default_factory=list,
        title="Dashboard Panel Devices",
        description="Devices shown in the dashboard power panel",
        json_schema_extra={"x-options-source": "smart-devices"},
    )
```

Add the `retention_days` field directly after `panel_devices` (still inside the class):

```python
    retention_days: int = Field(
        default=30,
        ge=0,
        le=365,
        title="Sample retention (days)",
        description="How long to keep this plugin's device samples (0 = unlimited).",
        json_schema_extra={"x-presets": [7, 30, 90, 180], "x-unlimited-value": 0},
    )
```

Verify `Field` is already imported at the top of the file (it is — `panel_devices` uses it).

- [ ] **Step 4: Add the i18n label to `get_translations()`**

In the same file, `get_translations()` returns an `en` and a `de` dict. Add a `settings_retention_days` entry to each (after `settings_panel_devices`):

In `"en"`:
```python
                "settings_retention_days": "Sample retention (days)",
```
In `"de"`:
```python
                "settings_retention_days": "Aufbewahrung der Messdaten (Tage)",
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_tapo_plugin_config.py -v`
Expected: PASS (all parametrized cases + schema-extension assertions).

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/installed/tapo_smart_plug/__init__.py backend/tests/plugins/test_tapo_plugin_config.py
git commit -m "feat(tapo): add configurable retention_days (0=unlimited) to plugin config"
```

---

## Task 2: Backend — per-plugin cleanup

**Files:**
- Modify: `backend/app/plugins/smart_device/retention.py`
- Modify: `backend/tests/plugins/test_smart_device_retention.py`

- [ ] **Step 1: Update the existing tests to the new per-plugin signature + add scope/unlimited tests**

In `backend/tests/plugins/test_smart_device_retention.py`:

Change the import line:
```python
from app.plugins.smart_device.retention import (
    cleanup_old_smart_device_samples,
    SMART_DEVICE_SAMPLE_RETENTION_DAYS,
)
```
to:
```python
from app.plugins.smart_device.retention import (
    cleanup_smart_device_samples,
    SMART_DEVICE_SAMPLE_RETENTION_DAYS,
)
```

Replace every call `cleanup_old_smart_device_samples(db_session, days_to_keep=30)` (in `test_deletes_all_capabilities_older_than_cutoff`, `test_preserves_imported_rows`, `test_nothing_to_delete`) with:
```python
cleanup_smart_device_samples(db_session, "tapo_smart_plug", 30)
```
(The `device` fixture's `plugin_name` is `"tapo_smart_plug"`, so these still target the seeded device.)

Append two new tests (they reuse the existing `device` fixture and `_add` helper):

```python
def test_scopes_to_plugin(db_session, device):
    """Cleanup only deletes samples of devices owned by the given plugin."""
    from app.models.smart_device import SmartDevice, SmartDeviceSample

    other = SmartDevice(
        name="Other", plugin_name="other_plugin",
        device_type_id="x", address="10.0.0.9",
        capabilities=["sensor"], is_active=True, is_online=True,
        created_by_user_id=1,
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    _add(db_session, device.id, "power_monitor", days_ago=60)   # tapo, old -> deleted
    _add(db_session, other.id, "sensor", days_ago=60)           # other plugin, old -> kept

    deleted = cleanup_smart_device_samples(db_session, "tapo_smart_plug", 30)

    assert deleted == 1
    remaining = {s.device_id for s in db_session.query(SmartDeviceSample).all()}
    assert remaining == {other.id}


def test_unlimited_keeps_everything(db_session, device):
    from app.models.smart_device import SmartDeviceSample

    _add(db_session, device.id, "power_monitor", days_ago=400)
    deleted = cleanup_smart_device_samples(db_session, "tapo_smart_plug", 0)
    assert deleted == 0
    assert db_session.query(SmartDeviceSample).count() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py -v`
Expected: FAIL — `cleanup_smart_device_samples` does not exist yet (ImportError).

- [ ] **Step 3: Replace the whole-table function with the per-plugin one**

In `backend/app/plugins/smart_device/retention.py`:

Change the imports block:
```python
from sqlalchemy.orm import Session

from app.models.smart_device import SmartDeviceSample
```
to:
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.smart_device import SmartDevice, SmartDeviceSample
```

Replace the entire `cleanup_old_smart_device_samples(...)` function (keep the `SMART_DEVICE_SAMPLE_RETENTION_DAYS = 30` constant above it) with:

```python
def cleanup_smart_device_samples(
    db: Session,
    plugin_name: str,
    days_to_keep: int,
) -> int:
    """Delete samples for devices owned by ``plugin_name`` older than the cutoff.

    Covers all capabilities of that plugin's devices. Rows whose ``data_json``
    contains ``"imported_from"`` (manually imported history) are always kept.
    ``days_to_keep <= 0`` means unlimited — nothing is deleted.

    Returns the number of deleted rows.
    """
    if days_to_keep <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    device_ids = select(SmartDevice.id).where(SmartDevice.plugin_name == plugin_name)

    deleted = db.query(SmartDeviceSample).filter(
        SmartDeviceSample.device_id.in_(device_ids),
        SmartDeviceSample.timestamp < cutoff,
        ~SmartDeviceSample.data_json.contains('"imported_from"'),
    ).delete(synchronize_session=False)

    db.commit()
    if deleted:
        logger.info(
            "Cleaned up %d smart_device_samples for plugin '%s' older than %d days "
            "(imported rows preserved)",
            deleted, plugin_name, days_to_keep,
        )
    return deleted
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py -v`
Expected: PASS (updated cleanup tests + `test_scopes_to_plugin` + `test_unlimited_keeps_everything` + the unchanged `test_default_is_30_days` and `test_poller_cleanup_gate`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/smart_device/retention.py backend/tests/plugins/test_smart_device_retention.py
git commit -m "refactor(smart-device): per-plugin sample cleanup (0=unlimited)"
```

---

## Task 3: Backend — poller reads each plugin's configured retention

**Files:**
- Modify: `backend/app/plugins/smart_device/poller.py`
- Test: `backend/tests/plugins/test_smart_device_retention.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_smart_device_retention.py`:

```python
def test_retention_days_for_plugin_reads_config(db_session):
    """Poller resolves retention from InstalledPlugin.config, default 30."""
    from app.plugins.smart_device.poller import SmartDevicePoller
    from app.services import plugin_service

    poller = SmartDevicePoller()

    # No config row -> default 30
    assert poller._retention_days_for_plugin(db_session, "tapo_smart_plug") == 30

    # Configured value
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"retention_days": 7}
    )
    assert poller._retention_days_for_plugin(db_session, "tapo_smart_plug") == 7

    # Unlimited
    plugin_service.update_config(
        db_session, name="tapo_smart_plug", validated_config={"retention_days": 0}
    )
    assert poller._retention_days_for_plugin(db_session, "tapo_smart_plug") == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py::test_retention_days_for_plugin_reads_config -v`
Expected: FAIL — `_retention_days_for_plugin` does not exist.

- [ ] **Step 3: Add the config-reading helper**

In `backend/app/plugins/smart_device/poller.py`, add this method to `SmartDevicePoller` (e.g. right above `_should_cleanup_samples`):

```python
    def _retention_days_for_plugin(self, db, plugin_name: str) -> int:
        """Resolve a plugin's configured sample retention (days).

        Falls back to SMART_DEVICE_SAMPLE_RETENTION_DAYS when the plugin has no
        config row or an unreadable value.
        """
        from app.plugins.smart_device.retention import SMART_DEVICE_SAMPLE_RETENTION_DAYS
        from app.services import plugin_service
        try:
            record = plugin_service.get_installed_plugin(db, plugin_name)
            cfg = (record.config or {}) if record else {}
            return int(cfg.get("retention_days", SMART_DEVICE_SAMPLE_RETENTION_DAYS))
        except (TypeError, ValueError):
            return SMART_DEVICE_SAMPLE_RETENTION_DAYS
```

- [ ] **Step 4: Rewrite `_maybe_cleanup_samples` to iterate plugins**

In the same file, replace the body of `_maybe_cleanup_samples` (currently calling `cleanup_old_smart_device_samples(db)`) with a per-plugin loop:

```python
    async def _maybe_cleanup_samples(self) -> None:
        """Run per-plugin sample cleanup if the daily interval has elapsed."""
        if self._db_session_factory is None:
            return
        now = time.time()
        if not self._should_cleanup_samples(now):
            return
        # Set before the synchronous cleanup. No await between the check and this
        # set, and cleanup is sync, so concurrent plugin loops cannot double-fire.
        self._last_sample_cleanup = now
        try:
            from app.plugins.smart_device.retention import cleanup_smart_device_samples
            db = self._db_session_factory()
            try:
                for plugin_name in list(self._plugins.keys()):
                    days = self._retention_days_for_plugin(db, plugin_name)
                    cleanup_smart_device_samples(db, plugin_name, days)
            finally:
                db.close()
        except Exception as exc:
            logger.debug("SmartDevicePoller: sample cleanup failed: %s", exc)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py -v`
Expected: PASS (all retention + poller tests, including the new config-reading test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/smart_device/poller.py backend/tests/plugins/test_smart_device_retention.py
git commit -m "feat(smart-device): poller applies per-plugin configured retention"
```

---

## Task 4: Frontend — number/retention renderer + i18n strings

**Files:**
- Modify: `client/src/components/plugins/PluginSettingsSection.tsx`
- Modify: `client/src/i18n/locales/en/plugins.json`, `client/src/i18n/locales/de/plugins.json`
- Test: `client/src/__tests__/components/plugins/PluginSettingsSection.test.tsx`

- [ ] **Step 1: Add the generic i18n strings (EN + DE)**

In `client/src/i18n/locales/en/plugins.json`, find the `"settings"` object (it has `title`, `save`, `saved`, `saveError`) and add:
```json
    "daysUnit": "days",
    "unlimited": "Unlimited",
    "unlimitedHint": "never deleted",
    "presetDays_one": "{{count}} day",
    "presetDays_other": "{{count}} days",
```
In `client/src/i18n/locales/de/plugins.json`, add to the same `"settings"` object:
```json
    "daysUnit": "Tage",
    "unlimited": "Unbegrenzt",
    "unlimitedHint": "wird nie gelöscht",
    "presetDays_one": "{{count}} Tag",
    "presetDays_other": "{{count}} Tage",
```
(Mind JSON commas — these are added as members of the existing `settings` object.)

Validate: `cd client && node -e "require('./src/i18n/locales/de/plugins.json'); require('./src/i18n/locales/en/plugins.json'); console.log('ok')"` → `ok`.

- [ ] **Step 2: Write the failing test**

Create `client/src/__tests__/components/plugins/PluginSettingsSection.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../../api/plugins', () => ({ updatePluginConfig: vi.fn().mockResolvedValue({}) }));
vi.mock('../../../api/smart-devices', () => ({ smartDevicesApi: { list: vi.fn().mockResolvedValue({ data: { devices: [] } }) } }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
const stableT = (k: string, opts?: Record<string, unknown>) =>
  opts && 'count' in opts ? `${k}:${String(opts.count)}` : k;
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: stableT, i18n: { language: 'en' } }) }));

import { PluginSettingsSection } from '../../../components/plugins/PluginSettingsSection';
import * as pluginsApi from '../../../api/plugins';

const SCHEMA = {
  properties: {
    retention_days: {
      type: 'integer', title: 'Sample retention (days)', default: 30,
      minimum: 0, maximum: 365, 'x-presets': [7, 30, 90, 180], 'x-unlimited-value': 0,
    },
  },
};

describe('PluginSettingsSection number/retention field', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the number input and the unlimited chip', async () => {
    render(<PluginSettingsSection pluginName="tapo_smart_plug" configSchema={SCHEMA} config={{ retention_days: 30 }} />);
    expect(screen.getByRole('spinbutton')).toBeTruthy();
    expect(screen.getByText('settings.unlimited')).toBeTruthy();
  });

  it('clicking a preset sets the value and saves it', async () => {
    render(<PluginSettingsSection pluginName="tapo_smart_plug" configSchema={SCHEMA} config={{ retention_days: 30 }} />);
    fireEvent.click(screen.getByText('settings.presetDays:90'));
    fireEvent.click(screen.getByText('settings.save'));
    await waitFor(() => expect(pluginsApi.updatePluginConfig).toHaveBeenCalledWith('tapo_smart_plug', { retention_days: 90 }));
  });

  it('clicking unlimited sets the sentinel (0)', async () => {
    render(<PluginSettingsSection pluginName="tapo_smart_plug" configSchema={SCHEMA} config={{ retention_days: 30 }} />);
    fireEvent.click(screen.getByText('settings.unlimited'));
    fireEvent.click(screen.getByText('settings.save'));
    await waitFor(() => expect(pluginsApi.updatePluginConfig).toHaveBeenCalledWith('tapo_smart_plug', { retention_days: 0 }));
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/plugins/PluginSettingsSection.test.tsx`
Expected: FAIL — no number field rendered (the component returns `null` for integer types), so `getByRole('spinbutton')` throws.

- [ ] **Step 4: Add the integer/number renderer**

In `client/src/components/plugins/PluginSettingsSection.tsx`, locate the `string` field block that ends just before the final `return null;` (the `if (schema.type === 'string') { ... }` block, then `return null;`). Insert this new block **between** the `string` block and `return null;`:

```tsx
        if (schema.type === 'integer' || schema.type === 'number') {
          const presets: number[] = Array.isArray(schema['x-presets']) ? schema['x-presets'] : [];
          const unlimitedValue = schema['x-unlimited-value'];
          const hasUnlimited = unlimitedValue !== undefined;
          const current = formData[key] ?? schema.default ?? '';
          const isUnlimited = hasUnlimited && current === unlimitedValue;
          const freeMin = hasUnlimited ? Math.max(1, schema.minimum ?? 1) : (schema.minimum ?? 0);
          return (
            <div key={key} className="space-y-1.5">
              <label className="text-sm text-gray-300">{label}</label>
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  type="number"
                  min={freeMin}
                  max={schema.maximum}
                  step={1}
                  disabled={isUnlimited}
                  value={isUnlimited ? '' : current}
                  onChange={(e) => setFormData({ ...formData, [key]: Number(e.target.value) })}
                  className="w-28 rounded bg-gray-700 border border-gray-600 px-3 py-1.5 text-sm text-gray-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 disabled:opacity-50"
                />
                <span className="text-xs text-gray-400">{t('settings.daysUnit')}</span>
                {isUnlimited && <span className="text-xs text-amber-400">{t('settings.unlimitedHint')}</span>}
              </div>
              {(presets.length > 0 || hasUnlimited) && (
                <div className="flex flex-wrap gap-1.5">
                  {presets.map((p) => (
                    <button
                      key={p}
                      type="button"
                      onClick={() => setFormData({ ...formData, [key]: p })}
                      className={`px-2 py-1 rounded-md text-xs border transition-colors ${current === p && !isUnlimited ? 'bg-blue-600 border-blue-500 text-white' : 'bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600'}`}
                    >
                      {t('settings.presetDays', { count: p })}
                    </button>
                  ))}
                  {hasUnlimited && (
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, [key]: unlimitedValue })}
                      className={`px-2 py-1 rounded-md text-xs border transition-colors ${isUnlimited ? 'bg-amber-600 border-amber-500 text-white' : 'bg-gray-700 border-gray-600 text-gray-300 hover:bg-gray-600'}`}
                    >
                      {t('settings.unlimited')}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/plugins/PluginSettingsSection.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Typecheck**

Run: `cd client && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add client/src/components/plugins/PluginSettingsSection.tsx client/src/i18n/locales/en/plugins.json client/src/i18n/locales/de/plugins.json client/src/__tests__/components/plugins/PluginSettingsSection.test.tsx
git commit -m "feat(plugins): number/retention field renderer (presets + unlimited) in plugin settings"
```

---

## Task 5: Regression + manual smoketest

**Files:** none (verification gate)

- [ ] **Step 1: Backend — affected modules**

Run: `cd backend && python -m pytest tests/plugins/test_smart_device_retention.py tests/plugins/test_tapo_plugin_config.py -v`
Expected: all pass.

- [ ] **Step 2: Frontend — typecheck + unit tests**

Run: `cd client && npx tsc --noEmit`
Expected: clean.

Run: `cd client && npx vitest run`
Expected: all pass.

- [ ] **Step 3: Manual smoketest**

Run (from the worktree, dev env with a seeded admin): `SKIP_SETUP=true python start_dev.py`
Then:
1. `/plugins` → select **Tapo Smart Plug** (must be enabled) → **Plugin Settings**.
2. Confirm the **Sample retention (days)** field shows a number input + preset chips (7/30/90/180) + an **Unlimited** chip.
3. Click a preset → Save → reload → value persists.
4. Click **Unlimited** → the input disables and shows "never deleted" → Save → reload → still unlimited (`retention_days = 0`).
5. (Optional DB check) With a non-zero value, a `power_monitor` sample older than the cutoff is removed on the next poller cleanup; an `imported_from` row and an unlimited setting keep everything.

- [ ] **Step 4: Final commit (if smoketest required fixes)**

```bash
git add -A
git commit -m "test(plugin-retention): fixes from smoketest"
```

---

## Notes for the implementer

- **DRY/YAGNI:** the number renderer is generic (any plugin with an `integer`/`number` schema field benefits); presets/unlimited are opt-in via `x-presets` / `x-unlimited-value`, mirroring the existing `x-options-source` convention.
- **Unlimited semantics:** `retention_days = 0` everywhere means "never auto-delete". The cleanup short-circuits on `days_to_keep <= 0`; the UI reaches 0 only via the Unlimited chip (free field min is clamped to 1).
- **Imported rows** (`data_json` contains `"imported_from"`) are always preserved — unchanged contract.
- **i18n:** `presetDays`/`approxDays`-style keys use i18next count pluralization (`presetDays_one`/`presetDays_other`); the Tapo field label comes from `get_translations()` (`settings_retention_days`) with `schema.title` as fallback.
- If importing `TapoPluginConfig` in the Task 1 test fails because the plugin module pulls an optional dependency at import time, import the schema via the loaded plugin instead — but the plugin's heavy deps (plugp100) are imported lazily inside methods, so a direct import is expected to work.
