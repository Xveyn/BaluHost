"""Unit tests for CoreUptimeInhibitor — the logind block-sleep wrapper."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.services.power.core_uptime_inhibitor import CoreUptimeInhibitor


def _alive_proc(pid: int = 4242) -> MagicMock:
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = pid
    proc.poll.return_value = None  # alive
    return proc


def _dead_proc(rc: int = 0) -> MagicMock:
    proc = MagicMock(spec=subprocess.Popen)
    proc.pid = 9999
    proc.poll.return_value = rc
    proc.returncode = rc
    return proc


def test_acquire_spawns_systemd_inhibit_with_correct_args():
    inh = CoreUptimeInhibitor()
    fake_proc = _alive_proc()

    with patch("app.services.power.core_uptime_inhibitor.shutil.which",
               return_value="/usr/bin/systemd-inhibit"), \
         patch("app.services.power.core_uptime_inhibitor.time.sleep"), \
         patch("app.services.power.core_uptime_inhibitor.subprocess.Popen",
               return_value=fake_proc) as mock_popen:
        ok = inh.acquire("test_reason")

    assert ok is True
    assert inh.is_held() is True
    args, _kwargs = mock_popen.call_args
    cmd = args[0]
    assert cmd[0] == "/usr/bin/systemd-inhibit"
    assert "--what=sleep" in cmd
    assert "--mode=block" in cmd
    assert "--who=BaluHost" in cmd
    assert "--why=test_reason" in cmd
    # Must hold the lock with a long-lived child so logind doesn't release it.
    assert cmd[-2:] == ["sleep", "infinity"]


def test_acquire_is_idempotent_when_already_held():
    inh = CoreUptimeInhibitor()
    inh._proc = _alive_proc()

    with patch("app.services.power.core_uptime_inhibitor.shutil.which",
               return_value="/usr/bin/systemd-inhibit"), \
         patch("app.services.power.core_uptime_inhibitor.subprocess.Popen") as mock_popen:
        ok = inh.acquire("again")

    assert ok is True
    mock_popen.assert_not_called()


def test_acquire_returns_false_when_binary_missing():
    inh = CoreUptimeInhibitor()
    with patch("app.services.power.core_uptime_inhibitor.shutil.which", return_value=None), \
         patch("app.services.power.core_uptime_inhibitor.subprocess.Popen") as mock_popen:
        ok = inh.acquire("dev")

    assert ok is False
    assert inh.is_held() is False
    mock_popen.assert_not_called()


def test_missing_binary_warning_emitted_once_only():
    inh = CoreUptimeInhibitor()
    with patch("app.services.power.core_uptime_inhibitor.shutil.which", return_value=None), \
         patch("app.services.power.core_uptime_inhibitor.logger.warning") as mock_warn:
        inh.acquire("first")
        inh.acquire("second")
        inh.acquire("third")

    assert mock_warn.call_count == 1


def test_acquire_re_acquires_after_subprocess_died():
    inh = CoreUptimeInhibitor()
    inh._proc = _dead_proc(rc=1)  # held a dead subprocess
    new_proc = _alive_proc(pid=5555)

    with patch("app.services.power.core_uptime_inhibitor.shutil.which",
               return_value="/usr/bin/systemd-inhibit"), \
         patch("app.services.power.core_uptime_inhibitor.time.sleep"), \
         patch("app.services.power.core_uptime_inhibitor.subprocess.Popen",
               return_value=new_proc) as mock_popen:
        ok = inh.acquire("recover")

    assert ok is True
    assert inh._proc is new_proc
    mock_popen.assert_called_once()


def test_release_terminates_running_subprocess():
    inh = CoreUptimeInhibitor()
    fake_proc = _alive_proc()
    inh._proc = fake_proc

    inh.release()

    fake_proc.terminate.assert_called_once()
    fake_proc.wait.assert_called_once_with(timeout=3.0)
    assert inh._proc is None
    assert inh.is_held() is False


def test_release_kills_when_terminate_times_out():
    inh = CoreUptimeInhibitor()
    fake_proc = _alive_proc()
    fake_proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="x", timeout=3.0), None]
    inh._proc = fake_proc

    inh.release()

    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_called_once()
    assert inh._proc is None


def test_release_is_idempotent_when_not_held():
    inh = CoreUptimeInhibitor()
    inh.release()  # never acquired
    assert inh._proc is None


def test_release_clears_handle_even_if_subprocess_already_exited():
    inh = CoreUptimeInhibitor()
    fake_proc = _dead_proc(rc=0)
    inh._proc = fake_proc

    inh.release()

    fake_proc.terminate.assert_not_called()
    assert inh._proc is None


def test_acquire_returns_false_when_popen_raises():
    inh = CoreUptimeInhibitor()
    with patch("app.services.power.core_uptime_inhibitor.shutil.which",
               return_value="/usr/bin/systemd-inhibit"), \
         patch("app.services.power.core_uptime_inhibitor.subprocess.Popen",
               side_effect=OSError("permission denied")):
        ok = inh.acquire("denied")

    assert ok is False
    assert inh.is_held() is False


def test_acquire_detects_immediate_polkit_denial():
    """If systemd-inhibit exits during the 0.2s settle window (polkit denied),
    acquire returns False and clears the handle so we don't pretend we're held."""
    inh = CoreUptimeInhibitor()
    # Process appears 'dead' immediately after spawn — simulates polkit denial.
    denied_proc = MagicMock(spec=subprocess.Popen)
    denied_proc.pid = 1234
    denied_proc.poll.return_value = 1  # exited
    denied_proc.returncode = 1
    denied_proc.stderr = MagicMock()
    denied_proc.stderr.read.return_value = b"Failed to inhibit: Access denied\n"

    with patch("app.services.power.core_uptime_inhibitor.shutil.which",
               return_value="/usr/bin/systemd-inhibit"), \
         patch("app.services.power.core_uptime_inhibitor.time.sleep"), \
         patch("app.services.power.core_uptime_inhibitor.subprocess.Popen",
               return_value=denied_proc):
        ok = inh.acquire("polkit_denied")

    assert ok is False
    assert inh._proc is None
    assert inh.is_held() is False
