# Status Strip Live-Pills i18n — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Internationalize the topbar live status strip so every pill's label and value render in the user's language instead of the backend's hardcoded German/English mix.

**Architecture:** Backend collectors stop emitting display strings and instead emit i18n keys + interpolation params (`label_key`, `label_params`, `value_key`, `value_params`); a single generic frontend `PillRenderer` translates them via `useTranslation('statusBar')`. `value` is retained for pure-data text (°C, HH:MM, counts) and as a `defaultValue` fallback for enum-ish states. We use an expand→contract migration: the schema first gains the new fields (keeping `label` optional), collectors and frontend switch over, then `label` is removed. `AlwaysAwakePill` stays the only special-cased pill.

**Tech Stack:** Backend — Python, Pydantic v2, pytest. Frontend — React + TypeScript, react-i18next, Vitest + React Testing Library.

---

## File Structure

**Backend**
- Modify: `backend/app/schemas/status_bar.py` — `PillState` gains `label_key`/`label_params`/`value_key`/`value_params`; `label` removed in the contract task.
- Modify: `backend/app/services/status_bar/collectors.py` — every collector emits keys instead of literals.
- Modify: `backend/tests/services/test_status_bar_collectors.py` — assertions switch from literal strings to keys/params.
- Modify: `backend/tests/services/test_status_bar_service.py` — direct `PillState` constructions + desktop value assertion updated in the contract / desktop tasks.

**Frontend**
- Modify: `client/src/api/statusBar.ts` — `PillState` interface mirrors the new backend schema.
- Modify: `client/src/components/topbar/pillRenderers.tsx` — generic translating renderer.
- Modify: `client/src/components/status-bar-config/StatusBarConfigTab.tsx` — preview builds the new `PillState` shape.
- Modify: `client/src/i18n/locales/de/statusBar.json` + `client/src/i18n/locales/en/statusBar.json` — new live/value keys.
- Create: `client/src/__tests__/components/topbar/pillRenderers.test.tsx` — renderer translation + fallback.
- Create: `client/src/__tests__/i18n/statusBar-parity.test.ts` — de/en key parity.

---

## Task 1: Schema — add i18n fields (expand phase)

**Files:**
- Modify: `backend/app/schemas/status_bar.py:50-59`
- Test: `backend/tests/services/test_status_bar_service.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/services/test_status_bar_service.py` (near the other schema tests, after `test_pill_state_minimal_construction`):

```python
def test_pill_state_accepts_i18n_fields():
    from app.schemas.status_bar import PillState
    s = PillState(
        id="vpn", kind="state", tone="success", href="/x",
        label_key="pills.vpn.live",
        value_key="pills.vpn.connected", value_params={"n": 2},
    )
    assert s.label_key == "pills.vpn.live"
    assert s.value_key == "pills.vpn.connected"
    assert s.value_params == {"n": 2}
    assert s.label_params is None


def test_pill_state_label_params_for_power():
    from app.schemas.status_bar import PillState
    s = PillState(
        id="power", kind="state", tone="info", href="/x",
        label_key="pills.power.profile", label_params={"preset": "Balanced", "level": "Surge"},
    )
    assert s.label_params == {"preset": "Balanced", "level": "Surge"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_status_bar_service.py::test_pill_state_accepts_i18n_fields -v`
Expected: FAIL with `ValidationError` / unexpected keyword (fields don't exist yet).

- [ ] **Step 3: Write minimal implementation**

Replace the `PillState` class body in `backend/app/schemas/status_bar.py` (lines 50-59) with:

```python
class PillState(BaseModel):
    """A rendered pill for the /state payload."""
    id: PILL_IDS
    kind: PillKind
    tone: PillTone
    label: Optional[str] = None           # legacy literal label — removed in the i18n contract task
    label_key: Optional[str] = None       # i18n key for the short live label, e.g. "pills.vpn.live"
    label_params: Optional[dict] = None   # interpolation params for label_key (only `power` uses it)
    value: Optional[str] = None           # pure-data value ("72°C", "14:30", "3") AND defaultValue fallback
    value_key: Optional[str] = None       # i18n key for a translatable value, e.g. "pills.vpn.connected"
    value_params: Optional[dict] = None   # interpolation params for value_key, e.g. {"n": 1}
    icon: Optional[str] = None
    href: str
    extra: Optional[dict] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_status_bar_service.py -v`
Expected: PASS (new tests pass; all existing tests still pass because `label` is kept).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/status_bar.py backend/tests/services/test_status_bar_service.py
git commit -m "feat(statusbar): add i18n key fields to PillState schema (expand phase)"
```

---

## Task 2: Locale keys (de + en) + parity test

**Files:**
- Modify: `client/src/i18n/locales/de/statusBar.json`
- Modify: `client/src/i18n/locales/en/statusBar.json`
- Test: `client/src/__tests__/i18n/statusBar-parity.test.ts` (create)

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/i18n/statusBar-parity.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import de from '../../i18n/locales/de/statusBar.json';
import en from '../../i18n/locales/en/statusBar.json';

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object'
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

describe('statusBar locale parity', () => {
  it('de and en have identical key sets', () => {
    expect(flatten(de as any).sort()).toEqual(flatten(en as any).sort());
  });

  it('has the new live label keys', () => {
    const keys = flatten(de as any);
    for (const k of ['pills.vpn.live', 'pills.pihole.live', 'pills.backup.live', 'pills.desktop.live']) {
      expect(keys).toContain(k);
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/i18n/statusBar-parity.test.ts`
Expected: FAIL on the second assertion (`pills.vpn.live` missing).

- [ ] **Step 3: Write minimal implementation**

In `client/src/i18n/locales/de/statusBar.json`, replace the entire `"pills"` block with:

```json
  "pills": {
    "power": { "name": "Energieprofil", "profile": "{{preset}} · {{level}}", "level": "{{level}}", "dynamic": "Dynamisch · {{governor}}", "dynamicBare": "Dynamisch" },
    "pihole": { "name": "Pi-hole DNS", "live": "Pi-hole", "on": "An", "off": "Aus" },
    "uploads": { "name": "Uploads / Downloads", "live": "Uploads" },
    "sync": { "name": "Sync", "live": "Sync", "conflicts": "{{n}} Konflikte" },
    "raid": {
      "name": "RAID-Zustand", "live": "RAID",
      "status": { "degraded": "Beeinträchtigt", "rebuilding": "Wird neu aufgebaut", "resyncing": "Re-Sync", "inactive": "Inaktiv", "failed": "Ausgefallen" }
    },
    "sleep": { "name": "Sleep-Modus", "live": "Sleep" },
    "vpn": { "name": "VPN-Clients", "live": "VPN", "connected": "{{n}} verbunden" },
    "temp": { "name": "Temperatur / Lüfter", "live": "Temp" },
    "alwaysAwake": {
      "name": "Immer wach / Kernbetriebszeit",
      "live": "Immer wach",
      "permanent": "Dauerhaft",
      "coreUptimeLive": "Kernbetriebszeit",
      "coreUptimeUntil": "bis {{time}}"
    },
    "scheduler": { "name": "Scheduler", "live": "Scheduler" },
    "backup": { "name": "Backup", "live": "Backup", "running": "läuft", "failed": "fehlgeschlagen" },
    "desktop": { "name": "Desktop (KDE)", "live": "Desktop", "on": "An", "off": "Aus · GPU idle" }
  },
```

In `client/src/i18n/locales/en/statusBar.json`, replace the entire `"pills"` block with:

```json
  "pills": {
    "power": { "name": "Power Profile", "profile": "{{preset}} · {{level}}", "level": "{{level}}", "dynamic": "Dynamic · {{governor}}", "dynamicBare": "Dynamic" },
    "pihole": { "name": "Pi-hole DNS", "live": "Pi-hole", "on": "On", "off": "Off" },
    "uploads": { "name": "Uploads / Downloads", "live": "Uploads" },
    "sync": { "name": "Sync", "live": "Sync", "conflicts": "{{n}} conflicts" },
    "raid": {
      "name": "RAID Health", "live": "RAID",
      "status": { "degraded": "Degraded", "rebuilding": "Rebuilding", "resyncing": "Re-syncing", "inactive": "Inactive", "failed": "Failed" }
    },
    "sleep": { "name": "Sleep Mode", "live": "Sleep" },
    "vpn": { "name": "VPN Clients", "live": "VPN", "connected": "{{n}} connected" },
    "temp": { "name": "Temperature / Fans", "live": "Temp" },
    "alwaysAwake": {
      "name": "Always Awake / Core Hours",
      "live": "Always Awake",
      "permanent": "Permanent",
      "coreUptimeLive": "Core Hours",
      "coreUptimeUntil": "until {{time}}"
    },
    "scheduler": { "name": "Scheduler", "live": "Scheduler" },
    "backup": { "name": "Backup", "live": "Backup", "running": "running", "failed": "failed" },
    "desktop": { "name": "Desktop (KDE)", "live": "Desktop", "on": "On", "off": "Off · GPU idle" }
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd client && npx vitest run src/__tests__/i18n/statusBar-parity.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client/src/i18n/locales/de/statusBar.json client/src/i18n/locales/en/statusBar.json client/src/__tests__/i18n/statusBar-parity.test.ts
git commit -m "feat(statusbar): add live label + value i18n keys (de/en) with parity test"
```

---

## Task 3: Convert collectors — power, pihole, uploads, sync, raid

**Files:**
- Modify: `backend/app/services/status_bar/collectors.py` (collect_power, collect_pihole, collect_uploads, collect_sync, collect_raid)
- Test: `backend/tests/services/test_status_bar_collectors.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/services/test_status_bar_collectors.py`, replace the four `power` tests (`test_power_pill_preset_and_level`, `test_power_pill_no_preset_fallback`, `test_power_pill_dynamic_mode_with_governor`, `test_power_pill_dynamic_mode_no_config`) with:

```python
@pytest.mark.asyncio
async def test_power_pill_preset_and_level():
    from app.services.status_bar import collectors
    preset = MagicMock(); preset.name = "Balanced"
    status = MagicMock(dynamic_mode_enabled=False, current_profile=MagicMock(value="surge"), active_preset=preset)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.profile"
    assert result["label_params"] == {"preset": "Balanced", "level": "Surge"}
    assert result["icon"] == "Zap"
    assert "value" not in result and "label" not in result


@pytest.mark.asyncio
async def test_power_pill_no_preset_fallback():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=False, current_profile=MagicMock(value="surge"), active_preset=None)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.level"
    assert result["label_params"] == {"level": "Surge"}


@pytest.mark.asyncio
async def test_power_pill_silent_without_profile():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=False, current_profile=None)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        assert await collectors.collect_power(MagicMock(), "admin") is None


@pytest.mark.asyncio
async def test_power_pill_dynamic_mode_with_governor():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=True, dynamic_mode_config=MagicMock(governor="schedutil"))
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.dynamic"
    assert result["label_params"] == {"governor": "schedutil"}


@pytest.mark.asyncio
async def test_power_pill_dynamic_mode_no_config():
    from app.services.status_bar import collectors
    status = MagicMock(dynamic_mode_enabled=True, dynamic_mode_config=None)
    mgr = MagicMock(); mgr.get_power_status = AsyncMock(return_value=status)
    with patch("app.services.power.manager.get_power_manager", return_value=mgr):
        result = await collectors.collect_power(MagicMock(), "admin")
    assert result["label_key"] == "pills.power.dynamicBare"
    assert "label_params" not in result
```

Replace `test_collect_sync_warns_on_conflicts` with:

```python
@pytest.mark.asyncio
async def test_collect_sync_warns_on_conflicts():
    from app.services.status_bar import collectors
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.count.return_value = 3
    result = await collectors.collect_sync(fake_db, "admin")
    assert result is not None
    assert result["tone"] == "warning"
    assert result["label_key"] == "pills.sync.live"
    assert result["value_key"] == "pills.sync.conflicts"
    assert result["value_params"] == {"n": 3}
```

Replace `test_collect_pihole_enabled_returns_success_tone` with:

```python
@pytest.mark.asyncio
async def test_collect_pihole_enabled_returns_success_tone():
    from app.services.status_bar import collectors
    fake_service = MagicMock()
    fake_service.get_status = AsyncMock(return_value={"blocking_enabled": True, "connected": True, "mode": "docker"})
    with patch.object(collectors, "get_pihole_service", return_value=fake_service):
        result = await collectors.collect_pihole(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["label_key"] == "pills.pihole.live"
    assert result["value_key"] == "pills.pihole.on"
```

Replace `test_collect_raid_warns_when_degraded` with:

```python
@pytest.mark.asyncio
async def test_collect_raid_warns_when_degraded():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_raid_array_statuses", return_value=["optimal", "degraded"]):
        result = await collectors.collect_raid(MagicMock(), "admin")
    assert result is not None
    assert result["tone"] in ("warning", "danger")
    assert result["label_key"] == "pills.raid.live"
    assert result["value_key"] == "pills.raid.status.degraded"
    assert result["value"] == "degraded"  # raw fallback for unknown statuses
```

Add a new uploads test (none exists today) after the pihole tests:

```python
@pytest.mark.asyncio
async def test_collect_uploads_counts_active():
    from app.services.status_bar import collectors
    p1 = MagicMock(status="uploading"); p2 = MagicMock(status="done")
    mgr = MagicMock(); mgr._progress = {"a": p1, "b": p2}
    with patch("app.services.upload_progress.get_upload_progress_manager", return_value=mgr):
        result = await collectors.collect_uploads(MagicMock(), "admin")
    assert result["label_key"] == "pills.uploads.live"
    assert result["value"] == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -k "power or sync or pihole or raid or uploads" -v`
Expected: FAIL (collectors still return `label`/literal `value`).

- [ ] **Step 3: Write the implementation**

In `backend/app/services/status_bar/collectors.py`, replace `collect_power` (lines 30-54) with:

```python
@_safe()
async def collect_power(db: Session, role: str) -> Optional[dict]:
    from app.services.power.manager import get_power_manager
    status = await get_power_manager().get_power_status()

    if getattr(status, "dynamic_mode_enabled", False):
        gov = getattr(getattr(status, "dynamic_mode_config", None), "governor", None)
        if gov:
            return {"kind": "state", "tone": "info", "label_key": "pills.power.dynamic",
                    "label_params": {"governor": gov}, "icon": "Zap"}
        return {"kind": "state", "tone": "info", "label_key": "pills.power.dynamicBare", "icon": "Zap"}

    profile = getattr(status, "current_profile", None)
    if not profile:
        return None
    level = str(getattr(profile, "value", profile)).replace("_", " ").title()

    preset = getattr(status, "active_preset", None)
    preset_name = getattr(preset, "name", None) if preset else None
    if preset_name:
        return {"kind": "state", "tone": "info", "label_key": "pills.power.profile",
                "label_params": {"preset": preset_name, "level": level}, "icon": "Zap"}
    return {"kind": "state", "tone": "info", "label_key": "pills.power.level",
            "label_params": {"level": level}, "icon": "Zap"}
```

Replace the `return {...}` in `collect_pihole` (lines 65-71) with:

```python
    return {
        "kind": "state",
        "tone": "success" if blocking else "neutral",
        "label_key": "pills.pihole.live",
        "value_key": "pills.pihole.on" if blocking else "pills.pihole.off",
        "icon": "Shield",
    }
```

Replace the `return {...}` in `collect_uploads` (lines 82-88) with:

```python
    return {
        "kind": "activity",
        "tone": "info",
        "label_key": "pills.uploads.live",
        "value": str(len(active)),
        "icon": "Upload",
    }
```

Replace the `return {...}` in `collect_sync` (lines 102-103) with:

```python
    return {"kind": "activity", "tone": "warning", "label_key": "pills.sync.live",
            "value_key": "pills.sync.conflicts", "value_params": {"n": conflicts}, "icon": "RefreshCw"}
```

Replace the `return {...}` in `collect_raid` (lines 131-137) with:

```python
    return {
        "kind": "alert",
        "tone": "danger" if failed else "warning",
        "label_key": "pills.raid.live",
        "value_key": f"pills.raid.status.{bad[0]}",
        "value": bad[0],
        "icon": "HardDrive",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -v`
Expected: PASS (converted tests pass; untouched collectors still pass).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/status_bar/collectors.py backend/tests/services/test_status_bar_collectors.py
git commit -m "feat(statusbar): emit i18n keys from power/pihole/uploads/sync/raid collectors"
```

---

## Task 4: Convert collectors — sleep, vpn, temp, scheduler

**Files:**
- Modify: `backend/app/services/status_bar/collectors.py` (collect_sleep, collect_vpn, collect_temp, collect_scheduler)
- Test: `backend/tests/services/test_status_bar_collectors.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/services/test_status_bar_collectors.py`, replace `test_vpn_neutral_when_configured_but_none_connected` and `test_vpn_success_when_peers_connected` with:

```python
@pytest.mark.asyncio
async def test_vpn_neutral_when_configured_but_none_connected():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_vpn_peer_counts", return_value=(0, 4)):
        result = await collectors.collect_vpn(MagicMock(), "admin")
    assert result is not None
    assert result["tone"] == "neutral"
    assert result["label_key"] == "pills.vpn.live"
    assert result["value_key"] == "pills.vpn.connected"
    assert result["value_params"] == {"n": 0}


@pytest.mark.asyncio
async def test_vpn_success_when_peers_connected():
    from app.services.status_bar import collectors
    with patch.object(collectors, "_vpn_peer_counts", return_value=(2, 4)):
        result = await collectors.collect_vpn(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["value_params"] == {"n": 2}
    assert result["label_key"] == "pills.vpn.live"
    assert "label" not in result
```

Add new tests (sleep, temp have none today; scheduler keeps its literal `value`) after the vpn tests:

```python
@pytest.mark.asyncio
async def test_collect_sleep_uses_label_key_and_raw_time():
    from app.services.status_bar import collectors
    status = MagicMock(schedule_enabled=True)
    config = MagicMock(schedule_sleep_time="23:30")
    mgr = MagicMock()
    mgr.get_status = MagicMock(return_value=status)
    mgr.get_config = MagicMock(return_value=config)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_sleep(MagicMock(), "admin")
    assert result["label_key"] == "pills.sleep.live"
    assert result["value"] == "23:30"


@pytest.mark.asyncio
async def test_collect_temp_uses_label_key_and_raw_celsius():
    from app.services.status_bar import collectors
    service = MagicMock()
    service.get_status = AsyncMock(return_value={"fans": [
        {"name": "cpu", "temperature_celsius": 95, "emergency_temp_celsius": 90},
    ]})
    with patch("app.services.power.fan_control.get_fan_control_service", return_value=service):
        result = await collectors.collect_temp(MagicMock(), "admin")
    assert result["label_key"] == "pills.temp.live"
    assert result["value"] == "95°C"


@pytest.mark.asyncio
async def test_collect_scheduler_uses_label_key():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    rows = [_exec("backup", "running", datetime(2026, 5, 28, 10, tzinfo=timezone.utc))]
    with patch.object(collectors, "_active_executions", return_value=rows):
        result = await collectors.collect_scheduler(MagicMock(), "admin")
    assert result["label_key"] == "pills.scheduler.live"
    assert result["value"] == "1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -k "vpn or sleep or temp or scheduler" -v`
Expected: FAIL (collectors still emit `label`).

- [ ] **Step 3: Write the implementation**

In `backend/app/services/status_bar/collectors.py`:

Replace the `return {...}` in `collect_sleep` (lines 157-158) with:

```python
    return {"kind": "state", "tone": "neutral", "label_key": "pills.sleep.live",
            "value": sleep_time, "icon": "Moon"}
```

Replace the `return {...}` in `collect_vpn` (lines 250-256) with:

```python
    return {
        "kind": "state",
        "tone": "success" if connected > 0 else "neutral",
        "label_key": "pills.vpn.live",
        "value_key": "pills.vpn.connected",
        "value_params": {"n": connected},
        "icon": "Lock",
    }
```

Replace the `return {...}` in `collect_scheduler` (lines 288-295) with:

```python
    return {
        "kind": "activity",
        "tone": "info",
        "label_key": "pills.scheduler.live",
        "value": str(len(rows)),
        "icon": "Clock",
        "extra": {"jobs": jobs},
    }
```

Replace the `return {...}` in `collect_temp` (lines 369-370) with:

```python
    return {"kind": "alert", "tone": "danger", "label_key": "pills.temp.live",
            "value": f"{int(temp)}°C", "icon": "Thermometer"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/status_bar/collectors.py backend/tests/services/test_status_bar_collectors.py
git commit -m "feat(statusbar): emit i18n keys from sleep/vpn/temp/scheduler collectors"
```

---

## Task 5: Convert collectors — backup, desktop, always_awake (+ coupled service test)

**Files:**
- Modify: `backend/app/services/status_bar/collectors.py` (collect_backup, collect_desktop, collect_always_awake)
- Test: `backend/tests/services/test_status_bar_collectors.py`
- Test: `backend/tests/services/test_status_bar_service.py:311-319` (desktop value assertion)

- [ ] **Step 1: Write the failing tests**

In `backend/tests/services/test_status_bar_collectors.py`, make exactly these edits to the backup tests:
- **Rename** `test_backup_in_progress_shows_laeuft` → `test_backup_in_progress_shows_running_key` and replace its body (below).
- **Replace the body** of `test_backup_failed_within_24h_is_danger` (keep the name) with the version below.
- **Replace the body** of `test_backup_running_beats_recent_failure` (keep the name) with the version below.
- **Leave unchanged**: `test_backup_failed_older_than_24h_is_silent`, `test_backup_completed_is_silent`.

The three resulting test functions:

```python
@pytest.mark.asyncio
async def test_backup_in_progress_shows_running_key():
    from datetime import datetime, timezone
    from app.services.status_bar import collectors
    running = _backup("in_progress", datetime(2026, 5, 28, 10, tzinfo=timezone.utc))
    with patch.object(collectors, "_running_backup", return_value=running), \
         patch.object(collectors, "_last_finished_backup", return_value=None):
        result = await collectors.collect_backup(MagicMock(), "admin")
    assert result["tone"] == "info"
    assert result["label_key"] == "pills.backup.live"
    assert result["value_key"] == "pills.backup.running"


@pytest.mark.asyncio
async def test_backup_failed_within_24h_is_danger():
    from datetime import datetime, timezone, timedelta
    from app.services.status_bar import collectors
    finished = datetime.now(timezone.utc) - timedelta(hours=2)
    failed = _backup("failed", finished - timedelta(minutes=5), finished)
    with patch.object(collectors, "_running_backup", return_value=None), \
         patch.object(collectors, "_last_finished_backup", return_value=failed):
        result = await collectors.collect_backup(MagicMock(), "admin")
    assert result["tone"] == "danger"
    assert result["value_key"] == "pills.backup.failed"


@pytest.mark.asyncio
async def test_backup_running_beats_recent_failure():
    from datetime import datetime, timezone, timedelta
    from app.services.status_bar import collectors
    running = _backup("in_progress", datetime.now(timezone.utc))
    finished = datetime.now(timezone.utc) - timedelta(hours=1)
    failed = _backup("failed", finished, finished)
    with patch.object(collectors, "_running_backup", return_value=running), \
         patch.object(collectors, "_last_finished_backup", return_value=failed):
        result = await collectors.collect_backup(MagicMock(), "admin")
    assert result["value_key"] == "pills.backup.running"
```

Replace `test_collect_desktop_running_neutral` and `test_collect_desktop_stopped_success` with:

```python
@pytest.mark.asyncio
async def test_collect_desktop_running_neutral():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="running")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result is not None
    assert result["tone"] == "neutral"
    assert result["label_key"] == "pills.desktop.live"
    assert result["value_key"] == "pills.desktop.on"
    assert result["icon"] == "Monitor"
    assert result["_state"] == "running"


@pytest.mark.asyncio
async def test_collect_desktop_stopped_success():
    from app.services.status_bar import collectors
    fake = MagicMock()
    fake.get_status = AsyncMock(return_value=MagicMock(state=MagicMock(value="stopped")))
    with patch("app.services.power.desktop.get_desktop_service", return_value=fake):
        result = await collectors.collect_desktop(MagicMock(), "admin")
    assert result["tone"] == "success"
    assert result["value_key"] == "pills.desktop.off"
    assert result["_state"] == "stopped"
```

Replace `test_always_awake_falls_back_to_core_uptime` with (label_key + drop German `value`, keep `extra.until`):

```python
@pytest.mark.asyncio
async def test_always_awake_falls_back_to_core_uptime():
    from datetime import datetime
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=True, current_window_ends_at=datetime(2026, 5, 29, 22, 0))
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result is not None
    assert result["icon"] == "Shield"
    assert result["tone"] == "success"
    assert result["label_key"] == "pills.alwaysAwake.coreUptimeLive"
    assert result["extra"]["variant"] == "core_uptime"
    assert result["extra"]["until"] == "22:00"
    assert "value" not in result
```

In `test_always_awake_takes_precedence_over_core_uptime` and `test_always_awake_permanent_has_permanent_value`, add a label_key assertion (keep existing `value == "permanent"`):

```python
    assert result["label_key"] == "pills.alwaysAwake.live"
```

In `backend/tests/services/test_status_bar_service.py`, replace `test_collect_state_always_shows_running` (lines 311-319) with:

```python
@pytest.mark.asyncio
async def test_collect_state_always_shows_running(db_session):
    svc = StatusBarService(db_session)
    _enable_desktop(svc, mode="always")
    with _patch_desktop_state("running"):
        resp = await svc.collect_state(role="admin")
    pill = next(p for p in resp.pills if p.id == "desktop")
    assert pill.value_key == "pills.desktop.on"
    assert pill.extra is None or "_state" not in (pill.extra or {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -k "backup or desktop or always_awake" tests/services/test_status_bar_service.py::test_collect_state_always_shows_running -v`
Expected: FAIL.

- [ ] **Step 3: Write the implementation**

In `backend/app/services/status_bar/collectors.py`:

In `collect_always_awake`, replace the `always_awake` branch (lines 191-199) with:

```python
        out = {"kind": "state", "tone": "warning", "label_key": "pills.alwaysAwake.live",
               "icon": "Coffee", "extra": {"variant": "always_awake"}}
        if aa.until is None:
            out["value"] = "permanent"
        else:
            secs = aa.expires_in_seconds or 0.0
            out["value"] = _format_countdown(secs)
            out["extra"]["expires_in_seconds"] = secs
        return out
```

Replace the `core_uptime` branch (lines 204-210) with:

```python
        out = {"kind": "state", "tone": "success", "label_key": "pills.alwaysAwake.coreUptimeLive",
               "icon": "Shield", "extra": {"variant": "core_uptime"}}
        until = _format_until(getattr(cu, "current_window_ends_at", None))
        if until:
            out["extra"]["until"] = until
        return out
```

Replace the running `return {...}` in `collect_backup` (lines 325-326) with:

```python
        return {"kind": "activity", "tone": "info", "label_key": "pills.backup.live",
                "value_key": "pills.backup.running", "icon": "Save"}
```

Replace the failed `return {...}` in `collect_backup` (lines 338-339) with:

```python
    return {"kind": "alert", "tone": "danger", "label_key": "pills.backup.live",
            "value_key": "pills.backup.failed", "icon": "Save"}
```

Replace the `return {...}` in `collect_desktop` (lines 382-389) with:

```python
    return {
        "kind": "state",
        "tone": "neutral" if running else "success",
        "label_key": "pills.desktop.live",
        "value_key": "pills.desktop.on" if running else "pills.desktop.off",
        "icon": "Monitor",
        "_state": state,  # private hint for the service's display-mode filter; popped before PillState
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py tests/services/test_status_bar_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/status_bar/collectors.py backend/tests/services/test_status_bar_collectors.py backend/tests/services/test_status_bar_service.py
git commit -m "feat(statusbar): emit i18n keys from backup/desktop/always_awake collectors"
```

---

## Task 6: Frontend — translating renderer, types, preview

**Files:**
- Modify: `client/src/api/statusBar.ts:16-25` (PillState interface)
- Modify: `client/src/components/topbar/pillRenderers.tsx`
- Modify: `client/src/components/status-bar-config/StatusBarConfigTab.tsx:42-52` (preview build)
- Test: `client/src/__tests__/components/topbar/pillRenderers.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `client/src/__tests__/components/topbar/pillRenderers.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PillRenderer } from '../../../components/topbar/pillRenderers';
import type { PillState } from '../../../api/statusBar';

const dict: Record<string, string> = {
  'pills.vpn.live': 'VPN',
  'pills.vpn.connected': '{{n}} connected',
  'pills.raid.live': 'RAID',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const tmpl = dict[key];
      if (tmpl === undefined) return (opts?.defaultValue as string) ?? key;
      return tmpl.replace(/\{\{(\w+)\}\}/g, (_m, k) => String(opts?.[k] ?? ''));
    },
  }),
}));

function renderPill(pill: PillState) {
  return render(<MemoryRouter><PillRenderer pill={pill} flat /></MemoryRouter>);
}

const base = { kind: 'state' as const, tone: 'info' as const, href: '/x' };

describe('PillRenderer', () => {
  it('translates label_key and value_key with params', () => {
    renderPill({ ...base, id: 'vpn', label_key: 'pills.vpn.live',
      value_key: 'pills.vpn.connected', value_params: { n: 2 } });
    expect(screen.getByText('VPN')).toBeInTheDocument();
    expect(screen.getByText('2 connected')).toBeInTheDocument();
  });

  it('falls back to raw value when value_key is unknown', () => {
    renderPill({ ...base, id: 'raid', label_key: 'pills.raid.live',
      value_key: 'pills.raid.status.weirdstate', value: 'weirdstate' });
    expect(screen.getByText('RAID')).toBeInTheDocument();
    expect(screen.getByText('weirdstate')).toBeInTheDocument();
  });

  it('renders a pure-data value verbatim when there is no value_key', () => {
    renderPill({ ...base, id: 'temp', label_key: 'pills.temp.live', value: '95°C' });
    expect(screen.getByText('95°C')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/topbar/pillRenderers.test.tsx`
Expected: FAIL (renderer still reads `pill.label`; type has no `label_key`).

- [ ] **Step 3: Write the implementation**

Replace the `PillState` interface in `client/src/api/statusBar.ts` (lines 16-25) with:

```ts
export interface PillState {
  id: PillId;
  kind: PillKind;
  tone: PillTone;
  label_key: string;
  label_params?: Record<string, unknown> | null;
  value?: string | null;
  value_key?: string | null;
  value_params?: Record<string, unknown> | null;
  icon?: string | null;
  href: string;
  extra?: Record<string, unknown> | null;
}
```

Replace the body of `client/src/components/topbar/pillRenderers.tsx` with:

```tsx
import { createElement } from 'react';
import { useTranslation } from 'react-i18next';
import { Pill } from '../ui/Pill';
import { AlwaysAwakePill } from './pills/AlwaysAwakePill';
import { resolveIcon } from './iconMap';
import type { PillState } from '../../api/statusBar';

export function PillRenderer({ pill, flat }: { pill: PillState; flat?: boolean }) {
  const { t } = useTranslation('statusBar');
  if (pill.id === 'always_awake') {
    return <AlwaysAwakePill pill={pill} flat={flat} />;
  }
  const label = t(pill.label_key, { ...(pill.label_params ?? {}) });
  const value = pill.value_key
    ? t(pill.value_key, { ...(pill.value_params ?? {}), defaultValue: pill.value ?? '' })
    : (pill.value ?? undefined);

  const iconComp = resolveIcon(pill.icon);
  const icon = iconComp ? createElement(iconComp, { className: 'h-3.5 w-3.5' }) : undefined;
  return (
    <Pill tone={pill.tone} label={label} value={value} href={pill.href} icon={icon} flat={flat} />
  );
}
```

Replace the `previewState` memo in `client/src/components/status-bar-config/StatusBarConfigTab.tsx` (lines 42-52) with (pass the config name via `label_key`; the renderer translates it):

```tsx
  const previewState: StatusBarStateResponse = useMemo(() => ({
    pills: cfg.pills
      .filter(p => p.enabled)
      .map(p => ({
        id: p.pill_id, kind: 'state' as const, tone: 'neutral' as const,
        // Preview shows the config name; strip the "statusBar." ns prefix so the
        // renderer's useTranslation('statusBar') resolves it.
        label_key: p.name_key.replace(/^statusBar\./, ''),
        href: p.href, value: null, value_key: null, value_params: null, icon: null, extra: null,
      })),
    show_bottom_upload: cfg.showBottomUpload,
  }), [cfg.pills, cfg.showBottomUpload]);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/components/topbar/pillRenderers.test.tsx src/__tests__/components/status-bar-config/`
Expected: PASS (new renderer test + existing config-tab tests).

- [ ] **Step 5: Typecheck the frontend**

Run: `cd client && npx tsc --noEmit`
Expected: no errors. (Confirms no remaining `pill.label` consumers and the preview shape matches the new interface.)

- [ ] **Step 6: Commit**

```bash
git add client/src/api/statusBar.ts client/src/components/topbar/pillRenderers.tsx client/src/components/status-bar-config/StatusBarConfigTab.tsx client/src/__tests__/components/topbar/pillRenderers.test.tsx
git commit -m "feat(statusbar): translate live pills in the frontend via key+params renderer"
```

---

## Task 7: Contract phase — remove legacy `label` field

**Files:**
- Modify: `backend/app/schemas/status_bar.py` (PillState — make `label_key` required, drop `label`/`label_params`? keep `label_params`)
- Modify: `backend/tests/services/test_status_bar_service.py` (routing fakes + minimal construction)
- Test: `backend/tests/services/test_status_bar_collectors.py` (drift guard)

- [ ] **Step 1: Write the failing tests**

In `backend/tests/services/test_status_bar_collectors.py`, add a drift-guard test at the end:

```python
@pytest.mark.asyncio
async def test_no_collector_emits_legacy_label_key():
    """Every collector must emit `label_key`, never the legacy literal `label`."""
    from app.services.status_bar import collectors
    from app.services.status_bar.collectors import COLLECTORS
    from unittest.mock import AsyncMock, MagicMock, patch
    # Patch every underlying service so each collector returns a populated dict.
    patches = [
        patch.object(collectors, "_vpn_peer_counts", return_value=(1, 2)),
        patch.object(collectors, "_raid_array_statuses", return_value=["degraded"]),
        patch.object(collectors, "_active_executions",
                     return_value=[_exec("backup", "running", None)]),
        patch.object(collectors, "_running_backup", return_value=_backup("in_progress", None)),
        patch.object(collectors, "_last_finished_backup", return_value=None),
    ]
    for p in patches:
        p.start()
    try:
        for name, fn in COLLECTORS.items():
            result = await fn(MagicMock(), "admin")
            if result is None:
                continue
            assert "label" not in result, f"collector {name} still emits legacy 'label'"
            assert "label_key" in result, f"collector {name} missing 'label_key'"
    finally:
        for p in patches:
            p.stop()
```

Update the direct construction test `test_pill_state_minimal_construction` in `backend/tests/services/test_status_bar_service.py` (line 35-38) to:

```python
def test_pill_state_minimal_construction():
    from app.schemas.status_bar import PillState
    s = PillState(id="raid", kind="alert", tone="warning", label_key="pills.raid.live", href="/x")
    assert s.value is None and s.extra is None
```

Update the three routing fakes in `test_status_bar_service.py` that return `{"label": ...}` (lines 143, 165, 188-189) — change `"label": "..."` to `"label_key": "pills.x.live"`. Specifically:
- `fake_power` (line 142-143): return `{"kind": "state", "tone": "info", "label_key": "pills.power.live"}`
- `fake` (line 164-165): return `{"kind": "state", "tone": "info", "label_key": "pills.power.live"}`
- `fake` (line 188-189): return `{"kind": "state", "tone": "info", "label_key": "pills.power.live"}`

(`test_collect_state_skips_collector_with_malformed_output`'s `good` fake at line 216-217 also returns `"label": "OK"` — change to `"label_key": "pills.power.live"`. The `bad` fake stays as-is; it is still invalid because `kind` is missing.)

- [ ] **Step 2: Run tests to establish the baseline**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py::test_no_collector_emits_legacy_label_key tests/services/test_status_bar_service.py -v`
Expected at this point: the new drift-guard test PASSES (collectors were already converted in Tasks 3-5), and the edited `test_pill_state_minimal_construction` + routing-fake tests PASS (because `label` is still an optional field). This task is a refactor, not test-first: the contract is enforced by the schema change in Step 3, which would break any test still passing `label=` — that is why the fakes are updated to `label_key` in Step 1 *before* the schema change.

- [ ] **Step 3: Write the implementation**

In `backend/app/schemas/status_bar.py`, replace the `PillState` class with the final form (remove `label`, make `label_key` required):

```python
class PillState(BaseModel):
    """A rendered pill for the /state payload."""
    id: PILL_IDS
    kind: PillKind
    tone: PillTone
    label_key: str                        # i18n key for the short live label, e.g. "pills.vpn.live"
    label_params: Optional[dict] = None   # interpolation params for label_key (only `power` uses it)
    value: Optional[str] = None           # pure-data value ("72°C", "14:30", "3") AND defaultValue fallback
    value_key: Optional[str] = None       # i18n key for a translatable value, e.g. "pills.vpn.connected"
    value_params: Optional[dict] = None   # interpolation params for value_key, e.g. {"n": 1}
    icon: Optional[str] = None
    href: str
    extra: Optional[dict] = None
```

- [ ] **Step 4: Run the full backend status-bar suite**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py tests/services/test_status_bar_service.py -v`
Expected: PASS (all routing fakes now emit `label_key`; `label` no longer accepted but nothing emits it).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/status_bar.py backend/tests/services/test_status_bar_collectors.py backend/tests/services/test_status_bar_service.py
git commit -m "refactor(statusbar): drop legacy label field, require label_key (contract phase)"
```

---

## Task 8: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && python -m pytest`
Expected: PASS (no regressions across the 1465 tests). If failures appear in unrelated Windows-flaky permission tests, re-run those standalone to confirm they are the known isolation flakes.

- [ ] **Step 2: Run the full frontend unit suite + typecheck**

Run: `cd client && npx vitest run && npx tsc --noEmit`
Expected: PASS, no TS errors.

- [ ] **Step 3: Manual smoke test (dev mode)**

Run: `python start_dev.py`
Then in the browser (login admin / DevMode2024):
- Open Settings → Topbar Status Strip, enable VPN, Pi-hole, Backup, Desktop pills.
- Switch language EN ↔ DE (LanguageSettings) and confirm the live strip labels/values change language (e.g. VPN "2 connected" ↔ "2 verbunden", Pi-hole "On/Off" ↔ "An/Aus").
- Confirm the config Live Preview still shows the enabled pills.

- [ ] **Step 4: Final commit (if any doc/touch-ups needed)**

```bash
git add -A
git commit -m "test(statusbar): verify live-strip i18n end to end" --allow-empty
```

---

## Notes for the implementer

- **Expand→contract**: Tasks 1-6 keep the legacy `label` field valid so every intermediate commit is green; Task 7 removes it once nothing emits it. Do not reorder Task 7 before the collectors are converted.
- **`{{n}}` not `{{count}}`**: value params use `n` deliberately to avoid i18next's plural-suffix resolution (which would look for `connected_one`/`connected_other`).
- **`value` doubles as fallback**: for `raid` the collector sends both `value_key` and raw `value`; the renderer's `defaultValue: pill.value` shows the raw status if a status key is missing.
- **`AlwaysAwakePill` is unchanged**: it already derives its label/value from its own i18n keys and ignores `label_key`. Its collector still emits a valid `label_key` for schema validity.
- **Route test is unaffected**: `backend/tests/api/test_status_bar_routes.py` only asserts `"pills" in r.json()` for `/state` (never a pill's `label`), and the default seed leaves all pills disabled (empty `pills`), so it stays green throughout the migration. No edits needed there.
- **Windows/CRLF**: the repo uses `core.autocrlf=true`; the JSON/TS edits will show "LF will be replaced by CRLF" warnings on commit — that is expected, not an error.
