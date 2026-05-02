# Core Operating Hours Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admins to define recurring time windows during which the BaluHost server stays awake (no auto-idle, no scheduled sleep, no escalation), auto-wakes from soft sleep at window start, and clamps any RTC wake-up after a manual suspend to the next window start.

**Architecture:** New table `core_uptime_windows` + master toggle column on `sleep_config`. Pure helper module (`core_uptime.py`) for window matching. Hooks integrated into the existing `SleepManagerService` loops. New CRUD REST endpoints under `/api/system/sleep/core-uptime/...`. New React panel `CoreUptimePanel` placed between status and config in the existing Sleep tab; status banner + warning extension on the existing panels.

**Tech Stack:** SQLAlchemy 2.0, Alembic, FastAPI, Pydantic v2, pytest, React 18, TypeScript, Tailwind, react-i18next.

**Spec:** `docs/superpowers/specs/2026-05-01-core-operating-hours-design.md`

---

## File Plan

### New
| Path | Purpose |
|---|---|
| `backend/app/services/power/core_uptime.py` | Pure window-matching helpers |
| `backend/alembic/versions/<rev>_add_core_uptime.py` | Schema migration |
| `backend/tests/services/test_core_uptime_helpers.py` | Unit tests for helpers |
| `backend/tests/services/test_sleep_core_uptime_integration.py` | Integration tests against `SleepManagerService` |
| `backend/tests/api/test_core_uptime_routes.py` | API CRUD tests |
| `client/src/api/coreUptime.ts` | Typed REST client |
| `client/src/components/power/CoreUptimePanel.tsx` | Main panel (master toggle, window list) |
| `client/src/components/power/CoreUptimeWindowCard.tsx` | Per-window edit card |

### Modified
| Path | Change |
|---|---|
| `backend/app/models/sleep.py` | Add `core_uptime_enabled` column to `SleepConfig`; add `CoreUptimeWindow` model |
| `backend/app/models/__init__.py` | Export `CoreUptimeWindow` |
| `backend/app/schemas/sleep.py` | New schemas; extend `SleepStatusResponse`, `SleepConfigResponse`, `SleepConfigUpdate`, `SleepTrigger` |
| `backend/app/services/power/sleep.py` | Loop hooks, `enter_true_suspend` clamp, `_was_in_core_uptime` state, `get_status` extension |
| `backend/app/api/routes/sleep.py` | New CRUD endpoints |
| `client/src/api/sleep.ts` | Extend types, new trigger label |
| `client/src/pages/SleepMode.tsx` | Insert `<CoreUptimePanel />` |
| `client/src/components/power/SleepModePanel.tsx` | Banner + suspend warning |
| `client/src/components/power/SleepConfigPanel.tsx` | Schedule-override hint |
| `client/src/components/power/index.ts` | Export new panel |
| `client/src/i18n/locales/de/common.json` | Add `sleep.coreUptime.*` strings |
| `client/src/i18n/locales/en/common.json` | Add `sleep.coreUptime.*` strings |

---

## Task 1: Database model + master-toggle column

**Files:**
- Modify: `backend/app/models/sleep.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Add `core_uptime_enabled` column to `SleepConfig`**

In `backend/app/models/sleep.py` inside class `SleepConfig`, add a new mapped column right after `disk_spindown_enabled`:

```python
    # Core Operating Hours (Kernbetriebszeit)
    core_uptime_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 2: Add `CoreUptimeWindow` model**

In the same file, append after `class SleepStateLog`:

```python
class CoreUptimeWindow(Base):
    """A recurring time window during which auto-sleep must NOT trigger."""
    __tablename__ = "core_uptime_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)    # "HH:MM"
    weekdays: Mapped[str] = mapped_column(String(15), nullable=False)   # CSV "0,1,2,3,4" (0=Mon..6=Sun)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CoreUptimeWindow(id={self.id}, {self.start_time}-{self.end_time}, weekdays={self.weekdays})>"
```

- [ ] **Step 3: Register the new model**

In `backend/app/models/__init__.py`, change:

```python
from app.models.sleep import SleepConfig, SleepStateLog
```

to:

```python
from app.models.sleep import SleepConfig, SleepStateLog, CoreUptimeWindow
```

And add `"CoreUptimeWindow"` to the `__all__` list next to the existing sleep entries.

- [ ] **Step 4: Verify model registration**

Run a quick import check:

```bash
cd backend && python -c "from app.models import CoreUptimeWindow, SleepConfig; print(CoreUptimeWindow.__tablename__, SleepConfig.__table__.columns['core_uptime_enabled'].type)"
```

Expected: `core_uptime_windows BOOLEAN`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/sleep.py backend/app/models/__init__.py
git commit -m "feat(sleep): add CoreUptimeWindow model + core_uptime_enabled column"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<rev>_add_core_uptime.py`

- [ ] **Step 1: Generate the migration**

```bash
cd backend && alembic revision --autogenerate -m "add core uptime windows and master toggle"
```

This creates a new file under `backend/alembic/versions/`. The autogenerated content should already contain `op.add_column("sleep_config", ...)` and `op.create_table("core_uptime_windows", ...)`.

- [ ] **Step 2: Verify the generated migration matches the spec**

Open the new file. The `upgrade()` body must contain (in this order, naming may differ slightly — autogenerate is not byte-exact):

```python
def upgrade() -> None:
    op.add_column(
        "sleep_config",
        sa.Column("core_uptime_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        "core_uptime_windows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("start_time", sa.String(length=5), nullable=False),
        sa.Column("end_time", sa.String(length=5), nullable=False),
        sa.Column("weekdays", sa.String(length=15), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_core_uptime_windows_id"), "core_uptime_windows", ["id"], unique=False)
```

If autogenerate misses anything (e.g. `server_default=sa.false()`), edit the file to match.

- [ ] **Step 3: Verify the downgrade**

```python
def downgrade() -> None:
    op.drop_index(op.f("ix_core_uptime_windows_id"), table_name="core_uptime_windows")
    op.drop_table("core_uptime_windows")
    op.drop_column("sleep_config", "core_uptime_enabled")
```

- [ ] **Step 4: Apply the migration to the dev SQLite DB and back**

```bash
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

Expected: all three commands print `Running upgrade ...` / `Running downgrade ...` lines without errors.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(sleep): alembic migration for core uptime windows"
```

---

## Task 3: Pure helper module — TDD

**Files:**
- Create: `backend/app/services/power/core_uptime.py`
- Create: `backend/tests/services/test_core_uptime_helpers.py`

- [ ] **Step 1: Write the failing test file**

`backend/tests/services/test_core_uptime_helpers.py`:

```python
"""Unit tests for pure core-uptime helpers (no DB)."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.power.core_uptime import (
    is_in_core_uptime,
    next_core_uptime_start,
    current_window_end,
)


def _w(start: str, end: str, weekdays: str = "0,1,2,3,4,5,6", enabled: bool = True, label: str | None = None):
    """Build a fake CoreUptimeWindow-shaped object for tests."""
    return SimpleNamespace(
        id=1,
        enabled=enabled,
        label=label,
        start_time=start,
        end_time=end,
        weekdays=weekdays,
    )


# ---- is_in_core_uptime ----

def test_in_window_simple_weekday():
    # Wednesday = weekday 2; window Mo-Fr 08:00-22:00; current = Wed 12:00
    now = datetime(2026, 5, 6, 12, 0)  # Wed
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    active, w = is_in_core_uptime(now, windows)
    assert active is True
    assert w is windows[0]


def test_outside_window_weekday_match():
    now = datetime(2026, 5, 6, 7, 59)  # Wed before start
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    active, w = is_in_core_uptime(now, windows)
    assert active is False
    assert w is None


def test_start_inclusive():
    now = datetime(2026, 5, 6, 8, 0)  # exactly start
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    assert is_in_core_uptime(now, windows)[0] is True


def test_end_exclusive():
    now = datetime(2026, 5, 6, 22, 0)  # exactly end
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    assert is_in_core_uptime(now, windows)[0] is False


def test_wrong_weekday():
    # Saturday = weekday 5; window only weekdays 0-4
    now = datetime(2026, 5, 9, 12, 0)  # Sat
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    assert is_in_core_uptime(now, windows)[0] is False


def test_disabled_window_ignored():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [_w("08:00", "22:00", "0,1,2,3,4", enabled=False)]
    assert is_in_core_uptime(now, windows) == (False, None)


def test_empty_windows_list():
    now = datetime(2026, 5, 6, 12, 0)
    assert is_in_core_uptime(now, []) == (False, None)


# ---- cross-midnight ----

def test_cross_midnight_active_late():
    # Friday window 22:00 -> 06:00 (Sat morning); now Fri 23:00
    now = datetime(2026, 5, 8, 23, 0)  # Fri
    windows = [_w("22:00", "06:00", "4")]  # Friday only
    assert is_in_core_uptime(now, windows)[0] is True


def test_cross_midnight_active_early_next_day():
    # Same window covers Sat 02:00 (since it started Fri 22:00)
    now = datetime(2026, 5, 9, 2, 0)  # Sat
    windows = [_w("22:00", "06:00", "4")]
    assert is_in_core_uptime(now, windows)[0] is True


def test_cross_midnight_not_active_saturday_evening():
    # Sat 23:00 is NOT covered (window starts on Fri only, already closed at Sat 06:00)
    now = datetime(2026, 5, 9, 23, 0)
    windows = [_w("22:00", "06:00", "4")]
    assert is_in_core_uptime(now, windows)[0] is False


def test_cross_midnight_end_exclusive():
    # Fri-window 22:00 -> 06:00; Sat 06:00 is NOT inside (end exclusive)
    now = datetime(2026, 5, 9, 6, 0)
    windows = [_w("22:00", "06:00", "4")]
    assert is_in_core_uptime(now, windows)[0] is False


# ---- multiple windows ----

def test_multiple_windows_union():
    now = datetime(2026, 5, 9, 11, 0)  # Sat 11:00
    windows = [
        _w("08:00", "22:00", "0,1,2,3,4"),  # workdays only
        _w("10:00", "23:30", "5,6"),         # weekend
    ]
    active, w = is_in_core_uptime(now, windows)
    assert active is True
    assert w.weekdays == "5,6"


def test_overlapping_windows_returns_first_match():
    now = datetime(2026, 5, 6, 12, 0)
    windows = [
        _w("00:00", "12:00", "2", label="A"),  # Wed morning
        _w("11:30", "23:30", "2", label="B"),  # overlaps
    ]
    active, w = is_in_core_uptime(now, windows)
    assert active is True
    assert w.label == "B"  # second wins because first ends at 12:00 (exclusive)


# ---- next_core_uptime_start ----

def test_next_start_today_later_today():
    now = datetime(2026, 5, 6, 7, 0)  # Wed before start
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    nxt = next_core_uptime_start(now, windows)
    assert nxt == datetime(2026, 5, 6, 8, 0)


def test_next_start_tomorrow():
    now = datetime(2026, 5, 6, 23, 0)  # Wed after end
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    nxt = next_core_uptime_start(now, windows)
    assert nxt == datetime(2026, 5, 7, 8, 0)


def test_next_start_skips_weekend():
    now = datetime(2026, 5, 8, 23, 0)  # Fri 23:00
    windows = [_w("08:00", "22:00", "0,1,2,3,4")]
    nxt = next_core_uptime_start(now, windows)
    assert nxt == datetime(2026, 5, 11, 8, 0)  # next Mon


def test_next_start_no_enabled_windows():
    assert next_core_uptime_start(datetime(2026, 5, 6, 12, 0), []) is None
    disabled = [_w("08:00", "22:00", "0,1,2,3,4", enabled=False)]
    assert next_core_uptime_start(datetime(2026, 5, 6, 12, 0), disabled) is None


def test_next_start_picks_earliest_across_windows():
    now = datetime(2026, 5, 8, 23, 0)  # Fri evening
    windows = [
        _w("08:00", "22:00", "0,1,2,3,4"),  # next: Mon 08:00
        _w("10:00", "23:30", "5,6"),         # next: Sat 10:00
    ]
    assert next_core_uptime_start(now, windows) == datetime(2026, 5, 9, 10, 0)


# ---- current_window_end ----

def test_current_window_end_same_day():
    now = datetime(2026, 5, 6, 12, 0)
    w = _w("08:00", "22:00", "0,1,2,3,4")
    assert current_window_end(now, w) == datetime(2026, 5, 6, 22, 0)


def test_current_window_end_cross_midnight_late_part():
    now = datetime(2026, 5, 8, 23, 0)  # Fri 23:00 inside window
    w = _w("22:00", "06:00", "4")
    assert current_window_end(now, w) == datetime(2026, 5, 9, 6, 0)


def test_current_window_end_cross_midnight_early_part():
    now = datetime(2026, 5, 9, 2, 0)  # Sat 02:00 inside Fri-started window
    w = _w("22:00", "06:00", "4")
    assert current_window_end(now, w) == datetime(2026, 5, 9, 6, 0)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python -m pytest tests/services/test_core_uptime_helpers.py -v
```

Expected: collection errors / `ModuleNotFoundError: app.services.power.core_uptime`.

- [ ] **Step 3: Implement the module**

Create `backend/app/services/power/core_uptime.py`:

```python
"""
Pure helpers for matching the current time against a set of core-uptime windows.

Conventions:
- Times are server-local (naive datetime), consistent with the existing schedule loop.
- start_time is INCLUSIVE, end_time is EXCLUSIVE.
- weekdays is a CSV of integers 0..6 (0=Monday..6=Sunday) — the days the window STARTS on.
- If end < start, the window crosses midnight (start_today .. 24:00 + 00:00 .. end_next_day).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _parse_weekdays(csv: str) -> set[int]:
    return {int(x) for x in csv.split(",") if x.strip() != ""}


def _crosses_midnight(start: str, end: str) -> bool:
    sh, sm = _parse_hhmm(start)
    eh, em = _parse_hhmm(end)
    return (eh, em) < (sh, sm)


def _window_active_at(now: datetime, w) -> bool:
    """True iff `now` lies inside this enabled window."""
    if not w.enabled:
        return False
    weekdays = _parse_weekdays(w.weekdays)
    sh, sm = _parse_hhmm(w.start_time)
    eh, em = _parse_hhmm(w.end_time)
    today = now.weekday()  # 0..6 Mon..Sun
    yesterday = (today - 1) % 7

    if _crosses_midnight(w.start_time, w.end_time):
        # Late part: started today (today in weekdays) AND now >= start_today
        if today in weekdays:
            start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if now >= start_today:
                return True
        # Early part: started yesterday (yesterday in weekdays) AND now < end_today
        if yesterday in weekdays:
            end_today = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            if now < end_today:
                return True
        return False
    else:
        if today not in weekdays:
            return False
        start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end_today = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        return start_today <= now < end_today


def is_in_core_uptime(now: datetime, windows: Sequence) -> tuple[bool, Optional[object]]:
    """Return (active, matching_window). First-match wins on overlap."""
    for w in windows:
        if _window_active_at(now, w):
            return True, w
    return False, None


def next_core_uptime_start(now: datetime, windows: Sequence) -> Optional[datetime]:
    """Return the earliest start datetime within the next 7 days, or None."""
    enabled = [w for w in windows if w.enabled]
    if not enabled:
        return None

    candidates: list[datetime] = []
    for w in enabled:
        sh, sm = _parse_hhmm(w.start_time)
        weekdays = _parse_weekdays(w.weekdays)
        for day_offset in range(0, 8):
            candidate_date = now + timedelta(days=day_offset)
            if candidate_date.weekday() not in weekdays:
                continue
            candidate = candidate_date.replace(hour=sh, minute=sm, second=0, microsecond=0)
            if candidate > now:
                candidates.append(candidate)
                break  # earliest for this window
    return min(candidates) if candidates else None


def current_window_end(now: datetime, w) -> datetime:
    """Return the datetime when the currently-active window ends.

    Caller must ensure `now` is actually inside `w`.
    """
    eh, em = _parse_hhmm(w.end_time)
    if _crosses_midnight(w.start_time, w.end_time):
        sh, sm = _parse_hhmm(w.start_time)
        start_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if now >= start_today:
            # We're in the late part — end is tomorrow at end_time
            return (now + timedelta(days=1)).replace(hour=eh, minute=em, second=0, microsecond=0)
        # We're in the early part — end is today at end_time
        return now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return now.replace(hour=eh, minute=em, second=0, microsecond=0)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && python -m pytest tests/services/test_core_uptime_helpers.py -v
```

Expected: all tests pass (around 20+ tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/core_uptime.py backend/tests/services/test_core_uptime_helpers.py
git commit -m "feat(sleep): pure helpers for core-uptime window matching"
```

---

## Task 4: Pydantic schemas

**Files:**
- Modify: `backend/app/schemas/sleep.py`

- [ ] **Step 1: Add `CORE_UPTIME_WAKE` to `SleepTrigger` enum**

In `backend/app/schemas/sleep.py`, locate `class SleepTrigger(str, Enum)` and add:

```python
    CORE_UPTIME_WAKE = "core_uptime_wake"
```

- [ ] **Step 2: Add new schemas at the bottom of the file**

```python
# ---------------------------------------------------------------------------
# Core Operating Hours (Kernbetriebszeit)
# ---------------------------------------------------------------------------

from pydantic import model_validator  # add to existing imports if not already


class CoreUptimeWindowBase(BaseModel):
    enabled: bool = True
    label: Optional[str] = Field(default=None, max_length=50)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM, server-local")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="HH:MM, exclusive")
    weekdays: list[int] = Field(..., description="Start days, 0=Mon..6=Sun, deduplicated, sorted")

    @field_validator("weekdays")
    @classmethod
    def _validate_weekdays(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("at least one weekday required")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekdays must be in range 0..6")
        return sorted(set(v))

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_hhmm(cls, v: str) -> str:
        h, m = map(int, v.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("invalid HH:MM time")
        return v

    @model_validator(mode="after")
    def _validate_distinct(self) -> "CoreUptimeWindowBase":
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must differ")
        return self


class CoreUptimeWindowCreate(CoreUptimeWindowBase):
    pass


class CoreUptimeWindowUpdate(BaseModel):
    """Partial update — every field optional."""
    enabled: Optional[bool] = None
    label: Optional[str] = Field(default=None, max_length=50)
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekdays: Optional[list[int]] = None

    @field_validator("weekdays")
    @classmethod
    def _validate_weekdays(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return v
        if not v:
            raise ValueError("at least one weekday required")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekdays must be in range 0..6")
        return sorted(set(v))


class CoreUptimeWindowResponse(CoreUptimeWindowBase):
    id: int
    created_at: datetime
    updated_at: datetime


class CoreUptimeStatus(BaseModel):
    enabled: bool = Field(default=False, description="Master toggle state")
    active: bool = Field(default=False, description="Whether some enabled window is currently active")
    current_window_label: Optional[str] = Field(default=None)
    current_window_ends_at: Optional[datetime] = Field(default=None)
    next_start: Optional[datetime] = Field(default=None)
```

- [ ] **Step 3: Extend existing schemas**

In `class SleepStatusResponse`, add at the end of the field list:

```python
    core_uptime: CoreUptimeStatus = Field(default_factory=CoreUptimeStatus)
```

In `class SleepConfigResponse`, add after `disk_spindown_enabled`:

```python
    core_uptime_enabled: bool = Field(default=False, description="Master toggle for core operating hours")
```

In `class SleepConfigUpdate`, add at the end:

```python
    core_uptime_enabled: Optional[bool] = None
```

- [ ] **Step 4: Verify the schemas import cleanly**

```bash
cd backend && python -c "from app.schemas.sleep import CoreUptimeWindowCreate, CoreUptimeStatus, SleepStatusResponse, SleepTrigger; print(SleepTrigger.CORE_UPTIME_WAKE.value)"
```

Expected: `core_uptime_wake`

- [ ] **Step 5: Quick validator smoke**

```bash
cd backend && python -c "
from app.schemas.sleep import CoreUptimeWindowCreate
import pydantic
try:
    CoreUptimeWindowCreate(start_time='08:00', end_time='08:00', weekdays=[0])
    print('FAIL: should have rejected equal times')
except pydantic.ValidationError as e:
    print('OK equal-times rejected')
try:
    CoreUptimeWindowCreate(start_time='08:00', end_time='22:00', weekdays=[])
    print('FAIL: should have rejected empty weekdays')
except pydantic.ValidationError as e:
    print('OK empty-weekdays rejected')
w = CoreUptimeWindowCreate(start_time='08:00', end_time='22:00', weekdays=[3,1,1,2])
print('weekdays sorted+dedup:', w.weekdays)
"
```

Expected:
```
OK equal-times rejected
OK empty-weekdays rejected
weekdays sorted+dedup: [1, 2, 3]
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/sleep.py
git commit -m "feat(sleep): pydantic schemas for core uptime windows"
```

---

## Task 5: Service hook into `_idle_detection_loop`

**Files:**
- Modify: `backend/app/services/power/sleep.py`
- Create: `backend/tests/services/test_sleep_core_uptime_integration.py`

- [ ] **Step 1: Write the failing test (idle counter does not advance during core uptime)**

`backend/tests/services/test_sleep_core_uptime_integration.py`:

```python
"""Integration tests: SleepManagerService respects core uptime windows."""
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from app.models.sleep import CoreUptimeWindow as CW, SleepConfig
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.schemas.sleep import SleepState, SleepTrigger


def _build_service():
    """Build a fresh SleepManagerService with a DevSleepBackend."""
    SleepManagerService._instance = None  # reset singleton
    return SleepManagerService(DevSleepBackend())


def _config(core_enabled: bool = True, auto_idle_enabled: bool = True, idle_timeout_minutes: int = 1):
    cfg = SleepConfig(
        id=1,
        auto_idle_enabled=auto_idle_enabled,
        idle_timeout_minutes=idle_timeout_minutes,
        idle_cpu_threshold=99.0,
        idle_disk_io_threshold=99.0,
        idle_http_threshold=999.0,
        auto_escalation_enabled=False,
        escalation_after_minutes=60,
        schedule_enabled=False,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=core_enabled,
    )
    return cfg


def _window_workdays_8_22() -> CW:
    return CW(
        id=1, enabled=True, label="Werktage",
        start_time="08:00", end_time="22:00", weekdays="0,1,2,3,4",
    )


def test_load_core_uptime_returns_empty_when_master_off():
    svc = _build_service()
    cfg = _config(core_enabled=False)
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch("app.services.power.sleep.SessionLocal") as mock_sl:
        # Should not even hit the DB for windows when master is off
        master, windows = svc._load_core_uptime()
    assert master is False
    assert windows == []


def test_load_core_uptime_returns_enabled_windows():
    svc = _build_service()
    cfg = _config(core_enabled=True)
    fake_session = MagicMock()
    fake_query = MagicMock()
    fake_query.scalars.return_value.all.return_value = [_window_workdays_8_22()]
    fake_session.execute.return_value = fake_query
    fake_session.__enter__ = lambda s: s
    fake_session.__exit__ = lambda *a: None
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch("app.services.power.sleep.SessionLocal", return_value=fake_session):
        master, windows = svc._load_core_uptime()
    assert master is True
    assert len(windows) == 1
    assert windows[0].label == "Werktage"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py::test_load_core_uptime_returns_empty_when_master_off -v
```

Expected: `AttributeError: 'SleepManagerService' object has no attribute '_load_core_uptime'`.

- [ ] **Step 3: Implement `_load_core_uptime` and integrate into `_idle_detection_loop`**

In `backend/app/services/power/sleep.py`:

a) Add a new import near the top of the file (after the `from app.models.sleep import ...` line):

```python
from app.models.sleep import SleepConfig as SleepConfigModel, SleepStateLog, CoreUptimeWindow as CoreUptimeWindowModel
from app.services.power import core_uptime as core_uptime_helpers
```

b) Add a new instance attribute in `__init__`:

```python
        self._was_in_core_uptime: bool = False
```

c) Add the loader method right after `_load_config`:

```python
    def _load_core_uptime(self) -> tuple[bool, list]:
        """Return (master_enabled, list_of_enabled_windows). Empty list if master off."""
        config = self._load_config()
        if not config or not config.core_uptime_enabled:
            return False, []
        try:
            db = SessionLocal()
            try:
                rows = db.execute(
                    select(CoreUptimeWindowModel).where(CoreUptimeWindowModel.enabled.is_(True))
                ).scalars().all()
                # Detach from session so callers can read attributes after close
                for r in rows:
                    db.expunge(r)
                return True, list(rows)
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to load core uptime windows: %s", e)
            return False, []
```

d) In `_idle_detection_loop`, after the existing `if not config or not config.auto_idle_enabled: ... continue` block AND before computing metrics, insert:

```python
                master, windows = self._load_core_uptime()
                if master:
                    in_core, _ = core_uptime_helpers.is_in_core_uptime(datetime.now(), windows)
                    if in_core:
                        self._consecutive_idle_checks = 0
                        self._idle_seconds = 0.0
                        continue
```

- [ ] **Step 4: Run the new tests**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Add an idle-loop test**

Append to `test_sleep_core_uptime_integration.py`:

```python
import asyncio


@pytest.mark.asyncio
async def test_idle_detection_skips_when_in_core_uptime():
    """During core uptime, idle counter must NOT advance."""
    svc = _build_service()
    cfg = _config(core_enabled=True, auto_idle_enabled=True, idle_timeout_minutes=1)

    # Force "currently in core uptime"
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())):
        svc._is_running = True
        svc._consecutive_idle_checks = 5
        svc._idle_seconds = 150.0

        # Run one iteration manually (avoid the 30s asyncio.sleep)
        async def fake_sleep(*_a, **_k):
            svc._is_running = False  # stop after first iter
        with patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
            await svc._idle_detection_loop()

        assert svc._consecutive_idle_checks == 0
        assert svc._idle_seconds == 0.0
```

- [ ] **Step 6: Run that test**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py::test_idle_detection_skips_when_in_core_uptime -v
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/services/test_sleep_core_uptime_integration.py
git commit -m "feat(sleep): block auto-idle during core uptime"
```

---

## Task 6: Schedule loop — suppress sleep + auto-wake edge

**Files:**
- Modify: `backend/app/services/power/sleep.py`
- Modify: `backend/tests/services/test_sleep_core_uptime_integration.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_sleep_core_uptime_integration.py`:

```python
@pytest.mark.asyncio
async def test_schedule_loop_skips_sleep_trigger_during_core_uptime():
    """Scheduled sleep_time match should NOT trigger sleep when in core uptime."""
    svc = _build_service()
    cfg = SleepConfig(
        id=1,
        auto_idle_enabled=False, idle_timeout_minutes=15, idle_cpu_threshold=5,
        idle_disk_io_threshold=0.5, idle_http_threshold=5,
        auto_escalation_enabled=False, escalation_after_minutes=60,
        schedule_enabled=True, schedule_sleep_time="12:00", schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None, wol_broadcast_address=None,
        pause_monitoring=False, pause_disk_io=False, reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=True,
    )

    enter_called = []

    async def fake_enter_soft_sleep(reason, trigger=None):
        enter_called.append((reason, trigger))
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())), \
         patch("app.services.power.sleep.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 6, 12, 0)  # Wed 12:00 — schedule match AND in core uptime
        svc.enter_soft_sleep = fake_enter_soft_sleep
        svc._is_running = True
        svc._current_state = SleepState.AWAKE

        async def stop_after_one(*_a, **_k):
            svc._is_running = False
        with patch("app.services.power.sleep.asyncio.sleep", side_effect=stop_after_one):
            await svc._schedule_check_loop()

    assert enter_called == []  # core uptime suppressed schedule trigger


@pytest.mark.asyncio
async def test_schedule_loop_auto_wake_on_core_uptime_start():
    """When transitioning into core uptime while in soft sleep, auto-wake fires."""
    svc = _build_service()
    cfg = _config(core_enabled=True)

    exit_called = []

    async def fake_exit_soft_sleep(reason):
        exit_called.append(reason)
        return True

    # Sequence: first iteration NOT in core uptime, second iteration IN core uptime
    in_core_sequence = iter([(False, None), (True, _window_workdays_8_22())])

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               side_effect=lambda *a, **k: next(in_core_sequence)):
        svc.exit_soft_sleep = fake_exit_soft_sleep
        svc._is_running = True
        svc._current_state = SleepState.SOFT_SLEEP
        svc._was_in_core_uptime = False

        ticks = [0]

        async def two_ticks(*_a, **_k):
            ticks[0] += 1
            if ticks[0] >= 2:
                svc._is_running = False

        with patch("app.services.power.sleep.asyncio.sleep", side_effect=two_ticks):
            await svc._schedule_check_loop()

    assert exit_called == ["core_uptime_started"]
    assert svc._was_in_core_uptime is True
```

- [ ] **Step 2: Run them — they should fail**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py::test_schedule_loop_skips_sleep_trigger_during_core_uptime tests/services/test_sleep_core_uptime_integration.py::test_schedule_loop_auto_wake_on_core_uptime_start -v
```

Expected: both fail (existing schedule loop has no core-uptime guard; auto-wake not implemented).

- [ ] **Step 3: Modify `_schedule_check_loop`**

Replace the body of `_schedule_check_loop` in `backend/app/services/power/sleep.py` with:

```python
    async def _schedule_check_loop(self) -> None:
        """Check sleep schedule and core-uptime auto-wake every 60 seconds."""
        while self._is_running:
            try:
                await asyncio.sleep(60)
                if not self._is_running:
                    break

                config = self._load_config()
                master, windows = self._load_core_uptime()
                in_core, _matched = (
                    core_uptime_helpers.is_in_core_uptime(datetime.now(), windows)
                    if master else (False, None)
                )

                # Auto-wake edge: AWAY -> IN, while in soft sleep
                if master and in_core and not self._was_in_core_uptime \
                        and self._current_state == SleepState.SOFT_SLEEP:
                    logger.info("Core uptime started while in soft sleep — auto-waking")
                    await self.exit_soft_sleep("core_uptime_started")
                # Track edge state regardless
                if master:
                    self._was_in_core_uptime = in_core
                else:
                    self._was_in_core_uptime = False

                if not config or not config.schedule_enabled:
                    continue

                now = datetime.now()
                current_time = now.strftime("%H:%M")

                if self._current_state == SleepState.AWAKE:
                    if self._time_matches(current_time, config.schedule_sleep_time):
                        if in_core:
                            logger.info(
                                "Schedule sleep trigger suppressed by active core uptime window",
                            )
                            continue
                        mode = config.schedule_mode
                        if mode == "suspend":
                            wake_dt = self._next_occurrence(config.schedule_wake_time)
                            await self.enter_true_suspend(
                                "scheduled_suspend",
                                SleepTrigger.SCHEDULE,
                                wake_at=wake_dt,
                            )
                        else:
                            await self.enter_soft_sleep("scheduled_sleep", SleepTrigger.SCHEDULE)
                elif self._current_state == SleepState.SOFT_SLEEP:
                    if self._time_matches(current_time, config.schedule_wake_time):
                        await self.exit_soft_sleep("scheduled_wake")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                self._last_error_at = datetime.now(timezone.utc)
                logger.warning("Error in schedule check loop: %s", e)
```

- [ ] **Step 4: Run the new tests**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -v
```

Expected: all integration tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/services/test_sleep_core_uptime_integration.py
git commit -m "feat(sleep): suppress schedule sleep + auto-wake on core uptime start"
```

---

## Task 7: Escalation guard + suspend `wake_at` clamp

**Files:**
- Modify: `backend/app/services/power/sleep.py`
- Modify: `backend/tests/services/test_sleep_core_uptime_integration.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_sleep_core_uptime_integration.py`:

```python
@pytest.mark.asyncio
async def test_escalation_aborts_during_core_uptime():
    """_escalation_monitor must return without escalating if in core uptime when timer fires."""
    svc = _build_service()
    cfg = SleepConfig(
        id=1,
        auto_idle_enabled=False, idle_timeout_minutes=15, idle_cpu_threshold=5,
        idle_disk_io_threshold=0.5, idle_http_threshold=5,
        auto_escalation_enabled=True, escalation_after_minutes=1,
        schedule_enabled=False, schedule_sleep_time="23:00", schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None, wol_broadcast_address=None,
        pause_monitoring=False, pause_disk_io=False, reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=True,
    )

    suspend_called = []

    async def fake_suspend(reason, trigger=None, wake_at=None):
        suspend_called.append((reason, trigger))
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, _window_workdays_8_22())):
        svc.enter_true_suspend = fake_suspend
        svc._is_running = True
        svc._current_state = SleepState.SOFT_SLEEP

        async def fast_sleep(*_a, **_k):
            return None
        with patch("app.services.power.sleep.asyncio.sleep", side_effect=fast_sleep):
            await svc._escalation_monitor()

    assert suspend_called == []


@pytest.mark.asyncio
async def test_enter_true_suspend_clamps_wake_at_to_next_core_start():
    """If wake_at is after next core uptime start, it is clamped to that start."""
    svc = _build_service()
    cfg = _config(core_enabled=True)
    next_start = datetime(2026, 5, 7, 8, 0)
    user_wake = datetime(2026, 5, 7, 23, 0)  # later than next_start

    captured_wake_at = []

    async def fake_suspend_system(wake_at=None):
        captured_wake_at.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.next_core_uptime_start",
               return_value=next_start), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.power.sleep.emit_system_suspend", new=lambda **k: None):
        svc._current_state = SleepState.SOFT_SLEEP  # skip implicit enter_soft_sleep
        await svc.enter_true_suspend("manual", SleepTrigger.MANUAL, wake_at=user_wake)

    assert captured_wake_at == [next_start]


@pytest.mark.asyncio
async def test_enter_true_suspend_uses_next_core_start_when_no_wake_at_given():
    svc = _build_service()
    cfg = _config(core_enabled=True)
    next_start = datetime(2026, 5, 7, 8, 0)

    captured_wake_at = []

    async def fake_suspend_system(wake_at=None):
        captured_wake_at.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [_window_workdays_8_22()])), \
         patch("app.services.power.sleep.core_uptime_helpers.next_core_uptime_start",
               return_value=next_start), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.power.sleep.emit_system_suspend", new=lambda **k: None):
        svc._current_state = SleepState.SOFT_SLEEP
        await svc.enter_true_suspend("manual", SleepTrigger.MANUAL, wake_at=None)

    assert captured_wake_at == [next_start]
```

(Note: the `emit_system_suspend` patch points to a name that may not exist by exact path — adjust if needed: `patch("app.services.notifications.events.emit_system_suspend")`.)

- [ ] **Step 2: Run them**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -v
```

Expected: the three new tests fail.

- [ ] **Step 3: Patch `_escalation_monitor`**

Replace the body of `_escalation_monitor` in `backend/app/services/power/sleep.py` with:

```python
    async def _escalation_monitor(self) -> None:
        """Monitor soft sleep duration and escalate to suspend if configured."""
        try:
            config = self._load_config()
            if not config or not config.auto_escalation_enabled:
                return

            wait_seconds = config.escalation_after_minutes * 60
            await asyncio.sleep(wait_seconds)

            if self._current_state != SleepState.SOFT_SLEEP or not self._is_running:
                return

            # Skip escalation if currently in a core-uptime window
            master, windows = self._load_core_uptime()
            if master:
                in_core, _ = core_uptime_helpers.is_in_core_uptime(datetime.now(), windows)
                if in_core:
                    logger.info("Auto-escalation skipped: currently in core uptime window")
                    return

            logger.info("Auto-escalation: soft sleep -> true suspend after %d minutes",
                        config.escalation_after_minutes)
            await self.enter_true_suspend(
                "auto_escalation",
                SleepTrigger.AUTO_ESCALATION,
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Error in escalation monitor: %s", e)
```

- [ ] **Step 4: Patch `enter_true_suspend` to clamp `wake_at`**

In `enter_true_suspend`, locate the line `prev_state = self._current_state` near the top of the method body. Insert immediately after it:

```python
        # Clamp wake_at to next core-uptime start, if any
        master, windows = self._load_core_uptime()
        if master:
            next_core = core_uptime_helpers.next_core_uptime_start(datetime.now(), windows)
            if next_core is not None and (wake_at is None or next_core < wake_at):
                logger.info(
                    "wake_at clamped to next core uptime start: %s (was %s)",
                    next_core, wake_at,
                )
                wake_at = next_core
```

- [ ] **Step 5: Run all integration tests**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -v
```

Expected: all pass. If `emit_system_suspend` patch path was wrong, fix to the correct dotted path used by `enter_true_suspend` (look at its imports near the call site).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/services/test_sleep_core_uptime_integration.py
git commit -m "feat(sleep): clamp suspend wake_at + skip auto-escalation in core uptime"
```

---

## Task 8: Status response includes `CoreUptimeStatus`

**Files:**
- Modify: `backend/app/services/power/sleep.py`
- Modify: `backend/tests/services/test_sleep_core_uptime_integration.py`

- [ ] **Step 1: Write the failing test**

Append to `test_sleep_core_uptime_integration.py`:

```python
def test_get_status_returns_core_uptime_block_when_active():
    svc = _build_service()
    cfg = _config(core_enabled=True)
    win = _window_workdays_8_22()

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(True, [win])), \
         patch("app.services.power.sleep.core_uptime_helpers.is_in_core_uptime",
               return_value=(True, win)), \
         patch("app.services.power.sleep.core_uptime_helpers.current_window_end",
               return_value=datetime(2026, 5, 6, 22, 0)), \
         patch("app.services.power.sleep.core_uptime_helpers.next_core_uptime_start",
               return_value=datetime(2026, 5, 7, 8, 0)):
        status = svc.get_status()

    assert status.core_uptime.enabled is True
    assert status.core_uptime.active is True
    assert status.core_uptime.current_window_label == "Werktage"
    assert status.core_uptime.current_window_ends_at == datetime(2026, 5, 6, 22, 0)
    assert status.core_uptime.next_start == datetime(2026, 5, 7, 8, 0)


def test_get_status_returns_empty_core_uptime_when_master_off():
    svc = _build_service()
    cfg = _config(core_enabled=False)

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])):
        status = svc.get_status()

    assert status.core_uptime.enabled is False
    assert status.core_uptime.active is False
    assert status.core_uptime.next_start is None
```

- [ ] **Step 2: Run it — should fail**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py::test_get_status_returns_core_uptime_block_when_active -v
```

Expected: `assert ... .enabled is True` fails because `get_status` doesn't populate `core_uptime`.

- [ ] **Step 3: Modify `get_status`**

In `backend/app/services/power/sleep.py`, replace the entire `get_status` method body with:

```python
    def get_status(self) -> SleepStatusResponse:
        """Get current sleep mode status."""
        config = self._load_config()
        metrics = self._get_activity_metrics()

        idle_threshold = 0.0
        if config:
            idle_threshold = config.idle_timeout_minutes * 60

        # Core uptime status
        from app.schemas.sleep import CoreUptimeStatus
        master, windows = self._load_core_uptime()
        core_status = CoreUptimeStatus(enabled=master)
        if master:
            now = datetime.now()
            in_core, matched = core_uptime_helpers.is_in_core_uptime(now, windows)
            core_status.active = in_core
            if in_core and matched is not None:
                core_status.current_window_label = matched.label
                core_status.current_window_ends_at = core_uptime_helpers.current_window_end(now, matched)
            core_status.next_start = core_uptime_helpers.next_core_uptime_start(now, windows)

        return SleepStatusResponse(
            current_state=self._current_state,
            state_since=self._state_since,
            idle_seconds=self._idle_seconds,
            idle_threshold_seconds=idle_threshold,
            activity_metrics=metrics,
            paused_services=self._paused_services,
            spun_down_disks=self._spun_down_disks,
            auto_idle_enabled=config.auto_idle_enabled if config else False,
            schedule_enabled=config.schedule_enabled if config else False,
            escalation_enabled=config.auto_escalation_enabled if config else False,
            core_uptime=core_status,
        )
```

- [ ] **Step 4: Run the tests**

```bash
cd backend && python -m pytest tests/services/test_sleep_core_uptime_integration.py -v
```

Expected: pass.

- [ ] **Step 5: Extend `get_config` to surface `core_uptime_enabled`**

In `backend/app/services/power/sleep.py`, in `get_config`, add `core_uptime_enabled=config.core_uptime_enabled` to the `SleepConfigResponse(...)` constructor at the end of the keyword arguments.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/services/test_sleep_core_uptime_integration.py
git commit -m "feat(sleep): expose core uptime block in status + config responses"
```

---

## Task 9: REST endpoints for window CRUD

**Files:**
- Modify: `backend/app/api/routes/sleep.py`
- Create: `backend/tests/api/test_core_uptime_routes.py`

- [ ] **Step 1: Write the failing test file**

`backend/tests/api/test_core_uptime_routes.py`:

```python
"""Tests for /api/system/sleep/core-uptime/* endpoints."""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_auth_headers
from app.core.config import settings


@pytest.fixture
def admin_headers(client: TestClient, admin_user) -> dict[str, str]:
    return get_auth_headers(client, settings.admin_username, settings.admin_password)


@pytest.fixture
def user_headers(client: TestClient, regular_user) -> dict[str, str]:
    return get_auth_headers(client, "testuser", "Testpass123!")


BASE = f"{settings.api_prefix}/system/sleep/core-uptime/windows"


def test_list_empty(client, admin_headers):
    r = client.get(BASE, headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_window_happy_path(client, admin_headers):
    payload = {
        "label": "Werktage",
        "start_time": "08:00",
        "end_time": "22:00",
        "weekdays": [0, 1, 2, 3, 4],
    }
    r = client.post(BASE, headers=admin_headers, json=payload)
    assert r.status_code in (200, 201)
    body = r.json()
    assert body["label"] == "Werktage"
    assert body["weekdays"] == [0, 1, 2, 3, 4]
    assert body["enabled"] is True
    assert "id" in body and body["id"] > 0


def test_create_rejects_empty_weekdays(client, admin_headers):
    r = client.post(BASE, headers=admin_headers, json={
        "start_time": "08:00", "end_time": "22:00", "weekdays": [],
    })
    assert r.status_code == 422


def test_create_rejects_equal_times(client, admin_headers):
    r = client.post(BASE, headers=admin_headers, json={
        "start_time": "08:00", "end_time": "08:00", "weekdays": [0],
    })
    assert r.status_code == 422


def test_create_rejects_invalid_hhmm(client, admin_headers):
    r = client.post(BASE, headers=admin_headers, json={
        "start_time": "25:00", "end_time": "22:00", "weekdays": [0],
    })
    assert r.status_code == 422


def test_create_forbidden_for_regular_user(client, user_headers):
    r = client.post(BASE, headers=user_headers, json={
        "start_time": "08:00", "end_time": "22:00", "weekdays": [0],
    })
    assert r.status_code == 403


def test_update_partial(client, admin_headers):
    created = client.post(BASE, headers=admin_headers, json={
        "label": "Werktage", "start_time": "08:00", "end_time": "22:00", "weekdays": [0, 1, 2, 3, 4],
    }).json()
    wid = created["id"]
    r = client.put(f"{BASE}/{wid}", headers=admin_headers, json={"label": "Office", "enabled": False})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Office"
    assert body["enabled"] is False
    assert body["weekdays"] == [0, 1, 2, 3, 4]  # unchanged


def test_update_404(client, admin_headers):
    r = client.put(f"{BASE}/9999", headers=admin_headers, json={"label": "x"})
    assert r.status_code == 404


def test_delete_happy(client, admin_headers):
    created = client.post(BASE, headers=admin_headers, json={
        "start_time": "08:00", "end_time": "22:00", "weekdays": [0],
    }).json()
    r = client.delete(f"{BASE}/{created['id']}", headers=admin_headers)
    assert r.status_code == 204
    listing = client.get(BASE, headers=admin_headers).json()
    assert listing == []


def test_delete_404(client, admin_headers):
    r = client.delete(f"{BASE}/9999", headers=admin_headers)
    assert r.status_code == 404


def test_master_toggle_via_config_endpoint(client, admin_headers):
    r = client.put(
        f"{settings.api_prefix}/system/sleep/config",
        headers=admin_headers,
        json={"core_uptime_enabled": True},
    )
    assert r.status_code == 200
    assert r.json()["core_uptime_enabled"] is True
```

- [ ] **Step 2: Run the test file — expect collection errors / 404s**

```bash
cd backend && python -m pytest tests/api/test_core_uptime_routes.py -v
```

Expected: 404s on every endpoint (routes don't exist yet).

- [ ] **Step 3: Add the endpoints**

In `backend/app/api/routes/sleep.py`:

a) Add to the imports near the top:

```python
from app.models.sleep import CoreUptimeWindow as CoreUptimeWindowModel
from app.schemas.sleep import (
    ...,  # keep existing
    CoreUptimeWindowCreate,
    CoreUptimeWindowUpdate,
    CoreUptimeWindowResponse,
)
```

b) Add helper functions and routes at the bottom of the file (before any closing `__all__` if present — there is none today, so just append):

```python
def _csv_to_list(csv: str) -> list[int]:
    return sorted({int(x) for x in csv.split(",") if x.strip()})


def _list_to_csv(items: list[int]) -> str:
    return ",".join(str(x) for x in sorted(set(items)))


def _to_response(row: CoreUptimeWindowModel) -> CoreUptimeWindowResponse:
    return CoreUptimeWindowResponse(
        id=row.id,
        enabled=row.enabled,
        label=row.label,
        start_time=row.start_time,
        end_time=row.end_time,
        weekdays=_csv_to_list(row.weekdays),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/core-uptime/windows",
    response_model=list[CoreUptimeWindowResponse],
)
@user_limiter.limit(get_limit("admin_operations"))
async def list_core_uptime_windows(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[CoreUptimeWindowResponse]:
    rows = db.query(CoreUptimeWindowModel).order_by(CoreUptimeWindowModel.id.asc()).all()
    return [_to_response(r) for r in rows]


@router.post(
    "/core-uptime/windows",
    response_model=CoreUptimeWindowResponse,
    status_code=201,
)
@user_limiter.limit(get_limit("admin_operations"))
async def create_core_uptime_window(
    request: Request, response: Response,
    body: CoreUptimeWindowCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> CoreUptimeWindowResponse:
    row = CoreUptimeWindowModel(
        enabled=body.enabled,
        label=body.label,
        start_time=body.start_time,
        end_time=body.end_time,
        weekdays=_list_to_csv(body.weekdays),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    audit_logger = get_audit_logger_db()
    audit_logger.log_security_event(
        action="core_uptime_window_create",
        user=current_user.username,
        resource=str(row.id),
        details={"start": row.start_time, "end": row.end_time, "weekdays": row.weekdays},
        success=True,
        db=db,
    )
    return _to_response(row)


@router.put(
    "/core-uptime/windows/{window_id}",
    response_model=CoreUptimeWindowResponse,
)
@user_limiter.limit(get_limit("admin_operations"))
async def update_core_uptime_window(
    request: Request, response: Response,
    window_id: int,
    body: CoreUptimeWindowUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> CoreUptimeWindowResponse:
    row = db.get(CoreUptimeWindowModel, window_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Window not found")

    update_data = body.model_dump(exclude_unset=True)
    if "weekdays" in update_data and update_data["weekdays"] is not None:
        update_data["weekdays"] = _list_to_csv(update_data["weekdays"])
    for field, value in update_data.items():
        setattr(row, field, value)

    # Validate end != start after partial update
    if row.start_time == row.end_time:
        raise HTTPException(status_code=422, detail="start_time and end_time must differ")

    db.commit()
    db.refresh(row)

    get_audit_logger_db().log_security_event(
        action="core_uptime_window_update",
        user=current_user.username,
        resource=str(row.id),
        details=update_data,
        success=True,
        db=db,
    )
    return _to_response(row)


@router.delete(
    "/core-uptime/windows/{window_id}",
    status_code=204,
)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_core_uptime_window(
    request: Request, response: Response,
    window_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> Response:
    row = db.get(CoreUptimeWindowModel, window_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Window not found")

    db.delete(row)
    db.commit()

    get_audit_logger_db().log_security_event(
        action="core_uptime_window_delete",
        user=current_user.username,
        resource=str(window_id),
        details={},
        success=True,
        db=db,
    )
    return Response(status_code=204)
```

- [ ] **Step 4: Verify `update_config` handles the new field**

The existing `update_config` in `SleepManagerService` uses `update.model_dump(exclude_unset=True)` and `setattr`, so `core_uptime_enabled` flows through automatically once the schema has it (Task 4). No change needed here.

- [ ] **Step 5: Run the API tests**

```bash
cd backend && python -m pytest tests/api/test_core_uptime_routes.py -v
```

Expected: all pass. If `test_create_window_happy_path` expects `200` and the route returns `201`, the assertion already accepts both.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/sleep.py backend/tests/api/test_core_uptime_routes.py
git commit -m "feat(sleep): REST endpoints for core uptime windows"
```

---

## Task 10: Frontend API client + extended sleep types

**Files:**
- Create: `client/src/api/coreUptime.ts`
- Modify: `client/src/api/sleep.ts`

- [ ] **Step 1: Create `client/src/api/coreUptime.ts`**

```typescript
/**
 * API client for Core Operating Hours (Kernbetriebszeit).
 *
 * Time windows during which the server must remain awake.
 */
import { apiClient } from '../lib/api';

export interface CoreUptimeWindow {
  id: number;
  enabled: boolean;
  label: string | null;
  start_time: string;   // "HH:MM"
  end_time: string;     // "HH:MM"
  weekdays: number[];   // 0=Mon..6=Sun, sorted, deduped
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

const BASE = '/api/system/sleep/core-uptime/windows';

export async function listCoreUptimeWindows(): Promise<CoreUptimeWindow[]> {
  const r = await apiClient.get<CoreUptimeWindow[]>(BASE);
  return r.data;
}

export async function createCoreUptimeWindow(
  data: CoreUptimeWindowCreate,
): Promise<CoreUptimeWindow> {
  const r = await apiClient.post<CoreUptimeWindow>(BASE, data);
  return r.data;
}

export async function updateCoreUptimeWindow(
  id: number,
  data: CoreUptimeWindowUpdate,
): Promise<CoreUptimeWindow> {
  const r = await apiClient.put<CoreUptimeWindow>(`${BASE}/${id}`, data);
  return r.data;
}

export async function deleteCoreUptimeWindow(id: number): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
}
```

- [ ] **Step 2: Extend `client/src/api/sleep.ts`**

a) Add the `CoreUptimeStatus` interface above `SleepStatusResponse`:

```typescript
export interface CoreUptimeStatus {
  enabled: boolean;
  active: boolean;
  current_window_label: string | null;
  current_window_ends_at: string | null;
  next_start: string | null;
}
```

b) Add `core_uptime: CoreUptimeStatus` to `SleepStatusResponse`.

c) Add `core_uptime_enabled: boolean` to `SleepConfigResponse` and `core_uptime_enabled?: boolean` to `SleepConfigUpdate`.

d) Add `'core_uptime_wake'` to `SleepTrigger`:

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

e) Add to `TRIGGER_LABELS`:

```typescript
  core_uptime_wake: 'Kernzeit-Wake',
```

- [ ] **Step 3: Type-check**

```bash
cd client && npx tsc --noEmit
```

Expected: no errors. (If `apiClient` import path differs in your tree, follow the same pattern as `client/src/api/sleep.ts`.)

- [ ] **Step 4: Commit**

```bash
git add client/src/api/coreUptime.ts client/src/api/sleep.ts
git commit -m "feat(sleep): frontend api client for core uptime windows"
```

---

## Task 11: `CoreUptimeWindowCard` component

**Files:**
- Create: `client/src/components/power/CoreUptimeWindowCard.tsx`

- [ ] **Step 1: Implement the card**

```tsx
/**
 * Per-window editable card for Core Operating Hours.
 *
 * Auto-saves on change. Optimistic update; on API error, parent reverts.
 */
import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { CoreUptimeWindow, CoreUptimeWindowUpdate } from '../../api/coreUptime';

const WEEKDAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

interface Props {
  window: CoreUptimeWindow;
  onChange: (id: number, patch: CoreUptimeWindowUpdate) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
}

export function CoreUptimeWindowCard({ window: w, onChange, onDelete }: Props) {
  const [label, setLabel] = useState(w.label ?? '');

  const crossesMidnight =
    w.end_time < w.start_time && w.end_time !== w.start_time;

  const toggleWeekday = (day: number) => {
    const next = w.weekdays.includes(day)
      ? w.weekdays.filter((d) => d !== day)
      : [...w.weekdays, day].sort();
    if (next.length === 0) return; // require at least one
    onChange(w.id, { weekdays: next });
  };

  return (
    <div className="rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 sm:p-4 space-y-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onChange(w.id, { enabled: !w.enabled })}
          className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors ${
            w.enabled ? 'bg-teal-500' : 'bg-slate-600'
          }`}
          aria-label="enable window"
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform ${
              w.enabled ? 'translate-x-4 ml-0.5' : 'translate-x-0.5'
            } mt-0.5`}
          />
        </button>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => {
            if (label !== (w.label ?? '')) {
              onChange(w.id, { label: label || null });
            }
          }}
          placeholder="Beschreibung"
          className="flex-1 rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-white placeholder-slate-600 focus:border-teal-400 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => onDelete(w.id)}
          className="rounded p-1.5 text-slate-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
          title="Löschen"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-wrap gap-1">
        {WEEKDAY_LABELS.map((lbl, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => toggleWeekday(idx)}
            className={`min-w-[2rem] rounded px-2 py-1 text-xs font-medium transition-colors ${
              w.weekdays.includes(idx)
                ? 'bg-teal-500/20 text-teal-300 border border-teal-500/40'
                : 'bg-slate-800/40 text-slate-500 border border-slate-700/40 hover:text-slate-300'
            }`}
          >
            {lbl}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="time"
          value={w.start_time}
          onChange={(e) => onChange(w.id, { start_time: e.target.value })}
          className="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-white focus:border-teal-400 focus:outline-none"
        />
        <span className="text-slate-500">→</span>
        <input
          type="time"
          value={w.end_time}
          onChange={(e) => onChange(w.id, { end_time: e.target.value })}
          className="rounded bg-slate-900 border border-slate-700 px-2 py-1 text-sm text-white focus:border-teal-400 focus:outline-none"
        />
        {crossesMidnight && (
          <span className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-0.5">
            bis nächsten Tag
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd client && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/power/CoreUptimeWindowCard.tsx
git commit -m "feat(sleep): per-window edit card for core uptime"
```

---

## Task 12: `CoreUptimePanel` component

**Files:**
- Create: `client/src/components/power/CoreUptimePanel.tsx`
- Modify: `client/src/components/power/index.ts`

- [ ] **Step 1: Implement the panel**

```tsx
/**
 * Core Operating Hours panel.
 *
 * Shows master toggle + list of windows + add button.
 * Auto-saves all changes (no global Save button).
 */
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Shield, Plus } from 'lucide-react';
import {
  listCoreUptimeWindows,
  createCoreUptimeWindow,
  updateCoreUptimeWindow,
  deleteCoreUptimeWindow,
  type CoreUptimeWindow,
  type CoreUptimeWindowUpdate,
} from '../../api/coreUptime';
import {
  getSleepConfig,
  updateSleepConfig,
} from '../../api/sleep';
import { CoreUptimeWindowCard } from './CoreUptimeWindowCard';

export function CoreUptimePanel() {
  const [masterEnabled, setMasterEnabled] = useState(false);
  const [windows, setWindows] = useState<CoreUptimeWindow[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const [cfg, ws] = await Promise.all([getSleepConfig(), listCoreUptimeWindows()]);
      setMasterEnabled(cfg.core_uptime_enabled);
      setWindows(ws);
    } catch {
      toast.error('Konnte Kernbetriebszeit nicht laden');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleMasterToggle = async () => {
    const next = !masterEnabled;
    setMasterEnabled(next); // optimistic
    try {
      await updateSleepConfig({ core_uptime_enabled: next });
    } catch (err) {
      setMasterEnabled(!next);
      toast.error(err instanceof Error ? err.message : 'Speichern fehlgeschlagen');
    }
  };

  const handleAdd = async () => {
    try {
      const created = await createCoreUptimeWindow({
        label: '',
        start_time: '08:00',
        end_time: '22:00',
        weekdays: [0, 1, 2, 3, 4],
      });
      setWindows((prev) => [...prev, created]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Anlegen fehlgeschlagen');
    }
  };

  const handleUpdate = async (id: number, patch: CoreUptimeWindowUpdate) => {
    const original = windows.find((w) => w.id === id);
    if (!original) return;
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, ...patch } as CoreUptimeWindow : w)),
    );
    try {
      const updated = await updateCoreUptimeWindow(id, patch);
      setWindows((prev) => prev.map((w) => (w.id === id ? updated : w)));
    } catch (err) {
      // Rollback
      setWindows((prev) => prev.map((w) => (w.id === id ? original : w)));
      toast.error(err instanceof Error ? err.message : 'Speichern fehlgeschlagen');
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Zeitfenster löschen?')) return;
    const original = windows;
    setWindows((prev) => prev.filter((w) => w.id !== id));
    try {
      await deleteCoreUptimeWindow(id);
    } catch (err) {
      setWindows(original);
      toast.error(err instanceof Error ? err.message : 'Löschen fehlgeschlagen');
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-32 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-emerald-400" />
          <div>
            <h4 className="text-sm font-medium text-white">Kernbetriebszeit</h4>
            <p className="mt-0.5 text-xs text-slate-400">
              Während dieser Zeitfenster bleibt der Server erreichbar; Auto-Sleep ist blockiert.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleMasterToggle}
          className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
            masterEnabled ? 'bg-emerald-500' : 'bg-slate-600'
          }`}
          aria-label="master toggle"
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
              masterEnabled ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
            } mt-0.5`}
          />
        </button>
      </div>

      {masterEnabled && (
        <div className="space-y-2">
          {windows.map((w) => (
            <CoreUptimeWindowCard
              key={w.id}
              window={w}
              onChange={handleUpdate}
              onDelete={handleDelete}
            />
          ))}
          <button
            type="button"
            onClick={handleAdd}
            className="w-full rounded-lg border border-dashed border-slate-600 hover:border-teal-500/40 hover:bg-teal-500/5 p-3 text-sm text-slate-400 hover:text-teal-300 transition-colors flex items-center justify-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Neues Zeitfenster hinzufügen
          </button>
          <p className="text-xs text-slate-500 mt-2">
            Während aktiver Fenster werden Auto-Idle-Sleep, Schedule-Sleep und Auto-Escalation blockiert.
            Manueller Suspend durch Admins bleibt möglich (mit Warnung).
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Export from index**

In `client/src/components/power/index.ts`, add at the end:

```typescript
export { CoreUptimePanel } from './CoreUptimePanel';
export { CoreUptimeWindowCard } from './CoreUptimeWindowCard';
```

- [ ] **Step 3: Type-check**

```bash
cd client && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/power/CoreUptimePanel.tsx client/src/components/power/index.ts
git commit -m "feat(sleep): core uptime panel with master toggle and window list"
```

---

## Task 13: Wire panel into the Sleep page

**Files:**
- Modify: `client/src/pages/SleepMode.tsx`

- [ ] **Step 1: Insert the new panel**

Replace the file contents with:

```tsx
/**
 * Sleep Mode Page
 *
 * Combines the sleep mode control panel, core operating hours configuration,
 * legacy sleep config, and history into a single page rendered as a tab in
 * SystemControlPage.
 */

import { SleepModePanel } from '../components/power/SleepModePanel';
import { CoreUptimePanel } from '../components/power/CoreUptimePanel';
import { SleepConfigPanel } from '../components/power/SleepConfigPanel';
import { SleepHistoryTable } from '../components/power/SleepHistoryTable';

export default function SleepMode() {
  return (
    <div className="space-y-6">
      <SleepModePanel />
      <CoreUptimePanel />
      <SleepConfigPanel />
      <SleepHistoryTable />
    </div>
  );
}
```

- [ ] **Step 2: Type-check + dev build smoke**

```bash
cd client && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/pages/SleepMode.tsx
git commit -m "feat(sleep): mount CoreUptimePanel in Sleep page"
```

---

## Task 14: Banner + suspend warning in `SleepModePanel`

**Files:**
- Modify: `client/src/components/power/SleepModePanel.tsx`

- [ ] **Step 1: Add the banner under the status header**

In `client/src/components/power/SleepModePanel.tsx`, locate the JSX state-card section (the one starting with `<div className="card border-slate-700/50 p-4 sm:p-6">` near the early part of the return). Just before the closing `</div>` of that card, but after the existing inner blocks, add:

```tsx
        {status.core_uptime?.active && (
          <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 flex items-start gap-2">
            <Shield className="h-4 w-4 text-emerald-300 mt-0.5 shrink-0" />
            <div className="text-xs text-emerald-200">
              <strong>Kernbetriebszeit aktiv</strong>
              {status.core_uptime.current_window_label
                ? ` — „${status.core_uptime.current_window_label}"`
                : ''}
              {status.core_uptime.current_window_ends_at
                ? ` — endet um ${formatTime(status.core_uptime.current_window_ends_at)}.`
                : '.'}{' '}
              Auto-Sleep blockiert.
            </div>
          </div>
        )}
        {!status.core_uptime?.active &&
          status.core_uptime?.enabled &&
          status.core_uptime?.next_start &&
          isWithinNextHours(status.core_uptime.next_start, 12) && (
            <div className="mt-3 rounded-lg bg-slate-800/40 text-slate-400 p-2 text-xs">
              Nächste Kernzeit: {formatRelative(status.core_uptime.next_start)}
            </div>
          )}
```

- [ ] **Step 2: Add the local helpers + import**

a) Add `Shield` to the existing `lucide-react` import line.

b) Add helper functions just above `export function SleepModePanel(...)`:

```tsx
function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function isWithinNextHours(iso: string, hours: number): boolean {
  const ms = new Date(iso).getTime() - Date.now();
  return ms > 0 && ms <= hours * 3600 * 1000;
}

function formatRelative(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow = d.toDateString() === tomorrow.toDateString();
  const time = formatTime(iso);
  if (sameDay) return `heute ${time}`;
  if (isTomorrow) return `morgen ${time}`;
  return `${d.toLocaleDateString()} ${time}`;
}
```

- [ ] **Step 3: Add the suspend warning**

Replace the body of `handleSuspend` with:

```tsx
  const handleSuspend = async () => {
    if (busy) return;
    const inCore = status?.core_uptime?.active;
    const ok = await confirm(
      inCore
        ? `⚠ Kernbetriebszeit ist aktiv${
            status?.core_uptime?.current_window_ends_at
              ? ` (bis ${formatTime(status.core_uptime.current_window_ends_at)})`
              : ''
          }.\nSuspend macht den Server für andere Nutzer unerreichbar.\nTrotzdem fortfahren?`
        : 'Suspend the system? The server will become unreachable. Wake via WoL or RTC alarm.',
      {
        title: 'True Suspend',
        variant: 'danger',
        confirmLabel: inCore ? 'Trotzdem suspenden' : 'Suspend Now',
      },
    );
    if (!ok) return;

    setBusy(true);
    try {
      await enterSuspend();
      toast.success('System suspending...');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to suspend');
    } finally {
      setBusy(false);
    }
  };
```

- [ ] **Step 4: Type-check**

```bash
cd client && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/SleepModePanel.tsx
git commit -m "feat(sleep): banner + suspend warning for core uptime"
```

---

## Task 15: Schedule-override hint in `SleepConfigPanel`

**Files:**
- Modify: `client/src/components/power/SleepConfigPanel.tsx`

- [ ] **Step 1: Add status import + state**

At the top of `SleepConfigPanel.tsx` near the existing API imports, add:

```typescript
import { getSleepStatus } from '../../api/sleep';
```

Inside `SleepConfigPanel()`, add a new state and load it inside `loadData()`:

```typescript
  const [coreUptimeMasterOn, setCoreUptimeMasterOn] = useState(false);
```

In `loadData`, after the `Promise.all` resolves and within the `try` block, append:

```typescript
      try {
        const st = await getSleepStatus();
        setCoreUptimeMasterOn(st.core_uptime?.enabled ?? false);
      } catch {
        // ignore — status is best-effort here
      }
```

- [ ] **Step 2: Render the hint inside the Schedule card**

Find the `<div>` containing the Schedule card (look for `Sleep Schedule` text). Inside that card, immediately after the closing `</div>` of the schedule fields block (i.e. inside the `{scheduleEnabled && (...)}` branch, at the bottom), add:

```tsx
            {coreUptimeMasterOn && (
              <div className="mt-2 rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
                ℹ Kernbetriebszeit hat Vorrang. Sleep-Schedule-Trigger werden während Kernzeit-Fenstern ignoriert.
              </div>
            )}
```

- [ ] **Step 3: Type-check**

```bash
cd client && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/power/SleepConfigPanel.tsx
git commit -m "feat(sleep): hint that core uptime overrides schedule"
```

---

## Task 16: i18n strings

**Files:**
- Modify: `client/src/i18n/locales/de/common.json`
- Modify: `client/src/i18n/locales/en/common.json`

Note: the panel currently uses hard-coded German strings. Wiring all of those through `t()` is a follow-up; for this task we just register the keys so future translation work has a starting point. The user-facing copy already matches the German default per the spec.

- [ ] **Step 1: Add German keys**

Open `client/src/i18n/locales/de/common.json`. Find the `"sleep"` block (search for `"sleep": "Schlafmodus"` — there are two: one inside `tabs` (just a label) and one as a category top-level key). Locate the larger object that contains keys like `"sleepConfirm"`, and append a new `coreUptime` sub-object:

```json
    "coreUptime": {
      "title": "Kernbetriebszeit",
      "description": "Während dieser Zeitfenster bleibt der Server erreichbar; Auto-Sleep ist blockiert.",
      "bannerActive": "Kernbetriebszeit aktiv",
      "bannerEndsAt": "endet um {{time}}",
      "addWindow": "Neues Zeitfenster hinzufügen",
      "crossMidnightBadge": "bis nächsten Tag",
      "warningInfo": "Während aktiver Fenster werden Auto-Idle-Sleep, Schedule-Sleep und Auto-Escalation blockiert. Manueller Suspend durch Admins bleibt möglich (mit Warnung).",
      "scheduleOverridden": "Kernbetriebszeit hat Vorrang. Sleep-Schedule-Trigger werden während Kernzeit-Fenstern ignoriert.",
      "suspendWarning": "Kernbetriebszeit ist aktiv (bis {{time}}). Suspend macht den Server für andere Nutzer unerreichbar.",
      "triggerLabel": "Kernzeit-Wake",
      "weekdays": {
        "0": "Mo", "1": "Di", "2": "Mi", "3": "Do", "4": "Fr", "5": "Sa", "6": "So"
      }
    }
```

- [ ] **Step 2: Add the same keys in English**

In `client/src/i18n/locales/en/common.json`, mirror the structure with English copy:

```json
    "coreUptime": {
      "title": "Core Operating Hours",
      "description": "While these windows are active, the server stays reachable and auto-sleep is blocked.",
      "bannerActive": "Core operating hours active",
      "bannerEndsAt": "ends at {{time}}",
      "addWindow": "Add new time window",
      "crossMidnightBadge": "until next day",
      "warningInfo": "While an active window is in effect, auto-idle sleep, schedule sleep, and auto-escalation are blocked. Manual admin suspend remains possible (with warning).",
      "scheduleOverridden": "Core operating hours take precedence. Schedule sleep triggers are ignored during active windows.",
      "suspendWarning": "Core operating hours are active (until {{time}}). Suspend will make the server unreachable to other users.",
      "triggerLabel": "Core-uptime wake",
      "weekdays": {
        "0": "Mon", "1": "Tue", "2": "Wed", "3": "Thu", "4": "Fri", "5": "Sat", "6": "Sun"
      }
    }
```

- [ ] **Step 3: Validate JSON**

```bash
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/common.json'))"
cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/common.json'))"
```

Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/common.json client/src/i18n/locales/en/common.json
git commit -m "feat(sleep): i18n strings for core uptime"
```

---

## Task 17: End-to-end verification

**Files:** none new

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend && python -m pytest -v -k "sleep or core_uptime"
```

Expected: all sleep-related tests pass (existing + new). Note the use of `-k` to scope the run; replace with the full suite if you want belt-and-suspenders coverage.

- [ ] **Step 2: Type-check the frontend**

```bash
cd client && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Build the frontend**

```bash
cd client && npm run build
```

Expected: successful build, no warnings about missing icons / unresolved imports.

- [ ] **Step 4: Manual smoke (dev mode)**

In two terminals:

```bash
# Terminal 1
python start_dev.py
```

Open `http://localhost:5173`, log in as `admin` / `DevMode2024`. Navigate to **System Control → Hardware → Sleep**. Verify:

1. The **Kernbetriebszeit** panel appears between the status panel and the configuration panel.
2. Toggling the master switch on enables window editing; clicking **Neues Zeitfenster hinzufügen** creates a window.
3. Editing the label, weekdays, and times persists across page reloads.
4. With `auto_idle_enabled` on, a window covering "now", and `idle_timeout_minutes=1`, the idle progress bar in `SleepModePanel` does not advance past 0.
5. The status banner ("Kernbetriebszeit aktiv...") shows during an active window.
6. Clicking **Suspend** during an active window shows an extended warning text. (Dev mode does not actually suspend the OS — the Suspend backend is mocked.)
7. The Schedule card in the Sleep config shows the override hint when both toggles are on.

If any of the seven checks fails, jump back to the relevant task.

- [ ] **Step 5: Final commit (only if any fix-ups were needed)**

If steps 1-4 all pass without code changes, no commit needed. If you found a bug and patched it, commit that fix:

```bash
git add -A
git commit -m "fix(sleep): smoke fixes for core uptime"
```

---

## Self-Review Result

Spec coverage:
- F1–F4 (CRUD + master toggle): Tasks 1, 2, 4, 9, 12.
- F5 (block auto-idle/schedule/escalation): Tasks 5, 6, 7.
- F6 (auto-wake from soft sleep): Task 6.
- F7 (clamp wake_at): Task 7.
- F8 (manual suspend with warning): Task 14.
- F9 (banner): Task 14.
- F10 (schedule override hint): Task 15.
- N1 (pure helpers): Task 3.
- N2 (one DB query per loop tick): Task 5 `_load_core_uptime`.
- N3 (additive migration): Task 2.
- N4 (admin auth + rate limit): Task 9.
- N5 (status remains user-readable): Task 8 (status route still uses `get_current_user`).

No placeholders, every code step contains the actual code, every command shows expected output. Type names (`CoreUptimeWindow`, `CoreUptimeWindowModel`, `core_uptime_helpers`, `CoreUptimeStatus`) used consistently across tasks.
