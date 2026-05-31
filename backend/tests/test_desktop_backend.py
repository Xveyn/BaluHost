from app.schemas.desktop import DesktopState, DesktopStatus


def test_desktop_state_enum_values():
    assert DesktopState.RUNNING.value == "running"
    assert DesktopState.STOPPED.value == "stopped"
    assert DesktopState.UNKNOWN.value == "unknown"


def test_desktop_status_defaults():
    s = DesktopStatus(state=DesktopState.RUNNING, display_manager="sddm")
    assert s.state is DesktopState.RUNNING
    assert s.display_manager == "sddm"
    assert s.detail is None


import asyncio
from unittest.mock import patch, MagicMock

from app.services.power.desktop_backend import (
    DevDesktopBackend,
    LinuxDesktopBackend,
)


def _completed(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_dev_backend_toggles_in_memory():
    b = DevDesktopBackend()
    assert asyncio.run(b.get_status()).state is DesktopState.RUNNING
    ok, _ = asyncio.run(b.disable())
    assert ok
    assert asyncio.run(b.get_status()).state is DesktopState.STOPPED
    ok, _ = asyncio.run(b.enable())
    assert ok
    assert asyncio.run(b.get_status()).state is DesktopState.RUNNING


def test_linux_status_active_maps_running():
    b = LinuxDesktopBackend(unit="sddm.service")
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=0, stdout="active\n")) as run:
        status = asyncio.run(b.get_status())
    assert status.state is DesktopState.RUNNING
    run.assert_called_once_with(
        ["systemctl", "is-active", "sddm.service"],
        capture_output=True, text=True, timeout=30,
    )


def test_linux_status_inactive_maps_stopped():
    b = LinuxDesktopBackend(unit="sddm.service")
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=3, stdout="inactive\n")):
        status = asyncio.run(b.get_status())
    assert status.state is DesktopState.STOPPED


def test_linux_disable_calls_sudo_systemctl_stop():
    b = LinuxDesktopBackend(unit="sddm.service")
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=0, stdout="")) as run:
        ok, _ = asyncio.run(b.disable())
    assert ok
    run.assert_called_once_with(
        ["sudo", "systemctl", "stop", "sddm.service"],
        capture_output=True, text=True, timeout=30,
    )


def test_linux_enable_calls_sudo_systemctl_start():
    b = LinuxDesktopBackend(unit="sddm.service")
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=0, stdout="")) as run:
        ok, _ = asyncio.run(b.enable())
    assert ok
    run.assert_called_once_with(
        ["sudo", "systemctl", "start", "sddm.service"],
        capture_output=True, text=True, timeout=30,
    )


def test_linux_disable_failure_returns_false_with_stderr():
    b = LinuxDesktopBackend(unit="sddm.service")
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=1, stdout="", stderr="boom")):
        ok, msg = asyncio.run(b.disable())
    assert ok is False
    assert "boom" in msg
