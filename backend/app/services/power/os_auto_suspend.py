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


def _serialize_kde_groups(groups: dict[str, dict[str, str]]) -> str:
    """Inverse of _parse_kde_groups. Preserves insertion order."""
    parts: list[str] = []
    for section, kv in groups.items():
        parts.append(section)
        for k, v in kv.items():
            parts.append(f"{k}={v}")
        parts.append("")  # blank line between sections
    return "\n".join(parts).rstrip() + "\n"


def _kde_signal_reload() -> None:
    """Best-effort: tell KDE PowerDevil to reparse config. Failure logged but not raised."""
    try:
        subprocess.run(
            ["qdbus6", "org.kde.kded6", "/modules/powerdevil", "reparseConfiguration"],
            timeout=2.0, capture_output=True, text=True, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.debug("KDE reload signal skipped: %s", exc)


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
        # Read-modify-write: preserve other sections (Battery, Migration, etc.).
        text = ""
        if _KDE_POWERDEVIL_RC.is_file():
            try:
                text = _KDE_POWERDEVIL_RC.read_text(encoding="utf-8")
            except OSError:
                text = ""
        groups = _parse_kde_groups(text)

        if not value.enabled or value.action == "ignore":
            # Disable = remove the section entirely (matches KDE UI uncheck behavior)
            groups.pop(_KDE_TARGET_SECTION, None)
        else:
            stype = 1 if value.action == "suspend" else 2  # action == "hibernate"
            groups[_KDE_TARGET_SECTION] = {
                "idleTime": str(value.timeout_minutes * 60_000),
                "suspendType": str(stype),
            }

        _KDE_POWERDEVIL_RC.parent.mkdir(parents=True, exist_ok=True)
        new_text = _serialize_kde_groups(groups)

        # Atomic write: tempfile in same dir + os.replace
        import os, tempfile  # noqa: PLC0415
        fd, tmp_path = tempfile.mkstemp(
            prefix=".powerdevilrc.", dir=str(_KDE_POWERDEVIL_RC.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_text)
            os.replace(tmp_path, _KDE_POWERDEVIL_RC)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        try:
            _kde_signal_reload()
        except Exception as exc:
            logger.warning("KDE reload signal failed (KConfigWatcher should still react): %s", exc)


# ---------------------------------------------------------------------------
# GNOME constants
# ---------------------------------------------------------------------------
_GNOME_SCHEMA = "org.gnome.settings-daemon.plugins.power"
_GNOME_KEY_TIMEOUT = "sleep-inactive-ac-timeout"
_GNOME_KEY_TYPE = "sleep-inactive-ac-type"
_GNOME_ACTION_TO_VALUE = {"suspend": "suspend", "hibernate": "hibernate", "ignore": "nothing"}
_GNOME_VALUE_TO_ACTION = {"suspend": "suspend", "hibernate": "hibernate", "nothing": "ignore"}


class GnomeAdapter:
    name = "gnome"
    label = "GNOME gsd-power"

    def is_available(self) -> bool:
        return True  # detector decides; keep is_available cheap

    def _gsettings_get(self, key: str) -> str:
        proc = subprocess.run(
            ["gsettings", "get", _GNOME_SCHEMA, key],
            capture_output=True, text=True, timeout=2.0, check=True,
        )
        return proc.stdout.strip()

    def _gsettings_set(self, key: str, value: str) -> None:
        subprocess.run(
            ["gsettings", "set", _GNOME_SCHEMA, key, value],
            check=True, capture_output=True, text=True, timeout=2.0,
        )

    def read(self) -> AutoSuspendValue:
        timeout_raw = self._gsettings_get(_GNOME_KEY_TIMEOUT)
        type_raw = self._gsettings_get(_GNOME_KEY_TYPE).strip("'\"")
        try:
            seconds = int(timeout_raw)
        except ValueError:
            seconds = 0
        action = _GNOME_VALUE_TO_ACTION.get(type_raw)
        if action is None:
            logger.warning(
                "GNOME sleep-inactive-ac-type=%r unknown — treating as ignore", type_raw
            )
            action = "ignore"
        timeout_minutes = seconds // 60
        enabled = action != "ignore" and timeout_minutes > 0
        return AutoSuspendValue(
            enabled=enabled,
            timeout_minutes=timeout_minutes if timeout_minutes > 0 else 15,
            action=action,  # type: ignore[arg-type]
        )

    def write(self, value: AutoSuspendValue) -> None:
        gnome_type = _GNOME_ACTION_TO_VALUE[value.action] if value.enabled else "nothing"
        seconds = value.timeout_minutes * 60
        self._gsettings_set(_GNOME_KEY_TIMEOUT, str(seconds))
        self._gsettings_set(_GNOME_KEY_TYPE, gnome_type)


# ---------------------------------------------------------------------------
# Active-PM detection
# ---------------------------------------------------------------------------
import sys  # noqa: E402
import threading  # noqa: E402
from time import monotonic  # noqa: E402

_SYSTEMD_DIR = Path("/etc/systemd")
_DBUS_PROBE_TIMEOUT = 2.0
_DETECT_CACHE_TTL = 30.0

_detect_lock = threading.Lock()
_detect_cache: tuple[Optional[OsAutoSuspendBackend], float] | None = None


def _detector_cache_clear() -> None:
    """Test helper."""
    global _detect_cache
    with _detect_lock:
        _detect_cache = None


def _probe_dbus_service(service: str) -> bool:
    """True if `service` is reachable on the session bus."""
    try:
        proc = subprocess.run(
            ["qdbus6", service],
            capture_output=True, text=True,
            timeout=_DBUS_PROBE_TIMEOUT, check=False,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    except OSError:
        return False


def detect_active_backend() -> Optional[OsAutoSuspendBackend]:
    """Return an instance of the active backend, cached 30s."""
    global _detect_cache
    if sys.platform != "linux":
        return None
    with _detect_lock:
        if _detect_cache is not None:
            backend, stored_at = _detect_cache
            if monotonic() - stored_at < _DETECT_CACHE_TTL:
                return backend

        backend: Optional[OsAutoSuspendBackend] = None
        if _probe_dbus_service("org.kde.Solid.PowerManagement"):
            backend = KdeAdapter()
        elif _probe_dbus_service("org.gnome.SettingsDaemon.Power"):
            backend = GnomeAdapter()
        elif _SYSTEMD_DIR.is_dir():
            backend = LogindAdapter()
        _detect_cache = (backend, monotonic())
        return backend


# ---------------------------------------------------------------------------
# Service-layer
# ---------------------------------------------------------------------------
from app.schemas.sleep import (  # noqa: E402
    OsAutoSuspendResponse, OsAutoSuspendUpdate, OsAutoSuspendAction,
)


def get_os_auto_suspend() -> OsAutoSuspendResponse:
    backend = detect_active_backend()
    if backend is None:
        return OsAutoSuspendResponse(
            supported=False, source="none", backend_label="",
            enabled=False, timeout_minutes=0, action=OsAutoSuspendAction.IGNORE,
        )
    value = backend.read()
    return OsAutoSuspendResponse(
        supported=True,
        source=backend.name,
        backend_label=backend.label,
        enabled=value.enabled,
        timeout_minutes=value.timeout_minutes,
        action=OsAutoSuspendAction(value.action),
    )


def set_os_auto_suspend(update: OsAutoSuspendUpdate) -> OsAutoSuspendResponse:
    backend = detect_active_backend()
    if backend is None:
        raise RuntimeError("no active power manager detected — cannot write")
    backend.write(AutoSuspendValue(
        enabled=update.enabled,
        timeout_minutes=update.timeout_minutes,
        action=update.action.value,  # type: ignore[arg-type]
    ))
    # Read back for sanity check / transparent value coercion.
    read_back = backend.read()
    return OsAutoSuspendResponse(
        supported=True,
        source=backend.name,
        backend_label=backend.label,
        enabled=read_back.enabled,
        timeout_minutes=read_back.timeout_minutes,
        action=OsAutoSuspendAction(read_back.action),
    )
