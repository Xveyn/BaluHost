"""One tray per session — but pairing must stay possible alongside it."""

import pytest

from baluhost_tray import single_instance


@pytest.fixture(autouse=True)
def runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def test_first_acquire_succeeds():
    assert single_instance.acquire("test-tray") is not None


def test_second_acquire_refused():
    single_instance.acquire("test-tray-2")
    with pytest.raises(single_instance.AlreadyRunning):
        single_instance.acquire("test-tray-2")


def test_different_names_do_not_collide():
    """--pair laeuft neben dem Dienst, also braucht es einen eigenen Namen."""
    single_instance.acquire("test-tray-3")
    assert single_instance.acquire("test-tray-3-pair") is not None


def test_lock_file_lands_in_runtime_dir(runtime_dir):
    single_instance.acquire("test-tray-4")
    assert (runtime_dir / "test-tray-4.lock").exists()


def test_missing_runtime_dir_falls_back(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert single_instance.acquire("test-tray-fallback") is not None
