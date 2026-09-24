"""Primary-Wahl: der Local-Channel wird nie Primary (#710).

`_try_become_primary()` arbitriert ueber einen flock auf
/tmp/baluhost-primary.lock. `baluhost-backend.service` laeuft mit
PrivateTmp=yes, `baluhost-backend-local.service` nicht -- zwei /tmp, zwei
Lock-Inodes, zwei Primaries. Auf BaluNode fuhren damit ab dem 21.09. zwei
Fan-Regelkreise gegeneinander auf dieselben PWM-Kanaele, dazu doppelte
Power-, Sleep- und Reboot-Logik.

Der Lock ist dafuer das falsche Werkzeug: der Local-Channel ist ein
Zweitzugang fuer einen bereits angemeldeten Admin, nie Besitzer der
Hardware. Die Rolle haengt deshalb am Kanal, nicht am Wettlauf um die Datei.

Der Lock-Pfad wird in beiden Tests auf tmp_path umgebogen: auf einer Box, auf
der die Local-Unit laeuft, haelt sie den Host-Lock selbst, und der Test haenge
sonst davon ab, wer gerade gewonnen hat.
"""

import pytest

from app.core import lifespan


@pytest.fixture
def lock_in_tmp(tmp_path, monkeypatch):
    lock = tmp_path / "baluhost-primary.lock"
    monkeypatch.setattr(lifespan, "Path", lambda _p: lock)
    monkeypatch.delenv("BALUHOST_PRIMARY_WORKER", raising=False)
    monkeypatch.setattr(lifespan, "_primary_lock_fd", None)
    yield lock
    if lifespan._primary_lock_fd is not None:
        lifespan._primary_lock_fd.close()


def test_local_channel_never_becomes_primary(lock_in_tmp, monkeypatch):
    monkeypatch.setattr(lifespan.settings, "channel", "local")

    assert lifespan._try_become_primary() is False
    # Nicht einmal versucht: ein angelegter Lock hiesse, der Kanal haette
    # mitgeboten und nur zufaellig verloren.
    assert not lock_in_tmp.exists()
    assert lifespan._primary_lock_fd is None


def test_remote_channel_still_elects_via_lock(lock_in_tmp, monkeypatch):
    monkeypatch.setattr(lifespan.settings, "channel", "remote")

    assert lifespan._try_become_primary() is True
    assert lock_in_tmp.exists()
