"""Integration tests for lifecycle notifications."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.notifications.events import (
    EventType,
    emit_system_resume_sync,
    emit_system_shutdown_sync,
    emit_system_startup_sync,
    emit_system_suspend_sync,
    get_event_emitter,
)


@pytest.fixture(autouse=True)
def reset_cooldowns():
    """Clear cooldown cache between tests."""
    from app.services.notifications import events as events_mod
    events_mod._cooldown_cache.clear()
    yield
    events_mod._cooldown_cache.clear()


@pytest.fixture(autouse=True)
def ensure_lifecycle_table():
    """Ensure system_lifecycle_events table exists in the production engine.

    Tests that exercise SessionLocal() directly (sleep.py and lifespan.py
    write through it) need the table to exist on the production engine,
    not the in-memory test DB. SKIP_APP_INIT=1 disables init_db, so we
    create the schema manually here and clean up after.
    """
    from app.core.database import engine
    from app.models.base import Base
    from app.models.system_lifecycle import SystemLifecycleEvent

    Base.metadata.create_all(bind=engine, tables=[SystemLifecycleEvent.__table__])
    # Clear any rows from prior tests
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        db.query(SystemLifecycleEvent).delete()
        db.commit()
    yield
    with SessionLocal() as db:
        db.query(SystemLifecycleEvent).delete()
        db.commit()


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


# ---------------------------------------------------------------------------
# Sleep.py: suspend + resume hooks
# ---------------------------------------------------------------------------


def test_suspend_persists_event_and_emits_before_kernel_suspend():
    """Order check: row inserted in system_lifecycle_events AND emit_system_suspend
    are both called BEFORE _backend.suspend_system()."""
    from app.schemas.sleep import SleepTrigger
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
    ), patch(
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


def test_suspend_emit_respects_3s_timeout():
    """If emit_system_suspend hangs > 3s, suspend continues anyway."""
    from app.schemas.sleep import SleepTrigger
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
        # 3s inner timeout + 2s DevBackend suspend simulation + overhead — give 10s outer.
        # The point: the slow emit (10s) must NOT stall the suspend; inner 3s timeout
        # must fire so the whole flow completes well before 10s.
        async def run():
            return await asyncio.wait_for(
                svc.enter_true_suspend("test", SleepTrigger.MANUAL),
                timeout=10.0,
            )

        result = asyncio.run(run())
        assert result is True
