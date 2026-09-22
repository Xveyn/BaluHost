"""Connection announcements and quiet mode."""

from baluhost_tray.announce import (
    RECONNECT_ANNOUNCE_AFTER,
    ConnectionAnnouncer,
    QuietMode,
)


def test_offline_announced_once():
    announcer = ConnectionAnnouncer()
    assert announcer.went_offline(now=100.0) is not None
    assert announcer.went_offline(now=160.0) is None, "kein Piepen im Minutentakt"


def test_short_outage_is_not_announced_on_return():
    announcer = ConnectionAnnouncer()
    announcer.went_offline(now=100.0)
    assert announcer.came_online(now=100.0 + RECONNECT_ANNOUNCE_AFTER - 1) is None


def test_long_outage_is_announced_on_return():
    announcer = ConnectionAnnouncer()
    announcer.went_offline(now=100.0)
    assert announcer.came_online(now=100.0 + RECONNECT_ANNOUNCE_AFTER + 1) is not None


def test_offline_can_be_announced_again_after_a_return():
    announcer = ConnectionAnnouncer()
    announcer.went_offline(now=100.0)
    announcer.came_online(now=500.0)
    assert announcer.went_offline(now=600.0) is not None


def test_return_without_prior_outage_is_silent():
    """Der erste Verbindungsaufbau beim Start ist keine Rueckkehr."""
    assert ConnectionAnnouncer().came_online(now=100.0) is None


def test_short_flap_does_not_reannounce_the_loss():
    """Ein kurzer Flatterer darf den Verlust nicht ein zweites Mal melden.

    came_online() setzt _announced zurueck, auch wenn es selbst stumm bleibt
    -- eine kurze Verbindungsphase (Handshake + Snapshot reichen) darf den
    zweiten Verlust trotzdem nicht erneut melden, sonst entsteht genau der
    Popup-Strom, den went_offline() verhindern soll.
    """
    announcer = ConnectionAnnouncer()
    assert announcer.went_offline(now=100.0) is not None
    assert announcer.came_online(now=150.0) is None, "Ausfall war zu kurz fuer eine Rueckkehr-Meldung"
    assert announcer.went_offline(now=160.0) is None, "60s seit der letzten Meldung -- noch kein Strom-Fenster vorbei"


def test_loss_announced_again_after_the_threshold_since_last_announcement():
    """Nach Ablauf der Rueckmeldeschwelle seit der letzten Meldung darf ein
    neuer Verlust wieder gemeldet werden -- sonst wird aus dem Strom-Schutz
    dauerhaftes Schweigen.
    """
    announcer = ConnectionAnnouncer()
    announcer.went_offline(now=100.0)
    announcer.came_online(now=150.0)  # kurzer Flatterer, bleibt stumm
    later = 100.0 + RECONNECT_ANNOUNCE_AFTER + 1
    assert announcer.went_offline(now=later) is not None


def test_quiet_mode_expires():
    quiet = QuietMode()
    quiet.mute_for(3600.0, now=1000.0)
    assert quiet.is_muted(now=1000.0 + 3599)
    assert not quiet.is_muted(now=1000.0 + 3601)


def test_quiet_mode_off_by_default():
    assert not QuietMode().is_muted(now=1000.0)


def test_quiet_mode_can_be_cleared():
    quiet = QuietMode()
    quiet.mute_for(3600.0, now=1000.0)
    quiet.clear()
    assert not quiet.is_muted(now=1001.0)
