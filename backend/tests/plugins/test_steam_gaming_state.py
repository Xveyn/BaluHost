"""The marker that remembers BaluHost put the box into gaming mode."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.installed.steam_gaming import gaming_state


@pytest.fixture
def storage(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(gaming_state.settings, "nas_storage_path", str(tmp_path))
    return tmp_path


class TestMarkerLocation:
    def test_lives_under_the_storage_systems_dir(self, storage):
        """Not /tmp: PrivateTmp makes that ephemeral per service start, and the
        four Uvicorn workers all have to see the same answer. .system/ survives
        a deploy (git reset --hard, no git clean)."""
        path = gaming_state.marker_path()

        assert path.parent.parent == storage / ".system"
        assert storage in path.parents


class TestMarkerLifecycle:
    def test_starts_out_inactive(self, storage):
        assert gaming_state.is_active() is False

    def test_start_then_end(self, storage):
        gaming_state.mark_started()
        assert gaming_state.is_active() is True

        gaming_state.mark_ended()
        assert gaming_state.is_active() is False

    def test_marking_started_twice_is_harmless(self, storage):
        gaming_state.mark_started()
        gaming_state.mark_started()

        assert gaming_state.is_active() is True

    def test_marking_ended_without_a_marker_is_harmless(self, storage):
        gaming_state.mark_ended()

        assert gaming_state.is_active() is False


class TestNothingHereBreaksTheMenu:
    """A storage hiccup must degrade to "offer the start action", never raise -
    this is read while building the power menu."""

    def test_unwritable_storage_does_not_raise(self, storage, monkeypatch):
        def _boom(*_args, **_kwargs):
            raise OSError("read-only file system")

        monkeypatch.setattr(Path, "mkdir", _boom)
        gaming_state.mark_started()

        assert gaming_state.is_active() is False

    def test_unreadable_marker_reads_as_inactive(self, storage, monkeypatch):
        gaming_state.mark_started()

        def _boom(*_args, **_kwargs):
            raise OSError("stale NFS handle")

        monkeypatch.setattr(Path, "exists", _boom)

        assert gaming_state.is_active() is False

    def test_failing_unlink_does_not_raise(self, storage, monkeypatch):
        gaming_state.mark_started()

        def _boom(*_args, **_kwargs):
            raise OSError("device busy")

        monkeypatch.setattr(Path, "unlink", _boom)
        gaming_state.mark_ended()  # must not raise
