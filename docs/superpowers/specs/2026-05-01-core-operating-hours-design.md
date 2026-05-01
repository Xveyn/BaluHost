# Design — Core Operating Hours (Kernbetriebszeit)

**Date:** 2026-05-01
**Status:** Approved (brainstorming complete, ready for implementation plan)
**Owner:** Xveyn

## 1. Goal

Allow admins to define one or more recurring time windows (with weekday selection) during which the BaluHost server **must remain awake** and reachable to other users. While such a "core operating hours" window is active, every automatic sleep/suspend trigger is suppressed; only an admin can still suspend manually, and only after acknowledging an explicit warning.

Surfaces as a new panel in the existing **System Control → Hardware → Sleep** tab, in the visual style of the surrounding cards.

## 2. Requirements

### Functional
- **F1** Admin can create, edit, enable/disable, and delete an arbitrary number of core-uptime windows.
- **F2** Each window has: optional label, start time `HH:MM`, end time `HH:MM`, weekday selection (Mon..Sun), per-window enabled flag.
- **F3** Windows may cross midnight (`end < start`); the configured weekdays describe the window's **start** day.
- **F4** A global master toggle enables/disables the whole feature without losing window definitions.
- **F5** While any enabled window is currently active:
  - Auto-idle sleep does not trigger (idle counter does not advance).
  - Schedule-based sleep does not trigger.
  - Auto-escalation from soft sleep to true suspend does not trigger.
- **F6** When an active window starts and the system is currently in **soft sleep**, the system auto-wakes (transition `SOFT_SLEEP → AWAKE`) within at most ~60 seconds.
- **F7** Whenever `enter_true_suspend` is called: the resulting `wake_at` is clamped to `min(provided_wake_at, next_core_uptime_start)`. If no `wake_at` was provided, the next core uptime start is used. RTC alarm fires accordingly. (In practice this fires only for manual admin suspend, since auto-escalation is suppressed during active windows per F5.)
- **F8** Manual admin suspend remains possible at all times. If invoked while a window is active, the confirmation dialog shows an extra warning line; the action proceeds only after explicit confirmation.
- **F9** A status banner in the Sleep panel makes the active window visible to all users (including non-admins) — fulfilling the user-transparency requirement.
- **F10** When the existing sleep-`schedule_enabled` and `core_uptime_enabled` are both on, the schedule is silently overridden during active windows. The schedule UI shows an info hint that core uptime takes precedence.

### Non-functional
- **N1** Helper functions for window matching are pure (no DB), unit-testable in isolation.
- **N2** Window list reload happens at most once per loop iteration (30 s for idle loop, 60 s for schedule loop). No caching layer needed.
- **N3** Migration is additive: one new column on `sleep_config`, one new table. No data migration required.
- **N4** All admin-facing endpoints are `Depends(get_current_admin)` and rate-limited via the existing `admin_operations` bucket.
- **N5** Status reads (`/sleep/status`) remain available to any authenticated user.

## 3. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│ Frontend (React)                                                   │
│  client/src/pages/SleepMode.tsx                                    │
│  ├── SleepModePanel.tsx       (+ banner if core_uptime.active)     │
│  ├── CoreUptimePanel.tsx      ← NEW                                │
│  ├── SleepConfigPanel.tsx     (+ schedule-override hint)           │
│  └── SleepHistoryTable.tsx    (+ "core_uptime_wake" trigger label) │
│                                                                    │
│  client/src/api/coreUptime.ts ← NEW                                │
│  client/src/api/sleep.ts      (+ core_uptime field on status)      │
└─────────────────────┬──────────────────────────────────────────────┘
                      │ HTTP /api/system/sleep/...
┌─────────────────────▼──────────────────────────────────────────────┐
│ Backend API (FastAPI)                                              │
│  backend/app/api/routes/sleep.py                                   │
│   + GET    /core-uptime/windows                                    │
│   + POST   /core-uptime/windows                                    │
│   + PUT    /core-uptime/windows/{id}                               │
│   + DELETE /core-uptime/windows/{id}                               │
│   ~ PUT    /config           (extended w/ core_uptime_enabled)     │
│   ~ GET    /status           (extended w/ core_uptime field)       │
└─────────────────────┬──────────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────────────┐
│ Service Layer                                                      │
│  backend/app/services/power/sleep.py (SleepManagerService)         │
│   ~ _idle_detection_loop      (skip when in_core_uptime)           │
│   ~ _schedule_check_loop      (skip + auto-wake edge detection)    │
│   ~ _escalation_monitor       (skip when in_core_uptime)           │
│   ~ enter_true_suspend        (clamp wake_at to next core start)   │
│                                                                    │
│  backend/app/services/power/core_uptime.py ← NEW                   │
│   • is_in_core_uptime(now, windows) -> (bool, Window|None)         │
│   • next_core_uptime_start(now, windows) -> datetime|None          │
│   • current_window_end(now, window) -> datetime                    │
└─────────────────────┬──────────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────────────┐
│ Database                                                           │
│  sleep_config              (+ core_uptime_enabled BOOL)            │
│  core_uptime_windows       ← NEW                                   │
└────────────────────────────────────────────────────────────────────┘
```

## 4. Data Model

### 4.1 New table `core_uptime_windows`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer | PK, indexed | |
| `enabled` | Boolean | not null, default `True` | Per-window flag, allows draft windows without deletion |
| `label` | String(50) | nullable | Optional human-readable name (e.g., "Werktage") |
| `start_time` | String(5) | not null | Format `HH:MM`, server-local time |
| `end_time` | String(5) | not null | Format `HH:MM`. If `end < start`, the window crosses midnight |
| `weekdays` | String(15) | not null | CSV of integers `0`=Mon … `6`=Sun, the days the window **starts** on |
| `created_at` | DateTime(tz=True) | not null, default `now()` | |
| `updated_at` | DateTime(tz=True) | not null, default `now()`, on update `now()` | |

### 4.2 Existing table `sleep_config` — new column

| Column | Type | Default | Notes |
|---|---|---|---|
| `core_uptime_enabled` | Boolean | `False` | Master toggle for the whole feature |

### 4.3 SQLAlchemy model

```python
# backend/app/models/sleep.py — appended to existing file

class CoreUptimeWindow(Base):
    __tablename__ = "core_uptime_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    weekdays: Mapped[str] = mapped_column(String(15), nullable=False)  # CSV "0,1,2,3,4"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

# Existing SleepConfig gets one extra mapped_column:
#   core_uptime_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

### 4.4 Alembic migration (additive)

```python
def upgrade():
    op.add_column(
        "sleep_config",
        sa.Column("core_uptime_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "core_uptime_windows",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("label", sa.String(50), nullable=True),
        sa.Column("start_time", sa.String(5), nullable=False),
        sa.Column("end_time", sa.String(5), nullable=False),
        sa.Column("weekdays", sa.String(15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

def downgrade():
    op.drop_table("core_uptime_windows")
    op.drop_column("sleep_config", "core_uptime_enabled")
```

## 5. Domain Helpers

New module `backend/app/services/power/core_uptime.py` — pure functions, no DB access. The caller (`SleepManagerService`) is responsible for loading the window list once per loop tick.

### 5.1 Window-matching semantics

- `start_time` is **inclusive** (`current >= start`).
- `end_time` is **exclusive** (`current < end`). This avoids double-matching at boundaries.
- For `end < start` (cross-midnight): the window covers `[start_today, 24:00)` ∪ `[00:00, end_next_day)`, **only if today's weekday is in `weekdays`**. The next day is implicitly included via the start-day rule.
- Multiple enabled windows: the system is "in core uptime" if **any** enabled window matches (union semantics).
- Disabled windows (`enabled=False`) are ignored entirely.

### 5.2 API surface

```python
def is_in_core_uptime(
    now: datetime,
    windows: Sequence[CoreUptimeWindow],
) -> tuple[bool, Optional[CoreUptimeWindow]]:
    """Return (active, matching_window). Picks the first matching enabled window."""

def next_core_uptime_start(
    now: datetime,
    windows: Sequence[CoreUptimeWindow],
) -> Optional[datetime]:
    """Earliest start datetime within next 7 days across all enabled windows.
       Returns None if no enabled windows exist."""

def current_window_end(
    now: datetime,
    window: CoreUptimeWindow,
) -> datetime:
    """Datetime when the currently-active window ends. Caller must ensure
       `now` is actually inside `window`."""
```

### 5.3 Time zone

All comparisons use server-local time (`datetime.now()` without tzinfo), consistent with the existing `_schedule_check_loop`. The current loop uses `now.strftime("%H:%M")` so we stay in the same convention.

## 6. Service Logic Changes

In `backend/app/services/power/sleep.py`:

### 6.1 Window-list cache helper

```python
def _load_core_uptime(self) -> tuple[bool, list[CoreUptimeWindow]]:
    """Return (master_enabled, list_of_enabled_windows). Called once per loop tick."""
```

Returns an empty list if the master toggle is off, so all callers can skip cheaply.

### 6.2 `_idle_detection_loop`

Before the existing idle check:

```python
master_enabled, windows = self._load_core_uptime()
if master_enabled:
    in_core, _ = is_in_core_uptime(datetime.now(), windows)
    if in_core:
        self._consecutive_idle_checks = 0
        self._idle_seconds = 0.0
        continue  # do not advance idle counter
```

### 6.3 `_schedule_check_loop`

Two changes inside the existing loop:

1. **Suppress schedule-sleep trigger** when in core uptime:
   ```python
   master_enabled, windows = self._load_core_uptime()
   in_core, _ = is_in_core_uptime(datetime.now(), windows) if master_enabled else (False, None)
   if self._current_state == SleepState.AWAKE and self._time_matches(...) and not in_core:
       # existing schedule-sleep dispatch
   ```
2. **Auto-wake edge detection**:
   ```python
   if master_enabled:
       if in_core and not self._was_in_core_uptime and self._current_state == SleepState.SOFT_SLEEP:
           await self.exit_soft_sleep("core_uptime_started")
       self._was_in_core_uptime = in_core
   else:
       self._was_in_core_uptime = False
   ```
   `_was_in_core_uptime: bool` is a new instance attribute initialised to `False`.

### 6.4 `_escalation_monitor`

After waking from `asyncio.sleep`:

```python
master_enabled, windows = self._load_core_uptime()
if master_enabled:
    in_core, _ = is_in_core_uptime(datetime.now(), windows)
    if in_core:
        return  # cancel escalation silently
```

### 6.5 `enter_true_suspend(reason, trigger, wake_at)`

Before kernel suspend:

```python
master_enabled, windows = self._load_core_uptime()
if master_enabled:
    next_core = next_core_uptime_start(datetime.now(), windows)
    if next_core is not None and (wake_at is None or next_core < wake_at):
        wake_at = next_core
```

The change is additive: if no core uptime is configured, behaviour is identical to today.

### 6.6 New SleepTrigger enum value

`backend/app/schemas/sleep.py`:

```python
class SleepTrigger(str, Enum):
    ...
    CORE_UPTIME_WAKE = "core_uptime_wake"
```

The trigger is logged via `_log_state_change` when auto-wake fires.

## 7. API Endpoints

All new routes live in the existing `backend/app/api/routes/sleep.py` (same `/api/system/sleep/` prefix, same `tags=["sleep"]`).

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| `GET` | `/api/system/sleep/core-uptime/windows` | admin | — | `list[CoreUptimeWindowResponse]` |
| `POST` | `/api/system/sleep/core-uptime/windows` | admin | `CoreUptimeWindowCreate` | `CoreUptimeWindowResponse` |
| `PUT` | `/api/system/sleep/core-uptime/windows/{id}` | admin | `CoreUptimeWindowUpdate` (partial) | `CoreUptimeWindowResponse` |
| `DELETE` | `/api/system/sleep/core-uptime/windows/{id}` | admin | — | `204 No Content` |

Existing endpoints, extended:

- `PUT /api/system/sleep/config` — `SleepConfigUpdate` and `SleepConfigResponse` gain `core_uptime_enabled: bool`.
- `GET /api/system/sleep/status` — `SleepStatusResponse` gains a nested `core_uptime: CoreUptimeStatus` object.

### 7.1 New Pydantic schemas (`backend/app/schemas/sleep.py`)

```python
class CoreUptimeWindowBase(BaseModel):
    enabled: bool = True
    label: Optional[str] = Field(default=None, max_length=50)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    weekdays: list[int] = Field(..., description="0=Monday..6=Sunday, deduplicated, sorted")

    @field_validator("weekdays")
    @classmethod
    def _validate_weekdays(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("at least one weekday required")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekdays must be 0..6")
        return sorted(set(v))

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_hhmm(cls, v: str) -> str:
        h, m = map(int, v.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("invalid HH:MM")
        return v

    @model_validator(mode="after")
    def _validate_times_distinct(self) -> "CoreUptimeWindowBase":
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must differ")
        return self


class CoreUptimeWindowCreate(CoreUptimeWindowBase):
    pass


class CoreUptimeWindowUpdate(BaseModel):
    enabled: Optional[bool] = None
    label: Optional[str] = Field(default=None, max_length=50)
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekdays: Optional[list[int]] = None
    # validators reused via mode="before" or after-update reload


class CoreUptimeWindowResponse(CoreUptimeWindowBase):
    id: int
    created_at: datetime
    updated_at: datetime


class CoreUptimeStatus(BaseModel):
    enabled: bool = Field(description="Master toggle state")
    active: bool = Field(description="Whether some enabled window is currently active")
    current_window_label: Optional[str] = None
    current_window_ends_at: Optional[datetime] = None
    next_start: Optional[datetime] = None


# Extension to SleepStatusResponse
class SleepStatusResponse(BaseModel):
    ...  # existing fields unchanged
    core_uptime: CoreUptimeStatus = Field(default_factory=CoreUptimeStatus)
```

`weekdays` is exposed as `list[int]` over the API. Backend serializes to/from the CSV column via a small helper in the service layer.

### 7.2 Rate limiting & audit

- Rate limit: `@user_limiter.limit(get_limit("admin_operations"))` on every new endpoint.
- Audit logging: create / update / delete each call `get_audit_logger_db().log_security_event(action="core_uptime_window_create" | "_update" | "_delete", ...)`. Reads are not audited.

## 8. Frontend

### 8.1 New API client `client/src/api/coreUptime.ts`

```typescript
export interface CoreUptimeWindow {
  id: number;
  enabled: boolean;
  label: string | null;
  start_time: string;   // "HH:MM"
  end_time: string;
  weekdays: number[];   // 0=Mon..6=Sun
  created_at: string;
  updated_at: string;
}

export interface CoreUptimeWindowCreate {
  enabled?: boolean;
  label?: string | null;
  start_time: string;
  end_time: string;
  weekdays: number[];
}

export type CoreUptimeWindowUpdate = Partial<CoreUptimeWindowCreate>;

export interface CoreUptimeStatus {
  enabled: boolean;
  active: boolean;
  current_window_label: string | null;
  current_window_ends_at: string | null;
  next_start: string | null;
}

export async function listCoreUptimeWindows(): Promise<CoreUptimeWindow[]>;
export async function createCoreUptimeWindow(data: CoreUptimeWindowCreate): Promise<CoreUptimeWindow>;
export async function updateCoreUptimeWindow(id: number, data: CoreUptimeWindowUpdate): Promise<CoreUptimeWindow>;
export async function deleteCoreUptimeWindow(id: number): Promise<void>;
```

### 8.2 Extension to `client/src/api/sleep.ts`

```typescript
export interface CoreUptimeStatus { /* mirror of backend */ }

export interface SleepStatusResponse {
  ...  // existing fields unchanged
  core_uptime: CoreUptimeStatus;
}

export interface SleepConfigResponse {
  ...
  core_uptime_enabled: boolean;
}

export interface SleepConfigUpdate {
  ...
  core_uptime_enabled?: boolean;
}

// Add to TRIGGER_LABELS and SleepTrigger union:
//   'core_uptime_wake' → 'Kernzeit-Wake' / 'Core-uptime wake'
```

### 8.3 New component `client/src/components/power/CoreUptimePanel.tsx`

Card-based layout, same visual language as siblings (`card border-slate-700/50 p-4 sm:p-6`).

```
┌─────────────────────────────────────────────────────────────┐
│ 🛡 Kernbetriebszeit                            [ Toggle ]    │   ← master toggle (sleep_config.core_uptime_enabled)
│ Server bleibt erreichbar; Auto-Sleep blockiert.              │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [✓]  ✏️ Werktage                      [Mo Di Mi Do Fr Sa So]   ✕ │
│ │      ⏰ 08:00  →  22:00                                  │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [✓]  ✏️ Wochenende                    [Mo Di Mi Do Fr Sa So]   ✕ │
│ │      ⏰ 10:00  →  23:30                                  │ │
│ └─────────────────────────────────────────────────────────┘ │
│ [ + Neues Zeitfenster hinzufügen ]                           │
│                                                              │
│ ℹ Während aktiver Fenster werden Auto-Idle-Sleep,            │
│   Schedule-Sleep und Auto-Escalation blockiert. Manueller    │
│   Suspend durch Admins bleibt möglich (mit Warnung).         │
└─────────────────────────────────────────────────────────────┘
```

Per-window card:
- Per-window enabled toggle (left) using same `Toggle` primitive as `SleepConfigPanel`.
- Inline-editable label `<input>` (placeholder: "Beschreibung").
- Weekday chips: 7 buttons Mo–So; active weekdays highlighted in `bg-teal-500/20 text-teal-300`, inactive in `bg-slate-800/40 text-slate-500`. Click toggles.
- Two `<input type="time">` fields with a `→` arrow between them. If `end < start`, a small badge "bis nächsten Tag" appears beside the arrow.
- Delete button (`✕`) opens `useConfirmDialog` — `variant: 'danger'`, `confirmLabel: 'Löschen'`.

Behaviour:
- **Auto-save on blur/change**, no global Save button. Optimistic local update; on API error, toast and reload from server.
- Validation:
  - Weekday list non-empty: red ring on chip row, save blocked.
  - `start_time !== end_time`: enforced both client- and server-side.

### 8.4 Extension to `SleepModePanel.tsx`

Banner directly under the status header, conditional on `status.core_uptime.active`:

```tsx
{status.core_uptime.active && (
  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 mb-3 flex items-start gap-2">
    <Shield className="h-4 w-4 text-emerald-300 mt-0.5" />
    <div className="text-xs text-emerald-200">
      <strong>Kernbetriebszeit aktiv</strong>
      {status.core_uptime.current_window_label && ` — „${status.core_uptime.current_window_label}"`}
      {status.core_uptime.current_window_ends_at &&
        ` — endet um ${formatTime(status.core_uptime.current_window_ends_at)}.`}
      {' '}Auto-Sleep blockiert.
    </div>
  </div>
)}
```

Optional secondary banner if `core_uptime.enabled && !core_uptime.active && next_start` is within the next 12 h:
> "Nächste Kernzeit: heute 18:00"

Style: dimmer `bg-slate-800/40 text-slate-400`.

`formatTime(iso)` is a small local helper that parses an ISO datetime and returns `HH:MM` in browser-local time (`new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })`). May live inline in the panel file — no shared util needed for one helper.

### 8.5 Suspend confirmation extension

`SleepModePanel.handleSuspend`:

```typescript
const inCore = status?.core_uptime?.active;
const ok = await confirm(
  inCore
    ? `⚠ Kernbetriebszeit ist aktiv${status.core_uptime.current_window_ends_at ? ` (bis ${formatTime(status.core_uptime.current_window_ends_at)})` : ''}.\nSuspend macht den Server für andere Nutzer unerreichbar.\nTrotzdem fortfahren?`
    : 'Suspend the system? The server will become unreachable. Wake via WoL or RTC alarm.',
  {
    title: 'True Suspend',
    variant: 'danger',
    confirmLabel: inCore ? 'Trotzdem suspenden' : 'Suspend Now',
  },
);
```

Same logic optionally mirrored in `client/src/components/PowerMenu.tsx` (the global power menu) — the implementation plan should explicitly verify whether `PowerMenu` also issues `enterSuspend()`.

### 8.6 Schedule-override hint in `SleepConfigPanel.tsx`

Inside the existing Schedule card, when both `scheduleEnabled` and `status.core_uptime.enabled` (master toggle) are true, render a small info note at the bottom of the card. We do not gate on whether windows actually exist — if the master toggle is on but no windows exist, the schedule keeps working anyway, and the hint correctly describes future behaviour once windows are added.

> "ℹ Kernbetriebszeit hat Vorrang. Sleep-Schedule-Trigger werden während Kernzeit-Fenstern ignoriert."

Styling: `text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded p-2 mt-2`.

The note is informational only — no automatic disable, no extra confirm.

### 8.7 Sleep history label

In `client/src/api/sleep.ts`, extend:

```typescript
export const TRIGGER_LABELS: Record<SleepTrigger, string> = {
  ...
  core_uptime_wake: 'Kernzeit-Wake',
};
```

`SleepTrigger` union gains `'core_uptime_wake'`.

### 8.8 Page composition

`client/src/pages/SleepMode.tsx`:

```tsx
return (
  <div className="space-y-6">
    <SleepModePanel />          {/* + banner if core_uptime.active */}
    <CoreUptimePanel />          {/* NEW — between status and config */}
    <SleepConfigPanel />         {/* + schedule override hint */}
    <SleepHistoryTable />
  </div>
);
```

### 8.9 i18n

All new user-facing strings under `sleep.coreUptime.*` in:
- `client/src/i18n/locales/de/common.json`
- `client/src/i18n/locales/en/common.json`

Keys (German wording authoritative; English mirrored):
- `sleep.coreUptime.title` — "Kernbetriebszeit"
- `sleep.coreUptime.description` — "Während dieser Zeitfenster bleibt der Server erreichbar; Auto-Sleep ist blockiert."
- `sleep.coreUptime.bannerActive` — "Kernbetriebszeit aktiv"
- `sleep.coreUptime.bannerEndsAt` — "endet um {{time}}"
- `sleep.coreUptime.addWindow` — "Neues Zeitfenster hinzufügen"
- `sleep.coreUptime.crossMidnightBadge` — "bis nächsten Tag"
- `sleep.coreUptime.warningInfo` — informational footer text (see panel sketch)
- `sleep.coreUptime.scheduleOverridden` — "Kernbetriebszeit hat Vorrang. Sleep-Schedule-Trigger werden während Kernzeit-Fenstern ignoriert."
- `sleep.coreUptime.suspendWarning` — "Kernbetriebszeit ist aktiv (bis {{time}}). Suspend macht den Server für andere Nutzer unerreichbar."
- `sleep.coreUptime.weekdays.{0..6}` — short labels Mo, Di, Mi, Do, Fr, Sa, So.
- `sleep.coreUptime.triggerLabel` — "Kernzeit-Wake"

## 9. Tests

Three new pytest files:

### 9.1 `backend/tests/services/test_core_uptime_helpers.py`
Pure unit tests against `core_uptime.py`:
- Inside / outside / boundary (start-inclusive, end-exclusive).
- Cross-midnight: window `weekdays=[4]`, `22:00→06:00` is active Fri 22:00, Sat 02:00; not active Sat 22:00 (that belongs to next Fri).
- Disabled window ignored.
- Multiple overlapping windows: union semantics.
- `next_core_uptime_start`: today-later, tomorrow, next-week, no-enabled-windows → `None`.

### 9.2 `backend/tests/services/test_sleep_core_uptime_integration.py`
Against real `SleepManagerService` with `DevSleepBackend`:
- Auto-idle counter does not advance while in core uptime.
- Schedule-sleep is suppressed.
- Auto-escalation aborts.
- `enter_true_suspend(wake_at=None)` clamps `wake_at` to next core start.
- `enter_true_suspend(wake_at=X)` with `X > next_core_start` → `wake_at` reduced to `next_core_start`.
- Soft-sleep → awake transition fires when entering an active window.

### 9.3 `backend/tests/api/test_core_uptime_routes.py`
- CRUD happy paths with admin token.
- 403 for non-admin.
- 422 for: empty `weekdays`, invalid HH:MM, `start_time == end_time`.
- 404 for delete / update of nonexistent ID.

Frontend tests are placeholders in the current repo, so no new frontend test files are added.

## 10. Edge cases & invariants

| # | Topic | Decision |
|---|---|---|
| 1 | Time zone | Server-local time everywhere; consistent with existing `_schedule_check_loop` |
| 2 | Boundary semantics | Start inclusive, end exclusive |
| 3 | Cross-midnight day attribution | `weekdays` describes the START day; the window may extend into the next day |
| 4 | Whole-day windows | Use `00:00→23:59` or two contiguous windows. No special "all-day" flag |
| 5 | Auto-wake latency | ≤ 60 s (matches `_schedule_check_loop` cadence) |
| 6 | DB load | One query per loop tick (every 30 s / 60 s); no caching layer |
| 7 | Race condition (manual + auto wake) | Both call `_exit_soft_sleep`; the existing state guard makes it idempotent |
| 8 | Resume from RTC-suspend | Existing `resume_from_suspend` path is unchanged. The `core_uptime_wake` trigger is logged only for the soft-sleep edge case |
| 9 | Concurrency on multi-worker prod | The sleep manager already uses `monitoring=True` only on the primary worker; secondary workers stay observers. No new sync needed |

## 11. Out of scope (YAGNI)

- Bulk weekday edits across multiple windows.
- Window-specific history / statistics.
- "Schedule conflicts with core uptime — disable schedule?" prompt. Only an info hint; user decides.
- Pagination of the windows endpoint (lists are small).
- API endpoint for "force-disable core uptime now without persisting" (admin can already toggle the master flag).
- Per-user / per-role override of the warning dialog text.

## 12. Acceptance Criteria

A reviewer can verify the feature works by:
1. Logging in as admin, creating two windows: `Mo–Fr 08:00→22:00` and `Sa–So 10:00→23:30`.
2. Toggling the master switch on; banner appears in the Sleep panel during the corresponding times.
3. Setting `idle_timeout_minutes=1` and `auto_idle_enabled=True` while a window is active — system stays awake; the idle progress bar resets to 0.
4. Manually issuing soft sleep, waiting until a window starts → system wakes within ≤ 60 s; history shows trigger `core_uptime_wake`.
5. Clicking Suspend during an active window → confirmation dialog shows the extra warning line.
6. Calling `POST /api/system/sleep/suspend` programmatically without `wake_at` → `rtcwake` is invoked with `wake_at == next_core_uptime_start`.
7. All new pytest files pass: `python -m pytest backend/tests/services/test_core_uptime_helpers.py backend/tests/services/test_sleep_core_uptime_integration.py backend/tests/api/test_core_uptime_routes.py -v`.

## 13. Files touched

### New
- `backend/app/services/power/core_uptime.py`
- `backend/alembic/versions/<rev>_add_core_uptime.py`
- `backend/tests/services/test_core_uptime_helpers.py`
- `backend/tests/services/test_sleep_core_uptime_integration.py`
- `backend/tests/api/test_core_uptime_routes.py`
- `client/src/api/coreUptime.ts`
- `client/src/components/power/CoreUptimePanel.tsx`

### Modified
- `backend/app/models/sleep.py` (new model + new column on `SleepConfig`)
- `backend/app/models/__init__.py` (export `CoreUptimeWindow`)
- `backend/app/schemas/sleep.py` (new schemas; extend `SleepStatusResponse`, `SleepConfigResponse`, `SleepConfigUpdate`, `SleepTrigger`)
- `backend/app/services/power/sleep.py` (loop changes, `enter_true_suspend` clamp, `_was_in_core_uptime` field, `get_status` extension)
- `backend/app/api/routes/sleep.py` (new endpoints, schemas wired)
- `client/src/api/sleep.ts` (new types, extended interfaces, new trigger label)
- `client/src/pages/SleepMode.tsx` (insert `CoreUptimePanel`)
- `client/src/components/power/SleepModePanel.tsx` (banner, suspend warning)
- `client/src/components/power/SleepConfigPanel.tsx` (schedule-override hint, master-toggle plumbing if reused there — otherwise master toggle lives only in CoreUptimePanel)
- `client/src/components/power/index.ts` (export `CoreUptimePanel`)
- `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json`
