"""Tests for the tray's websocket watcher — ordering, snapshot, backoff."""

from unittest.mock import MagicMock

from baluhost_tray.state import IconState, TrayState
from baluhost_tray.watch import Watcher, backoff_delays


def test_backoff_stays_in_its_jitter_window():
    """Jeder Wert liegt im Fenster seines gedeckelten Exponentials.

    Bewusst keine Monotonie-Zusage: sobald der Deckel greift, stammen die
    letzten Werte aus demselben Intervall und sind nur zufaellig aufsteigend —
    ein Monotonie-Test waere in rund der Haelfte der Laeufe rot.
    """
    delays = backoff_delays(8, base=1.0, cap=60.0)
    assert len(delays) == 8
    for attempt, delay in enumerate(delays):
        ceiling = min(60.0, 1.0 * (2 ** attempt))
        assert ceiling * 0.5 <= delay <= ceiling, f"attempt {attempt}: {delay}"
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


def test_snapshot_transport_error_is_reported_not_raised():
    """Ein Transportfehler beim GET muss load_snapshot() nicht verlassen."""
    session = MagicMock()
    session.client.return_value.get.side_effect = OSError("connection refused")
    state = TrayState()
    state.set_connected(True)
    watcher = Watcher(session, state)
    assert watcher.load_snapshot() is False


def test_snapshot_malformed_body_is_reported_not_raised():
    """Eine 200-Antwort mit kaputtem Inhalt ist ein Fehlschlag, kein Absturz.

    Hier fehlt das 'id'-Feld -- derselbe Schutz deckt auch json(), das
    einen Fehler wirft."""
    watcher, _, _ = _watcher([
        {"notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
    ])
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


def test_frame_with_unusable_id_is_ignored_not_raised():
    """Ein kaputtes Feld darf keinen Reconnect kosten.

    Vorher warf int("abc") aus handle_frame heraus, run_cycle brach ab und
    run_loop baute die Verbindung neu auf — fuer ein einzelnes Feld.
    """
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": "abc", "notification_type": "critical",
                    "title": "SMART", "message": "Fehler"},
    })
    assert outcome.popups == []
    assert outcome.reload_needed is False
    assert state.unread_count() == 0


def test_numeric_string_id_still_counts():
    """Eine Ziffernfolge als String ist brauchbar — nur Unsinn nicht."""
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": "5", "notification_type": "critical",
                    "title": "SMART", "message": "Fehler"},
    })
    assert [p.notification_id for p in outcome.popups] == [5]
    assert state.icon_state() == IconState.CRITICAL


def test_state_frame_applies_the_usable_ids_and_drops_the_rest():
    """Was verstanden wurde, stimmt weiterhin — nur der Unsinn faellt weg."""
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
        {"id": 2, "notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
    ])
    watcher.load_snapshot()
    watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": [1, "kaputt"], "action": "read"},
    })
    assert state.unread_count() == 1        # 1 ist weg, 2 bleibt


def test_state_frame_with_unusable_ids_container_is_ignored():
    watcher, state, _ = _watcher([
        {"id": 1, "notification_type": "critical", "is_read": False,
         "title": "x", "message": "y"},
    ])
    watcher.load_snapshot()
    outcome = watcher.handle_frame({
        "type": "notification_state",
        "payload": {"ids": "1", "action": "read"},
    })
    assert outcome.reload_needed is False
    assert state.unread_count() == 1        # unveraendert, nichts geraten


def test_frame_with_non_dict_payload_is_ignored():
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({"type": "notification", "payload": [1, 2]})
    assert outcome.popups == []
    assert state.unread_count() == 0


def test_frame_without_id_is_ignored_like_a_broken_one():
    """Fehlendes und kaputtes id-Feld werden gleich behandelt.

    Vorher wurde bei fehlendem Feld stillschweigend Meldung 0 angewandt,
    waehrend "id": null den ganzen Frame verwarf — dieselbe Luecke, zwei
    verschiedene Ausgaenge.
    """
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"notification_type": "critical", "title": "x", "message": "y"},
    })
    assert outcome.popups == []
    assert state.unread_count() == 0


def test_frame_with_null_id_is_ignored():
    watcher, state, _ = _watcher([])
    outcome = watcher.handle_frame({
        "type": "notification",
        "payload": {"id": None, "notification_type": "critical",
                    "title": "x", "message": "y"},
    })
    assert outcome.popups == []
    assert state.unread_count() == 0
