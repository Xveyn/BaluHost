"""Desktop (display-power) control backends.

A dev backend with in-memory state and a linux backend that toggles the
display outputs via KWin's ``kscreen-doctor --dpms on|off``.

Why DPMS and not ``systemctl stop sddm``: physically stopping the display
manager is counterproductive for GPU power on multi-output AMD systems. When
sddm stops, the kernel framebuffer console lights *all* connected outputs at
once, which pins the dGPU VRAM clock at maximum (measured ~78W idle on an
RX 7900 XTX). Turning the outputs off via DPMS instead keeps the KWin session
running but sets the DRM connectors to disabled (display_count -> 0), so the
dGPU can deep-idle (measured ~18W). See tests/test_desktop_backend.py and
docs/superpowers/plans/2026-05-30-desktop-toggle.md.
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional, Protocol, Tuple

from app.schemas.desktop import DesktopState, DesktopStatus
from app.services.power.gpu.display_detector import get_active_display_count


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
        return True, "Displays on (dev)"

    async def disable(self) -> Tuple[bool, str]:
        self._running = False
        return True, "Displays off (dev)"


class LinuxDesktopBackend:
    """Toggles display power via KWin DPMS (kscreen-doctor); keeps sddm/KWin up.

    ``disable()`` turns the outputs off (``--dpms off``) so the dGPU can idle;
    ``enable()`` turns them back on. ``get_status()`` reports RUNNING while at
    least one DRM connector is active, STOPPED when all outputs are off.
    """

    def __init__(self, unit: str = "sddm.service", uid: Optional[int] = None) -> None:
        self._unit = unit
        self._uid = uid if uid is not None else os.getuid()

    def _session_env(self) -> dict:
        """Env so kscreen-doctor can reach the user's Wayland session.

        The backend runs as the session user (uid match) but outside the
        graphical session, so XDG_RUNTIME_DIR/WAYLAND_DISPLAY must be set.
        """
        env = dict(os.environ)
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{self._uid}")
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")
        return env

    def _run(self, cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=self._session_env()
        )

    async def get_status(self) -> DesktopStatus:
        name = self._unit.removesuffix(".service")
        try:
            count = await get_active_display_count()
        except Exception as exc:  # pragma: no cover - defensive
            return DesktopStatus(state=DesktopState.UNKNOWN, display_manager=name, detail=str(exc))
        if count > 0:
            return DesktopStatus(
                state=DesktopState.RUNNING, display_manager=name,
                detail=f"{count} active display(s)",
            )
        return DesktopStatus(state=DesktopState.STOPPED, display_manager=name, detail="displays off")

    async def enable(self) -> Tuple[bool, str]:
        return self._exec(["kscreen-doctor", "--dpms", "on"])

    async def disable(self) -> Tuple[bool, str]:
        return self._exec(["kscreen-doctor", "--dpms", "off"])

    def _exec(self, cmd: list[str]) -> Tuple[bool, str]:
        try:
            result = self._run(cmd)
        except subprocess.TimeoutExpired:
            return False, f"{' '.join(cmd)} timed out"
        except FileNotFoundError:
            return False, "kscreen-doctor not found (is the desktop session running?)"
        if result.returncode == 0:
            return True, (result.stdout or "").strip() or "ok"
        return False, (result.stderr or "").strip() or f"exit {result.returncode}"
