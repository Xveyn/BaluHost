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
from unittest.mock import patch, MagicMock, AsyncMock

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


# --- A1: disable/enable drive display power off/on via KWin DPMS (kscreen-doctor),
#         not `systemctl stop sddm` (which lights fbcon on all outputs and pins the
#         dGPU VRAM clock at ~78W). KWin keeps running. ---

def test_linux_disable_calls_kscreen_dpms_off():
    b = LinuxDesktopBackend(uid=1000)
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=0, stdout="")) as run:
        ok, _ = asyncio.run(b.disable())
    assert ok
    assert run.call_args.args[0] == ["kscreen-doctor", "--dpms", "off"]
    env = run.call_args.kwargs["env"]
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert env["WAYLAND_DISPLAY"] == "wayland-0"


def test_linux_enable_calls_kscreen_dpms_on():
    b = LinuxDesktopBackend(uid=1000)
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=0, stdout="")) as run:
        ok, _ = asyncio.run(b.enable())
    assert ok
    assert run.call_args.args[0] == ["kscreen-doctor", "--dpms", "on"]


def test_linux_disable_failure_returns_false_with_stderr():
    b = LinuxDesktopBackend(uid=1000)
    with patch("app.services.power.desktop_backend.subprocess.run",
               return_value=_completed(returncode=1, stdout="", stderr="no compositor")):
        ok, msg = asyncio.run(b.disable())
    assert ok is False
    assert "no compositor" in msg


def test_linux_disable_missing_kscreen_returns_false():
    b = LinuxDesktopBackend(uid=1000)
    with patch("app.services.power.desktop_backend.subprocess.run",
               side_effect=FileNotFoundError()):
        ok, msg = asyncio.run(b.disable())
    assert ok is False
    assert "kscreen-doctor" in msg


# --- status reflects display power: any active display -> RUNNING, none -> STOPPED ---

def test_linux_status_displays_on_maps_running():
    b = LinuxDesktopBackend()
    with patch("app.services.power.desktop_backend.get_active_display_count",
               new=AsyncMock(return_value=1)):
        status = asyncio.run(b.get_status())
    assert status.state is DesktopState.RUNNING


def test_linux_status_no_displays_maps_stopped():
    b = LinuxDesktopBackend()
    with patch("app.services.power.desktop_backend.get_active_display_count",
               new=AsyncMock(return_value=0)):
        status = asyncio.run(b.get_status())
    assert status.state is DesktopState.STOPPED


def test_linux_status_error_maps_unknown():
    b = LinuxDesktopBackend()
    with patch("app.services.power.desktop_backend.get_active_display_count",
               new=AsyncMock(side_effect=OSError("boom"))):
        status = asyncio.run(b.get_status())
    assert status.state is DesktopState.UNKNOWN
