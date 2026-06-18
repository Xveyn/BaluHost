# Suspend on Core-Uptime Exit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in option that true-suspends the server as soon as a Core Operating Hours (Kernbetriebszeit) window ends, once the system is idle.

**Architecture:** A new boolean flag `core_uptime_suspend_on_exit` on `sleep_config`. The existing `_schedule_check_loop` arms an in-memory pending state on the falling edge of an active window, then fires `enter_true_suspend(... wake_at=None)` (reusing the existing F7 clamp to the next window start) on the next tick where the system is idle and unattended.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 + Alembic, Pydantic v2, pytest (async), React 18 + TypeScript + Vite, i18next.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-18-core-uptime-suspend-on-exit-design.md`.
- New flag default is `False` (opt-in). Behaviour unchanged when off.
- No new API endpoint — the flag rides the existing `PUT/GET /api/system/sleep/config`.
- Alembic migration must chain onto the **real** `alembic heads`, not the stale dev-DB head.
- Repo uses `core.autocrlf=true` on Windows; let git handle line endings (the LF→CRLF warning on commit is expected).
- Backend: 4-space indent, snake_case, type hints, async I/O. Frontend: functional components, Tailwind, `useTranslation('system')`, `toast` for errors.
- Server-local naive `datetime.now()` throughout the sleep loops (existing convention).

---

### Task 1: DB column + Alembic migration

**Files:**
- Modify: `backend/app/models/sleep.py` (the `SleepConfig` class, "Core Operating Hours" block)
- Create: `backend/alembic/versions/<rev>_add_core_uptime_suspend_on_exit.py`

**Interfaces:**
- Produces: `SleepConfig.core_uptime_suspend_on_exit: bool` (column on table `sleep_config`).

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/sleep.py`, find the "Core Operating Hours (Kernbetriebszeit)" comment block:

```python
    # Core Operating Hours (Kernbetriebszeit)
    core_uptime_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

Replace it with:

```python
    # Core Operating Hours (Kernbetriebszeit)
    core_uptime_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Opt-in: suspend as soon as a core-uptime window ends (once the system is idle)
    core_uptime_suspend_on_exit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 2: Determine the real migration head**

Run: `cd backend && alembic heads`
Expected: prints exactly one revision id (e.g. `a1b2c3d4e5f6 (head)`). Note this id — it becomes `down_revision`. If more than one head prints, STOP and reconcile heads first (do not branch the history).

- [ ] **Step 3: Create the migration**

Create `backend/alembic/versions/20260618_add_core_uptime_suspend_on_exit.py` with the head id from Step 2 substituted into `down_revision`:

```python
"""add core_uptime_suspend_on_exit to sleep_config

Revision ID: cu_suspend_on_exit
Revises: <HEAD_FROM_STEP_2>
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa

revision = "cu_suspend_on_exit"
down_revision = "<HEAD_FROM_STEP_2>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sleep_config",
        sa.Column(
            "core_uptime_suspend_on_exit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("sleep_config", "core_uptime_suspend_on_exit")
```

- [ ] **Step 4: Apply the migration in dev**

Run: `cd backend && alembic upgrade head`
Expected: `Running upgrade <HEAD> -> cu_suspend_on_exit, add core_uptime_suspend_on_exit to sleep_config`. No errors.

- [ ] **Step 5: Verify the column exists**

Run: `cd backend && python -c "import sqlite3; print([r[1] for r in sqlite3.connect('baluhost.db').execute('PRAGMA table_info(sleep_config)')])"`
Expected: the printed list includes `'core_uptime_suspend_on_exit'`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/sleep.py backend/alembic/versions/20260618_add_core_uptime_suspend_on_exit.py
git commit -m "feat(sleep): add core_uptime_suspend_on_exit column + migration"
```

---

### Task 2: Schema fields + trigger enum + get_config wiring

**Files:**
- Modify: `backend/app/schemas/sleep.py` (`SleepTrigger`, `SleepConfigUpdate`, `SleepConfigResponse`)
- Modify: `backend/app/services/power/sleep.py` (`get_config`)

**Interfaces:**
- Consumes: `SleepConfig.core_uptime_suspend_on_exit` (Task 1).
- Produces:
  - `SleepTrigger.CORE_UPTIME_EXIT = "core_uptime_exit"`
  - `SleepConfigUpdate.core_uptime_suspend_on_exit: Optional[bool]`
  - `SleepConfigResponse.core_uptime_suspend_on_exit: bool`

- [ ] **Step 1: Add the trigger enum value**

In `backend/app/schemas/sleep.py`, find:

```python
class SleepTrigger(str, Enum):
    """What triggered the sleep state change."""
    MANUAL = "manual"
    AUTO_IDLE = "auto_idle"
    SCHEDULE = "schedule"
    AUTO_WAKE = "auto_wake"
    AUTO_ESCALATION = "auto_escalation"
    WOL = "wol"
    RTC_WAKE = "rtc_wake"
    CORE_UPTIME_WAKE = "core_uptime_wake"
```

Add the new value at the end of the enum body:

```python
    CORE_UPTIME_WAKE = "core_uptime_wake"
    CORE_UPTIME_EXIT = "core_uptime_exit"
```

- [ ] **Step 2: Add the field to `SleepConfigUpdate`**

In `SleepConfigUpdate`, find `core_uptime_enabled: Optional[bool] = None` and add the new field directly after it:

```python
    core_uptime_enabled: Optional[bool] = None
    core_uptime_suspend_on_exit: Optional[bool] = None
```

- [ ] **Step 3: Add the field to `SleepConfigResponse`**

In `SleepConfigResponse`, find the core-operating-hours line and add the new field after it:

```python
    # Core operating hours
    core_uptime_enabled: bool = Field(default=False, description="Master toggle for core operating hours")
    core_uptime_suspend_on_exit: bool = Field(default=False, description="Suspend when a core-uptime window ends")
```

- [ ] **Step 4: Wire it into `get_config`**

In `backend/app/services/power/sleep.py`, in `get_config`, find `core_uptime_enabled=config.core_uptime_enabled,` in the `SleepConfigResponse(...)` constructor and add the new field after it:

```python
            core_uptime_enabled=config.core_uptime_enabled,
            core_uptime_suspend_on_exit=bool(config.core_uptime_suspend_on_exit),
```

(`update_config` needs no change — its generic `setattr` loop already persists the new field.)

- [ ] **Step 5: Verify import + roundtrip**

Run: `cd backend && python -c "from app.schemas.sleep import SleepTrigger, SleepConfigUpdate, SleepConfigResponse; print(SleepTrigger.CORE_UPTIME_EXIT.value); print('core_uptime_suspend_on_exit' in SleepConfigUpdate.model_fields); print(SleepConfigResponse().core_uptime_suspend_on_exit)"`
Expected:
```
core_uptime_exit
True
False
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/sleep.py backend/app/services/power/sleep.py
git commit -m "feat(sleep): schema + trigger + get_config for suspend-on-exit"
```

---

### Task 3: Service logic — arm on window-end, fire when idle (TDD)

**Files:**
- Modify: `backend/app/services/power/sleep.py` (`SleepManagerService.__init__`, `_schedule_check_loop`)
- Test: `backend/tests/services/test_sleep_core_uptime_integration.py`

**Interfaces:**
- Consumes: `SleepTrigger.CORE_UPTIME_EXIT`, `config.core_uptime_suspend_on_exit` (Task 2), existing `_is_system_idle`, `_get_activity_metrics`, `_is_user_present`, `_is_always_awake`, `enter_true_suspend`, `_load_core_uptime`, `core_uptime_helpers.is_in_core_uptime`, `self._was_in_core_uptime`.
- Produces: instance attribute `self._core_uptime_exit_pending: bool`.

- [ ] **Step 1: Extend the `_config` test helper with the new flag**

In `backend/tests/services/test_sleep_core_uptime_integration.py`, change the `_config` signature and body. Find:

```python
def _config(core_enabled: bool = True, auto_idle_enabled: bool = True, idle_timeout_minutes: int = 1):
    cfg = SleepConfig(
```

Replace the signature line with:

```python
def _config(core_enabled: bool = True, auto_idle_enabled: bool = True, idle_timeout_minutes: int = 1,
            suspend_on_exit: bool = False):
    cfg = SleepConfig(
```

Then find the last kwarg in that `SleepConfig(...)` call:

```python
        core_uptime_enabled=core_enabled,
    )
    return cfg
```

Replace it with:

```python
        core_uptime_enabled=core_enabled,
        core_uptime_suspend_on_exit=suspend_on_exit,
    )
    return cfg
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/services/test_sleep_core_uptime_integration.py`:

```python
# --------------------------------------------------------------------------
# Suspend on core-uptime exit (2026-06-18)
# --------------------------------------------------------------------------

def _patch_loop_env(svc, cfg, *, in_core, idle, present=False, always_awake=False):
    """Common patch set for driving _schedule_check_loop one or more ticks.

    `in_core` may be a tuple (active, window) or a side_effect callable.
    """
    is_in_core = in_core if callable(in_core) else (lambda *a, **k: in_core)
    return [
        patch.object(svc, "_load_config", return_value=cfg),
        patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])),
        patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime", side_effect=is_in_core),
        patch.object(svc, "_is_system_idle", return_value=idle),
        patch.object(svc, "_is_user_present", return_value=present),
        patch.object(svc, "_is_always_awake", return_value=always_awake),
    ]


@pytest.mark.asyncio
async def test_suspend_on_exit_arms_and_fires_when_idle():
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=True)
    suspend_calls = []

    async def fake_suspend(reason, trigger=None, wake_at=None):
        suspend_calls.append((reason, trigger, wake_at))
        return True

    patches = _patch_loop_env(svc, cfg, in_core=(False, None), idle=True)
    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True  # we were inside a window on the previous tick

        async def stop_after_one(*_a, **_k):
            svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one))
        await svc._schedule_check_loop()

    assert len(suspend_calls) == 1
    assert suspend_calls[0][0] == "core_uptime_exit"
    assert suspend_calls[0][1] == SleepTrigger.CORE_UPTIME_EXIT
    assert suspend_calls[0][2] is None  # wake_at=None -> clamped inside enter_true_suspend
    assert svc._core_uptime_exit_pending is False


@pytest.mark.asyncio
async def test_suspend_on_exit_waits_while_busy():
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=True)
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append((a, k))
        return True

    patches = _patch_loop_env(svc, cfg, in_core=(False, None), idle=False)  # busy
    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        async def stop_after_one(*_a, **_k):
            svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one))
        await svc._schedule_check_loop()

    assert suspend_calls == []                       # busy -> no suspend
    assert svc._core_uptime_exit_pending is True     # armed, waiting


@pytest.mark.asyncio
async def test_suspend_on_exit_fires_on_next_idle_tick():
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=True)
    suspend_calls = []

    async def fake_suspend(reason, trigger=None, wake_at=None):
        suspend_calls.append(reason)
        return True

    idle_seq = iter([False, True])  # tick1 busy, tick2 idle

    import contextlib
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(svc, "_load_config", return_value=cfg))
        stack.enter_context(patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])))
        stack.enter_context(patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
                                  side_effect=lambda *a, **k: (False, None)))
        stack.enter_context(patch.object(svc, "_is_system_idle", side_effect=lambda *a, **k: next(idle_seq)))
        stack.enter_context(patch.object(svc, "_is_user_present", return_value=False))
        stack.enter_context(patch.object(svc, "_is_always_awake", return_value=False))
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        ticks = [0]

        async def two_ticks(*_a, **_k):
            ticks[0] += 1
            if ticks[0] >= 2:
                svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=two_ticks))
        await svc._schedule_check_loop()

    assert suspend_calls == ["core_uptime_exit"]  # fired exactly once, on the idle tick


@pytest.mark.asyncio
async def test_suspend_on_exit_blocked_by_presence():
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=True)
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append(a)
        return True

    patches = _patch_loop_env(svc, cfg, in_core=(False, None), idle=True, present=True)
    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        async def stop_after_one(*_a, **_k):
            svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one))
        await svc._schedule_check_loop()

    assert suspend_calls == []
    assert svc._core_uptime_exit_pending is True  # stays armed; presence is a gate, not a disarm


@pytest.mark.asyncio
async def test_suspend_on_exit_blocked_by_always_awake():
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=True)
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append(a)
        return True

    patches = _patch_loop_env(svc, cfg, in_core=(False, None), idle=True, always_awake=True)
    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        async def stop_after_one(*_a, **_k):
            svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one))
        await svc._schedule_check_loop()

    assert suspend_calls == []


@pytest.mark.asyncio
async def test_suspend_on_exit_disarmed_by_new_window():
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=True)
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append(a)
        return True

    patches = _patch_loop_env(svc, cfg, in_core=(True, _window_workdays_8_22()), idle=True)
    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True
        svc._core_uptime_exit_pending = True  # pretend a prior tick armed it

        async def stop_after_one(*_a, **_k):
            svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one))
        await svc._schedule_check_loop()

    assert suspend_calls == []
    assert svc._core_uptime_exit_pending is False  # new active window disarms


@pytest.mark.asyncio
async def test_suspend_on_exit_flag_off_never_arms():
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=False)  # feature off
    suspend_calls = []

    async def fake_suspend(*a, **k):
        suspend_calls.append(a)
        return True

    patches = _patch_loop_env(svc, cfg, in_core=(False, None), idle=True)
    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        async def stop_after_one(*_a, **_k):
            svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one))
        await svc._schedule_check_loop()

    assert suspend_calls == []
    assert svc._core_uptime_exit_pending is False


@pytest.mark.asyncio
async def test_suspend_on_exit_works_without_schedule():
    """Regression guard: must fire even though schedule_enabled is False
    (insert position is BEFORE the `if not schedule_enabled: continue`)."""
    svc = _build_service()
    cfg = _config(core_enabled=True, suspend_on_exit=True)  # schedule_enabled defaults False
    suspend_calls = []

    async def fake_suspend(reason, trigger=None, wake_at=None):
        suspend_calls.append(reason)
        return True

    patches = _patch_loop_env(svc, cfg, in_core=(False, None), idle=True)
    import contextlib
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.AWAKE
        svc._was_in_core_uptime = True

        async def stop_after_one(*_a, **_k):
            svc._is_running = False

        stack.enter_context(patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one))
        await svc._schedule_check_loop()

    assert suspend_calls == ["core_uptime_exit"]
```

- [ ] **Step 3: Run the tests — they should fail**

Run: `cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -k suspend_on_exit -v`
Expected: FAIL — `AttributeError: ... '_core_uptime_exit_pending'` and/or no suspend fired (logic not implemented yet).

- [ ] **Step 4: Initialize the pending attribute in `__init__`**

In `backend/app/services/power/sleep.py`, in `SleepManagerService.__init__`, find the line that initializes the core-uptime edge tracker:

```python
        self._was_in_core_uptime = False
```

Add directly after it:

```python
        self._was_in_core_uptime = False
        # Armed when a core-uptime window ends and core_uptime_suspend_on_exit is on;
        # fires a true suspend on the next idle/unattended tick. In-memory only.
        self._core_uptime_exit_pending = False
```

- [ ] **Step 5: Insert the arm/fire block in `_schedule_check_loop`**

In `_schedule_check_loop`, find the inhibitor reconcile call followed by the edge-state tracking block:

```python
                # Logind inhibitor management — converged to the desired state
                # every tick so a crashed inhibitor subprocess gets re-acquired,
                # a master-toggle-off promptly releases, and Always-Awake also
                # blocks third-party suspends.
                self._reconcile_sleep_inhibitor(config, in_core=in_core)

                # Track edge state regardless. When master is off we force False so
                # that re-enabling the toggle while inside an active window registers
                # as a fresh rising edge on the next tick and triggers auto-wake.
                if master:
                    self._was_in_core_uptime = in_core
                else:
                    self._was_in_core_uptime = False
```

Insert the new block **between** the `_reconcile_sleep_inhibitor(...)` call and the `# Track edge state regardless.` comment (so `falling_edge` reads the still-current prior `_was_in_core_uptime`):

```python
                self._reconcile_sleep_inhibitor(config, in_core=in_core)

                # Suspend-on-exit: arm on the falling edge of an active window,
                # fire a true suspend once the system is idle and unattended.
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

                if (
                    self._core_uptime_exit_pending
                    and self._current_state == SleepState.AWAKE
                    and not in_core
                    and config is not None
                    and not self._is_always_awake(config)
                    and not self._is_user_present(config)
                    and self._is_system_idle(config, self._get_activity_metrics())
                ):
                    logger.info(
                        "Suspend-on-exit: system idle after core uptime — entering true suspend"
                    )
                    self._core_uptime_exit_pending = False
                    await self.enter_true_suspend(
                        "core_uptime_exit", SleepTrigger.CORE_UPTIME_EXIT, wake_at=None,
                    )

                # Track edge state regardless. When master is off we force False so
```

(Leave the existing `# Track edge state regardless.` block and everything after it unchanged.)

- [ ] **Step 6: Run the suspend-on-exit tests — they should pass**

Run: `cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -k suspend_on_exit -v`
Expected: PASS (7 tests).

- [ ] **Step 7: Run the whole core-uptime + sleep suite — no regression**

Run: `cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py tests/test_sleep.py -v`
Expected: all pass (existing + new).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/services/test_sleep_core_uptime_integration.py
git commit -m "feat(sleep): arm + fire true suspend on core-uptime window end"
```

---

### Task 4: Frontend API types + history label

**Files:**
- Modify: `client/src/api/sleep.ts`

**Interfaces:**
- Consumes: backend `core_uptime_suspend_on_exit` field and `core_uptime_exit` trigger (Tasks 2–3).
- Produces: TS `SleepConfigResponse.core_uptime_suspend_on_exit`, `SleepConfigUpdate.core_uptime_suspend_on_exit`, `SleepTrigger` union member `'core_uptime_exit'`, `TRIGGER_LABELS.core_uptime_exit`.

- [ ] **Step 1: Extend the `SleepTrigger` union**

In `client/src/api/sleep.ts`, find:

```typescript
export type SleepTrigger =
  | 'manual'
  | 'auto_idle'
  | 'schedule'
  | 'auto_wake'
  | 'auto_escalation'
  | 'wol'
  | 'rtc_wake'
  | 'core_uptime_wake';
```

Replace the last line with:

```typescript
  | 'core_uptime_wake'
  | 'core_uptime_exit';
```

- [ ] **Step 2: Add the config fields**

In `SleepConfigResponse`, find `core_uptime_enabled: boolean;` and add after it:

```typescript
  core_uptime_enabled: boolean;
  core_uptime_suspend_on_exit: boolean;
```

In `SleepConfigUpdate`, find `core_uptime_enabled?: boolean;` and add after it:

```typescript
  core_uptime_enabled?: boolean;
  core_uptime_suspend_on_exit?: boolean;
```

- [ ] **Step 3: Add the history label**

In `TRIGGER_LABELS`, find `core_uptime_wake: 'Kernzeit-Wake',` and add after it:

```typescript
  core_uptime_wake: 'Kernzeit-Wake',
  core_uptime_exit: 'Kernzeit-Ende',
```

- [ ] **Step 4: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors. (`TRIGGER_LABELS` is `Record<SleepTrigger, string>`, so a missing key would fail here — confirms the union + map stay in sync.)

- [ ] **Step 5: Commit**

```bash
git add client/src/api/sleep.ts
git commit -m "feat(sleep): frontend types + history label for suspend-on-exit"
```

---

### Task 5: Frontend toggle in CoreUptimePanel + i18n

**Files:**
- Modify: `client/src/components/power/CoreUptimePanel.tsx`
- Modify: `client/src/i18n/locales/de/system.json`
- Modify: `client/src/i18n/locales/en/system.json`

**Interfaces:**
- Consumes: `getSleepConfig`/`updateSleepConfig` (already imported), `SleepConfigResponse.core_uptime_suspend_on_exit` (Task 4), i18n keys `sleep.coreUptime.suspendOnExit` / `suspendOnExitDesc`.

- [ ] **Step 1: Add i18n keys (German)**

In `client/src/i18n/locales/de/system.json`, locate the `"coreUptime"` object nested under `"sleep"` (it contains keys like `"title"`, `"description"`, `"masterToggle"`, `"addWindow"`, `"blockedActions"`). Add two keys inside that object (e.g. right after `"blockedActions"`):

```json
      "suspendOnExit": "Beim Fenster-Ende suspenden",
      "suspendOnExitDesc": "Suspendet den Server, sobald die Kernbetriebszeit endet (sobald das System idle ist).",
```

Ensure the preceding line ends with a comma and the JSON stays valid.

- [ ] **Step 2: Add i18n keys (English)**

In `client/src/i18n/locales/en/system.json`, locate the same `sleep.coreUptime` object and add:

```json
      "suspendOnExit": "Suspend when window ends",
      "suspendOnExitDesc": "Suspends the server as soon as the core operating window ends (once the system is idle).",
```

- [ ] **Step 3: Validate both JSON files**

Run:
```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/system.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/en/system.json','utf8')); console.log('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Add state + loader in the panel**

In `client/src/components/power/CoreUptimePanel.tsx`, find the state declarations:

```typescript
  const [masterEnabled, setMasterEnabled] = useState(false);
  const [windows, setWindows] = useState<CoreUptimeWindow[]>([]);
  const [loading, setLoading] = useState(true);
```

Add a new state after `masterEnabled`:

```typescript
  const [masterEnabled, setMasterEnabled] = useState(false);
  const [suspendOnExit, setSuspendOnExit] = useState(false);
  const [windows, setWindows] = useState<CoreUptimeWindow[]>([]);
  const [loading, setLoading] = useState(true);
```

In `refresh`, find:

```typescript
      const [cfg, ws] = await Promise.all([getSleepConfig(), listCoreUptimeWindows()]);
      setMasterEnabled(cfg.core_uptime_enabled);
      setWindows(ws);
```

Add the new setter:

```typescript
      const [cfg, ws] = await Promise.all([getSleepConfig(), listCoreUptimeWindows()]);
      setMasterEnabled(cfg.core_uptime_enabled);
      setSuspendOnExit(cfg.core_uptime_suspend_on_exit);
      setWindows(ws);
```

- [ ] **Step 5: Add the toggle handler**

In `CoreUptimePanel.tsx`, find `handleMasterToggle` and add a sibling handler directly after its closing `};`:

```typescript
  const handleSuspendOnExitToggle = async () => {
    const next = !suspendOnExit;
    setSuspendOnExit(next); // optimistic
    try {
      await updateSleepConfig({ core_uptime_suspend_on_exit: next });
    } catch (err) {
      setSuspendOnExit(!next);
      toast.error(err instanceof Error ? err.message : t('sleep.coreUptime.saveFailed'));
    }
  };
```

- [ ] **Step 6: Render the toggle inside the `masterEnabled` block**

In the JSX, find the bottom of the `{masterEnabled && (...)}` block:

```tsx
          <p className="text-xs text-slate-500 mt-2">
            {t('sleep.coreUptime.blockedActions')}
          </p>
        </div>
      )}
```

Insert the toggle row immediately before that `<p ...>blockedActions</p>`:

```tsx
          <div className="flex items-start justify-between gap-3 pt-2 border-t border-slate-700/50">
            <div>
              <p className="text-sm text-white">{t('sleep.coreUptime.suspendOnExit')}</p>
              <p className="mt-0.5 text-xs text-slate-400">{t('sleep.coreUptime.suspendOnExitDesc')}</p>
            </div>
            <button
              type="button"
              onClick={handleSuspendOnExitToggle}
              className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
                suspendOnExit ? 'bg-emerald-500' : 'bg-slate-600'
              }`}
              aria-label={t('sleep.coreUptime.suspendOnExit')}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
                  suspendOnExit ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
                } mt-0.5`}
              />
            </button>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            {t('sleep.coreUptime.blockedActions')}
          </p>
```

- [ ] **Step 7: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add client/src/components/power/CoreUptimePanel.tsx client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json
git commit -m "feat(sleep): UI toggle + i18n for suspend-on-core-uptime-exit"
```

---

### Task 6: Final verification

**Files:** none new (fix-ups only if a check fails)

- [ ] **Step 1: Backend — focused suite**

Run: `cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py tests/test_sleep.py -v`
Expected: all pass.

- [ ] **Step 2: Frontend — type-check + build**

Run: `cd client && npx tsc --noEmit && npm run build`
Expected: no type errors, successful build.

- [ ] **Step 3: Frontend — unit tests**

Run: `cd client && npx vitest run`
Expected: pass (no sleep-panel unit tests should break; if none touch CoreUptimePanel, suite is green).

- [ ] **Step 4: Manual smoke (dev mode)**

In two terminals: `python start_dev.py`, then open `http://localhost:5173`, log in as `admin` / `DevMode2024`. Go to **System Control → Hardware → Sleep**. Verify:

1. The **Kernbetriebszeit** panel shows the new "Beim Fenster-Ende suspenden" toggle when the master toggle is on.
2. Toggling it persists across a page reload (`GET /config` returns `core_uptime_suspend_on_exit: true`).
3. With master on, a window covering "now" minus a minute (so it just ended), `suspend_on_exit` on, and the system idle: within ~60 s the dev backend logs `Suspend-on-exit: system idle after core uptime — entering true suspend` and `[DEV] Simulated system suspend with RTC wake at <next window start>`. The Sleep history shows a **Kernzeit-Ende** entry.
4. With `suspend_on_exit` off, no such suspend occurs (idle timer counts up from 0 instead).

If any check fails, jump back to the relevant task.

- [ ] **Step 5: Final commit (only if fix-ups were needed)**

```bash
git add -A
git commit -m "fix(sleep): smoke fixes for suspend-on-exit"
```

---

## Self-Review Result

**Spec coverage:**
- F1 (opt-in flag, default off): Task 1 (column) + Task 2 (schema).
- F2 (arm on falling edge): Task 3 Step 5.
- F3 (fire when idle + presence/always-awake gated): Task 3 Step 5 + tests.
- F4 (true suspend, `wake_at=None` → F7 clamp): Task 3 Step 5; verified by `wake_at is None` assertion.
- F5 (persist/pending while busy): `test_suspend_on_exit_waits_while_busy`, `..._fires_on_next_idle_tick`.
- F6 (disarm on new window / flag off / fire): `..._disarmed_by_new_window`, `..._flag_off_never_arms`.
- F7 (trigger `CORE_UPTIME_EXIT` → history "Kernzeit-Ende"): Task 2 Step 1 + Task 4 Step 3.
- F8 (frontend toggle): Task 5.
- N1 (no new loop, 60 s cadence): Task 3 inserts into `_schedule_check_loop`.
- N2 (additive migration): Task 1.
- N3 (no new endpoint): Task 2 (rides existing config route).
- N4 (in-memory pending): Task 3 Step 4.

**Placeholder scan:** `<HEAD_FROM_STEP_2>` / `<rev>` are intentional, resolved in Task 1 Steps 2–3 from live `alembic heads`. No other placeholders.

**Type consistency:** `core_uptime_suspend_on_exit` (snake_case backend, same key in TS); `SleepTrigger.CORE_UPTIME_EXIT` / `'core_uptime_exit'`; `_core_uptime_exit_pending` used consistently across `__init__`, loop, and tests. `_patch_loop_env` helper signature matches all call sites.
