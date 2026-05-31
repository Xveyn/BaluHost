"""Desktop (display-manager) control backends.

Mirrors the sleep backend pattern: a dev backend with in-memory state and a
linux backend that wraps `systemctl` for sddm.service.
"""
from __future__ import annotations

import subprocess
from typing import Protocol, Tuple

from app.schemas.desktop import DesktopState, DesktopStatus


class DesktopBackend(Protocol):
    async def get_status(self) -> DesktopStatus: ...
    async def enable(self) -> Tuple[bool, str]: ...
    async def disable(self) -> Tuple[bool, str]: ...


class DevDesktopBackend:
    """In-memory backend for dev mode / non-Linux hosts."""

    def __init__(self, unit: str = "sddm.service") -> None:
        self._unit = unit
        self._running = True

    async def get_status(self) -> DesktopStatus:
        state = DesktopState.RUNNING if self._running else DesktopState.STOPPED
        return DesktopStatus(
            state=state,
            display_manager=self._unit.removesuffix(".service"),
            detail="dev backend (in-memory)",
        )

    async def enable(self) -> Tuple[bool, str]:
        self._running = True
        return True, "Desktop started (dev)"

    async def disable(self) -> Tuple[bool, str]:
        self._running = False
        return True, "Desktop stopped (dev)"


class LinuxDesktopBackend:
    """Controls the display manager via systemctl."""

    def __init__(self, unit: str = "sddm.service") -> None:
        self._unit = unit

    def _run(self, cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    async def get_status(self) -> DesktopStatus:
        name = self._unit.removesuffix(".service")
        try:
            result = self._run(["systemctl", "is-active", self._unit])
        except subprocess.TimeoutExpired:
            return DesktopStatus(state=DesktopState.UNKNOWN, display_manager=name,
                                 detail="is-active timed out")
        out = (result.stdout or "").strip()
        if out == "active":
            state = DesktopState.RUNNING
        elif out in ("inactive", "failed", "deactivating", "activating"):
            state = DesktopState.STOPPED
        else:
            state = DesktopState.UNKNOWN
        return DesktopStatus(state=state, display_manager=name, detail=out or None)

    async def enable(self) -> Tuple[bool, str]:
        return self._exec(["sudo", "systemctl", "start", self._unit])

    async def disable(self) -> Tuple[bool, str]:
        return self._exec(["sudo", "systemctl", "stop", self._unit])

    def _exec(self, cmd: list[str]) -> Tuple[bool, str]:
        try:
            result = self._run(cmd)
        except subprocess.TimeoutExpired:
            return False, f"{' '.join(cmd)} timed out"
        if result.returncode == 0:
            return True, (result.stdout or "").strip() or "ok"
        return False, (result.stderr or "").strip() or f"exit {result.returncode}"
