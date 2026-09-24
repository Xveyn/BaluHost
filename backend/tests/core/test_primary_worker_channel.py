"""The local-channel unit must never own the hardware loops.

Production runs two systemd units of the same app. baluhost-backend sets
PrivateTmp=true, baluhost-backend-local does not, so each unit sees a different
/tmp/baluhost-primary.lock and BOTH elected a primary worker — confirmed live
on 2026-09-23 (PID 1339281 and PID 1338770 both logged "Primary worker: True").
Fan control, the power manager, the SMART collector and mDNS all ran twice, and
so did the scheduled-reboot tick, which means two processes could independently
fire `systemctl reboot`.

Note for anyone reading a failure here: tests/conftest.py:31 sets
BALUHOST_CHANNEL=local for the whole suite, so after this change
_try_become_primary() returns False by default everywhere. The tests below that
need the production behaviour set settings.channel explicitly.
"""

from pathlib import Path

import pytest

from app.core import lifespan as lifespan_module


@pytest.fixture(autouse=True)
def _release_lock():
    yield
    fd = getattr(lifespan_module, "_primary_lock_fd", None)
    if fd is not None:
        fd.close()
        lifespan_module._primary_lock_fd = None


def test_local_channel_never_becomes_primary(monkeypatch, tmp_path):
    monkeypatch.setattr(lifespan_module.settings, "channel", "local")
    touched = tmp_path / "should-not-exist.lock"
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", touched)

    assert lifespan_module._try_become_primary() is False
    assert not touched.exists(), "the local channel must not even open the lock"


def test_remote_channel_still_wins_the_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(lifespan_module.settings, "channel", "remote")
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", tmp_path / "primary.lock")

    assert lifespan_module._try_become_primary() is True


def test_explicit_env_override_still_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(lifespan_module.settings, "channel", "remote")
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", tmp_path / "primary.lock")
    monkeypatch.setenv("BALUHOST_PRIMARY_WORKER", "0")

    assert lifespan_module._try_become_primary() is False


def test_second_remote_process_does_not_also_win(monkeypatch, tmp_path):
    """The flock behaviour that keeps one owner within a unit must survive."""
    import fcntl

    lock = tmp_path / "primary.lock"
    monkeypatch.setattr(lifespan_module.settings, "channel", "remote")
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", lock)

    holder = open(lock, "a")
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert lifespan_module._try_become_primary() is False
    finally:
        holder.close()
