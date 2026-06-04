# Per-Plugin Smart-Device Sample Retention (configurable under Plugins) — Design

**Date:** 2026-06-04
**Branch:** `feat/monitoring-retention-ui` (same branch/PR as #154 — chosen to stack here)
**Status:** Approved design — ready for implementation planning
**Builds on:** the smart-device retention introduced earlier on this branch
(`plugins/smart_device/retention.py::cleanup_old_smart_device_samples`, the
`SmartDevicePoller` daily cleanup trigger, and `SMART_DEVICE_SAMPLE_RETENTION_DAYS`).

## Problem

Smart-device sample retention is currently a fixed 30-day constant covering the
whole `smart_device_samples` table. Admins want to configure how long the Tapo
power-plug plugin keeps its samples, **directly under Plugins**, with quick
presets, a free custom value, and an "unlimited / never delete" option.

## Goal

Make smart-device sample retention configurable **per smart_device plugin** via
the existing plugin-config mechanism (`GET/PUT /api/plugins/{name}/config` +
the schema-driven settings form on the Plugins page), starting with Tapo.

## Non-Goals (YAGNI)

- No per-device or per-capability retention (per-plugin granularity only).
- No upper bound beyond 365 days for finite values (0 = unlimited covers
  "keep very long").
- No Tapo-specific frontend bundle — the generic plugin-settings form is extended
  instead (benefits all plugins).
- No change to the import-preservation contract (`imported_from` rows are always
  kept).

## Background (existing mechanism)

- Each plugin may define `get_config_schema()` (Pydantic). Tapo already returns
  `TapoPluginConfig` from `get_config_schema()`.
- `GET /api/plugins/{name}/config` returns `{config, schema}` where `schema` is
  `model_json_schema()`; `PUT` validates via `plugin.validate_config()` and
  persists to `InstalledPlugin.config` (admin-only).
- The frontend `components/plugins/PluginSettingsSection.tsx` renders a form from
  `schema.properties`. It currently handles `array` (with
  `x-options-source: 'smart-devices'`), `boolean`, and `string`, and returns
  `null` for any other type — so it does **not** yet render `integer`/`number`.
- `SmartDevice.plugin_name` identifies which plugin owns each device;
  `SmartDeviceSample.device_id` → `SmartDevice` gives the owning plugin.
- The poller (`SmartDevicePoller`) runs in the single MonitoringWorker process and
  already triggers a daily cleanup (from this branch).

## Design

### A. Tapo config field

Add to `TapoPluginConfig` (in `backend/app/plugins/installed/tapo_smart_plug/__init__.py`):

```python
retention_days: int = Field(
    default=30,
    ge=0,
    le=365,
    title="Sample retention (days)",
    json_schema_extra={"x-presets": [7, 30, 90, 180], "x-unlimited-value": 0},
)
```

- `0` = **unlimited** (never auto-delete this plugin's samples).
- `1–365` = retain that many days.
- Exposed automatically via `model_json_schema()` (includes `minimum`/`maximum`
  and the `x-presets`/`x-unlimited-value` extensions). Validation via the existing
  `validate_config()` (Pydantic).

### B. Per-plugin cleanup

Refactor the whole-table cleanup introduced earlier on this branch into a
per-plugin function in `backend/app/plugins/smart_device/retention.py`:

```python
SMART_DEVICE_SAMPLE_RETENTION_DAYS = 30  # default when a plugin has no config

def cleanup_smart_device_samples(db: Session, plugin_name: str, days_to_keep: int) -> int:
    """Delete samples for devices owned by `plugin_name` older than the cutoff,
    across all capabilities, preserving rows whose data_json contains
    "imported_from". days_to_keep <= 0 means unlimited — nothing is deleted."""
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
    return deleted
```

The poller's cleanup helper (`_maybe_cleanup_samples`) iterates the loaded
smart_device plugins; for each it reads
`InstalledPlugin.config.get("retention_days", SMART_DEVICE_SAMPLE_RETENTION_DAYS)`
and calls `cleanup_smart_device_samples(db, plugin_name, days_to_keep)`. A plugin
with no config row → 30-day default. `retention_days == 0` → skipped (kept
forever).

> Net behaviour vs. this branch's current state: identical 30-day cleanup until
> an admin changes the value; cleanup is now scoped per plugin and can be set to
> unlimited.

### C. Frontend — generic number/retention renderer

Extend `PluginSettingsSection.tsx` with a renderer for
`schema.type === 'integer' || schema.type === 'number'`, driven by the same
`x-` schema-extension convention already used for `x-options-source`:

- Base: an `<input type="number">` with `max` (from `maximum`) and `step={1}`,
  value stored as a number in `formData`. When an `x-unlimited-value` sentinel is
  present, the free field's `min` is clamped to `max(1, minimum)` so the sentinel
  (0) is reachable **only** via the Unlimited chip, not by typing it.
- If `schema['x-presets']` is an array → render **preset chips** for those values
  (highlight the active one).
- If `schema['x-unlimited-value']` is defined → render an **"Unlimited" chip** that
  sets the value to that sentinel; while active, show "Unlimited — never deleted"
  and visually mark it.

Without these extensions the renderer is a plain number input (reusable for any
plugin). Label resolution is unchanged: `pluginT['settings_retention_days']`
falls back to `schema.title` ("Sample retention (days)").

### D. i18n

Add the German label for the field via the plugin-translation mechanism that
feeds `PluginSettingsSection`'s `translations`/`pluginT` (e.g.
`settings_retention_days` = "Aufbewahrung der Messdaten (Tage)", plus an
"Unbegrenzt" string for the unlimited chip). Exact source of the plugin
translation bundle is resolved during planning; the `schema.title` fallback keeps
the field labelled even if the translation is absent. Generic UI strings
("Unlimited", "days") live in the `plugins` namespace locale files (`de`/`en`).

### E. Error handling
- Backend: out-of-range values rejected by the Pydantic schema (`ge=0, le=365`)
  → `PUT /config` returns 400 via the existing `validate_config` path.
- Frontend: number input clamped to `[min, max]`; the unlimited chip is the only
  way to set 0 (so the free field stays within 1–365). Save errors via the
  existing toast.
- Admin-only (plugin-config endpoints are admin-gated).

## Testing

**Backend (pytest):**
- `TapoPluginConfig` accepts `retention_days` 0, 30, 365; rejects -1 and 366.
- `cleanup_smart_device_samples(db, "tapo_smart_plug", 30)` deletes only that
  plugin's device samples older than cutoff; leaves another plugin's samples and
  `imported_from` rows untouched.
- `cleanup_smart_device_samples(..., 0)` deletes nothing.
- Poller reads each plugin's `retention_days` from config (default 30 when no
  config row) and applies per-plugin cleanup.

**Frontend (Vitest):** `PluginSettingsSection`
- renders an `integer` field with preset chips and an "Unlimited" chip;
- clicking a preset sets that value; clicking "Unlimited" sets the sentinel (0)
  and shows the unlimited state;
- free numeric entry updates `formData`;
- Save calls `updatePluginConfig(name, {... retention_days})`.

**Manual smoketest:** `/plugins` → Tapo → Settings → set retention to a preset /
custom / Unlimited → Save → reload persists; verify (dev) that a sample older
than the cutoff is removed on the next poller cleanup, and that an `imported_from`
row and an unlimited setting keep everything.

## Files Touched

**Backend**
- `app/plugins/installed/tapo_smart_plug/__init__.py` — add `retention_days` to `TapoPluginConfig`.
- `app/plugins/smart_device/retention.py` — per-plugin `cleanup_smart_device_samples` (refactor of the whole-table function).
- `app/plugins/smart_device/poller.py` — `_maybe_cleanup_samples` reads each plugin's config and runs per-plugin cleanup.
- Tests: `tests/plugins/test_smart_device_retention.py` (extend), Tapo plugin config tests.

**Frontend**
- `src/components/plugins/PluginSettingsSection.tsx` — number/retention renderer (presets + unlimited via `x-` extensions).
- `src/i18n/locales/{de,en}/plugins.json` — generic strings (Unlimited, days) + Tapo field label via the plugin-translation path.
- Frontend tests under `src/__tests__/`.

## Open Questions

None at spec-writing time. (The exact source of the Tapo plugin's translation
bundle is an implementation detail for the plan; the `schema.title` fallback
guarantees a usable label regardless.)
