# Status-Strip Wake Pill (Always Awake + Kernbetriebszeit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the topbar `always_awake` status pill fall back to showing the active Kernbetriebszeit (core-uptime) window when the manual Always-Awake override is off, with proper DE/EN translations.

**Architecture:** One backend collector (`collect_always_awake`) gains a priority fallback — Always Awake first (unchanged), else the currently-active core-uptime window, else silent. Both states already come from a single `sleep_manager.get_status()` call. The dedicated `AlwaysAwakePill` renderer becomes i18n-driven and branches on an `extra.variant` discriminator the backend now emits.

**Tech Stack:** Python / FastAPI / pytest (backend); React + TypeScript / react-i18next (frontend).

**Spec:** `docs/superpowers/specs/2026-05-29-statusbar-wake-pill-design.md`

**Working dir:** All paths are relative to the worktree root `D:/Programme (x86)/Baluhost/.claude/worktrees/topbar-statusbar`. Backend `pytest` runs from the `backend/` subfolder.

---

### Task 1: Backend collector fallback to Kernbetriebszeit (TDD)

**Files:**
- Modify: `backend/app/services/status_bar/collectors.py` (`collect_always_awake`, new `_format_until`)
- Test: `backend/tests/services/test_status_bar_collectors.py`

- [ ] **Step 1: Fix the existing silent-when-disabled test**

In `backend/tests/services/test_status_bar_collectors.py`, the test `test_always_awake_silent_when_disabled` builds a bare `MagicMock()` status; after the change `status.core_uptime.active` would be a truthy auto-mock and the collector would no longer return `None`. Pin it false. Replace the test body with:

```python
@pytest.mark.asyncio
async def test_always_awake_silent_when_disabled():
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=False)
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        assert await collectors.collect_always_awake(MagicMock(), "admin") is None
```

- [ ] **Step 2: Add the three new failing tests**

Append to `backend/tests/services/test_status_bar_collectors.py`:

```python
@pytest.mark.asyncio
async def test_always_awake_falls_back_to_core_uptime():
    from datetime import datetime
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(
        active=True, current_window_ends_at=datetime(2026, 5, 29, 22, 0))
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result is not None
    assert result["icon"] == "Shield"
    assert result["tone"] == "success"
    assert result["value"] == "bis 22:00"
    assert result["extra"]["variant"] == "core_uptime"
    assert result["extra"]["until"] == "22:00"


@pytest.mark.asyncio
async def test_always_awake_takes_precedence_over_core_uptime():
    from datetime import datetime
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=True, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(
        active=True, current_window_ends_at=datetime(2026, 5, 29, 22, 0))
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        result = await collectors.collect_always_awake(MagicMock(), "admin")
    assert result["tone"] == "warning"
    assert result["extra"]["variant"] == "always_awake"
    assert result["value"] == "permanent"


@pytest.mark.asyncio
async def test_always_awake_and_core_uptime_both_off_silent():
    from app.services.status_bar import collectors
    fake_status = MagicMock()
    fake_status.always_awake = MagicMock(enabled=False, until=None, expires_in_seconds=None)
    fake_status.core_uptime = MagicMock(active=False)
    mgr = MagicMock(); mgr.get_status = MagicMock(return_value=fake_status)
    with patch.object(collectors, "get_sleep_manager", return_value=mgr):
        assert await collectors.collect_always_awake(MagicMock(), "admin") is None
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -v -k "always_awake"`
Expected: `test_always_awake_falls_back_to_core_uptime` FAILS (collector returns `None`, has no Shield branch); precedence/both-off tests may already pass. `test_always_awake_permanent_has_permanent_value` and `test_always_awake_with_expiry_exposes_seconds` still PASS.

- [ ] **Step 4: Implement the fallback in the collector**

In `backend/app/services/status_bar/collectors.py`, add `_format_until` next to `_format_countdown` (above `collect_always_awake`):

```python
def _format_until(dt) -> Optional[str]:
    """Format a window-end datetime as 24h HH:MM (server-local). None-safe."""
    if dt is None:
        return None
    try:
        return dt.strftime("%H:%M")
    except Exception:  # noqa: BLE001 - value is optional, never block the pill
        return None
```

Then replace the body of `collect_always_awake` with:

```python
@_safe()
async def collect_always_awake(db: Session, role: str) -> Optional[dict]:
    manager = get_sleep_manager()
    if manager is None:
        return None
    status = manager.get_status()

    aa = getattr(status, "always_awake", None)
    if aa is not None and aa.enabled:
        out = {"kind": "state", "tone": "warning", "label": "Always Awake",
               "icon": "Coffee", "extra": {"variant": "always_awake"}}
        if aa.until is None:
            out["value"] = "permanent"
        else:
            secs = aa.expires_in_seconds or 0.0
            out["value"] = _format_countdown(secs)
            out["extra"]["expires_in_seconds"] = secs
        return out

    # Fallback: Kernbetriebszeit window currently active (always-awake overrides it)
    cu = getattr(status, "core_uptime", None)
    if cu is not None and getattr(cu, "active", False):
        out = {"kind": "state", "tone": "success", "label": "Kernbetriebszeit",
               "icon": "Shield", "extra": {"variant": "core_uptime"}}
        until = _format_until(getattr(cu, "current_window_ends_at", None))
        if until:
            out["value"] = f"bis {until}"
            out["extra"]["until"] = until
        return out

    return None
```

- [ ] **Step 5: Run the full collector test file to verify all pass**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py -v`
Expected: PASS (all, including the unchanged scheduler/backup/pihole/raid/sync tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/status_bar/collectors.py backend/tests/services/test_status_bar_collectors.py
git commit -m "feat(statusbar): always-awake pill falls back to active Kernbetriebszeit"
```

---

### Task 2: i18n keys for both pill variants (DE + EN)

**Files:**
- Modify: `client/src/i18n/locales/de/statusBar.json`
- Modify: `client/src/i18n/locales/en/statusBar.json`

- [ ] **Step 1: Update the German keys**

In `client/src/i18n/locales/de/statusBar.json`, replace the `alwaysAwake` entry inside `pills` (currently `"alwaysAwake": { "name": "Immer wach" }`) with:

```json
    "alwaysAwake": {
      "name": "Immer wach / Kernbetriebszeit",
      "live": "Immer wach",
      "permanent": "Dauerhaft",
      "coreUptimeLive": "Kernbetriebszeit",
      "coreUptimeUntil": "bis {{time}}"
    },
```

- [ ] **Step 2: Update the English keys**

In `client/src/i18n/locales/en/statusBar.json`, replace the corresponding `alwaysAwake` entry inside `pills` with:

```json
    "alwaysAwake": {
      "name": "Always Awake / Core Hours",
      "live": "Always Awake",
      "permanent": "Permanent",
      "coreUptimeLive": "Core Hours",
      "coreUptimeUntil": "until {{time}}"
    },
```

- [ ] **Step 3: Validate both JSON files parse**

Run: `cd client && node -e "require('./src/i18n/locales/de/statusBar.json'); require('./src/i18n/locales/en/statusBar.json'); console.log('ok')"`
Expected: prints `ok` (no JSON syntax error).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/statusBar.json client/src/i18n/locales/en/statusBar.json
git commit -m "i18n(statusbar): wake-pill keys for always-awake + core-hours (de/en)"
```

---

### Task 3: i18n-driven AlwaysAwakePill renderer

**Files:**
- Modify: `client/src/components/topbar/pills/AlwaysAwakePill.tsx`

- [ ] **Step 1: Replace the component with the variant-aware, i18n version**

Replace the entire contents of `client/src/components/topbar/pills/AlwaysAwakePill.tsx` with:

```tsx
import { createElement } from 'react';
import { useTranslation } from 'react-i18next';
import { Pill } from '../../ui/Pill';
import { useCountdown } from '../../../hooks/useCountdown';
import { resolveIcon } from '../iconMap';
import type { PillState } from '../../../api/statusBar';

export function AlwaysAwakePill({ pill, flat }: { pill: PillState; flat?: boolean }) {
  const { t } = useTranslation('statusBar');
  const variant = pill.extra?.variant;
  const expires = typeof pill.extra?.expires_in_seconds === 'number'
    ? (pill.extra!.expires_in_seconds as number)
    : null;
  const countdown = useCountdown(expires);

  let label: string;
  let value: string | undefined;
  if (variant === 'core_uptime') {
    label = t('pills.alwaysAwake.coreUptimeLive');
    const until = typeof pill.extra?.until === 'string' ? (pill.extra!.until as string) : undefined;
    value = until ? t('pills.alwaysAwake.coreUptimeUntil', { time: until }) : undefined;
  } else {
    label = t('pills.alwaysAwake.live');
    value = countdown ?? (expires === null ? t('pills.alwaysAwake.permanent') : pill.value ?? undefined);
  }

  const iconComp = resolveIcon(pill.icon);
  const icon = iconComp ? createElement(iconComp, { className: 'h-3.5 w-3.5' }) : undefined;
  return (
    <Pill
      tone={pill.tone}
      label={label}
      value={value}
      href={pill.href}
      icon={icon}
      flat={flat}
    />
  );
}
```

- [ ] **Step 2: Type-check the frontend**

Run: `cd client && npx tsc --noEmit`
Expected: no errors referencing `AlwaysAwakePill.tsx`.

- [ ] **Step 3: Build the frontend to confirm no compile regressions**

Run: `cd client && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/topbar/pills/AlwaysAwakePill.tsx
git commit -m "feat(statusbar): i18n-driven wake pill (always-awake + core-hours variants)"
```

---

### Task 4: End-to-end verification (dev mode)

**Files:** none (manual run-through)

- [ ] **Step 1: Run the backend status-bar test suites once more**

Run: `cd backend && python -m pytest tests/services/test_status_bar_collectors.py tests/services/test_status_bar_service.py tests/api/test_status_bar_routes.py -v`
Expected: all PASS.

- [ ] **Step 2: Start dev mode**

Run (from worktree root): `python start_dev.py`
Log in as `admin` / `DevMode2024`. Open **System Control → System → Status Bar**, enable the **Immer wach / Kernbetriebszeit** pill (admin-only, locked), save.

- [ ] **Step 3: Verify the Always-Awake branch (unchanged)**

In **System Control → Hardware → Sleep**, turn **Immer wach** on with a 1h preset. Within ~10s the topbar pill shows ☕ **Immer wach** with a live countdown. Switch UI language to English → label reads **Always Awake**; permanent mode → value **Permanent**.

- [ ] **Step 4: Verify the Kernbetriebszeit fallback**

Turn **Immer wach** off. In the **Kernbetriebszeit** panel, add a window covering the current time (e.g. `00:00 → 23:59`, all weekdays) and enable the master toggle. Within ~10s the topbar pill shows 🛡 **Kernbetriebszeit · bis 23:59** (DE) / **Core Hours · until 23:59** (EN), tone green.

- [ ] **Step 5: Verify precedence and silence**

Turn **Immer wach** back on while the window is still active → pill flips to ☕ Always Awake (override wins). Turn both off → pill disappears from the strip.

- [ ] **Step 6: Final commit (only if any verification fix was needed)**

```bash
git add -A
git commit -m "test(statusbar): verify wake-pill core-uptime fallback in dev mode"
```

---

## Notes for the implementer

- The `_safe()` decorator wrapping `collect_always_awake` guarantees the collector never raises — do not add try/except inside the body beyond what the spec shows.
- `extra.variant` is the single source of truth the frontend branches on; keep it in sync if the backend payload changes.
- Time is rendered as 24h `HH:MM` server-side (matching the existing `sleep` pill); only the `bis`/`until` prefix is translated client-side.
- Frontend unit tests are placeholders in this repo (per convention) — coverage for this change is the backend collector tests plus the manual dev-mode run-through.
