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
