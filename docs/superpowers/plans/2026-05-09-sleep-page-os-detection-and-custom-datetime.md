# Sleep Page: OS-Sleep-Settings banner + Always-Awake custom datetime — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only OS-sleep-settings card at the top of `/sleep`, and extend the AlwaysAwakePanel preset row with a fifth custom datetime button capped at 7 days.

**Architecture:** A new backend service `os_sleep_inspector` parses `/etc/systemd/{logind,sleep}.conf{,.d}/*` and runs one `systemctl is-enabled` call. Cached 60s, admin-only endpoint at `GET /api/system/sleep/os-settings`. Frontend renders the banner above the existing panels and adds a popover-style datetime picker (`<input type="datetime-local">`, no new deps) to `AlwaysAwakePanel`. Backend `SleepConfigUpdate` validator gains a 7-day horizon cap.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, pytest. React 18, TypeScript strict, Tailwind, react-i18next. Native HTML inputs (no date-picker library).

**Spec:** `docs/superpowers/specs/2026-05-09-sleep-page-os-detection-and-custom-datetime-design.md`

---

## Task 1: Backend — `os_sleep_inspector` pure helpers

**Files:**
- Create: `backend/app/services/power/os_sleep_inspector.py`
- Test: `backend/tests/services/power/test_os_sleep_inspector_helpers.py`

This task delivers the file/INI parsing helpers and the platform guard. The endpoint and cache come in later tasks.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/power/test_os_sleep_inspector_helpers.py`:

```python
"""Tests for os_sleep_inspector low-level helpers."""
import sys
from pathlib import Path

import pytest

from app.services.power import os_sleep_inspector as ins


class TestParseSystemdIni:
    def test_parses_simple_key_value(self, tmp_path: Path):
        f = tmp_path / "logind.conf"
        f.write_text("[Login]\nIdleAction=suspend\nIdleActionSec=30min\n")
        result = ins._parse_systemd_ini(f, section="Login")
        assert result == {"IdleAction": "suspend", "IdleActionSec": "30min"}

    def test_skips_comments_and_blanks(self, tmp_path: Path):
        f = tmp_path / "sleep.conf"
        f.write_text(
            "# top comment\n"
            "; semicolon comment\n"
            "\n"
            "[Sleep]\n"
            "AllowSuspend=yes\n"
            "  # inline indented comment\n"
            "AllowHibernation=no\n"
        )
        result = ins._parse_systemd_ini(f, section="Sleep")
        assert result == {"AllowSuspend": "yes", "AllowHibernation": "no"}

    def test_only_returns_requested_section(self, tmp_path: Path):
        f = tmp_path / "logind.conf"
        f.write_text(
            "[Login]\nIdleAction=ignore\n"
            "[Other]\nFoo=bar\n"
        )
        assert ins._parse_systemd_ini(f, section="Login") == {"IdleAction": "ignore"}
        assert ins._parse_systemd_ini(f, section="Other") == {"Foo": "bar"}

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert ins._parse_systemd_ini(tmp_path / "nope.conf", section="Login") == {}

    def test_malformed_lines_are_skipped(self, tmp_path: Path):
        f = tmp_path / "logind.conf"
        f.write_text("[Login]\nIdleAction=suspend\nthis line has no equals\nIdleActionSec=30min\n")
        result = ins._parse_systemd_ini(f, section="Login")
        assert result == {"IdleAction": "suspend", "IdleActionSec": "30min"}


class TestMergeDropIns:
    def test_drop_in_overrides_base(self, tmp_path: Path):
        base = {"IdleAction": "ignore", "HandleLidSwitch": "suspend"}
        drop_dir = tmp_path / "logind.conf.d"
        drop_dir.mkdir()
        (drop_dir / "30-baluhost.conf").write_text("[Login]\nIdleAction=suspend\n")
        merged = ins._merge_drop_ins(base, drop_dir, section="Login")
        assert merged["IdleAction"] == "suspend"
        assert merged["HandleLidSwitch"] == "suspend"  # untouched

    def test_drop_ins_applied_in_filename_order(self, tmp_path: Path):
        base: dict[str, str] = {}
        drop_dir = tmp_path / "logind.conf.d"
        drop_dir.mkdir()
        (drop_dir / "10-first.conf").write_text("[Login]\nIdleAction=ignore\n")
        (drop_dir / "20-second.conf").write_text("[Login]\nIdleAction=suspend\n")
        merged = ins._merge_drop_ins(base, drop_dir, section="Login")
        assert merged["IdleAction"] == "suspend"  # later filename wins

    def test_missing_directory_returns_base_unchanged(self, tmp_path: Path):
        base = {"IdleAction": "ignore"}
        merged = ins._merge_drop_ins(base, tmp_path / "nope.d", section="Login")
        assert merged == base


class TestPlatformGuard:
    def test_unsupported_platform_short_circuits(self, monkeypatch):
        monkeypatch.setattr(ins.sys, "platform", "win32")
        report = ins.inspect_os_sleep(force_refresh=True)
        assert report.platform_supported is False
        assert report.logind == {}
        assert report.sleep_conf == {}
        assert report.targets == {}
        assert report.issues == []

    def test_no_systemd_dir_short_circuits(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(ins.sys, "platform", "linux")
        monkeypatch.setattr(ins, "_SYSTEMD_DIR", tmp_path / "absent")
        report = ins.inspect_os_sleep(force_refresh=True)
        assert report.platform_supported is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_helpers.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.power.os_sleep_inspector'`.

- [ ] **Step 3: Create the module skeleton**

Create `backend/app/services/power/os_sleep_inspector.py`:

```python
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


@dataclass(frozen=True)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_helpers.py -v`

Expected: PASS for all 11 tests in this file.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/os_sleep_inspector.py backend/tests/services/power/test_os_sleep_inspector_helpers.py
git commit -m "feat(sleep): add os_sleep_inspector INI parser and platform guard"
```

---

## Task 2: Backend — classifier rules

**Files:**
- Modify: `backend/app/services/power/os_sleep_inspector.py`
- Test: `backend/tests/services/power/test_os_sleep_inspector_classifier.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/power/test_os_sleep_inspector_classifier.py`:

```python
"""Tests for the os_sleep_inspector issue classifier."""
import pytest

from app.services.power import os_sleep_inspector as ins


def _classify(
    *,
    logind: dict[str, str] | None = None,
    sleep_conf: dict[str, str] | None = None,
    targets: dict[str, str] | None = None,
    has_lid: bool = False,
) -> list[ins.OsSleepIssue]:
    return ins._classify(
        logind=logind or {},
        sleep_conf=sleep_conf or {},
        targets=targets or {},
        has_lid=has_lid,
    )


class TestClassifier:
    def test_idle_action_suspend_warns(self):
        issues = _classify(logind={"IdleAction": "suspend", "IdleActionSec": "30min"})
        keys = {i.key for i in issues}
        assert "logind.idle_action.suspend" in keys
        suspend = next(i for i in issues if i.key == "logind.idle_action.suspend")
        assert suspend.severity == "warning"
        assert suspend.detail is not None and "30min" in suspend.detail

    def test_idle_action_hibernate_warns_with_distinct_key(self):
        issues = _classify(logind={"IdleAction": "hibernate"})
        assert any(i.key == "logind.idle_action.hibernate" and i.severity == "warning" for i in issues)

    def test_idle_action_hybrid_sleep_warns(self):
        issues = _classify(logind={"IdleAction": "hybrid-sleep"})
        assert any(i.key == "logind.idle_action.hybrid_sleep" and i.severity == "warning" for i in issues)

    def test_idle_action_ignore_does_not_warn(self):
        issues = _classify(logind={"IdleAction": "ignore"})
        assert not any(i.key.startswith("logind.idle_action.") for i in issues)

    def test_lid_switch_suspend_with_lid_emits_info(self):
        issues = _classify(logind={"HandleLidSwitch": "suspend"}, has_lid=True)
        assert any(i.key == "logind.lid_switch.suspend" and i.severity == "info" for i in issues)

    def test_lid_switch_suspend_without_lid_silent(self):
        issues = _classify(logind={"HandleLidSwitch": "suspend"}, has_lid=False)
        assert not any(i.key.startswith("logind.lid_switch.") for i in issues)

    def test_lid_switch_hibernate_emits_info_with_distinct_key(self):
        issues = _classify(logind={"HandleLidSwitch": "hibernate"}, has_lid=True)
        assert any(i.key == "logind.lid_switch.hibernate" for i in issues)

    def test_sleep_conf_suspend_disabled_emits_info(self):
        issues = _classify(sleep_conf={"AllowSuspend": "no"})
        assert any(i.key == "sleep_conf.suspend_disabled" and i.severity == "info" for i in issues)

    def test_suspend_target_masked_is_error(self):
        issues = _classify(targets={"suspend.target": "masked"})
        assert any(i.key == "targets.suspend.masked" and i.severity == "error" for i in issues)

    def test_clean_config_emits_no_issues(self):
        issues = _classify(
            logind={"IdleAction": "ignore", "HandleLidSwitch": "ignore"},
            sleep_conf={"AllowSuspend": "yes"},
            targets={"suspend.target": "enabled"},
            has_lid=True,
        )
        assert issues == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_classifier.py -v`

Expected: FAIL — `AttributeError: module 'app.services.power.os_sleep_inspector' has no attribute '_classify'`.

- [ ] **Step 3: Add `_classify` to the module**

Append to `backend/app/services/power/os_sleep_inspector.py` (above the `inspect_os_sleep` function):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_classifier.py -v`

Expected: PASS for all 10 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/os_sleep_inspector.py backend/tests/services/power/test_os_sleep_inspector_classifier.py
git commit -m "feat(sleep): add os_sleep_inspector classifier rules"
```

---

## Task 3: Backend — full `inspect_os_sleep` integration + cache + resilience

**Files:**
- Modify: `backend/app/services/power/os_sleep_inspector.py`
- Test: `backend/tests/services/power/test_os_sleep_inspector_integration.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/power/test_os_sleep_inspector_integration.py`:

```python
"""Integration tests for inspect_os_sleep — file resolution, subprocess, cache, resilience."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.power import os_sleep_inspector as ins


@pytest.fixture(autouse=True)
def _clean_cache():
    ins._cache_clear()
    yield
    ins._cache_clear()


@pytest.fixture
def linux_fs(tmp_path: Path, monkeypatch):
    """Layout a fake /etc/systemd tree under tmp_path and point the module at it."""
    systemd = tmp_path / "etc" / "systemd"
    systemd.mkdir(parents=True)
    (systemd / "logind.conf.d").mkdir()
    (systemd / "sleep.conf.d").mkdir()
    monkeypatch.setattr(ins, "_SYSTEMD_DIR", systemd)
    monkeypatch.setattr(ins, "_LOGIND_CONF", systemd / "logind.conf")
    monkeypatch.setattr(ins, "_LOGIND_DROPIN_DIRS", (systemd / "logind.conf.d",))
    monkeypatch.setattr(ins, "_SLEEP_CONF", systemd / "sleep.conf")
    monkeypatch.setattr(ins, "_SLEEP_DROPIN_DIRS", (systemd / "sleep.conf.d",))
    monkeypatch.setattr(ins, "_LID_SENSOR", tmp_path / "no-lid")
    monkeypatch.setattr(ins.sys, "platform", "linux")
    return systemd


def _fake_systemctl(targets: dict[str, str]):
    """Build a subprocess.run replacement that emits one status per target."""
    def runner(cmd, *args, **kwargs):
        # Return order matches argv order after the leading systemctl args.
        names = cmd[2:]  # ["systemctl", "is-enabled", *names]
        out = "\n".join(targets.get(n, "disabled") for n in names) + "\n"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=out, stderr="")
    return runner


def test_full_report_resolves_drop_ins_and_targets(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "logind.conf.d" / "30-baluhost.conf").write_text("[Login]\nIdleAction=suspend\nIdleActionSec=30min\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    with patch.object(ins.subprocess, "run", side_effect=_fake_systemctl({
        "sleep.target": "enabled",
        "suspend.target": "masked",
        "hibernate.target": "disabled",
        "hybrid-sleep.target": "disabled",
        "suspend-then-hibernate.target": "disabled",
    })):
        report = ins.inspect_os_sleep(force_refresh=True)

    assert report.platform_supported is True
    assert report.logind["IdleAction"] == "suspend"
    assert report.sleep_conf["AllowSuspend"] == "yes"
    assert report.targets["suspend.target"] == "masked"
    keys = {i.key for i in report.issues}
    assert "logind.idle_action.suspend" in keys
    assert "targets.suspend.masked" in keys
    # logind.conf and the drop-in were both read; sleep.conf too.
    assert any("logind.conf" in s for s in report.sources)
    assert any("30-baluhost.conf" in s for s in report.sources)
    assert any("sleep.conf" in s for s in report.sources)


def test_cache_hit_skips_subprocess(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    with patch.object(ins.subprocess, "run", side_effect=_fake_systemctl({})) as run_mock:
        ins.inspect_os_sleep(force_refresh=False)
        ins.inspect_os_sleep(force_refresh=False)
    assert run_mock.call_count == 1


def test_force_refresh_bypasses_cache(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    with patch.object(ins.subprocess, "run", side_effect=_fake_systemctl({})) as run_mock:
        ins.inspect_os_sleep(force_refresh=True)
        ins.inspect_os_sleep(force_refresh=True)
    assert run_mock.call_count == 2


def test_subprocess_timeout_does_not_raise(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=5)
    with patch.object(ins.subprocess, "run", side_effect=boom):
        report = ins.inspect_os_sleep(force_refresh=True)
    assert report.platform_supported is True
    assert report.targets == {}


def test_subprocess_failure_does_not_raise(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    def boom(*args, **kwargs):
        raise FileNotFoundError("systemctl not found")
    with patch.object(ins.subprocess, "run", side_effect=boom):
        report = ins.inspect_os_sleep(force_refresh=True)
    assert report.platform_supported is True
    assert report.targets == {}


def test_unexpected_exception_yields_inspector_failed(linux_fs: Path):
    """If a helper raises unexpectedly, return a report with an inspector.failed issue."""
    with patch.object(ins, "_parse_systemd_ini", side_effect=RuntimeError("kaboom")):
        report = ins.inspect_os_sleep(force_refresh=True)
    assert report.platform_supported is True
    assert any(i.key == "inspector.failed" and i.severity == "error" for i in report.issues)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_integration.py -v`

Expected: FAIL — most tests fail because `inspect_os_sleep` is still the stub from Task 1.

- [ ] **Step 3: Replace `inspect_os_sleep` with the full implementation**

In `backend/app/services/power/os_sleep_inspector.py`, replace the stub `inspect_os_sleep` at the bottom with:

```python
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
        logind: dict[str, str] = {}
        sources: list[str] = []
        if _LOGIND_CONF.is_file():
            logind = _parse_systemd_ini(_LOGIND_CONF, section="Login")
            sources.append(str(_LOGIND_CONF))
        for d in _LOGIND_DROPIN_DIRS:
            if d.is_dir():
                before = dict(logind)
                logind = _merge_drop_ins(logind, d, section="Login")
                # Track only files we actually read.
                for f in sorted(d.glob("*.conf")):
                    if f.is_file() and (f.read_text(encoding="utf-8", errors="replace") or before != logind):
                        sources.append(str(f))

        sleep_conf: dict[str, str] = {}
        if _SLEEP_CONF.is_file():
            sleep_conf = _parse_systemd_ini(_SLEEP_CONF, section="Sleep")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_integration.py -v`

Expected: PASS for all 6 tests.

- [ ] **Step 5: Run the full inspector test suite to confirm no regression**

Run: `cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_helpers.py tests/services/power/test_os_sleep_inspector_classifier.py tests/services/power/test_os_sleep_inspector_integration.py -v`

Expected: PASS for all 27 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/os_sleep_inspector.py backend/tests/services/power/test_os_sleep_inspector_integration.py
git commit -m "feat(sleep): wire os_sleep_inspector with systemctl + cache + resilience"
```

---

## Task 4: Backend — Pydantic schemas + 7-day cap

**Files:**
- Modify: `backend/app/schemas/sleep.py`
- Test: `backend/tests/test_sleep_schemas.py` (new)

This task adds the response schema for the OS-settings endpoint and tightens the always-awake validator.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_sleep_schemas.py`:

```python
"""Schema-level tests for OsSleepReportResponse and the 7-day cap."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas.sleep import (
    OsSleepIssueModel,
    OsSleepReportResponse,
    SleepConfigUpdate,
)


class TestOsSleepReportResponse:
    def test_minimal_payload_validates(self):
        payload = {"platform_supported": False}
        m = OsSleepReportResponse(**payload)
        assert m.platform_supported is False
        assert m.logind == {}
        assert m.issues == []
        assert m.sources == []

    def test_full_payload_round_trip(self):
        payload = {
            "platform_supported": True,
            "logind": {"IdleAction": "suspend"},
            "sleep_conf": {"AllowSuspend": "yes"},
            "targets": {"suspend.target": "enabled"},
            "issues": [
                {"severity": "warning", "key": "logind.idle_action.suspend",
                 "message": "logind suspends after idle", "detail": "30min"}
            ],
            "sources": ["/etc/systemd/logind.conf"],
            "collected_at": "2026-05-09T12:00:00+00:00",
        }
        m = OsSleepReportResponse(**payload)
        assert m.issues[0].severity == "warning"
        assert m.issues[0].key == "logind.idle_action.suspend"

    def test_severity_must_be_known(self):
        bad = {
            "platform_supported": True,
            "issues": [{"severity": "purple", "key": "x", "message": "y"}],
        }
        with pytest.raises(ValidationError):
            OsSleepReportResponse(**bad)


class TestAlwaysAwake7DayCap:
    def test_until_at_7_days_minus_5min_accepted(self):
        v = datetime.now(timezone.utc) + timedelta(days=7) - timedelta(minutes=5)
        SleepConfigUpdate(always_awake_until=v)  # must not raise

    def test_until_8_days_in_future_rejected(self):
        v = datetime.now(timezone.utc) + timedelta(days=8)
        with pytest.raises(ValidationError) as exc:
            SleepConfigUpdate(always_awake_until=v)
        assert "7 days" in str(exc.value) or "7 Tagen" in str(exc.value)

    def test_until_naive_datetime_normalized_then_capped(self):
        # Naive value 8 days out — should be normalized to UTC and rejected.
        v = (datetime.utcnow() + timedelta(days=8)).replace(tzinfo=None)
        with pytest.raises(ValidationError):
            SleepConfigUpdate(always_awake_until=v)

    def test_until_in_past_still_rejected(self):
        v = datetime.now(timezone.utc) - timedelta(minutes=1)
        with pytest.raises(ValidationError):
            SleepConfigUpdate(always_awake_until=v)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sleep_schemas.py -v`

Expected: FAIL — `ImportError` on `OsSleepIssueModel`/`OsSleepReportResponse`, plus the 7-day cap tests fail because the validator doesn't enforce a max yet.

- [ ] **Step 3: Add response schemas to `backend/app/schemas/sleep.py`**

Add after the existing `AlwaysAwakeStatus` class (after line 84):

```python
# ---------------------------------------------------------------------------
# OS Sleep Inspector
# ---------------------------------------------------------------------------

class OsSleepIssueModel(BaseModel):
    """One issue surfaced by the OS sleep inspector."""
    severity: Literal["info", "warning", "error"]
    key: str = Field(..., description="Stable identifier, used for i18n lookup")
    message: str = Field(..., description="Fallback human-readable message")
    detail: Optional[str] = Field(default=None)


class OsSleepReportResponse(BaseModel):
    """Snapshot of OS sleep configuration (read-only)."""
    platform_supported: bool = Field(..., description="False on Windows / when /etc/systemd is missing")
    logind: dict[str, str] = Field(default_factory=dict)
    sleep_conf: dict[str, str] = Field(default_factory=dict)
    targets: dict[str, str] = Field(default_factory=dict)
    issues: list[OsSleepIssueModel] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Tighten the 7-day cap in `_validate_until_future`**

Replace the `_validate_until_future` validator on `SleepConfigUpdate` (currently at lines 193-204) with:

```python
    @field_validator("always_awake_until")
    @classmethod
    def _validate_until_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return v
        # Normalize naive datetimes to UTC
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        # Reject "now" as well: a non-future timestamp is meaningless for an override
        if v <= now:
            raise ValueError("always_awake_until must be in the future (UTC)")
        # Reject far-future values: max 7 days horizon
        if v > now + _MAX_ALWAYS_AWAKE_HORIZON:
            raise ValueError("always_awake_until must be at most 7 days in the future")
        return v
```

Just above the `class SleepConfigUpdate` definition (above line 168), add the constant:

```python
from datetime import timedelta as _timedelta  # local alias to avoid touching the existing import
_MAX_ALWAYS_AWAKE_HORIZON = _timedelta(days=7)
```

If `timedelta` is already imported via `from datetime import …` at the top, simplify to `_MAX_ALWAYS_AWAKE_HORIZON = timedelta(days=7)` and skip the local alias. (Check the top of the file before adding the import.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sleep_schemas.py -v`

Expected: PASS for all 7 tests.

- [ ] **Step 6: Run the existing always-awake test suites to confirm no regression**

Run: `cd backend && python -m pytest tests/services/test_sleep_always_awake.py tests/api/test_sleep_always_awake_routes.py tests/test_sleep.py -v`

Expected: PASS for all existing tests (existing presets stay well under 7 days).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/sleep.py backend/tests/test_sleep_schemas.py
git commit -m "feat(sleep): add OsSleepReportResponse + 7-day always-awake cap"
```

---

## Task 5: Backend — `GET /os-settings` endpoint

**Files:**
- Modify: `backend/app/api/routes/sleep.py`
- Test: `backend/tests/api/test_sleep_os_settings_route.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_sleep_os_settings_route.py`:

```python
"""Tests for GET /api/system/sleep/os-settings."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.power.os_sleep_inspector import OsSleepIssue, OsSleepReport


@pytest.fixture
def stub_report():
    return OsSleepReport(
        platform_supported=True,
        logind={"IdleAction": "suspend"},
        sleep_conf={"AllowSuspend": "yes"},
        targets={"suspend.target": "enabled"},
        issues=[OsSleepIssue(
            severity="warning",
            key="logind.idle_action.suspend",
            message="logind suspends after idle",
            detail="30min",
        )],
        sources=["/etc/systemd/logind.conf"],
        collected_at=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
    )


def test_requires_admin(client, regular_user_token):
    """Non-admin users get 403."""
    res = client.get(
        "/api/system/sleep/os-settings",
        headers={"Authorization": f"Bearer {regular_user_token}"},
    )
    assert res.status_code == 403


def test_returns_report_for_admin(client, admin_token, stub_report):
    with patch(
        "app.api.routes.sleep.os_sleep_inspector.inspect_os_sleep",
        return_value=stub_report,
    ):
        res = client.get(
            "/api/system/sleep/os-settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["platform_supported"] is True
    assert body["logind"]["IdleAction"] == "suspend"
    assert body["issues"][0]["key"] == "logind.idle_action.suspend"


def test_force_param_bypasses_cache(client, admin_token, stub_report):
    with patch(
        "app.api.routes.sleep.os_sleep_inspector.inspect_os_sleep",
        return_value=stub_report,
    ) as inspect_mock:
        res = client.get(
            "/api/system/sleep/os-settings?force=true",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert res.status_code == 200
    inspect_mock.assert_called_once_with(force_refresh=True)


def test_default_does_not_force_refresh(client, admin_token, stub_report):
    with patch(
        "app.api.routes.sleep.os_sleep_inspector.inspect_os_sleep",
        return_value=stub_report,
    ) as inspect_mock:
        client.get(
            "/api/system/sleep/os-settings",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    inspect_mock.assert_called_once_with(force_refresh=False)
```

If the existing `client` / `admin_token` / `regular_user_token` fixtures don't exist under that exact name, look at one of the existing route tests in `backend/tests/api/test_sleep_*` (e.g. `test_sleep_always_awake_routes.py`) for the project's fixture conventions, and adopt the same names — do NOT invent new fixtures.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_sleep_os_settings_route.py -v`

Expected: FAIL — endpoint returns 404 (not yet defined).

- [ ] **Step 3: Add the endpoint**

In `backend/app/api/routes/sleep.py`, add the import near the other service imports (around line 37):

```python
from app.services.power import os_sleep_inspector
from app.schemas.sleep import OsSleepReportResponse
```

Add the endpoint between the existing `/capabilities` route (ends ~line 241) and `/my-permissions` (starts ~line 244):

```python
@router.get("/os-settings", response_model=OsSleepReportResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_os_sleep_settings(
    request: Request, response: Response,
    force: bool = False,
    current_user: User = Depends(get_current_admin),
) -> OsSleepReportResponse:
    """Read-only snapshot of OS-level sleep configuration (admin only)."""
    report = os_sleep_inspector.inspect_os_sleep(force_refresh=force)
    return OsSleepReportResponse(
        platform_supported=report.platform_supported,
        logind=report.logind,
        sleep_conf=report.sleep_conf,
        targets=report.targets,
        issues=[
            {"severity": i.severity, "key": i.key, "message": i.message, "detail": i.detail}
            for i in report.issues
        ],
        sources=report.sources,
        collected_at=report.collected_at,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_sleep_os_settings_route.py -v`

Expected: PASS for all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/sleep.py backend/tests/api/test_sleep_os_settings_route.py
git commit -m "feat(sleep): GET /api/system/sleep/os-settings (admin)"
```

---

## Task 6: Backend — extend always-awake route tests for the 7-day cap

**Files:**
- Modify: `backend/tests/api/test_sleep_always_awake_routes.py`

- [ ] **Step 1: Add new tests**

Append to `backend/tests/api/test_sleep_always_awake_routes.py` (the file structure / fixtures are already established — match the conventions of the existing tests in this file):

```python
def test_until_rejected_when_more_than_7_days(client, admin_token):
    from datetime import datetime, timedelta, timezone
    eight_days = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat()
    res = client.put(
        "/api/system/sleep/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"always_awake_enabled": True, "always_awake_until": eight_days},
    )
    assert res.status_code == 422
    assert "7 days" in res.text or "7 Tagen" in res.text


def test_until_accepted_at_6_days_23h(client, admin_token):
    from datetime import datetime, timedelta, timezone
    target = (datetime.now(timezone.utc) + timedelta(days=6, hours=23)).isoformat()
    res = client.put(
        "/api/system/sleep/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"always_awake_enabled": True, "always_awake_until": target},
    )
    assert res.status_code == 200
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_sleep_always_awake_routes.py -v`

Expected: PASS — all existing tests still pass and the two new ones validate the cap.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_sleep_always_awake_routes.py
git commit -m "test(sleep): cover 7-day always-awake cap on PUT /config"
```

---

## Task 7: Backend — full sleep test suite sweep

**Files:** none new (verification step)

- [ ] **Step 1: Run sleep-scoped pytest**

Run: `cd backend && python -m pytest -v -k "sleep or os_sleep"`

Expected: all tests pass — none should regress from Tasks 1-6.

- [ ] **Step 2: Run the full backend test suite**

Run: `cd backend && python -m pytest -q`

Expected: same pass/fail surface as before this branch (per memory `feedback_run_tests_before_pr`). Any *new* failures in unrelated tests need investigation before continuing.

If the run is clean, no commit is needed. If a fix-up is required, commit it as `fix(sleep): …` referencing the underlying cause.

---

## Task 8: Frontend — API client types and `getOsSleepSettings`

**Files:**
- Modify: `client/src/api/sleep.ts`

- [ ] **Step 1: Add types and the API function**

In `client/src/api/sleep.ts`, add after the existing `AlwaysAwakeStatus` interface (after line 54), inside the "Types" section:

```typescript
export type OsSleepSeverity = 'info' | 'warning' | 'error';

export interface OsSleepIssue {
  severity: OsSleepSeverity;
  key: string;
  message: string;
  detail: string | null;
}

export interface OsSleepReport {
  platform_supported: boolean;
  logind: Record<string, string>;
  sleep_conf: Record<string, string>;
  targets: Record<string, string>;
  issues: OsSleepIssue[];
  sources: string[];
  collected_at: string;
}
```

Add the API function at the end of the file (after `getSleepCapabilities`, line 237):

```typescript
export async function getOsSleepSettings(force = false): Promise<OsSleepReport> {
  const response = await apiClient.get<OsSleepReport>('/api/system/sleep/os-settings', {
    params: force ? { force: true } : undefined,
  });
  return response.data;
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/api/sleep.ts
git commit -m "feat(sleep): frontend api client for os-settings"
```

---

## Task 9: Frontend — i18n keys

**Files:**
- Modify: `client/src/i18n/locales/de/system.json`
- Modify: `client/src/i18n/locales/en/system.json`

- [ ] **Step 1: Add the German keys**

In `client/src/i18n/locales/de/system.json`, locate the `sleep` object. Add a new `osSettings` block (sibling of `alwaysAwake` and the other sleep blocks):

```json
"osSettings": {
  "title": "OS-Sleep-Einstellungen",
  "refresh": "Aktualisieren",
  "detailsToggle": "Details",
  "allClear": "Keine OS-Sleep-Trigger aktiv. BaluHost steuert Sleep allein.",
  "sources": "Quellen",
  "loading": "Wird geladen…",
  "loadFailed": "OS-Sleep-Einstellungen konnten nicht geladen werden",
  "issue": {
    "logind.idle_action.suspend": "logind: IdleAction=suspend (außerhalb von BaluHost)",
    "logind.idle_action.hibernate": "logind: IdleAction=hibernate (außerhalb von BaluHost)",
    "logind.idle_action.hybrid_sleep": "logind: IdleAction=hybrid-sleep (außerhalb von BaluHost)",
    "logind.lid_switch.suspend": "logind: HandleLidSwitch=suspend",
    "logind.lid_switch.hibernate": "logind: HandleLidSwitch=hibernate",
    "sleep_conf.suspend_disabled": "OS hat Suspend deaktiviert (AllowSuspend=no)",
    "targets.suspend.masked": "suspend.target ist maskiert",
    "inspector.failed": "OS-Sleep-Detection fehlgeschlagen"
  }
}
```

In the same `sleep.alwaysAwake` block, add these new keys (siblings of the existing `preset1h`, `presetPermanent`, etc.):

```json
"presetCustom": "Bis Datum…",
"activeCustom": "Bis {{datetime}}",
"pickerLabel": "Datum & Uhrzeit",
"pickerApply": "Übernehmen",
"pickerCancel": "Abbrechen",
"pickerErrorPast": "Zeitpunkt muss in der Zukunft liegen (mind. 5 Min)",
"pickerErrorMax": "Maximal 7 Tage in der Zukunft"
```

- [ ] **Step 2: Add the English keys**

Mirror in `client/src/i18n/locales/en/system.json`:

```json
"osSettings": {
  "title": "OS sleep settings",
  "refresh": "Refresh",
  "detailsToggle": "Details",
  "allClear": "No OS-level sleep triggers active. BaluHost is in sole control.",
  "sources": "Sources",
  "loading": "Loading…",
  "loadFailed": "Failed to load OS sleep settings",
  "issue": {
    "logind.idle_action.suspend": "logind: IdleAction=suspend (outside BaluHost)",
    "logind.idle_action.hibernate": "logind: IdleAction=hibernate (outside BaluHost)",
    "logind.idle_action.hybrid_sleep": "logind: IdleAction=hybrid-sleep (outside BaluHost)",
    "logind.lid_switch.suspend": "logind: HandleLidSwitch=suspend",
    "logind.lid_switch.hibernate": "logind: HandleLidSwitch=hibernate",
    "sleep_conf.suspend_disabled": "OS has suspend disabled (AllowSuspend=no)",
    "targets.suspend.masked": "suspend.target is masked",
    "inspector.failed": "OS sleep detection failed"
  }
}
```

For `sleep.alwaysAwake`:

```json
"presetCustom": "Until date…",
"activeCustom": "Until {{datetime}}",
"pickerLabel": "Date & time",
"pickerApply": "Apply",
"pickerCancel": "Cancel",
"pickerErrorPast": "Must be in the future (at least 5 min)",
"pickerErrorMax": "At most 7 days in the future"
```

- [ ] **Step 3: Type-check + lint the JSON**

Run: `cd client && npx tsc --noEmit`

Expected: no errors. Also visually scan both files for trailing commas / missing commas.

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json
git commit -m "feat(sleep): i18n strings for os-settings banner + custom datetime"
```

---

## Task 10: Frontend — `OsSleepSettingsBanner` component

**Files:**
- Create: `client/src/components/power/OsSleepSettingsBanner.tsx`

- [ ] **Step 1: Create the component**

Create `client/src/components/power/OsSleepSettingsBanner.tsx`:

```tsx
/**
 * OS Sleep Settings Banner
 *
 * Read-only card at the top of the Sleep page. Surfaces OS-level sleep
 * triggers (logind, sleep.conf, masked targets) so users understand which
 * sleep behaviour BaluHost actually owns. No edit functionality.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle2, Info, RefreshCw, ShieldAlert } from 'lucide-react';

import {
  getOsSleepSettings,
  type OsSleepIssue,
  type OsSleepReport,
  type OsSleepSeverity,
} from '../../api/sleep';

const ICON_FOR: Record<OsSleepSeverity, typeof AlertTriangle> = {
  info: Info,
  warning: AlertTriangle,
  error: ShieldAlert,
};

const COLOR_FOR: Record<OsSleepSeverity, string> = {
  info: 'text-slate-300',
  warning: 'text-amber-400',
  error: 'text-red-400',
};

function IssueLine({ issue }: { issue: OsSleepIssue }) {
  const { t } = useTranslation('system');
  const Icon = ICON_FOR[issue.severity];
  const colorClass = COLOR_FOR[issue.severity];
  const text = t(`sleep.osSettings.issue.${issue.key}`, { defaultValue: issue.message });
  return (
    <div className="flex items-start gap-2 text-sm">
      <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${colorClass}`} />
      <div>
        <span className="text-slate-200">{text}</span>
        {issue.detail && (
          <p className="mt-0.5 text-xs text-slate-400">{issue.detail}</p>
        )}
      </div>
    </div>
  );
}

function DetailsTable({ report }: { report: OsSleepReport }) {
  const { t } = useTranslation('system');
  const rows: Array<[string, string]> = [];
  for (const [k, v] of Object.entries(report.logind)) rows.push([`logind.${k}`, v]);
  for (const [k, v] of Object.entries(report.sleep_conf)) rows.push([`sleep.${k}`, v]);
  for (const [k, v] of Object.entries(report.targets)) rows.push([`targets.${k}`, v]);
  return (
    <details className="mt-3 group">
      <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200 select-none">
        {t('sleep.osSettings.detailsToggle')}
      </summary>
      <div className="mt-2 space-y-1 pl-4 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="text-slate-500 font-mono">{k}</span>
            <span className="text-slate-300 font-mono">= {v}</span>
          </div>
        ))}
        {report.sources.length > 0 && (
          <div className="pt-2 text-slate-500">
            {t('sleep.osSettings.sources')}: {report.sources.join(', ')}
          </div>
        )}
      </div>
    </details>
  );
}

export function OsSleepSettingsBanner() {
  const { t } = useTranslation('system');
  const [report, setReport] = useState<OsSleepReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (force = false) => {
    if (force) setRefreshing(true);
    setError(null);
    try {
      const data = await getOsSleepSettings(force);
      setReport(data);
    } catch {
      setError(t('sleep.osSettings.loadFailed'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [t]);

  useEffect(() => {
    load(false);
  }, [load]);

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-4 sm:p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-5 w-1/3 bg-slate-700/50 rounded" />
          <div className="h-4 w-2/3 bg-slate-700/40 rounded" />
        </div>
      </div>
    );
  }

  // Hide entirely on unsupported platforms (no banner, no placeholder).
  if (report && !report.platform_supported && !error) {
    return null;
  }

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-medium text-white">{t('sleep.osSettings.title')}</h4>
        <button
          type="button"
          onClick={() => load(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs text-slate-400 hover:text-slate-200 hover:bg-slate-700/40 transition-colors disabled:opacity-60"
          aria-label={t('sleep.osSettings.refresh')}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          {t('sleep.osSettings.refresh')}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-sm">
          <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-red-400" />
          <span className="text-slate-200">{error}</span>
        </div>
      )}

      {report && !error && (
        <>
          {report.issues.length === 0 ? (
            <div className="flex items-start gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-emerald-400" />
              <span className="text-slate-200">{t('sleep.osSettings.allClear')}</span>
            </div>
          ) : (
            <div className="space-y-2">
              {report.issues.map((issue) => (
                <IssueLine key={issue.key} issue={issue} />
              ))}
            </div>
          )}
          <DetailsTable report={report} />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/power/OsSleepSettingsBanner.tsx
git commit -m "feat(sleep): OsSleepSettingsBanner component"
```

---

## Task 11: Frontend — mount the banner on the Sleep page

**Files:**
- Modify: `client/src/pages/SleepMode.tsx`

- [ ] **Step 1: Add the component as the first child**

Replace the contents of `client/src/pages/SleepMode.tsx` with:

```tsx
/**
 * Sleep Mode Page
 *
 * Combines the sleep mode control panel, core operating hours configuration,
 * legacy sleep config, and history into a single page rendered as a tab in
 * SystemControlPage.
 */

import { OsSleepSettingsBanner } from '../components/power/OsSleepSettingsBanner';
import { SleepModePanel } from '../components/power/SleepModePanel';
import { AlwaysAwakePanel } from '../components/power/AlwaysAwakePanel';
import { CoreUptimePanel } from '../components/power/CoreUptimePanel';
import { SleepConfigPanel } from '../components/power/SleepConfigPanel';
import { SleepHistoryTable } from '../components/power/SleepHistoryTable';

export default function SleepMode() {
  return (
    <div className="space-y-6">
      <OsSleepSettingsBanner />
      <SleepModePanel />
      <AlwaysAwakePanel />
      <CoreUptimePanel />
      <SleepConfigPanel />
      <SleepHistoryTable />
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add client/src/pages/SleepMode.tsx
git commit -m "feat(sleep): mount OsSleepSettingsBanner at top of Sleep page"
```

---

## Task 12: Frontend — `AlwaysAwakePanel` custom datetime button + popover

**Files:**
- Modify: `client/src/components/power/AlwaysAwakePanel.tsx`

This is the largest single edit. Read the file end-to-end before editing.

- [ ] **Step 1: Read the current `AlwaysAwakePanel`**

Open `client/src/components/power/AlwaysAwakePanel.tsx` to understand the existing optimistic-update pattern (`setPreset` lines 116-141) and the preset inference block (lines 58-81). Match those patterns when extending.

- [ ] **Step 2: Replace the file contents**

Replace `client/src/components/power/AlwaysAwakePanel.tsx` with:

```tsx
/**
 * Always-Awake panel.
 *
 * Master toggle + optional expiry presets (1h/4h/8h/permanent) plus a
 * custom datetime picker capped at 7 days.
 * Auto-saves all changes; manual Sleep/Suspend on the server side
 * automatically clears the override.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { Coffee, Clock, X } from 'lucide-react';
import {
  getSleepConfig,
  getSleepStatus,
  updateSleepConfig,
} from '../../api/sleep';

type Preset = '1h' | '4h' | '8h' | 'permanent' | 'custom';

const PRESET_HOURS: Record<Exclude<Preset, 'permanent' | 'custom'>, number> = {
  '1h': 1,
  '4h': 4,
  '8h': 8,
};

const MIN_HORIZON_MS = 5 * 60 * 1000;        // 5 minutes
const MAX_HORIZON_MS = 7 * 24 * 3600 * 1000; // 7 days

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  // Within the next 7 days: "DD.MM. HH:mm". Beyond (shouldn't happen with the cap)
  // we still render the full date.
  const ddmm = d.toLocaleDateString([], { day: '2-digit', month: '2-digit' });
  const hhmm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `${ddmm} ${hhmm}`;
}

function formatRemaining(seconds: number): string {
  if (seconds < 0) return '0m';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/** Convert a Date into the value format expected by <input type="datetime-local"> in the user's local TZ. */
function toLocalInputValue(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function AlwaysAwakePanel() {
  const { t } = useTranslation('system');
  const [enabled, setEnabled] = useState(false);
  const [until, setUntil] = useState<string | null>(null);
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [coreUptimeEnabled, setCoreUptimeEnabled] = useState(false);
  const [activePreset, setActivePreset] = useState<Preset | null>(null);
  const [loading, setLoading] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerValue, setPickerValue] = useState<string>('');
  const [pickerError, setPickerError] = useState<string | null>(null);
  const tickRef = useRef<number | null>(null);
  const pickerRef = useRef<HTMLDivElement | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [cfg, status] = await Promise.all([getSleepConfig(), getSleepStatus()]);
      setEnabled(cfg.always_awake_enabled ?? false);
      setUntil(cfg.always_awake_until ?? null);
      setExpiresIn(status.always_awake?.expires_in_seconds ?? null);
      setScheduleEnabled(cfg.schedule_enabled);
      setCoreUptimeEnabled(cfg.core_uptime_enabled ?? false);

      if (!cfg.always_awake_enabled) {
        setActivePreset(null);
      } else if (cfg.always_awake_until == null) {
        setActivePreset('permanent');
      } else {
        const remaining = status.always_awake?.expires_in_seconds ?? 0;
        const candidates: Array<[Preset, number]> = [
          ['1h', 1 * 3600],
          ['4h', 4 * 3600],
          ['8h', 8 * 3600],
        ];
        let best: Preset | null = null;
        let bestDiff = 5 * 60;
        for (const [p, sec] of candidates) {
          const diff = Math.abs(remaining - sec);
          if (diff <= bestDiff) {
            bestDiff = diff;
            best = p;
          }
        }
        setActivePreset(best ?? 'custom');
      }
    } catch {
      toast.error(t('sleep.alwaysAwake.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (expiresIn === null) {
      if (tickRef.current) window.clearInterval(tickRef.current);
      return;
    }
    tickRef.current = window.setInterval(() => {
      setExpiresIn((prev) => (prev === null ? null : Math.max(0, prev - 1)));
    }, 1000);
    return () => {
      if (tickRef.current) window.clearInterval(tickRef.current);
    };
  }, [expiresIn !== null]);

  useEffect(() => {
    if (expiresIn === 0) {
      setExpiresIn(null);
      refresh();
    }
  }, [expiresIn, refresh]);

  // Close popover on outside click / Escape.
  useEffect(() => {
    if (!pickerOpen) return;
    const onDown = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setPickerOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPickerOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [pickerOpen]);

  const setPreset = async (preset: Exclude<Preset, 'custom'>) => {
    const newUntil =
      preset === 'permanent'
        ? null
        : new Date(Date.now() + PRESET_HOURS[preset] * 3600 * 1000).toISOString();
    const previousEnabled = enabled;
    const previousUntil = until;
    const previousExpiresIn = expiresIn;
    const previousActivePreset = activePreset;
    setEnabled(true);
    setUntil(newUntil);
    setExpiresIn(newUntil ? PRESET_HOURS[preset as keyof typeof PRESET_HOURS] * 3600 : null);
    setActivePreset(preset);
    try {
      await updateSleepConfig({
        always_awake_enabled: true,
        always_awake_until: newUntil,
      });
    } catch (err) {
      setEnabled(previousEnabled);
      setUntil(previousUntil);
      setExpiresIn(previousExpiresIn);
      setActivePreset(previousActivePreset);
      toast.error(err instanceof Error ? err.message : t('sleep.alwaysAwake.saveFailed'));
    }
  };

  const setCustomPreset = async (localValue: string) => {
    const target = new Date(localValue);
    if (Number.isNaN(target.getTime())) {
      setPickerError(t('sleep.alwaysAwake.pickerErrorPast'));
      return;
    }
    const delta = target.getTime() - Date.now();
    if (delta < MIN_HORIZON_MS) {
      setPickerError(t('sleep.alwaysAwake.pickerErrorPast'));
      return;
    }
    if (delta > MAX_HORIZON_MS) {
      setPickerError(t('sleep.alwaysAwake.pickerErrorMax'));
      return;
    }

    const newUntil = target.toISOString();
    const previousEnabled = enabled;
    const previousUntil = until;
    const previousExpiresIn = expiresIn;
    const previousActivePreset = activePreset;
    setEnabled(true);
    setUntil(newUntil);
    setExpiresIn(Math.floor(delta / 1000));
    setActivePreset('custom');
    setPickerOpen(false);
    setPickerError(null);
    try {
      await updateSleepConfig({
        always_awake_enabled: true,
        always_awake_until: newUntil,
      });
    } catch (err) {
      setEnabled(previousEnabled);
      setUntil(previousUntil);
      setExpiresIn(previousExpiresIn);
      setActivePreset(previousActivePreset);
      toast.error(err instanceof Error ? err.message : t('sleep.alwaysAwake.saveFailed'));
    }
  };

  const openPicker = () => {
    const seed =
      activePreset === 'custom' && until
        ? new Date(until)
        : new Date(Date.now() + 4 * 3600 * 1000); // default seed: now+4h
    setPickerValue(toLocalInputValue(seed));
    setPickerError(null);
    setPickerOpen(true);
  };

  const handleCancel = async () => {
    const prev = { enabled, until, expiresIn, activePreset };
    setEnabled(false);
    setUntil(null);
    setExpiresIn(null);
    setActivePreset(null);
    try {
      await updateSleepConfig({ always_awake_enabled: false });
    } catch (err) {
      setEnabled(prev.enabled);
      setUntil(prev.until);
      setExpiresIn(prev.expiresIn);
      setActivePreset(prev.activePreset);
      toast.error(err instanceof Error ? err.message : t('sleep.alwaysAwake.saveFailed'));
    }
  };

  const handleMasterToggle = async () => {
    if (enabled) {
      await handleCancel();
    } else {
      await setPreset('permanent');
    }
  };

  if (loading) {
    return (
      <div className="card border-slate-700/50 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700/50 rounded w-1/3" />
          <div className="h-24 bg-slate-700/50 rounded" />
        </div>
      </div>
    );
  }

  const minLocal = toLocalInputValue(new Date(Date.now() + MIN_HORIZON_MS));
  const maxLocal = toLocalInputValue(new Date(Date.now() + MAX_HORIZON_MS));

  return (
    <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Coffee className="h-4 w-4 text-amber-400" />
          <div>
            <h4 className="text-sm font-medium text-white">{t('sleep.alwaysAwake.title')}</h4>
            <p className="mt-0.5 text-xs text-slate-400">{t('sleep.alwaysAwake.description')}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleMasterToggle}
          className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors ${
            enabled ? 'bg-amber-500' : 'bg-slate-600'
          }`}
          aria-label={t('sleep.alwaysAwake.masterToggle')}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
              enabled ? 'translate-x-5.5 ml-0.5' : 'translate-x-0.5'
            } mt-0.5`}
          />
        </button>
      </div>

      {enabled && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-xs text-amber-200">
            <Clock className="h-4 w-4 shrink-0" />
            {until && expiresIn !== null ? (
              <span>{t('sleep.alwaysAwake.activeUntil', {
                time: formatTime(until),
                remaining: formatRemaining(expiresIn),
              })}</span>
            ) : (
              <span>{t('sleep.alwaysAwake.activePermanent')}</span>
            )}
            <button
              type="button"
              onClick={handleCancel}
              className="ml-auto inline-flex items-center gap-1 rounded px-2 py-0.5 text-slate-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
            >
              <X className="h-3.5 w-3.5" />
              {t('sleep.alwaysAwake.cancel')}
            </button>
          </div>

          {(scheduleEnabled || coreUptimeEnabled) && until && (
            <div className="rounded border border-amber-500/20 bg-amber-500/10 p-2 text-xs text-amber-300">
              {t('sleep.alwaysAwake.hintScheduleResumes', { time: formatTime(until) })}
            </div>
          )}
          {(scheduleEnabled || coreUptimeEnabled) && !until && (
            <div className="rounded border border-blue-500/20 bg-blue-500/10 p-2 text-xs text-blue-300">
              {t('sleep.alwaysAwake.hintPermanentClearToResume')}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        {(['1h', '4h', '8h', 'permanent'] as const).map((p) => {
          const isActive = enabled && activePreset === p;
          const labelKey =
            p === 'permanent'
              ? 'sleep.alwaysAwake.presetPermanent'
              : (`sleep.alwaysAwake.preset${p}` as const);
          return (
            <button
              key={p}
              type="button"
              onClick={() => setPreset(p)}
              className={`min-w-[3.5rem] rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? 'bg-amber-500/30 text-amber-200 border border-amber-500/50'
                  : 'bg-slate-800/40 text-slate-400 border border-slate-700/40 hover:text-amber-300 hover:border-amber-500/30'
              }`}
            >
              {t(labelKey)}
            </button>
          );
        })}

        <div className="relative" ref={pickerRef}>
          <button
            type="button"
            onClick={openPicker}
            className={`min-w-[3.5rem] rounded px-3 py-1.5 text-xs font-medium transition-colors ${
              enabled && activePreset === 'custom'
                ? 'bg-amber-500/30 text-amber-200 border border-amber-500/50'
                : 'bg-slate-800/40 text-slate-400 border border-slate-700/40 hover:text-amber-300 hover:border-amber-500/30'
            }`}
          >
            {enabled && activePreset === 'custom' && until
              ? t('sleep.alwaysAwake.activeCustom', { datetime: formatDateTime(until) })
              : t('sleep.alwaysAwake.presetCustom')}
          </button>

          {pickerOpen && (
            <div className="absolute z-10 mt-2 right-0 sm:right-auto sm:left-0 w-72 rounded-md border border-slate-700/60 bg-slate-900 p-3 shadow-xl space-y-2">
              <label className="block text-xs text-slate-300">
                {t('sleep.alwaysAwake.pickerLabel')}
                <input
                  type="datetime-local"
                  className="mt-1 block w-full rounded border border-slate-700/60 bg-slate-800 px-2 py-1 text-sm text-slate-100"
                  min={minLocal}
                  max={maxLocal}
                  value={pickerValue}
                  onChange={(e) => {
                    setPickerValue(e.target.value);
                    setPickerError(null);
                  }}
                />
              </label>
              {pickerError && (
                <p className="text-xs text-red-400">{pickerError}</p>
              )}
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setPickerOpen(false)}
                  className="rounded px-2 py-1 text-xs text-slate-400 hover:text-slate-200"
                >
                  {t('sleep.alwaysAwake.pickerCancel')}
                </button>
                <button
                  type="button"
                  onClick={() => setCustomPreset(pickerValue)}
                  className="rounded px-2 py-1 text-xs font-medium bg-amber-500/30 text-amber-200 border border-amber-500/50 hover:bg-amber-500/40"
                >
                  {t('sleep.alwaysAwake.pickerApply')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd client && npx tsc --noEmit`

Expected: no errors.

- [ ] **Step 4: Build the frontend**

Run: `cd client && npm run build`

Expected: successful build with no warnings about missing icons or unresolved imports.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/power/AlwaysAwakePanel.tsx
git commit -m "feat(sleep): always-awake custom datetime button (capped 7d)"
```

---

## Task 13: End-to-end verification (manual smoke)

**Files:** none new

This is the manual smoke gate — type checks and build are not enough.

- [ ] **Step 1: Start dev mode**

Run (from project root):

```bash
python start_dev.py
```

Open `http://localhost:5173`, log in as `admin` / `DevMode2024`. Navigate to **System Control → Hardware → Sleep**.

- [ ] **Step 2: Verify the OS-Sleep banner**

On Windows dev mode the banner should NOT appear. The page should show the existing 5 panels in their current order. Inspect the browser console — no errors.

If running on a Linux dev environment with `/etc/systemd` present, the banner should appear above `SleepModePanel` with at least the "all clear" line, and `[Refresh ⟳]` should reload the report.

- [ ] **Step 3: Verify the custom datetime button**

In the AlwaysAwakePanel preset row, the 5th button labelled "Bis Datum…" should appear after `Dauerhaft`. Click it:

1. A popover opens below/beside the button containing a datetime input with `min` ≈ now+5min, `max` ≈ now+7d.
2. Pick a datetime ~2 days in the future, click **Übernehmen**.
3. The popover closes, the button switches to "Bis DD.MM. HH:mm" with active styling, and the activity row shows "Aktiv bis HH:mm (in 1d 23h)".
4. Reload the page. The button still shows the custom value with active styling.
5. Re-open the popover, change the value to "1 hour from now", click **Übernehmen**. The chip should switch from `custom` back to `1h` (the inference promotes the closest matching preset within 5min).
6. Click the master toggle off, then on. State resets to `Dauerhaft` as before.

- [ ] **Step 4: Verify the 7-day cap**

Open the popover, manually type a date 8 days in the future. Click **Übernehmen** — the inline error "Maximal 7 Tage in der Zukunft" appears, the popover stays open, no API call fires. (Inspect the Network tab to confirm.)

If you hit `Übernehmen` very fast and still get to the API: backend returns 422 and the optimistic state reverts with a toast. Either path is acceptable.

- [ ] **Step 5: Run the full backend test suite (final gate)**

Run: `cd backend && python -m pytest -q`

Expected: same pass/fail surface as before the branch (per memory `feedback_run_tests_before_pr`).

- [ ] **Step 6: Final commit (if any fix-ups were needed)**

If steps 1-5 pass without changes, no commit needed. If you found a bug:

```bash
git add -A
git commit -m "fix(sleep): smoke fixes for os-settings banner / custom datetime"
```

---

## Self-Review

Spec coverage:
- §3 page layout ordering: Task 11.
- §4.2 inspector helpers + platform guard: Task 1.
- §4.2 classifier rules table: Task 2 (one key per `IdleAction` variant — verified in tests).
- §4.2 cache + resilience: Task 3.
- §4.3 endpoint: Task 5.
- §4.4 banner UI: Task 10.
- §4.5 API client types: Task 8.
- §5 backend 7-day cap: Task 4 (validator) and Task 6 (route-level integration test).
- §5.3 frontend custom button + popover: Task 12.
- §5.4 native popover (no Radix): Task 12 (uses `mousedown` listener + Escape).
- §6 i18n keys: Task 9.
- §7 data flow: covered implicitly by Tasks 3, 5, 12 (test traces match spec).
- §8 error handling: Tasks 3, 10, 12.
- §9 testing strategy: Tasks 1-7 cover all listed backend tests; Task 13 covers frontend manual smoke.

Placeholder scan: no `TBD`/`TODO`. Two locations call out conditional handling that the engineer must adapt:
- Task 4 step 4 mentions "if `timedelta` is already imported, drop the alias" — this is a real choice the engineer must make, not a placeholder.
- Task 5 step 1 instructs adopting the project's existing fixture names — necessary because the writer of this plan can't see those fixtures from the task summary.

Type/name consistency:
- `OsSleepIssue` (dataclass) vs `OsSleepIssueModel` (Pydantic) — distinct on purpose; they cross at the route handler in Task 5 step 3.
- `inspect_os_sleep(force_refresh=...)` keyword used consistently in Tasks 1, 3, 5.
- Cache helpers `_cache_get` / `_cache_put` / `_cache_clear` referenced consistently across Tasks 1 and 3.
- Frontend `Preset` union evolves from `'1h' | '4h' | '8h' | 'permanent'` to add `'custom'` in Task 12; `setPreset` is narrowed via `Exclude<Preset, 'custom'>` to preserve type safety.
