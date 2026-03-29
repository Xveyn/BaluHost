"""Tests for storage permission helpers."""
import os
import stat
import sys
from pathlib import Path

import pytest

from app.services.files.storage_permissions import (
    STORAGE_DIR_MODE,
    STORAGE_FILE_MODE,
    STORAGE_UMASK,
    set_storage_dir_permissions,
    set_storage_file_permissions,
    ensure_dir_with_permissions,
)

posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX permission bits (setgid, group write) not supported on Windows",
)


class TestConstants:
    def test_dir_mode_value(self):
        assert STORAGE_DIR_MODE == 0o2775

    def test_file_mode_value(self):
        assert STORAGE_FILE_MODE == 0o0664

    def test_umask_value(self):
        assert STORAGE_UMASK == 0o002


class TestSetStorageDirPermissions:
    @posix_only
    def test_sets_permissions_on_directory(self, tmp_path):
        d = tmp_path / "testdir"
        d.mkdir(mode=0o700)

        set_storage_dir_permissions(d)

        actual = stat.S_IMODE(d.stat().st_mode)
        assert actual == STORAGE_DIR_MODE

    def test_ignores_nonexistent_path(self, tmp_path):
        missing = tmp_path / "missing"
        # Should not raise
        set_storage_dir_permissions(missing)


class TestSetStorageFilePermissions:
    @posix_only
    def test_sets_permissions_on_file(self, tmp_path):
        f = tmp_path / "testfile.txt"
        f.write_text("hello")
        f.chmod(0o600)

        set_storage_file_permissions(f)

        actual = stat.S_IMODE(f.stat().st_mode)
        assert actual == STORAGE_FILE_MODE

    def test_ignores_nonexistent_path(self, tmp_path):
        missing = tmp_path / "missing.txt"
        set_storage_file_permissions(missing)


class TestEnsureDirWithPermissions:
    @posix_only
    def test_creates_dir_with_correct_permissions(self, tmp_path):
        d = tmp_path / "a" / "b" / "c"

        ensure_dir_with_permissions(d)

        assert d.is_dir()
        actual = stat.S_IMODE(d.stat().st_mode)
        assert actual == STORAGE_DIR_MODE

    @posix_only
    def test_existing_dir_gets_permissions_fixed(self, tmp_path):
        d = tmp_path / "existing"
        d.mkdir(mode=0o700)

        ensure_dir_with_permissions(d)

        actual = stat.S_IMODE(d.stat().st_mode)
        assert actual == STORAGE_DIR_MODE

    @posix_only
    def test_parent_dirs_also_get_permissions(self, tmp_path):
        d = tmp_path / "parent" / "child"

        ensure_dir_with_permissions(d)

        parent_mode = stat.S_IMODE((tmp_path / "parent").stat().st_mode)
        child_mode = stat.S_IMODE(d.stat().st_mode)
        assert parent_mode == STORAGE_DIR_MODE
        assert child_mode == STORAGE_DIR_MODE

    def test_creates_nested_directories(self, tmp_path):
        """Verify directory creation works on all platforms."""
        d = tmp_path / "x" / "y" / "z"

        ensure_dir_with_permissions(d)

        assert d.is_dir()
