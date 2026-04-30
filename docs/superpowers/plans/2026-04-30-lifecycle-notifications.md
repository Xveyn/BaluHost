# Lifecycle Push Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add push & in-app notifications for the four NAS lifecycle events (Suspend / Resume / Shutdown / Startup) by reusing the existing `EventEmitter` and adding a small persistence table for downtime tracking.

**Architecture:** Hook into exactly four code points (`enter_true_suspend()` pre/post in `sleep.py`, `_startup()` and `_shutdown()` in `lifespan.py`), all behind the existing `IS_PRIMARY_WORKER` guard. New DB table `system_lifecycle_events` stores raw events so the next cold-boot can compute "Letzter Shutdown vor X" from history. New notification category `lifecycle` (priority=1, type=info) — admins get pushes by default via existing routing, non-admins opt-in via `notification_routing`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Alembic, pytest, asyncio, existing `EventEmitter` in `services/notifications/events.py`.

**Spec:** `docs/superpowers/specs/2026-04-30-lifecycle-notifications-design.md`

---

## File Structure

**New files:**
- `backend/app/models/system_lifecycle.py` — SQLAlchemy model
- `backend/app/services/notifications/lifecycle_helpers.py` — `format_duration_human()`, `german_trigger_label()`
- `backend/alembic/versions/<auto>_add_system_lifecycle_events.py` — Alembic migration (auto-generated)
- `backend/tests/test_lifecycle_helpers.py` — pure-function tests
- `backend/tests/test_lifecycle_notifications.py` — integration tests for hooks

**Modified files:**
- `backend/app/models/__init__.py` — register new model
- `backend/app/services/notifications/events.py` — 4 new `EventType` values, 4 `EVENT_CONFIGS`, cooldowns, sync+async convenience helpers
- `backend/app/services/power/sleep.py` — `enter_true_suspend()`: emit suspend + persist event before kernel suspend; emit resume + persist event after wake
- `backend/app/core/lifespan.py` — `_startup()`: emit startup with downtime context; `_shutdown()`: emit shutdown with 3s timeout

---

## Task 1: Helper `format_duration_human` and `german_trigger_label`

**Files:**
- Create: `backend/app/services/notifications/lifecycle_helpers.py`
- Test: `backend/tests/test_lifecycle_helpers.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_lifecycle_helpers.py`:

```python
"""Tests for lifecycle helpers (pure functions, no DB)."""
import pytest

from app.services.notifications.lifecycle_helpers import (
    format_duration_human,
    german_trigger_label,
)


def test_format_duration_handles_none():
    assert format_duration_human(None) == "unbekannt"


def test_format_duration_seconds_only():
    assert format_duration_human(0) == "0s"
    assert format_duration_human(12) == "12s"
    assert format_duration_human(59) == "59s"


def test_format_duration_minutes():
    assert format_duration_human(60) == "1min"
    assert format_duration_human(125) == "2min 5s"
    assert format_duration_human(3599) == "59min 59s"


def test_format_duration_hours():
    assert format_duration_human(3600) == "1h"
    assert format_duration_human(4 * 3600 + 32 * 60) == "4h 32min"
    assert format_duration_human(86399) == "23h 59min"


def test_format_duration_days():
    assert format_duration_human(86400) == "1 Tag"
    assert format_duration_human(2 * 86400) == "2 Tage"
    assert format_duration_human(3 * 86400 + 2 * 3600) == "3 Tage 2h"


def test_format_duration_negative_returns_unknown():
    # Clock skew / wrong timestamps shouldn't crash
    assert format_duration_human(-5) == "unbekannt"


def test_german_trigger_label_known():
    assert german_trigger_label("manual") == "manuell"
    assert german_trigger_label("schedule") == "geplant"
    assert german_trigger_label("auto_idle") == "Auto-Idle"
    assert german_trigger_label("auto_escalation") == "Auto-Eskalation"
    assert german_trigger_label("api") == "API"
    assert german_trigger_label("signal") == "Signal"


def test_german_trigger_label_unknown_falls_back():
    assert german_trigger_label("xyz") == "xyz"
    assert german_trigger_label(None) == "unbekannt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_lifecycle_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.notifications.lifecycle_helpers`

- [ ] **Step 3: Write the helper module**

Create `backend/app/services/notifications/lifecycle_helpers.py`:

```python
"""Pure helpers for lifecycle notifications: human-readable durations and trigger labels."""
from __future__ import annotations

from typing import Optional


_TRIGGER_LABELS_DE: dict[str, str] = {
    "manual": "manuell",
    "schedule": "geplant",
    "auto_idle": "Auto-Idle",
    "auto_escalation": "Auto-Eskalation",
    "auto_wake": "Auto-Wake",
    "api": "API",
    "signal": "Signal",
}


def format_duration_human(seconds: Optional[float]) -> str:
    """Format a duration in seconds as a short German string.

    Examples:
        12        -> "12s"
        125       -> "2min 5s"
        4*3600+32*60 -> "4h 32min"
        3*86400+2*3600 -> "3 Tage 2h"
        None      -> "unbekannt"
    """
    if seconds is None or seconds < 0:
        return "unbekannt"

    s = int(seconds)
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)

    if days >= 1:
        unit = "Tag" if days == 1 else "Tage"
        if hours:
            return f"{days} {unit} {hours}h"
        return f"{days} {unit}"

    if hours >= 1:
        if minutes:
            return f"{hours}h {minutes}min"
        return f"{hours}h"

    if minutes >= 1:
        if secs:
            return f"{minutes}min {secs}s"
        return f"{minutes}min"

    return f"{secs}s"


def german_trigger_label(trigger: Optional[str]) -> str:
    """Map a SleepTrigger / lifecycle trigger value to a German label.

    Falls back to the raw value (or "unbekannt" if None).
    """
    if trigger is None:
        return "unbekannt"
    return _TRIGGER_LABELS_DE.get(trigger, trigger)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_lifecycle_helpers.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/lifecycle_helpers.py backend/tests/test_lifecycle_helpers.py
git commit -m "feat(notifications): add lifecycle helpers (format_duration_human, german_trigger_label)"
```

---

## Task 2: SQLAlchemy model `SystemLifecycleEvent`

**Files:**
- Create: `backend/app/models/system_lifecycle.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the model**

Create `backend/app/models/system_lifecycle.py`:

```python
"""Database model for NAS lifecycle events (suspend/resume/shutdown/startup)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class SystemLifecycleEvent(Base):
    """Single NAS lifecycle transition (suspend/resume/shutdown/startup).

    Used by the lifecycle-notifications feature to compute downtime
    ("Letzter Shutdown vor X") on cold boot. New rows are inserted from
    `services/power/sleep.py` and `core/lifespan.py`.
    """

    __tablename__ = "system_lifecycle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    trigger: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_lifecycle_type_ts", "event_type", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<SystemLifecycleEvent({self.event_type} @ {self.timestamp})>"
```

- [ ] **Step 2: Register in models/__init__.py**

Edit `backend/app/models/__init__.py`:

Add an import line near the other model imports (preserve alphabetical / group ordering — place after the `sleep` import on line 66):

```python
from app.models.system_lifecycle import SystemLifecycleEvent
```

Add `"SystemLifecycleEvent",` to the `__all__` list (place after `"SleepStateLog",`).

- [ ] **Step 3: Verify model imports cleanly**

Run: `cd backend && python -c "from app.models import SystemLifecycleEvent; print(SystemLifecycleEvent.__tablename__)"`
Expected: `system_lifecycle_events`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/system_lifecycle.py backend/app/models/__init__.py
git commit -m "feat(models): add SystemLifecycleEvent for lifecycle history"
```

---

## Task 3: Alembic migration

**Files:**
- Create: `backend/alembic/versions/<auto>_add_system_lifecycle_events.py`

- [ ] **Step 1: Auto-generate the migration**

Run: `cd backend && alembic revision --autogenerate -m "add system_lifecycle_events table"`
Expected: New file under `backend/alembic/versions/<rev>_add_system_lifecycle_events.py`

- [ ] **Step 2: Review the generated migration**

Open the new file. Confirm `upgrade()` contains:

- `op.create_table('system_lifecycle_events', ...)` with columns `id`, `event_type`, `timestamp`, `trigger`, `details_json`
- `op.create_index('ix_lifecycle_type_ts', 'system_lifecycle_events', ['event_type', 'timestamp'])`
- An `ix_system_lifecycle_events_event_type` and `ix_system_lifecycle_events_timestamp` index (auto-generated from `index=True` on the columns)

Confirm `downgrade()` drops the indexes and the table.

If the auto-generated migration is missing the composite `ix_lifecycle_type_ts` index, add it manually after `op.create_table(...)`:

```python
op.create_index('ix_lifecycle_type_ts', 'system_lifecycle_events', ['event_type', 'timestamp'], unique=False)
```

And to `downgrade()` before `op.drop_table(...)`:

```python
op.drop_index('ix_lifecycle_type_ts', table_name='system_lifecycle_events')
```

- [ ] **Step 3: Apply the migration locally**

Run: `cd backend && alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> <rev>, add system_lifecycle_events table`

- [ ] **Step 4: Verify the table exists**

Run: `cd backend && python -c "from app.core.database import engine; from sqlalchemy import inspect; print('system_lifecycle_events' in inspect(engine).get_table_names())"`
Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(db): migration for system_lifecycle_events table"
```

---

## Task 4: New EventTypes, configs, cooldowns

**Files:**
- Modify: `backend/app/services/notifications/events.py`

- [ ] **Step 1: Add EventType values**

Edit `backend/app/services/notifications/events.py`. In the `EventType` enum (around line 59), add four new values at the end of the enum body, right after the plugin events:

```python
    # System lifecycle events
    SYSTEM_SUSPEND = "lifecycle.suspend"
    SYSTEM_RESUME = "lifecycle.resume"
    SYSTEM_SHUTDOWN = "lifecycle.shutdown"
    SYSTEM_STARTUP = "lifecycle.startup"
```

- [ ] **Step 2: Add cooldown entries**

In the `_COOLDOWN_SECONDS` dict (around line 19), add:

```python
    "lifecycle.suspend": 60,        # 1min — guard against rapid retries
    "lifecycle.resume": 60,         # 1min
    # No cooldown for shutdown/startup — legitimate reboots must always notify
```

- [ ] **Step 3: Add EVENT_CONFIGS entries**

In the `EVENT_CONFIGS` dict (around line 128), add at the end (before the closing `}`):

```python
    # System lifecycle events
    EventType.SYSTEM_SUSPEND: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="NAS wird suspended",
        message_template="NAS geht in Suspend-Modus ({trigger_label}). Verbindung wird kurz unterbrochen.",
        action_url="/admin/system-control?tab=sleep",
    ),
    EventType.SYSTEM_RESUME: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="NAS wieder online",
        message_template="NAS aufgewacht nach {duration_human} Suspend ({trigger_label}).",
        action_url="/admin/system-control?tab=sleep",
    ),
    EventType.SYSTEM_SHUTDOWN: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="NAS wird heruntergefahren",
        message_template="NAS fährt herunter ({trigger_label}).",
        action_url="/admin/system-control",
    ),
    EventType.SYSTEM_STARTUP: EventConfig(
        priority=1,
        category="lifecycle",
        notification_type="info",
        title_template="NAS hochgefahren",
        message_template="NAS ist wieder einsatzbereit. Letzter Shutdown vor {downtime_human}.",
        action_url="/",
    ),
```

- [ ] **Step 4: Run existing notification tests to confirm no regression**

Run: `cd backend && python -m pytest tests/ -k "notification or event" -v`
Expected: All previously-passing tests still pass (no failures introduced).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/events.py
git commit -m "feat(notifications): add lifecycle event types, configs, cooldowns"
```

---

## Task 5: Convenience emit helpers (sync + async)

**Files:**
- Modify: `backend/app/services/notifications/events.py`
- Test: `backend/tests/test_lifecycle_notifications.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_lifecycle_notifications.py`:

```python
"""Integration tests for lifecycle notifications."""
from unittest.mock import patch, MagicMock

import pytest

from app.services.notifications.events import (
    EventType,
    emit_system_suspend_sync,
    emit_system_resume_sync,
    emit_system_shutdown_sync,
    emit_system_startup_sync,
    get_event_emitter,
)


@pytest.fixture(autouse=True)
def reset_cooldowns():
    """Clear cooldown cache between tests."""
    from app.services.notifications import events as events_mod
    events_mod._cooldown_cache.clear()
    yield
    events_mod._cooldown_cache.clear()


def test_emit_system_suspend_sync_calls_emitter():
    """emit_system_suspend_sync calls EventEmitter with SYSTEM_SUSPEND event."""
    emitter = get_event_emitter()
    with patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_system_suspend_sync(trigger="manual")
        mock_emit.assert_called_once()
        args, kwargs = mock_emit.call_args
        assert args[0] == EventType.SYSTEM_SUSPEND
        assert kwargs.get("trigger_label") == "manuell"


def test_emit_system_resume_sync_includes_duration_and_trigger():
    """emit_system_resume_sync passes duration_human and trigger_label."""
    emitter = get_event_emitter()
    with patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_system_resume_sync(trigger="schedule", duration_seconds=4 * 3600 + 32 * 60)
        args, kwargs = mock_emit.call_args
        assert args[0] == EventType.SYSTEM_RESUME
        assert kwargs.get("duration_human") == "4h 32min"
        assert kwargs.get("trigger_label") == "geplant"


def test_emit_system_shutdown_sync_with_api_trigger():
    emitter = get_event_emitter()
    with patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_system_shutdown_sync(trigger="api")
        args, kwargs = mock_emit.call_args
        assert args[0] == EventType.SYSTEM_SHUTDOWN
        assert kwargs.get("trigger_label") == "API"


def test_emit_system_startup_sync_with_known_downtime():
    emitter = get_event_emitter()
    with patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_system_startup_sync(downtime_seconds=125)
        args, kwargs = mock_emit.call_args
        assert args[0] == EventType.SYSTEM_STARTUP
        assert kwargs.get("downtime_human") == "2min 5s"


def test_emit_system_startup_sync_with_unknown_downtime():
    emitter = get_event_emitter()
    with patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_system_startup_sync(downtime_seconds=None)
        args, kwargs = mock_emit.call_args
        assert kwargs.get("downtime_human") == "unbekannt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v`
Expected: FAIL with `ImportError: cannot import name 'emit_system_suspend_sync'`

- [ ] **Step 3: Add convenience helpers to events.py**

Edit `backend/app/services/notifications/events.py`. At the bottom of the file (after the existing `emit_*_sync` helpers), add:

```python
# ---------------------------------------------------------------------------
# Lifecycle event helpers
# ---------------------------------------------------------------------------


def emit_system_suspend_sync(trigger: str) -> None:
    """Emit lifecycle.suspend event (sync) — fired BEFORE kernel suspend."""
    from app.services.notifications.lifecycle_helpers import german_trigger_label
    get_event_emitter().emit_for_admins_sync(
        EventType.SYSTEM_SUSPEND,
        cooldown_entity="suspend",
        trigger=trigger,
        trigger_label=german_trigger_label(trigger),
    )


def emit_system_resume_sync(trigger: str, duration_seconds: float | None) -> None:
    """Emit lifecycle.resume event (sync) — fired after wake from suspend."""
    from app.services.notifications.lifecycle_helpers import (
        format_duration_human,
        german_trigger_label,
    )
    get_event_emitter().emit_for_admins_sync(
        EventType.SYSTEM_RESUME,
        cooldown_entity="resume",
        trigger=trigger,
        trigger_label=german_trigger_label(trigger),
        duration_seconds=duration_seconds,
        duration_human=format_duration_human(duration_seconds),
    )


def emit_system_shutdown_sync(trigger: str) -> None:
    """Emit lifecycle.shutdown event (sync) — fired early in _shutdown()."""
    from app.services.notifications.lifecycle_helpers import german_trigger_label
    get_event_emitter().emit_for_admins_sync(
        EventType.SYSTEM_SHUTDOWN,
        trigger=trigger,
        trigger_label=german_trigger_label(trigger),
    )


def emit_system_startup_sync(downtime_seconds: float | None) -> None:
    """Emit lifecycle.startup event (sync) — fired at end of _startup()."""
    from app.services.notifications.lifecycle_helpers import format_duration_human
    get_event_emitter().emit_for_admins_sync(
        EventType.SYSTEM_STARTUP,
        downtime_seconds=downtime_seconds,
        downtime_human=format_duration_human(downtime_seconds),
    )


async def emit_system_suspend(trigger: str) -> None:
    """Async wrapper — used in `enter_true_suspend()`."""
    emit_system_suspend_sync(trigger)


async def emit_system_resume(trigger: str, duration_seconds: float | None) -> None:
    """Async wrapper — used in `enter_true_suspend()` after resume."""
    emit_system_resume_sync(trigger, duration_seconds)


async def emit_system_shutdown(trigger: str) -> None:
    """Async wrapper — used in `_shutdown()`."""
    emit_system_shutdown_sync(trigger)


async def emit_system_startup(downtime_seconds: float | None) -> None:
    """Async wrapper — used in `_startup()`."""
    emit_system_startup_sync(downtime_seconds)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/events.py backend/tests/test_lifecycle_notifications.py
git commit -m "feat(notifications): add sync+async convenience helpers for lifecycle events"
```

---

## Task 6: Wire suspend hook in sleep.py

**Files:**
- Modify: `backend/app/services/power/sleep.py:707-753` (`enter_true_suspend`)
- Test: `backend/tests/test_lifecycle_notifications.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_lifecycle_notifications.py`:

```python
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.schemas.sleep import SleepTrigger


def test_suspend_persists_event_and_emits_before_kernel_suspend(tmp_path, monkeypatch):
    """Order check: row inserted in system_lifecycle_events AND emit_system_suspend
    are both called BEFORE _backend.suspend_system()."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend
    from app.core.database import SessionLocal
    from app.models.system_lifecycle import SystemLifecycleEvent

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    call_order: list[str] = []

    original_suspend = backend.suspend_system

    async def tracked_suspend(*args, **kwargs):
        call_order.append("kernel_suspend")
        return await original_suspend(*args, **kwargs)

    backend.suspend_system = tracked_suspend  # type: ignore[method-assign]

    with patch(
        "app.services.notifications.events.emit_system_suspend",
        new=AsyncMock(side_effect=lambda *a, **kw: call_order.append("emit_suspend")),
    ) as mock_emit, patch(
        "app.services.notifications.events.emit_system_resume",
        new=AsyncMock(),
    ):
        asyncio.run(svc.enter_true_suspend("test", SleepTrigger.MANUAL))

    # emit must come BEFORE kernel_suspend
    assert call_order.index("emit_suspend") < call_order.index("kernel_suspend"), call_order

    # DB row must exist for the suspend event
    with SessionLocal() as db:
        suspend_rows = db.query(SystemLifecycleEvent).filter_by(event_type="suspend").all()
        assert len(suspend_rows) >= 1
        assert suspend_rows[-1].trigger == "manual"


def test_suspend_emit_respects_3s_timeout(monkeypatch):
    """If emit_system_suspend hangs > 3s, suspend continues anyway."""
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    async def slow_emit(*args, **kwargs):
        await asyncio.sleep(10)  # would hang for 10s

    with patch(
        "app.services.notifications.events.emit_system_suspend",
        new=AsyncMock(side_effect=slow_emit),
    ), patch(
        "app.services.notifications.events.emit_system_resume",
        new=AsyncMock(),
    ):
        # Whole call must finish in < 5s (3s timeout + small overhead from suspend itself)
        async def run():
            return await asyncio.wait_for(
                svc.enter_true_suspend("test", SleepTrigger.MANUAL),
                timeout=5.0,
            )

        result = asyncio.run(run())
        assert result is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py::test_suspend_persists_event_and_emits_before_kernel_suspend -v`
Expected: FAIL — no rows inserted, no emit called

- [ ] **Step 3: Modify `enter_true_suspend()` in sleep.py**

Edit `backend/app/services/power/sleep.py`. Locate the `enter_true_suspend()` method (around line 707). Replace the body from `prev_state = self._current_state` through the end of the method with:

```python
        prev_state = self._current_state

        # Enter soft sleep first if awake
        if self._current_state == SleepState.AWAKE:
            ok = await self.enter_soft_sleep(reason, trigger)
            if not ok:
                return False

        self._current_state = SleepState.ENTERING_SUSPEND

        # 1. Persist the suspend event so cold-boot scenarios can compute downtime,
        #    AND so resume can read the trigger back from the DB.
        suspend_event_id: Optional[int] = None
        try:
            db = SessionLocal()
            try:
                from app.models.system_lifecycle import SystemLifecycleEvent
                ev = SystemLifecycleEvent(
                    event_type="suspend",
                    trigger=trigger.value,
                    details_json=json.dumps({"reason": reason}) if reason else None,
                )
                db.add(ev)
                db.commit()
                suspend_event_id = ev.id
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not persist lifecycle suspend event: %s", exc)

        # 2. Emit push notification BEFORE kernel suspend (best-effort, 3s timeout).
        try:
            from app.services.notifications.events import emit_system_suspend
            await asyncio.wait_for(
                emit_system_suspend(trigger=trigger.value),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Lifecycle suspend push timed out after 3s — proceeding with suspend anyway")
        except Exception as exc:
            logger.warning("Lifecycle suspend push failed: %s — proceeding", exc)

        self._log_state_change(
            SleepState.SOFT_SLEEP, SleepState.TRUE_SUSPEND, reason, trigger,
            details={"wake_at": wake_at.isoformat() if wake_at else None},
        )

        self._current_state = SleepState.TRUE_SUSPEND
        self._state_since = datetime.now(timezone.utc)
        suspend_started_at = datetime.now(timezone.utc)

        # 3. Suspend the system. When *wake_at* is given the backend uses
        #    ``rtcwake -m mem`` which sets the RTC alarm and suspends atomically.
        ok = await self._backend.suspend_system(wake_at=wake_at)

        # When system resumes (or suspend failed), we'll be back here.
        # Revert to SOFT_SLEEP so _exit_soft_sleep accepts the transition.
        self._current_state = SleepState.SOFT_SLEEP
        self._state_since = datetime.now(timezone.utc)

        # 4. Persist resume event + emit resume notification (only on successful suspend).
        if ok:
            duration_seconds = (datetime.now(timezone.utc) - suspend_started_at).total_seconds()
            try:
                db = SessionLocal()
                try:
                    from app.models.system_lifecycle import SystemLifecycleEvent
                    resume_ev = SystemLifecycleEvent(
                        event_type="resume",
                        trigger=trigger.value,
                        details_json=json.dumps({
                            "duration_seconds": duration_seconds,
                            "suspend_event_id": suspend_event_id,
                        }),
                    )
                    db.add(resume_ev)
                    db.commit()
                finally:
                    db.close()
            except Exception as exc:
                logger.warning("Could not persist lifecycle resume event: %s", exc)

            try:
                from app.services.notifications.events import emit_system_resume
                await emit_system_resume(
                    trigger=trigger.value,
                    duration_seconds=duration_seconds,
                )
            except Exception as exc:
                logger.warning("Lifecycle resume push failed: %s", exc)

            logger.info("System resumed from suspend")
            await self._exit_soft_sleep("resume_from_suspend")
        else:
            logger.error("System suspend failed, remaining in soft sleep")

        return ok
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v -k suspend`
Expected: Both new suspend tests pass.

- [ ] **Step 5: Run full sleep-related test suite to verify no regression**

Run: `cd backend && python -m pytest tests/ -k "sleep" -v`
Expected: All previously-passing sleep tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/test_lifecycle_notifications.py
git commit -m "feat(sleep): emit lifecycle.suspend + lifecycle.resume + persist events"
```

---

## Task 7: Wire shutdown hook in lifespan.py

**Files:**
- Modify: `backend/app/core/lifespan.py` (add `_emit_lifecycle_shutdown()` helper, call from `_shutdown()`)
- Test: `backend/tests/test_lifecycle_notifications.py`

We extract the work into a `_emit_lifecycle_shutdown()` helper (symmetric to Task 8's `_emit_lifecycle_startup()`) so it can be unit-tested without running the full `_shutdown()` lifecycle.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_lifecycle_notifications.py`:

```python
def test_shutdown_persists_event_before_emit(monkeypatch):
    """_emit_lifecycle_shutdown writes system_lifecycle_events row BEFORE emit."""
    from app.core import lifespan
    from app.core.database import SessionLocal
    from app.models.system_lifecycle import SystemLifecycleEvent

    monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", True)

    with SessionLocal() as db:
        db.query(SystemLifecycleEvent).delete()
        db.commit()

    row_count_at_emit: list[int] = []

    async def tracked_emit(*args, **kwargs):
        with SessionLocal() as db:
            row_count_at_emit.append(
                db.query(SystemLifecycleEvent).filter_by(event_type="shutdown").count()
            )

    with patch(
        "app.services.notifications.events.emit_system_shutdown",
        new=AsyncMock(side_effect=tracked_emit),
    ):
        asyncio.run(lifespan._emit_lifecycle_shutdown())

    assert row_count_at_emit and row_count_at_emit[0] == 1, (
        f"Shutdown row must exist when emit is called; got count={row_count_at_emit}"
    )


def test_shutdown_emit_respects_3s_timeout(monkeypatch):
    """If emit_system_shutdown hangs > 3s, _emit_lifecycle_shutdown returns anyway."""
    import time as _time
    from app.core import lifespan

    monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", True)

    async def slow_emit(*args, **kwargs):
        await asyncio.sleep(10)

    start = _time.monotonic()
    with patch(
        "app.services.notifications.events.emit_system_shutdown",
        new=AsyncMock(side_effect=slow_emit),
    ):
        asyncio.run(lifespan._emit_lifecycle_shutdown())
    elapsed = _time.monotonic() - start
    assert elapsed < 5.0, f"Lifecycle shutdown took {elapsed}s — 3s timeout did not fire"


def test_shutdown_secondary_worker_does_not_emit(monkeypatch):
    """Non-primary worker must not emit lifecycle.shutdown."""
    from app.core import lifespan
    from app.core.database import SessionLocal
    from app.models.system_lifecycle import SystemLifecycleEvent

    monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", False)

    with SessionLocal() as db:
        db.query(SystemLifecycleEvent).delete()
        db.commit()

    with patch(
        "app.services.notifications.events.emit_system_shutdown",
        new=AsyncMock(),
    ) as mock_emit:
        asyncio.run(lifespan._emit_lifecycle_shutdown())
        mock_emit.assert_not_called()

    with SessionLocal() as db:
        assert db.query(SystemLifecycleEvent).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v -k shutdown`
Expected: FAIL — `AttributeError: module ... has no attribute '_emit_lifecycle_shutdown'`

- [ ] **Step 3: Add `_emit_lifecycle_shutdown()` helper + call it from `_shutdown()`**

Edit `backend/app/core/lifespan.py`.

First, add a new module-level helper. Place it near the other private helpers, e.g., right above `async def _startup` (it will sit next to the matching `_emit_lifecycle_startup` you'll add in Task 8):

```python
async def _emit_lifecycle_shutdown(trigger: str = "signal") -> None:
    """Emit the lifecycle.shutdown notification and persist a 'shutdown' row.

    Run as the very first step of `_shutdown()`. Best-effort: row insert
    happens before the FCM emit so the next startup can compute downtime
    even when FCM hangs. Emit is bounded to 3s. No-op on secondary workers.
    """
    if not IS_PRIMARY_WORKER:
        return

    try:
        from app.core.database import SessionLocal
        from app.models.system_lifecycle import SystemLifecycleEvent
        from app.services.notifications.events import emit_system_shutdown

        # 1. Persist the shutdown row FIRST.
        with SessionLocal() as db:
            ev = SystemLifecycleEvent(
                event_type="shutdown",
                trigger=trigger,
                details_json=None,
            )
            db.add(ev)
            db.commit()

        # 2. Emit the push (best-effort, 3s max).
        try:
            await asyncio.wait_for(
                emit_system_shutdown(trigger=trigger),
                timeout=3.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Lifecycle shutdown push timed out after 3s — continuing shutdown")
        except Exception as exc:
            logger.warning("Lifecycle shutdown push failed: %s — continuing shutdown", exc)
    except Exception as exc:
        logger.warning("Lifecycle shutdown step failed (non-fatal): %s", exc)
```

Then in `_shutdown()` (around line 488), insert the call as the very first action — before the `from app.services import jobs` import block:

```python
    # ---- Lifecycle notification (best-effort, must run BEFORE app dies) ----
    await _emit_lifecycle_shutdown()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v -k shutdown`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/lifespan.py backend/tests/test_lifecycle_notifications.py
git commit -m "feat(lifespan): emit lifecycle.shutdown + persist row before app dies"
```

---

## Task 8: Wire startup hook in lifespan.py

**Files:**
- Modify: `backend/app/core/lifespan.py:_startup()`
- Test: `backend/tests/test_lifecycle_notifications.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_lifecycle_notifications.py`:

```python
from datetime import timedelta


def test_startup_calculates_downtime_from_last_shutdown(monkeypatch):
    """Given a 'shutdown' row 5min in the past, startup emit gets downtime ~300s."""
    from app.core import lifespan
    from app.core.database import SessionLocal
    from app.models.system_lifecycle import SystemLifecycleEvent

    monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", True)

    # Seed a shutdown 5min ago
    with SessionLocal() as db:
        db.query(SystemLifecycleEvent).delete()
        db.commit()
        old = SystemLifecycleEvent(
            event_type="shutdown",
            trigger="signal",
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        db.add(old)
        db.commit()

    captured: dict = {}

    async def capture_emit(downtime_seconds=None, **kwargs):
        captured["downtime_seconds"] = downtime_seconds

    with patch(
        "app.services.notifications.events.emit_system_startup",
        new=AsyncMock(side_effect=capture_emit),
    ):
        asyncio.run(lifespan._emit_lifecycle_startup())

    assert captured["downtime_seconds"] is not None
    assert 290 < captured["downtime_seconds"] < 310, captured


def test_startup_handles_missing_last_shutdown(monkeypatch):
    """Empty DB → downtime_seconds=None, no crash."""
    from app.core import lifespan
    from app.core.database import SessionLocal
    from app.models.system_lifecycle import SystemLifecycleEvent

    monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", True)

    with SessionLocal() as db:
        db.query(SystemLifecycleEvent).delete()
        db.commit()

    captured: dict = {}

    async def capture_emit(downtime_seconds=None, **kwargs):
        captured["downtime_seconds"] = downtime_seconds

    with patch(
        "app.services.notifications.events.emit_system_startup",
        new=AsyncMock(side_effect=capture_emit),
    ):
        asyncio.run(lifespan._emit_lifecycle_startup())

    assert captured.get("downtime_seconds") is None


def test_startup_secondary_worker_does_not_emit(monkeypatch):
    """Non-primary worker must not emit lifecycle.startup."""
    from app.core import lifespan

    monkeypatch.setattr(lifespan, "IS_PRIMARY_WORKER", False)

    with patch(
        "app.services.notifications.events.emit_system_startup",
        new=AsyncMock(),
    ) as mock_emit:
        asyncio.run(lifespan._emit_lifecycle_startup())
        mock_emit.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v -k startup`
Expected: FAIL — `AttributeError: module ... has no attribute '_emit_lifecycle_startup'`

- [ ] **Step 3: Add `_emit_lifecycle_startup()` helper + call it from `_startup()`**

Edit `backend/app/core/lifespan.py`.

First, add a new module-level helper near the other private helpers (e.g., right above `async def _startup`):

```python
async def _emit_lifecycle_startup() -> None:
    """Emit the lifecycle.startup notification with downtime context.

    Reads the most recent 'shutdown' row from system_lifecycle_events to
    compute downtime. Inserts a 'startup' row. No-op on secondary workers.
    """
    if not IS_PRIMARY_WORKER:
        return

    try:
        from app.core.database import SessionLocal
        from app.models.system_lifecycle import SystemLifecycleEvent
        from app.services.notifications.events import emit_system_startup
        from sqlalchemy import desc

        downtime_seconds: float | None = None
        with SessionLocal() as db:
            last_shutdown = (
                db.query(SystemLifecycleEvent)
                .filter(SystemLifecycleEvent.event_type == "shutdown")
                .order_by(desc(SystemLifecycleEvent.timestamp))
                .first()
            )
            if last_shutdown and last_shutdown.timestamp:
                ts = last_shutdown.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                downtime_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
                if downtime_seconds < 0:
                    downtime_seconds = None

            ev = SystemLifecycleEvent(
                event_type="startup",
                trigger=None,
                details_json=None,
            )
            db.add(ev)
            db.commit()

        try:
            await emit_system_startup(downtime_seconds=downtime_seconds)
        except Exception as exc:
            logger.warning("Lifecycle startup push failed: %s", exc)
    except Exception as exc:
        logger.warning("Lifecycle startup step failed (non-fatal): %s", exc)
```

Then in `_startup()` (around line 319, immediately after `logger.info("Primary worker: %s (PID %d)", IS_PRIMARY_WORKER, os.getpid())`), add the call:

```python
    # Lifecycle notification: emit startup with downtime context
    await _emit_lifecycle_startup()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v -k startup`
Expected: 3 passed

- [ ] **Step 5: Run full lifecycle test file**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py -v`
Expected: All tests in this file pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/lifespan.py backend/tests/test_lifecycle_notifications.py
git commit -m "feat(lifespan): emit lifecycle.startup with downtime context in _startup()"
```

---

## Task 9: Cooldown verification test

**Files:**
- Test: `backend/tests/test_lifecycle_notifications.py`

- [ ] **Step 1: Add cooldown tests**

Add to `backend/tests/test_lifecycle_notifications.py`:

```python
def test_cooldown_60s_for_suspend():
    """Two suspend emits within 60s — second is suppressed by cooldown."""
    from app.services.notifications import events as events_mod
    events_mod._cooldown_cache.clear()

    emitter = events_mod.get_event_emitter()
    with patch.object(emitter, "_db_session_factory", return_value=None):
        # First call should not be in cooldown
        assert events_mod._check_cooldown("lifecycle.suspend", "suspend") is False
        events_mod._set_cooldown("lifecycle.suspend", "suspend")
        # Second call within 60s should be in cooldown
        assert events_mod._check_cooldown("lifecycle.suspend", "suspend") is True


def test_no_cooldown_for_shutdown_startup():
    """Shutdown / startup have NO cooldown (legitimate reboot loops must always notify)."""
    from app.services.notifications import events as events_mod
    events_mod._cooldown_cache.clear()

    # Even after setting cooldown, _check_cooldown returns False because there's
    # no entry in _COOLDOWN_SECONDS for these.
    events_mod._set_cooldown("lifecycle.shutdown")
    events_mod._set_cooldown("lifecycle.startup")
    assert events_mod._check_cooldown("lifecycle.shutdown") is False
    assert events_mod._check_cooldown("lifecycle.startup") is False
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_lifecycle_notifications.py::test_cooldown_60s_for_suspend tests/test_lifecycle_notifications.py::test_no_cooldown_for_shutdown_startup -v`
Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_lifecycle_notifications.py
git commit -m "test(notifications): cover lifecycle cooldown configuration"
```

---

## Task 10: Final verification — full test suite + manual smoketest

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: All previously-passing tests still pass + the new lifecycle tests pass. Zero new failures.

- [ ] **Step 2: Start dev server**

Run (in a separate terminal): `python start_dev.py`
Wait until log line `Application startup complete` appears.

- [ ] **Step 3: Verify startup emit fired**

Open `http://localhost:3001/api/notifications` (logged-in admin) — confirm a `lifecycle.startup` notification appears with title "NAS hochgefahren".

Or via DB:
```bash
cd backend && python -c "from app.core.database import SessionLocal; from app.models import SystemLifecycleEvent; \
  db = SessionLocal(); \
  print(list((e.event_type, e.timestamp, e.trigger) for e in db.query(SystemLifecycleEvent).all())); \
  db.close()"
```
Expected: At least one row with `event_type='startup'`.

- [ ] **Step 4: Trigger a manual suspend**

POST to `/api/sleep/suspend` (via Swagger UI at `http://localhost:3001/docs` or curl with admin token).
Expected: New row `event_type='suspend'` appears, plus a `lifecycle.suspend` notification. Dev backend then immediately "wakes" and a `lifecycle.resume` notification appears with `duration_human` set.

- [ ] **Step 5: Trigger a graceful shutdown**

POST to `/api/system/shutdown`.
Expected: `event_type='shutdown'` row appears, push notification "NAS wird heruntergefahren" sent before process exits.

- [ ] **Step 6: Restart dev server**

Run: `python start_dev.py` again.
Expected: New `event_type='startup'` row, push notification "NAS hochgefahren. Letzter Shutdown vor Xs" with realistic downtime.

- [ ] **Step 7: Verify mobile push reception (if Firebase configured)**

If a paired mobile device exists: confirm the four push notifications arrived during steps 3-6. If Firebase is not configured in dev, skip — in-app notifications above are sufficient evidence.

- [ ] **Step 8: Final commit (if any cleanup needed)**

If steps 1-7 surfaced bugs, fix and commit. Otherwise no commit needed for verification.

---

## Done

Feature complete. The four lifecycle notifications (Suspend / Resume / Shutdown / Startup) now fire via the existing `EventEmitter`, recipients honor the new `lifecycle` notification category, and downtime context is computed from the persistent `system_lifecycle_events` table.
