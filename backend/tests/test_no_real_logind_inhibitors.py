"""The test suite must never take a real logind lock (#747).

`systemd-inhibit ... sleep infinity` is its own process: it outlives pytest,
gets adopted by the user manager and keeps blocking suspend on the machine the
tests ran on. The autouse guard in `conftest.py` refuses to start it at all.

The probes below use `--version`, which exits immediately and takes no lock —
so a missing guard makes these tests fail without leaving anything behind.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest


def test_popen_of_systemd_inhibit_is_refused(forbid_real_logind_inhibitors):
    attempts = forbid_real_logind_inhibitors

    with pytest.raises(AssertionError, match="systemd-inhibit"):
        subprocess.Popen(["/usr/bin/systemd-inhibit", "--version"])

    assert attempts == [["/usr/bin/systemd-inhibit", "--version"]]
    attempts.clear()  # deliberate attempt — don't let the teardown fail this test


def test_subprocess_run_of_systemd_inhibit_is_refused(forbid_real_logind_inhibitors):
    attempts = forbid_real_logind_inhibitors

    with pytest.raises(AssertionError, match="systemd-inhibit"):
        subprocess.run(["systemd-inhibit", "--version"], capture_output=True)

    assert len(attempts) == 1
    attempts.clear()


async def test_asyncio_subprocess_of_systemd_inhibit_is_refused(
    forbid_real_logind_inhibitors,
):
    attempts = forbid_real_logind_inhibitors

    with pytest.raises(AssertionError, match="systemd-inhibit"):
        await asyncio.create_subprocess_exec("systemd-inhibit", "--version")

    assert len(attempts) == 1
    attempts.clear()


def test_executable_keyword_is_checked_too(forbid_real_logind_inhibitors):
    """`Popen(["x"], executable=...)` runs the executable, whatever argv[0] says."""
    attempts = forbid_real_logind_inhibitors

    with pytest.raises(AssertionError, match="systemd-inhibit"):
        subprocess.Popen(["harmless-name", "--version"], executable="/usr/bin/systemd-inhibit")

    assert len(attempts) == 1
    attempts.clear()


def test_string_command_is_checked_too(forbid_real_logind_inhibitors):
    attempts = forbid_real_logind_inhibitors

    with pytest.raises(AssertionError, match="systemd-inhibit"):
        subprocess.Popen("systemd-inhibit --version", shell=True)

    assert len(attempts) == 1
    attempts.clear()


def test_guard_survives_a_monkeypatch_undo(forbid_real_logind_inhibitors, monkeypatch):
    """Some tests call `monkeypatch.undo()` mid-test. The guard must not hang
    on the test's own monkeypatch — it holds for the whole session."""
    attempts = forbid_real_logind_inhibitors
    monkeypatch.undo()

    with pytest.raises(AssertionError, match="systemd-inhibit"):
        subprocess.Popen(["systemd-inhibit", "--version"])

    assert len(attempts) == 1
    attempts.clear()


def test_other_commands_still_run(forbid_real_logind_inhibitors):
    result = subprocess.run(
        [sys.executable, "-c", "print('systemd-inhibit')"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "systemd-inhibit"
    assert forbid_real_logind_inhibitors == []


def test_guard_keeps_popen_usable_as_a_mock_spec(forbid_real_logind_inhibitors):
    """Tests build `MagicMock(spec=subprocess.Popen)`; the guard must stay a class."""
    from unittest.mock import MagicMock

    proc = MagicMock(spec=subprocess.Popen)
    proc.poll.return_value = None

    assert proc.poll() is None
    assert isinstance(subprocess.Popen, type)
