"""Pfad-Jail des optical_drive-Plugins (CodeQL py/path-injection).

Normale Nutzer duerfen nur dorthin lesen und schreiben, wohin der Dateimanager
sie auch laesst. Getestet wird die Uebersetzung absolut -> NAS-relativ -> Jail.
"""
import os

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.plugins.installed.optical_drive.paths import jail_user_path


class _User:
    def __init__(self, user_id: int, username: str, role: str):
        self.id = user_id
        self.username = username
        self.role = role


ALICE = _User(2, "alice", "user")
ADMIN = _User(1, "admin", "admin")


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    (root / "alice").mkdir(parents=True)
    (root / "bob").mkdir()
    (root / "Shared").mkdir()
    monkeypatch.setattr(settings, "nas_storage_path", str(root))
    return root


def _status(call) -> int:
    with pytest.raises(HTTPException) as exc:
        call()
    return exc.value.status_code


class TestNormalUser:
    def test_own_home_is_allowed(self, storage):
        target = storage / "alice" / "rips" / "disc.iso"
        assert jail_user_path(str(target), ALICE, None, write=True) == str(target)

    def test_shared_is_allowed(self, storage):
        target = storage / "Shared" / "disc.iso"
        assert jail_user_path(str(target), ALICE, None, write=True) == str(target)

    def test_foreign_home_is_denied(self, storage):
        assert _status(
            lambda: jail_user_path(str(storage / "bob" / "x.iso"), ALICE, None, write=True)
        ) == 403

    def test_foreign_home_is_denied_for_reading_too(self, storage):
        assert _status(
            lambda: jail_user_path(str(storage / "bob" / "x.iso"), ALICE, None, write=False)
        ) == 403

    def test_storage_root_is_denied(self, storage):
        assert _status(lambda: jail_user_path(str(storage), ALICE, None, write=True)) == 403

    def test_traversal_out_of_home_is_denied(self, storage):
        sneaky = f"{storage}/alice/../bob/x.iso"
        assert _status(lambda: jail_user_path(sneaky, ALICE, None, write=True)) == 403

    def test_sibling_with_same_prefix_is_denied(self, storage):
        evil = storage.parent / "storage-evil" / "alice" / "x.iso"
        assert _status(lambda: jail_user_path(str(evil), ALICE, None, write=True)) == 403

    def test_symlink_pointing_out_of_home_is_denied(self, storage, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        os.symlink(outside, storage / "alice" / "link")
        target = storage / "alice" / "link" / "x.iso"
        assert _status(lambda: jail_user_path(str(target), ALICE, None, write=True)) == 403

    def test_symlink_into_foreign_home_is_denied(self, storage):
        os.symlink(storage / "bob", storage / "alice" / "peek")
        target = storage / "alice" / "peek" / "x.iso"
        assert _status(lambda: jail_user_path(str(target), ALICE, None, write=False)) == 403

    def test_backup_path_is_denied(self, storage, tmp_path, monkeypatch):
        backups = tmp_path / "backups"
        backups.mkdir()
        monkeypatch.setattr(settings, "nas_backup_path", str(backups))
        assert _status(
            lambda: jail_user_path(str(backups / "x.iso"), ALICE, None, write=False)
        ) == 403

    def test_relative_path_is_rejected(self, storage):
        assert _status(lambda: jail_user_path("alice/x.iso", ALICE, None, write=True)) == 400

    def test_shared_with_me_is_not_a_write_target(self, storage):
        target = storage / "Shared with me"
        assert _status(lambda: jail_user_path(str(target), ALICE, None, write=True)) == 403


class TestAdmin:
    def test_admin_may_use_foreign_home(self, storage):
        target = storage / "bob" / "x.iso"
        assert jail_user_path(str(target), ADMIN, None, write=True) == str(target)

    def test_admin_keeps_backup_path(self, storage, tmp_path, monkeypatch):
        backups = tmp_path / "backups"
        backups.mkdir()
        monkeypatch.setattr(settings, "nas_backup_path", str(backups))
        target = backups / "x.iso"
        assert jail_user_path(str(target), ADMIN, None, write=False) == str(target)
