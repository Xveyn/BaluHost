"""RAID tool detection must not depend on the caller's PATH (#605).

mdadm and mkfs.* live in /usr/sbin. systemd's PATH for the service contains
it, an interactive user shell on Debian usually does not. With a plain
shutil.which() the same box answered "RAID not available" from a diagnostic
shell while the service used mdadm fine. sudo resolves mdadm through its own
secure_path, so execution was never the problem for mdadm - but mkfs.* runs
without sudo, so there the lookup result has to be what gets executed.
"""
from __future__ import annotations

import os
import platform
import stat
from unittest import mock

import pytest

from app.schemas.system import FormatDiskRequest
from app.services.hardware.raid import mdadm_backend
from app.services.hardware.raid.mdadm_backend import MdadmRaidBackend, _which_system


def _install_tool(directory, name: str) -> str:
    """Create an executable stub that shutil.which() accepts on this OS."""
    filename = f"{name}.exe" if os.name == "nt" else name
    path = directory / filename
    path.write_text("")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def _same_file(found, expected: str) -> bool:
    """Windows' which() appends the PATHEXT suffix upper-cased (.EXE)."""
    return found is not None and os.path.normcase(found) == os.path.normcase(expected)


@pytest.fixture
def sbin_only(tmp_path, monkeypatch):
    """A fake /usr/sbin that is NOT on PATH; PATH points somewhere empty."""
    sbin = tmp_path / "sbin"
    sbin.mkdir()
    empty = tmp_path / "bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(mdadm_backend, "_SYSTEM_SBIN_DIRS", (str(sbin),))
    return sbin


def test_which_system_finds_a_tool_that_is_only_in_sbin(sbin_only):
    expected = _install_tool(sbin_only, "mdadm")

    assert _same_file(_which_system("mdadm"), expected)


def test_which_system_still_honours_the_callers_path(tmp_path, monkeypatch):
    on_path = tmp_path / "custom"
    on_path.mkdir()
    expected = _install_tool(on_path, "mdadm")
    monkeypatch.setenv("PATH", str(on_path))
    monkeypatch.setattr(mdadm_backend, "_SYSTEM_SBIN_DIRS", ())

    assert _same_file(_which_system("mdadm"), expected)


def test_which_system_returns_none_when_the_tool_is_nowhere(sbin_only):
    assert _which_system("mdadm") is None


def test_is_supported_does_not_depend_on_the_callers_path(sbin_only):
    _install_tool(sbin_only, "mdadm")

    with mock.patch.object(platform, "system", return_value="Linux"):
        assert MdadmRaidBackend.is_supported() is True


def test_is_supported_is_false_when_mdadm_is_really_missing(sbin_only):
    with mock.patch.object(platform, "system", return_value="Linux"):
        assert MdadmRaidBackend.is_supported() is False


def test_format_disk_executes_the_mkfs_it_found(sbin_only):
    """mkfs runs without sudo, so the found absolute path must be argv[0] -
    otherwise detection says yes and execution fails with FileNotFoundError."""
    mkfs = _install_tool(sbin_only, "mkfs.ext4")
    backend = MdadmRaidBackend.__new__(MdadmRaidBackend)  # skip the mdadm check

    with mock.patch.object(backend, "_get_os_disk_name", return_value="nvme0n1"), \
         mock.patch.object(backend, "_normalize_device", return_value="/dev/sdb"), \
         mock.patch.object(backend, "_run") as mock_run:
        backend.format_disk(FormatDiskRequest(disk="sdb", filesystem="ext4"))

    assert _same_file(mock_run.call_args.args[0][0], mkfs)
