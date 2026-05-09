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
# Public entry point — minimal version for Task 1
# Full implementation lands in Task 3.
# ---------------------------------------------------------------------------
def inspect_os_sleep(force_refresh: bool = False) -> OsSleepReport:
    if sys.platform != "linux" or not _SYSTEMD_DIR.is_dir():
        return OsSleepReport(platform_supported=False)
    # Real implementation arrives in Task 3.
    return OsSleepReport(platform_supported=True)
