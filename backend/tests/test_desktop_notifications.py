"""Tests for desktop disable/enable notifications."""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

import app.services.notifications.service as _notification_service_mod
from app.services.notifications.events import (
    EventEmitter,
    EVENT_CONFIGS,
    EventType,
    _COOLDOWN_SECONDS,
)


def test_desktop_event_configs_present():
    assert EventType.DESKTOP_DISABLED.value == "lifecycle.desktop_disabled"
    assert EventType.DESKTOP_ENABLED.value == "lifecycle.desktop_enabled"
    for et in (EventType.DESKTOP_DISABLED, EventType.DESKTOP_ENABLED):
        cfg = EVENT_CONFIGS[et]
        assert cfg.category == "lifecycle"
        assert cfg.priority == 1
        assert cfg.notification_type == "info"
        assert "{username}" in cfg.message_template
        assert cfg.action_url == "/admin/system-control?tab=sleep"


def test_desktop_event_cooldowns_present():
    assert _COOLDOWN_SECONDS["lifecycle.desktop_disabled"] == 30
    assert _COOLDOWN_SECONDS["lifecycle.desktop_enabled"] == 30


# ---------------------------------------------------------------------------
# Gate: any_admin_wants_desktop_event
# ---------------------------------------------------------------------------

def _emitter_with_db(db: MagicMock) -> EventEmitter:
    emitter = EventEmitter()
    emitter.set_db_session_factory(lambda: db)
    return emitter


def _db_with_admins(*ids: int) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [(i,) for i in ids]
    return db


def _svc_with_prefs(category_preferences):
    svc = MagicMock()
    prefs = MagicMock()
    prefs.category_preferences = category_preferences
    svc.get_user_preferences.return_value = prefs
    return svc


def test_gate_default_true_when_no_pref():
    db = _db_with_admins(1)
    emitter = _emitter_with_db(db)
    svc = _svc_with_prefs(None)
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc):
        assert emitter.any_admin_wants_desktop_event("disabled") is True
        assert emitter.any_admin_wants_desktop_event("enabled") is True


def test_gate_per_event_independent():
    db = _db_with_admins(1)
    emitter = _emitter_with_db(db)
    svc = _svc_with_prefs({"desktop_notifications": {"disabled": False, "enabled": True}})
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc):
        assert emitter.any_admin_wants_desktop_event("disabled") is False
        assert emitter.any_admin_wants_desktop_event("enabled") is True


def test_gate_false_when_no_admins():
    db = _db_with_admins()  # no admins
    emitter = _emitter_with_db(db)
    svc = _svc_with_prefs({"desktop_notifications": {"disabled": True}})
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc):
        assert emitter.any_admin_wants_desktop_event("disabled") is False


def test_gate_true_when_factory_missing():
    """No DB factory configured (e.g. early startup) -> do not suppress."""
    emitter = EventEmitter()  # no set_db_session_factory
    assert emitter.any_admin_wants_desktop_event("disabled") is True


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------

def test_emit_desktop_disabled_calls_emit_when_wanted():
    from app.services.notifications.events import emit_desktop_disabled_sync, get_event_emitter
    emitter = get_event_emitter()
    with patch.object(emitter, "any_admin_wants_desktop_event", return_value=True), \
         patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_desktop_disabled_sync("alice")
    mock_emit.assert_called_once()
    args, kwargs = mock_emit.call_args
    assert args[0] == EventType.DESKTOP_DISABLED
    assert kwargs.get("username") == "alice"
    assert kwargs.get("cooldown_entity") == "desktop"


def test_emit_desktop_enabled_calls_emit_when_wanted():
    from app.services.notifications.events import emit_desktop_enabled_sync, get_event_emitter
    emitter = get_event_emitter()
    with patch.object(emitter, "any_admin_wants_desktop_event", return_value=True), \
         patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_desktop_enabled_sync("bob")
    mock_emit.assert_called_once()
    args, kwargs = mock_emit.call_args
    assert args[0] == EventType.DESKTOP_ENABLED
    assert kwargs.get("username") == "bob"


def test_emit_desktop_disabled_suppressed_when_not_wanted():
    from app.services.notifications.events import emit_desktop_disabled_sync, get_event_emitter
    emitter = get_event_emitter()
    with patch.object(emitter, "any_admin_wants_desktop_event", return_value=False), \
         patch.object(emitter, "emit_for_admins_sync") as mock_emit:
        emit_desktop_disabled_sync("alice")
    mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

def test_cooldown_suppresses_second_disable_within_window():
    from app.services.notifications.events import _cooldown_cache
    _cooldown_cache.clear()
    db = _db_with_admins(1)
    notif = MagicMock()
    notif.id = 1
    emitter = _emitter_with_db(db)
    svc = MagicMock()
    svc.get_user_preferences.return_value = None
    svc._get_category_pref.return_value = {"error": True, "success": False, "mobile": False, "desktop": False}
    with patch.object(_notification_service_mod, "get_notification_service", lambda: svc), \
         patch("app.services.notifications.events.EventEmitter._send_push_sync"), \
         patch("app.models.notification.Notification", return_value=notif), \
         patch("app.services.notification_routing.get_routed_user_ids", return_value=[]):
        emitter.emit_for_admins_sync(EventType.DESKTOP_DISABLED, cooldown_entity="desktop", username="admin")
        emitter.emit_for_admins_sync(EventType.DESKTOP_DISABLED, cooldown_entity="desktop", username="admin")
    db.add.assert_called_once()  # second suppressed by 30s cooldown


# ---------------------------------------------------------------------------
# Route wiring (uses TestClient + admin auth)
# ---------------------------------------------------------------------------

from app.core.config import settings

_DISABLE_URL = f"{settings.api_prefix}/system/sleep/desktop/disable"
_ENABLE_URL = f"{settings.api_prefix}/system/sleep/desktop/enable"


def test_route_emits_on_disable_success(client, admin_headers):
    with patch("app.api.routes.desktop.emit_desktop_disabled", new=AsyncMock()) as m:
        r = client.post(_DISABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
    m.assert_awaited_once()
    assert m.await_args.args[0] == settings.admin_username


def test_route_emits_on_enable_success(client, admin_headers):
    with patch("app.api.routes.desktop.emit_desktop_enabled", new=AsyncMock()) as m:
        r = client.post(_ENABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
    m.assert_awaited_once()
    assert m.await_args.args[0] == settings.admin_username


def test_route_no_emit_on_disable_failure(client, admin_headers):
    svc = MagicMock()
    svc.disable = AsyncMock(return_value=(False, "boom"))
    with patch("app.api.routes.desktop.get_desktop_service", return_value=svc), \
         patch("app.api.routes.desktop.emit_desktop_disabled", new=AsyncMock()) as m:
        r = client.post(_DISABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is False
    m.assert_not_awaited()


def test_route_emit_failure_does_not_break_toggle(client, admin_headers):
    with patch("app.api.routes.desktop.emit_desktop_disabled",
               new=AsyncMock(side_effect=RuntimeError("push down"))):
        r = client.post(_DISABLE_URL, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["success"] is True
