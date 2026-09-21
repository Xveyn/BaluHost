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


def test_tooltip_tells_the_two_greys_apart():
    """Grau hat zwei Ursachen und zwei verschiedene Handlungen: warten oder
    neu koppeln. Die Desktop-Meldung ist nach Sekunden weg, der Tooltip ist
    die einzige dauerhafte Erklaerung — also muss er den Unterschied sagen."""
    unreachable = TrayState()
    unreachable.set_connected(False)

    revoked = TrayState()
    revoked.set_connected(False)
    revoked.set_paired(False)

    assert unreachable.tooltip() != revoked.tooltip()
    assert "nicht erreichbar" in unreachable.tooltip()
    assert "gekoppelt" in revoked.tooltip()
    assert "--pair" in revoked.tooltip(), "der Tooltip muss die Handlung nennen"


def test_unpaired_is_grey_like_unreachable():
    """Nur der Text unterscheidet sich, die Farbe nicht — ein fuenfter
    Icon-Zustand traegt keine Information, die eine Farbe halten kann."""
    state = TrayState()
    state.set_connected(False)
    state.set_paired(False)
    assert state.icon_state() == IconState.OFFLINE

    # Auch wenn ein Aufrufer das passende set_connected(False) vergisst.
    stale = TrayState()
    stale.set_connected(True)
    stale.set_paired(False)
    stale.apply_snapshot([(1, "critical")])
    assert stale.icon_state() == IconState.OFFLINE


def test_a_fresh_state_counts_as_paired():
    """Der Tray startet nur mit Token — ohne sie kommt main gar nicht hierher."""
    assert TrayState().paired is True


from baluhost_tray.state import PendingPopup, PopupQueue


def _popup(n: int) -> PendingPopup:
    return PendingPopup(notification_id=n, title=f"Titel {n}", message=f"Text {n}")


def test_queue_starts_empty():
    assert PopupQueue().is_empty()


def test_release_returns_and_clears():
    queue = PopupQueue()
    queue.hold(_popup(1))
    queue.hold(_popup(2))
    released, summary = queue.release()
    assert [p.notification_id for p in released] == [1, 2]
    assert queue.is_empty()


def test_below_threshold_no_summary():
    queue = PopupQueue()
    for n in (1, 2, 3):
        queue.hold(_popup(n))
    released, summary = queue.release()
    assert summary is None


def test_at_threshold_summarises():
    queue = PopupQueue()
    for n in (1, 2, 3, 4):
        queue.hold(_popup(n))
    released, summary = queue.release()
    assert summary is not None
    title, message = summary
    assert "4" in title or "4" in message


def test_same_notification_held_once():
    """Ein Reconnect darf dieselbe Meldung nicht doppelt zustellen."""
    queue = PopupQueue()
    queue.hold(_popup(1))
    queue.hold(_popup(1))
    released, _ = queue.release()
    assert len(released) == 1


def test_deduplication_keeps_first_entry():
    """Bei Entdopplung wird der erste Eintrag behalten, nicht der letzte."""
    queue = PopupQueue()
    first = PendingPopup(notification_id=1, title="Erster", message="Text 1")
    second = PendingPopup(notification_id=1, title="Zweiter", message="Text 2")
    queue.hold(first)
    queue.hold(second)
    released, _ = queue.release()
    assert len(released) == 1
    assert released[0].title == "Erster"


def test_second_release_empty():
    """Ein zweites release() direkt danach liefert leere Liste und None."""
    queue = PopupQueue()
    queue.hold(_popup(1))
    queue.release()
    released, summary = queue.release()
    assert released == []
    assert summary is None
