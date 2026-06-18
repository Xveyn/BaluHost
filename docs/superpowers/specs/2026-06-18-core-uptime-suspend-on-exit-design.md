# Design — Suspend on Core-Uptime Exit

**Date:** 2026-06-18
**Status:** Approved (brainstorming complete, ready for implementation plan)
**Owner:** Xveyn

## 1. Goal

Add an opt-in option to the Core Operating Hours (Kernbetriebszeit) feature that **suspends the
server as soon as a core-uptime window ends**, instead of leaving the idle timer to count up from
zero again.

### Background — current behaviour

While a core-uptime window is active, the idle detection loop resets the idle counter to `0` on
every tick (`backend/app/services/power/sleep.py`, `_idle_detection_loop`):

```python
master, windows = self._load_core_uptime()
if master:
    in_core, _ = core_uptime_helpers.is_in_core_uptime(datetime.now(), windows)
    if in_core:
        self._consecutive_idle_checks = 0
        self._idle_seconds = 0.0
        continue
```

Consequence: when the window ends, the counter stands at `0`, so the system only auto-sleeps after
another full `idle_timeout_minutes` of continuous idleness. There is no falling-edge trigger today —
only a rising edge (window starts → auto-wake from soft sleep). This design adds the missing
falling-edge path, gated behind a new opt-in flag.

## 2. Requirements

### Functional
- **F1** A new master-independent opt-in flag `core_uptime_suspend_on_exit` (default `False`).
  Only meaningful while `core_uptime_enabled` (the feature master toggle) is on, since a falling
  edge can only occur for an enabled window.
- **F2** When an active window ends (falling edge: was in core, now not) and the flag is on, the
  service **arms** a pending-suspend state (`_core_uptime_exit_pending = True`).
- **F3** While armed, on the next loop tick where the system is **idle** (existing
  `_is_system_idle` criteria: CPU/disk-IO/HTTP under threshold, no active uploads) **and** no user
  is present (`_is_user_present`) **and** Always-Awake is not active (`_is_always_awake`), the
  service performs a **true suspend** and disarms.
- **F4** The suspend is a **true suspend** (`enter_true_suspend`). `wake_at` is passed as `None`;
  the existing F7 clamp in `enter_true_suspend` sets `wake_at` to `next_core_uptime_start`, so the
  RTC alarm wakes the box at the next window start.
- **F5** If the system is busy at window-end, the pending state **persists** (armed) and fires the
  moment the system becomes idle — without waiting the full `idle_timeout_minutes`.
- **F6** The pending state is **disarmed** when: a new core-uptime window becomes active
  (`in_core` true again), the flag is turned off, or the suspend fires successfully.
- **F7** The suspend is logged with a new `SleepTrigger.CORE_UPTIME_EXIT` value, surfaced in the
  Sleep history as "Kernzeit-Ende".
- **F8** A frontend toggle "Beim Fenster-Ende suspenden" in the `CoreUptimePanel`, auto-saved like
  the surrounding controls.

### Non-functional
- **N1** No new background loop; the logic lives inside the existing `_schedule_check_loop`
  (60 s cadence). Suspend fires ≤ 60 s after the system becomes idle, consistent with the existing
  core-uptime auto-wake latency (F6 of the original feature).
- **N2** Additive migration: one new boolean column on `sleep_config`. No data migration.
- **N3** No new API endpoint. The flag rides the existing `PUT /api/system/sleep/config` route via
  the generic `setattr` update loop.
- **N4** The pending state is in-memory only (an instance attribute), consistent with the existing
  in-memory `_was_in_core_uptime` / `_consecutive_idle_checks`.

## 3. Data Model

### 3.1 `sleep_config` — new column

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `core_uptime_suspend_on_exit` | Boolean | not null, default `False` | Opt-in: suspend when a window ends |

SQLAlchemy model (`backend/app/models/sleep.py`, in the "Core Operating Hours" block):

```python
core_uptime_suspend_on_exit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

### 3.2 Alembic migration

Additive column. **Must chain onto the real `alembic heads`** (not the stale dev-DB head — see the
multi-head pitfall). One `op.add_column("sleep_config", sa.Column("core_uptime_suspend_on_exit",
sa.Boolean(), nullable=False, server_default=sa.false()))`; downgrade drops it.

### 3.3 In-memory service state

`SleepManagerService.__init__`: new attribute `self._core_uptime_exit_pending: bool = False`.

## 4. Service Logic (`backend/app/services/power/sleep.py`)

All changes are inside the existing `_schedule_check_loop`, inserted **after** the auto-wake
edge-detection block and **before** the `if not config or not config.schedule_enabled: continue`
line — so the feature works even when the sleep schedule is disabled.

At that point in the loop, `master`, `windows`, `in_core` and the prior `_was_in_core_uptime` are
already computed (the existing auto-wake block uses them). Note the auto-wake block updates
`self._was_in_core_uptime` at its end, so the falling-edge check must read it **before** that
update, OR we capture the prior value first. The implementation plan will place the arm/fire block
**before** `_was_in_core_uptime` is reassigned, using the still-current prior value.

```python
# Falling-edge arm / disarm for "suspend on core-uptime exit"
falling_edge = master and self._was_in_core_uptime and not in_core
if config and config.core_uptime_suspend_on_exit:
    if falling_edge:
        logger.info("Core uptime window ended — arming suspend-on-exit")
        self._core_uptime_exit_pending = True
    if in_core:
        # A window is active again — disarm.
        self._core_uptime_exit_pending = False
else:
    self._core_uptime_exit_pending = False

# Fire when armed and the system is genuinely idle / unattended
if (
    self._core_uptime_exit_pending
    and self._current_state == SleepState.AWAKE
    and not in_core
    and config is not None
    and not self._is_always_awake(config)
    and not self._is_user_present(config)
    and self._is_system_idle(config, self._get_activity_metrics())
):
    logger.info("Suspend-on-exit: system idle after core uptime — entering true suspend")
    self._core_uptime_exit_pending = False
    await self.enter_true_suspend(
        "core_uptime_exit", SleepTrigger.CORE_UPTIME_EXIT, wake_at=None,
    )
```

Ordering note: this block must run before the existing
`if master: self._was_in_core_uptime = in_core else: ... = False` reassignment, because
`falling_edge` depends on the prior value. The implementation plan moves the arm/fire block directly
above that reassignment (after the auto-wake edge `exit_soft_sleep` call and the
`_reconcile_sleep_inhibitor` call).

### `wake_at` clamp reuse

`enter_true_suspend(reason, trigger, wake_at=None)` already contains (F7 of the original feature):

```python
master_enabled, windows = self._load_core_uptime()
if master_enabled:
    next_core = next_core_uptime_start(datetime.now(), windows)
    if next_core is not None and (wake_at is None or next_core < wake_at):
        wake_at = next_core
```

So passing `wake_at=None` yields an RTC alarm at the next window start. No change to
`enter_true_suspend` is required.

## 5. Schema & API (`backend/app/schemas/sleep.py`)

### 5.1 New `SleepTrigger` value

```python
class SleepTrigger(str, Enum):
    ...
    CORE_UPTIME_WAKE = "core_uptime_wake"
    CORE_UPTIME_EXIT = "core_uptime_exit"   # NEW
```

### 5.2 Config schemas

- `SleepConfigUpdate`: `core_uptime_suspend_on_exit: Optional[bool] = None`
- `SleepConfigResponse`: `core_uptime_suspend_on_exit: bool = Field(default=False, description="Suspend when a core-uptime window ends")`

`update_config` needs no change — the generic `setattr` loop already persists the new field.
`get_config` must add `core_uptime_suspend_on_exit=config.core_uptime_suspend_on_exit` to the
`SleepConfigResponse(...)` constructor.

### 5.3 API

No new endpoint. `PUT /api/system/sleep/config` carries the flag; `GET /api/system/sleep/config`
returns it.

## 6. Frontend

### 6.1 `client/src/components/power/CoreUptimePanel.tsx`
- Load `core_uptime_suspend_on_exit` via `getSleepConfig()` in the existing `refresh()`.
- Render an auto-save toggle "Beim Fenster-Ende suspenden" beneath the window list (same `Toggle`
  styling as the master toggle). On change, optimistic update + `updateSleepConfig({
  core_uptime_suspend_on_exit: next })`, rollback + toast on error.
- The toggle is shown whenever the panel is shown; it is only behaviourally relevant while the
  master toggle is on (mirror the existing "schedule override hint" pattern — no hard disable).

### 6.2 `client/src/api/sleep.ts`
- `SleepTrigger` union gains `'core_uptime_exit'`.
- `TRIGGER_LABELS` gains `core_uptime_exit: 'Kernzeit-Ende'`.

### 6.3 i18n (`client/src/i18n/locales/{de,en}/common.json`)
Under `sleep.coreUptime`:
- de: `suspendOnExit: "Beim Fenster-Ende suspenden"`, `suspendOnExitDesc: "Suspendet den Server,
  sobald die Kernbetriebszeit endet (sobald das System idle ist)."`
- en: `suspendOnExit: "Suspend when window ends"`, `suspendOnExitDesc: "Suspends the server as soon
  as the core operating window ends (once the system is idle)."`

(The panel currently uses hard-coded German strings; registering keys mirrors the existing
core-uptime i18n approach. Wiring through `t()` is out of scope, same as the original feature.)

## 7. Tests

### 7.1 `backend/tests/services/test_sleep_core_uptime_integration.py` (extend)
- `test_suspend_on_exit_arms_and_fires_when_idle` — falling edge with flag on + idle metrics →
  `enter_true_suspend` called once with `SleepTrigger.CORE_UPTIME_EXIT` and `wake_at=None`; pending
  cleared.
- `test_suspend_on_exit_waits_while_busy` — falling edge, but `_is_system_idle` False → no suspend,
  pending stays `True`; next tick idle → fires.
- `test_suspend_on_exit_blocked_by_presence` — armed + idle but `_is_user_present` True → no
  suspend, pending stays.
- `test_suspend_on_exit_blocked_by_always_awake` — armed + idle but `_is_always_awake` True → no
  suspend.
- `test_suspend_on_exit_disarmed_by_new_window` — armed, then `in_core` True on a later tick →
  pending cleared, no suspend.
- `test_suspend_on_exit_flag_off_never_arms` — falling edge with flag off → pending never set.
- `test_suspend_on_exit_works_without_schedule` — `schedule_enabled=False` → still arms/fires
  (regression guard for the insert position above the `schedule_enabled` continue).

Helpers reuse the existing `_config(...)` / `_window_workdays_8_22()` fixtures; the new flag is
threaded through `_config` with a `suspend_on_exit: bool = False` kwarg.

### 7.2 Regression
`cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py tests/test_sleep.py -v`
— all existing sleep tests still pass.

## 8. Edge cases & invariants

| # | Topic | Decision |
|---|---|---|
| 1 | Restart while armed | `_core_uptime_exit_pending` is in-memory; a restart right after window-end loses the arming. Accepted, consistent with `_was_in_core_uptime`. |
| 2 | Multi-worker prod | Only the primary worker runs the monitoring loops (original feature edge #9). No double suspend. |
| 3 | Manual soft-sleep while armed | Pending persists; fires on next AWAKE + idle tick. Intentional (per user decision). |
| 4 | Window-end during busy period | Pending waits; fires when idle or is disarmed by the next window start. |
| 5 | Flag toggled off while armed | `else` branch clears pending on the next tick. |
| 6 | Master toggle off | No active windows → no falling edge → never armed. Defensive `else` clear still runs. |
| 7 | `wake_at` | Always next core start via existing F7 clamp; no manual `wake_at` for this trigger. |

## 9. Out of scope (YAGNI)

- Configurable grace period / delay between window-end and suspend (idle gating already prevents
  abrupt interruption).
- A "suspend now, ignore idle" variant (the user chose idle-gated only).
- Persisting the pending state across restarts.
- Soft-sleep variant on exit (the user chose true suspend).
- A dedicated status field for "exit-suspend armed" in `GET /status`.

## 10. Acceptance Criteria

1. Admin enables `core_uptime_enabled`, defines a window ending soon, and enables
   "Beim Fenster-Ende suspenden".
2. While idle past the window end, the server performs a true suspend within ~60 s and the Sleep
   history shows a "Kernzeit-Ende" entry.
3. With an active upload running across the window end, the server stays awake; once the upload
   finishes (system idle), it suspends.
4. With the flag off, behaviour is unchanged (idle timer counts up from 0 after the window).
