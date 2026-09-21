"""Tests for the tray's websocket watcher — ordering, snapshot, backoff."""

from unittest.mock import MagicMock

import pytest

from baluhost_tray.state import IconState, TrayState
from baluhost_tray.watch import Watcher, backoff_delays


def test_backoff_grows_and_caps():
    delays = backoff_delays(8, base=1.0, cap=60.0)
    assert all(b >= a for a, b in zip(delays, delays[1:]))
    assert max(delays) <= 60.0


def test_backoff_has_jitter():
    """Ohne Jitter kommen nach einem Backend-Neustart alle Clients gleichzeitig."""
    assert backoff_delays(8) != backoff_delays(8)


def _watcher(unread: list[dict], status: int = 200):
    session = MagicMock()
    response = MagicMock()
    response.status_code = status
    response.json.return_value = {
        "notifications": unread,
        "unread_count": len(unread),
        "total": len(unread),
    }
    session.client.return_value.get.return_value = response
    state = TrayState()
    state.set_connected(True)
    return Watcher(session, state), state, session


def test_snapshot_asks_for_unread_only():
    watcher, _, session = _watcher([])
    watcher.load_snapshot()
    params = session.client.return_value.get.call_args[1]["params"]
    assert params["unread_only"] is True
    assert params["page_size"] == 100


def test_snapshot_fills_state():
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "RAID", "message": "degradiert"},
    ])
    assert watcher.load_snapshot() is True
    assert state.icon_state() == IconState.CRITICAL


def test_snapshot_failure_is_reported_not_swallowed():
    """429 darf nicht als 'verbunden, alles gut' durchgehen."""
    watcher, _, _ = _watcher([], status=429)
    assert watcher.load_snapshot() is False


def test_frame_after_snapshot_wins():
    """Ein 'gelesen', das nach dem Snapshot verarbeitet wird, gilt — die
    Reihenfolge selbst stellt run_cycle her (Task 17)."""
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "RAID", "message": "degradiert"},
    ])
    watcher.load_snapshot()
    watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": [1], "action": "read"},
    })
    assert state.icon_state() == IconState.OK


def test_new_critical_frame_yields_popup():
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": 5, "notification_type": "critical",
                    "title": "SMART", "message": "Platte meldet Fehler"},
    })
    assert [p.notification_id for p in outcome.popups] == [5]
    assert state.icon_state() == IconState.CRITICAL


def test_warning_frame_colours_without_popup():
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": 6, "notification_type": "warning",
                    "title": "Backup", "message": "uebersprungen"},
    })
    assert outcome.popups == []
    assert state.icon_state() == IconState.WARNING


def test_single_state_action_removes_the_ids():
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
    ])
    watcher.load_snapshot()
    watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": [1], "action": "dismissed"},
    })
    assert state.icon_state() == IconState.OK


def test_bulk_action_asks_for_reload_instead_of_clearing():
    """read_all kann einen Kategoriefilter getragen haben — leeren waere
    geraten, nachladen ist gewusst."""
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
    ])
    watcher.load_snapshot()
    outcome = watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": [], "action": "read_all"},
    })
    assert outcome.reload_needed is True
    assert state.icon_state() == IconState.CRITICAL  # unveraendert bis zum Neuabgleich


def test_unknown_frame_type_ignored():
    watcher, _, _ = _watcher([])
    outcome = watcher.handle_frame({"type": "pong", "payload": {}})
    assert outcome.popups == [] and outcome.reload_needed is False
