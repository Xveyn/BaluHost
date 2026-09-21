"""Tests for the tray state machine — the icon colour is derived here."""

import pytest

from baluhost_tray.state import IconState, TrayState


@pytest.mark.parametrize(
    "connected,unread,expected",
    [
        (False, [], IconState.OFFLINE),
        (False, [(1, "critical")], IconState.OFFLINE),
        (True, [], IconState.OK),
        (True, [(1, "info")], IconState.OK),
        (True, [(1, "warning")], IconState.WARNING),
        (True, [(1, "critical")], IconState.CRITICAL),
        (True, [(1, "warning"), (2, "critical")], IconState.CRITICAL),
        (True, [(1, "critical"), (2, "warning")], IconState.CRITICAL),
    ],
)
def test_icon_state(connected, unread, expected):
    state = TrayState()
    state.set_connected(connected)
    state.apply_snapshot(unread)
    assert state.icon_state() == expected


def test_snapshot_replaces_previous_content():
    """Nach einer Offline-Phase ist der Snapshot die Wahrheit, kein Merge."""
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.apply_snapshot([(2, "warning")])
    assert state.icon_state() == IconState.WARNING


def test_snapshot_brings_back_an_expired_snooze():
    """Gesnoozte Meldungen filtert der Server heraus und spaeter wieder ein.
    Der periodische Neuabgleich ist der einzige Weg zurueck auf rot."""
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.remove([1])                       # gesnoozt
    assert state.icon_state() == IconState.OK
    state.apply_snapshot([(1, "critical")])  # Frist abgelaufen
    assert state.icon_state() == IconState.CRITICAL


def test_remove_clears_colour():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.remove([1])
    assert state.icon_state() == IconState.OK


def test_remove_unknown_id_is_harmless():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical")])
    state.remove([99])
    assert state.icon_state() == IconState.CRITICAL


def test_add_upgrades_colour():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "warning")])
    state.add(2, "critical")
    assert state.icon_state() == IconState.CRITICAL


def test_unknown_type_does_not_colour():
    """Ein neuer Typ im Backend darf das Icon nicht auf rot raten."""
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "moonphase")])
    assert state.icon_state() == IconState.OK


def test_tooltip_counts_unread_without_promising_health():
    state = TrayState()
    state.set_connected(True)
    state.apply_snapshot([(1, "critical"), (2, "warning")])
    assert "2" in state.tooltip()

    state.apply_snapshot([])
    assert state.tooltip() == "BaluHost — nichts Ungelesenes"


def test_tooltip_says_offline_when_disconnected():
    state = TrayState()
    state.set_connected(False)
    assert "erreichbar" in state.tooltip()


from baluhost_tray.state import PendingPopup, PopupQueue


def _popup(n: int) -> PendingPopup:
    return PendingPopup(notification_id=n, title=f"Titel {n}", message=f"Text {n}")


def test_queue_starts_empty():
    assert PopupQueue().is_empty()


def test_release_returns_and_clears():
    queue = PopupQueue()
    queue.hold(_popup(1))
    queue.hold(_popup(2))
    released = queue.release()
    assert [p.notification_id for p in released] == [1, 2]
    assert queue.is_empty()


def test_below_threshold_no_summary():
    queue = PopupQueue()
    for n in (1, 2, 3):
        queue.hold(_popup(n))
    assert queue.summary() is None


def test_at_threshold_summarises():
    queue = PopupQueue()
    for n in (1, 2, 3, 4):
        queue.hold(_popup(n))
    title, message = queue.summary()
    assert "4" in title or "4" in message


def test_same_notification_held_once():
    """Ein Reconnect darf dieselbe Meldung nicht doppelt zustellen."""
    queue = PopupQueue()
    queue.hold(_popup(1))
    queue.hold(_popup(1))
    assert len(queue.release()) == 1
