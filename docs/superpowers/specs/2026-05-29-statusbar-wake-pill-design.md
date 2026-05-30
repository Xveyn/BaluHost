# Status-Strip "Wach-Grund" Pill — Always Awake + Kernbetriebszeit-Fallback

**Date:** 2026-05-29
**Status:** Approved (brainstorming complete)
**Author:** Sven (Xveyn) + Claude
**Context branch:** `worktree-topbar-statusbar` (PR #110), builds on `docs/superpowers/specs/2026-05-27-topbar-statusbar-design.md`

## Problem

The topbar status strip has an `always_awake` pill that appears only while the manual
**Always Awake** override is active, and is silent otherwise. The recurring
**Kernbetriebszeit** (core-uptime) feature *also* keeps the NAS awake by suppressing
auto-sleep, but it has no presence in the strip at all. In the sleep logic, Always
Awake already takes precedence over Kernbetriebszeit (`_idle_detection_loop` /
`_schedule_check_loop` check always-awake first). The pill should mirror that
override relationship instead of going dark whenever the manual override is off but a
core-uptime window is keeping the system awake.

## Solution

Repurpose the existing `always_awake` pill into a single **"why the system stays
awake"** indicator with a priority fallback. Same pill id, same catalog slot, same
visibility lock — no new catalog entry, no schema, no migration.

Both states are already available from the **one call** the collector makes:
`sleep_manager.get_status()` returns both `.always_awake` and `.core_uptime`
(`active`, `current_window_label`, `current_window_ends_at`). `Shield` is already in
the frontend `iconMap.ts`. So this is a focused change to one collector + the one
dedicated pill renderer + i18n + tests.

## Behavior

Priority order inside `collect_always_awake`:

| # | Condition | Pill output |
|---|---|---|
| 1 | `always_awake.enabled` | **unchanged**: icon `Coffee`, tone `warning`, value = live countdown (`03:42`) or `permanent`; `extra.expires_in_seconds` when timed |
| 2 | else `core_uptime.active` | **new**: icon `Shield`, tone `success`, label `Kernbetriebszeit`, value `bis HH:MM` (from `current_window_ends_at`, server-local 24h); no countdown |
| 3 | else | `None` (silent — same as today) |

Always Awake wins; Kernbetriebszeit shows only when a window is *currently* active;
nothing shows when neither blocks auto-sleep. No "next window" preview (deliberate —
keeps the strip quiet).

## i18n (explicit requirement)

The live-strip label is today a hardcoded backend string. To respect translations,
the **frontend** `AlwaysAwakePill` renders its label/value via
`useTranslation('statusBar')` for **both** variants. The backend passes a `variant`
discriminator and the raw `HH:MM` so the frontend can localize the `bis`/`until`
prefix; the backend `label`/`value` remain valid fallbacks.

New keys in `client/src/i18n/locales/{de,en}/statusBar.json` under `pills.alwaysAwake`:

| Key | DE | EN |
|---|---|---|
| `name` (rename) | `Immer wach / Kernbetriebszeit` | `Always Awake / Core Hours` |
| `live` | `Immer wach` | `Always Awake` |
| `permanent` | `Dauerhaft` | `Permanent` |
| `coreUptimeLive` | `Kernbetriebszeit` | `Core Hours` |
| `coreUptimeUntil` | `bis {{time}}` | `until {{time}}` |

`name` is the config-tab label (now reflects the dual purpose); the others drive the
live strip. Time stays 24h `HH:MM` (consistent with the existing Sleep pill, which
also renders a raw `HH:MM`).

## Backend — `backend/app/services/status_bar/collectors.py`

`collect_always_awake` gains the fallback branch and a `variant` marker in `extra`:

```python
def _format_until(dt) -> Optional[str]:
    if dt is None:
        return None
    try:
        return dt.strftime("%H:%M")
    except Exception:  # noqa: BLE001 - value is optional, never block the pill
        return None


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

The `_safe()` decorator already guarantees the collector never raises. `extra.variant`
is additive — existing always-awake consumers (countdown via `expires_in_seconds`)
are unaffected.

## Frontend — `client/src/components/topbar/pills/AlwaysAwakePill.tsx`

i18n-driven, branches on `extra.variant`:

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
    <Pill tone={pill.tone} label={label} value={value} href={pill.href} icon={icon} flat={flat} />
  );
}
```

No change to `PillRenderer` (already routes `always_awake` here), `iconMap`
(`Shield` present), `Pill`, `useCountdown`, or `api/statusBar.ts`
(`extra: Record<string, unknown>` already permits `variant`/`until`).

## Tests — `backend/tests/services/test_status_bar_collectors.py`

- **Fix** `test_always_awake_silent_when_disabled`: the bare `MagicMock` status makes
  `core_uptime.active` truthy, so the test must set
  `fake_status.core_uptime = MagicMock(active=False)` to keep asserting `None`.
- **Add** `test_always_awake_falls_back_to_core_uptime`: `always_awake.enabled=False`,
  `core_uptime.active=True`, `current_window_ends_at=<dt 22:00>` → result has
  `icon="Shield"`, `tone="success"`, `value="bis 22:00"`, `extra.variant="core_uptime"`.
- **Add** `test_always_awake_takes_precedence_over_core_uptime`: both active → result is
  the always-awake payload (`tone="warning"`, `extra.variant="always_awake"`).
- **Add** `test_always_awake_and_core_uptime_both_off_silent`: both off → `None`.

`test_always_awake_permanent_has_permanent_value` and
`test_always_awake_with_expiry_exposes_seconds` keep passing (always-awake branch
returns before the core-uptime check; assertions check keys that still exist).

Frontend tests are placeholders per repo convention — none added.

## Edge cases

| Case | Handling |
|---|---|
| `current_window_ends_at` is `None` while `active=True` | `value` omitted; pill shows label only (`Kernbetriebszeit`) |
| `core_uptime` attr missing on status (older shape) | `getattr(..., None)` → silent |
| Always-awake expires between polls while a core window is active | next poll falls through to the core-uptime branch; pill flips Coffee→Shield (≤10s lag) |
| Collector raises | `_safe()` returns `None`; pill silently absent |
| Window-ends datetime is tz-aware | `strftime("%H:%M")` works regardless of tzinfo |

## Out of scope

- No new pill / catalog entry / schema / migration / API change.
- No "next window" upcoming-state preview.
- No client-side locale time formatting (24h `HH:MM` kept, matching the Sleep pill).
- No changes to the `sleep` pill (still shows the schedule sleep time).
