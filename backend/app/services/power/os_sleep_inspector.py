"""
OS sleep settings inspector.

Read-only inspection of systemd's logind/sleep configuration plus
sleep-related target enablement, classified into severity-tagged issues
for display on the Sleep page banner.

No subprocess sudo, no writes — purely defensive observation.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — overridable in tests via monkeypatch
# ---------------------------------------------------------------------------
_SYSTEMD_DIR = Path("/etc/systemd")

_LOGIND_CONF = Path("/etc/systemd/logind.conf")
_LOGIND_DROPIN_DIRS = (
    Path("/etc/systemd/logind.conf.d"),
    Path("/run/systemd/logind.conf.d"),
)
_SLEEP_CONF = Path("/etc/systemd/sleep.conf")
_SLEEP_DROPIN_DIRS = (
    Path("/etc/systemd/sleep.conf.d"),
    Path("/run/systemd/sleep.conf.d"),
)
_TARGET_NAMES = (
    "sleep.target",
    "suspend.target",
    "hibernate.target",
    "hybrid-sleep.target",
    "suspend-then-hibernate.target",
)
_LID_SENSOR = Path("/proc/acpi/button/lid")

_CACHE_TTL_SECONDS = 60.0
_SUBPROCESS_TIMEOUT_SECONDS = 5.0


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------
Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class OsSleepIssue:
    severity: Severity
    key: str
    message: str
    detail: Optional[str] = None


@dataclass
class OsSleepReport:
    platform_supported: bool
    logind: dict[str, str] = field(default_factory=dict)
    sleep_conf: dict[str, str] = field(default_factory=dict)
    targets: dict[str, str] = field(default_factory=dict)
    issues: list[OsSleepIssue] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_cached: tuple[OsSleepReport, float] | None = None


def _cache_get() -> Optional[OsSleepReport]:
    with _cache_lock:
        if _cached is None:
            return None
        report, stored_at = _cached
        if monotonic() - stored_at > _CACHE_TTL_SECONDS:
            return None
        return report


def _cache_put(report: OsSleepReport) -> None:
    global _cached
    with _cache_lock:
        _cached = (report, monotonic())


def _cache_clear() -> None:
    """Test helper: invalidate the cache."""
    global _cached
    with _cache_lock:
        _cached = None


# ---------------------------------------------------------------------------
# INI parsing helpers
# ---------------------------------------------------------------------------
def _parse_systemd_ini(path: Path, section: str) -> dict[str, str]:
    """
    Minimal systemd-style INI reader. Returns a flat dict for the given section.
    Missing files yield {}. Malformed lines are skipped (logged at WARNING).
    """
    result: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return result
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return result

    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line[1:-1] == section
            continue
        if not in_section:
            continue
        if "=" not in line:
            logger.warning("Skipping malformed line in %s: %r", path, raw)
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def _merge_drop_ins(base: dict[str, str], drop_in_dir: Path, section: str) -> dict[str, str]:
    """
    Apply drop-in overrides from drop_in_dir, filename-sorted (systemd's behaviour).
    Returns a new dict; does not mutate `base`.
    """
    merged = dict(base)
    try:
        files = sorted(p for p in drop_in_dir.iterdir() if p.is_file() and p.suffix == ".conf")
    except FileNotFoundError:
        return merged
    except OSError as exc:
        logger.warning("Could not list drop-ins in %s: %s", drop_in_dir, exc)
        return merged
    for f in files:
        merged.update(_parse_systemd_ini(f, section=section))
    return merged


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
_IDLE_ACTION_KEYS = {
    "suspend": "logind.idle_action.suspend",
    "hibernate": "logind.idle_action.hibernate",
    "hybrid-sleep": "logind.idle_action.hybrid_sleep",
}
_LID_KEYS = {
    "suspend": "logind.lid_switch.suspend",
    "hibernate": "logind.lid_switch.hibernate",
}


def _classify(
    *,
    logind: dict[str, str],
    sleep_conf: dict[str, str],
    targets: dict[str, str],
    has_lid: bool,
) -> list[OsSleepIssue]:
    issues: list[OsSleepIssue] = []

    idle_action = logind.get("IdleAction", "").strip().lower()
    if idle_action in _IDLE_ACTION_KEYS:
        idle_after = logind.get("IdleActionSec", "").strip() or None
        issues.append(OsSleepIssue(
            severity="warning",
            key=_IDLE_ACTION_KEYS[idle_action],
            message=f"logind: IdleAction={idle_action} (außerhalb von BaluHost)",
            detail=(f"Wird nach {idle_after} Idle ausgelöst" if idle_after else None),
        ))

    lid_switch = logind.get("HandleLidSwitch", "").strip().lower()
    if has_lid and lid_switch in _LID_KEYS:
        issues.append(OsSleepIssue(
            severity="info",
            key=_LID_KEYS[lid_switch],
            message=f"logind: HandleLidSwitch={lid_switch}",
            detail="Lid-Sensor erkannt — manueller Deckel-Schluss löst OS-Sleep aus",
        ))

    if sleep_conf.get("AllowSuspend", "").strip().lower() == "no":
        issues.append(OsSleepIssue(
            severity="info",
            key="sleep_conf.suspend_disabled",
            message="OS hat Suspend deaktiviert (AllowSuspend=no)",
            detail="BaluHost-Suspend wird fehlschlagen, solange diese Einstellung aktiv ist",
        ))

    if targets.get("suspend.target") == "masked":
        issues.append(OsSleepIssue(
            severity="error",
            key="targets.suspend.masked",
            message="suspend.target ist maskiert",
            detail="BaluHost kann das System nicht in Suspend versetzen",
        ))

    return issues


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------
def _systemctl_is_enabled(target_names: tuple[str, ...]) -> dict[str, str]:
    """
    Run `systemctl is-enabled <name1> <name2> …`. Returns a {name: status} dict.
    On any failure (FileNotFoundError, TimeoutExpired, non-zero exit) returns {}.
    """
    try:
        proc = subprocess.run(
            ["systemctl", "is-enabled", *target_names],
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("systemctl is-enabled failed: %s", exc)
        return {}
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if len(lines) != len(target_names):
        logger.warning(
            "Unexpected systemctl line count: got %d, expected %d",
            len(lines), len(target_names),
        )
    return {name: status for name, status in zip(target_names, lines)}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def inspect_os_sleep(force_refresh: bool = False) -> OsSleepReport:
    """
    Inspect OS sleep settings. Returns a report suitable for read-only display.
    Cached for 60s; pass force_refresh=True to bypass.
    """
    if sys.platform != "linux" or not _SYSTEMD_DIR.is_dir():
        return OsSleepReport(platform_supported=False)

    if not force_refresh:
        cached = _cache_get()
        if cached is not None:
            return cached

    try:
        sources: list[str] = []

        logind: dict[str, str] = _parse_systemd_ini(_LOGIND_CONF, section="Login")
        if _LOGIND_CONF.is_file():
            sources.append(str(_LOGIND_CONF))
        for d in _LOGIND_DROPIN_DIRS:
            if d.is_dir():
                logind = _merge_drop_ins(logind, d, section="Login")
                for f in sorted(d.glob("*.conf")):
                    if f.is_file():
                        sources.append(str(f))

        sleep_conf: dict[str, str] = _parse_systemd_ini(_SLEEP_CONF, section="Sleep")
        if _SLEEP_CONF.is_file():
            sources.append(str(_SLEEP_CONF))
        for d in _SLEEP_DROPIN_DIRS:
            if d.is_dir():
                sleep_conf = _merge_drop_ins(sleep_conf, d, section="Sleep")
                for f in sorted(d.glob("*.conf")):
                    if f.is_file():
                        sources.append(str(f))

        targets = _systemctl_is_enabled(_TARGET_NAMES)
        has_lid = _LID_SENSOR.is_dir()

        issues = _classify(
            logind=logind, sleep_conf=sleep_conf, targets=targets, has_lid=has_lid,
        )

        report = OsSleepReport(
            platform_supported=True,
            logind=logind,
            sleep_conf=sleep_conf,
            targets=targets,
            issues=issues,
            sources=sources,
        )
    except Exception as exc:
        logger.exception("os_sleep_inspector failed: %s", exc)
        report = OsSleepReport(
            platform_supported=True,
            issues=[OsSleepIssue(
                severity="error",
                key="inspector.failed",
                message="OS-Sleep-Detection fehlgeschlagen",
                detail=str(exc),
            )],
        )

    _cache_put(report)
    return report
