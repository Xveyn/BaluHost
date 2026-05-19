"""
OS Auto-Suspend — bidirectional read/write of idle-suspend across power managers.

Detects the active session-level power manager (KDE PowerDevil / GNOME
gsd-power) or falls back to systemd-logind and dispatches read/write
through a common adapter protocol. Read-through architecture: no DB copy.

Helper script (root-required for logind) lives at
/usr/local/lib/baluhost/baluhost-write-logind-idle and is invoked via
sudo with a NOPASSWD entry installed by deploy/install/modules/13-power-helpers.sh.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

ActionLiteral = Literal["suspend", "hibernate", "ignore"]


@dataclass(frozen=True)
class AutoSuspendValue:
    """Normalised auto-suspend setting, identical shape across all backends."""
    enabled: bool
    timeout_minutes: int
    action: ActionLiteral


class OsAutoSuspendBackend(Protocol):
    """
    Structural interface for auto-suspend read/write adapters.

    Implementations live in this same module: KdeAdapter, GnomeAdapter,
    LogindAdapter. The active adapter is selected at request time by the
    detector based on which power manager is currently running.
    """
    name: Literal["kde", "gnome", "logind"]
    label: str

    def is_available(self) -> bool: ...
    def read(self) -> AutoSuspendValue: ...
    def write(self, value: AutoSuspendValue) -> None: ...


# ---------------------------------------------------------------------------
# logind constants (module-level for monkeypatching in tests)
# ---------------------------------------------------------------------------
_LOGIND_CONF = Path("/etc/systemd/logind.conf")
_LOGIND_DROPIN_DIRS: tuple[Path, ...] = (
    Path("/etc/systemd/logind.conf.d"),
    Path("/run/systemd/logind.conf.d"),
)
_HELPER_PATH = "/usr/local/lib/baluhost/baluhost-write-logind-idle"
_SUDO_TIMEOUT_SECONDS = 10.0


def _parse_login_ini(path: Path) -> dict[str, str]:
    """Reuse minimal logic from os_sleep_inspector for [Login] section."""
    from app.services.power.os_sleep_inspector import _parse_systemd_ini  # noqa: PLC0415
    return _parse_systemd_ini(path, section="Login")


def _merge_drop_ins(base: dict[str, str], drop_dir: Path) -> dict[str, str]:
    from app.services.power.os_sleep_inspector import _merge_drop_ins as _m  # noqa: PLC0415
    return _m(base, drop_dir, section="Login")


def _parse_idle_action_sec(raw: str) -> int:
    """Parse '15min', '900s', or '900' → minutes (int). Returns 0 on parse error or negative input."""
    s = raw.strip().lower()
    if not s:
        return 0
    try:
        if s.endswith("min"):
            value = int(s[:-3])
        elif s.endswith("s"):
            value = int(s[:-1]) // 60
        else:
            value = int(s) // 60
    except ValueError:
        return 0
    return value if value > 0 else 0


# ---------------------------------------------------------------------------
# LogindAdapter
# ---------------------------------------------------------------------------

class LogindAdapter:
    name = "logind"
    label = "systemd-logind"

    def is_available(self) -> bool:
        return Path("/etc/systemd").is_dir()

    def read(self) -> AutoSuspendValue:
        merged = _parse_login_ini(_LOGIND_CONF)
        for d in _LOGIND_DROPIN_DIRS:
            if d.is_dir():
                merged = _merge_drop_ins(merged, d)
        action = merged.get("IdleAction", "ignore").strip().lower()
        if action not in {"suspend", "hibernate", "ignore"}:
            logger.warning("logind IdleAction=%r unknown — treating as ignore", action)
            action = "ignore"
        timeout = _parse_idle_action_sec(merged.get("IdleActionSec", ""))
        enabled = action != "ignore" and timeout > 0
        return AutoSuspendValue(
            enabled=enabled,
            timeout_minutes=timeout if timeout > 0 else 15,
            action=action,  # type: ignore[arg-type]
        )

    def write(self, value: AutoSuspendValue) -> None:
        timeout_seconds = max(60, value.timeout_minutes * 60)
        action = value.action if value.enabled else "ignore"
        cmd = [
            "sudo", "-n", _HELPER_PATH,
            "--timeout", str(timeout_seconds),
            "--action", action,
        ]
        try:
            subprocess.run(
                cmd, check=True, capture_output=True, text=True,
                timeout=_SUDO_TIMEOUT_SECONDS,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"logind helper failed (rc={exc.returncode}): {exc.stderr}"
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(
                "logind helper not installed — rerun deploy/install/install.sh --module 13-power-helpers"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("logind helper timeout") from exc


# ---------------------------------------------------------------------------
# KDE constants
# ---------------------------------------------------------------------------
_KDE_POWERDEVIL_RC = Path.home() / ".config" / "powerdevilrc"
_KDE_TARGET_SECTION = "[AC][SuspendSession]"
_KDE_SUSPEND_TYPE_MAP = {1: "suspend", 2: "hibernate"}


def _parse_kde_groups(text: str) -> dict[str, dict[str, str]]:
    """Parse KDE-style INI: section headers can be '[A][B]'. Returns {section: {k: v}}."""
    out: dict[str, dict[str, str]] = {}
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line
            out.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[current][key.strip()] = value.strip()
    return out


# ---------------------------------------------------------------------------
# KdeAdapter
# ---------------------------------------------------------------------------

class KdeAdapter:
    name = "kde"
    label = "KDE PowerDevil"

    def is_available(self) -> bool:
        # Detection lives in ActivePmDetector; here just say "yes if rc OR D-Bus present"
        # but is_available is the cheap probe. Real detection is in Task 8.
        return True  # overridden by detector — keep cheap

    def read(self) -> AutoSuspendValue:
        if not _KDE_POWERDEVIL_RC.is_file():
            return AutoSuspendValue(enabled=False, timeout_minutes=15, action="suspend")
        try:
            text = _KDE_POWERDEVIL_RC.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", _KDE_POWERDEVIL_RC, exc)
            return AutoSuspendValue(enabled=False, timeout_minutes=15, action="suspend")
        groups = _parse_kde_groups(text)
        section = groups.get(_KDE_TARGET_SECTION)
        if section is None:
            return AutoSuspendValue(enabled=False, timeout_minutes=15, action="suspend")
        try:
            idle_ms = int(section.get("idleTime", "0"))
        except ValueError:
            idle_ms = 0
        try:
            stype = int(section.get("suspendType", "0"))
        except ValueError:
            stype = 0
        action = _KDE_SUSPEND_TYPE_MAP.get(stype)
        if action is None:
            logger.warning("KDE suspendType=%d unknown — treating as ignore", stype)
            action = "ignore"
        timeout_minutes = max(0, idle_ms // 60000)
        enabled = action != "ignore" and timeout_minutes > 0
        return AutoSuspendValue(
            enabled=enabled,
            timeout_minutes=timeout_minutes if timeout_minutes > 0 else 15,
            action=action,  # type: ignore[arg-type]
        )

    def write(self, value: AutoSuspendValue) -> None:
        raise NotImplementedError  # Task 6
