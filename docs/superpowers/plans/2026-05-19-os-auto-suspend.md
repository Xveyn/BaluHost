# OS Auto-Suspend Bidirectional Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose OS-level auto-suspend-at-idle settings (KDE PowerDevil / GNOME gsd-power / systemd-logind) bidirectionally — readable and writable from both the OS-native panels and the BaluHost web UI.

**Architecture:** Read-through (no DB copy). Backend detects the active power manager at request time and dispatches to one of three adapters (Kde/Gnome/Logind) behind a common protocol. systemd writes go through a sudoers-whitelisted helper script; KDE/GNOME writes happen directly under the running `sven` UID 1000.

**Tech Stack:** FastAPI + Pydantic v2, Python 3.13, subprocess for `gsettings`/`qdbus6`/`sudo`, plain Bash for the helper, React + TypeScript + Vitest.

**Spec:** `docs/superpowers/specs/2026-05-19-os-auto-suspend-bidirectional-design.md`

**URL prefix note:** `sleep.router` is mounted at `/system/sleep` (`backend/app/api/routes/__init__.py:68`), so new routes are `GET/PUT /api/system/sleep/os-auto-suspend`. The spec used the shorter conceptual form `/api/sleep/...` — this plan uses the actual full URL.

---

## File Structure

### Backend (new)
- `backend/app/services/power/os_auto_suspend.py` — protocol, 3 adapters (KdeAdapter, GnomeAdapter, LogindAdapter), ActivePmDetector with 30s cache, service helpers
- `backend/tests/services/power/test_os_auto_suspend_adapters.py` — adapter unit tests
- `backend/tests/services/power/test_os_auto_suspend_detector.py` — detector tests
- `backend/tests/api/test_os_auto_suspend_route.py` — route integration tests
- `backend/tests/services/power/test_os_sleep_inspector_idle_backends.py` — inspector-extension tests

### Backend (modified)
- `backend/app/schemas/sleep.py` — add `OsAutoSuspendAction`, `OsAutoSuspendResponse`, `OsAutoSuspendUpdate`
- `backend/app/api/routes/sleep.py` — add two route handlers + audit logging
- `backend/app/services/power/os_sleep_inspector.py` — extend report with KDE/GNOME idle issues
- `backend/tests/test_sleep_schemas.py` — schema validation tests

### Frontend (new)
- `client/src/components/power/OsAutoSuspendCard.tsx` — the card component
- `client/src/components/power/__tests__/OsAutoSuspendCard.test.tsx` — Vitest tests

### Frontend (modified)
- `client/src/api/sleep.ts` — add types + `getOsAutoSuspend()` + `setOsAutoSuspend()`
- `client/src/i18n/locales/de/system.json` — German strings under `sleep.osAutoSuspend.*`
- `client/src/i18n/locales/en/system.json` — English strings
- `client/src/pages/SleepMode.tsx` — render new card next to `OsSleepSettingsBanner`

### Deploy (new)
- `deploy/install/scripts/baluhost-write-logind-idle.sh` — root-privileged helper
- `deploy/install/scripts/test-baluhost-write-logind-idle.sh` — Bash test runner
- `deploy/install/templates/sudoers-baluhost-power` — sudoers template
- `deploy/install/modules/13-power-helpers.sh` — installer module

### Deploy (modified)
- `deploy/install/install.sh` — register `13-power-helpers` in MODULES array

---

## Tasks

### Task 1: Pydantic schemas

**Files:**
- Modify: `backend/app/schemas/sleep.py` (append at end before final blank lines)
- Test: `backend/tests/test_sleep_schemas.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_sleep_schemas.py`:

```python
class TestOsAutoSuspendSchemas:
    def test_update_rejects_timeout_zero(self):
        from app.schemas.sleep import OsAutoSuspendUpdate
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            OsAutoSuspendUpdate(enabled=True, timeout_minutes=0, action="suspend")

    def test_update_rejects_timeout_too_large(self):
        from app.schemas.sleep import OsAutoSuspendUpdate
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            OsAutoSuspendUpdate(enabled=True, timeout_minutes=1441, action="suspend")

    def test_update_accepts_valid_payload(self):
        from app.schemas.sleep import OsAutoSuspendUpdate, OsAutoSuspendAction
        u = OsAutoSuspendUpdate(enabled=True, timeout_minutes=15, action="suspend")
        assert u.timeout_minutes == 15
        assert u.action == OsAutoSuspendAction.SUSPEND

    def test_action_enum_values(self):
        from app.schemas.sleep import OsAutoSuspendAction
        assert OsAutoSuspendAction.SUSPEND == "suspend"
        assert OsAutoSuspendAction.HIBERNATE == "hibernate"
        assert OsAutoSuspendAction.IGNORE == "ignore"

    def test_response_supports_unsupported_platform(self):
        from app.schemas.sleep import OsAutoSuspendResponse
        r = OsAutoSuspendResponse(
            supported=False, source="none", backend_label="",
            enabled=False, timeout_minutes=0, action="ignore",
        )
        assert r.supported is False
        assert r.timeout_minutes == 0
```

(If `pytest` is not yet imported in the test file, add `import pytest` at the top.)

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_sleep_schemas.py::TestOsAutoSuspendSchemas -v
```
Expected: 5 failures with `ImportError: cannot import name 'OsAutoSuspendUpdate' from 'app.schemas.sleep'`.

- [ ] **Step 3: Implement the schemas**

Append to `backend/app/schemas/sleep.py` (after the existing `CoreUptimeWindowResponse` block, before final blank line):

```python
# ---------------------------------------------------------------------------
# OS Auto-Suspend (bidirectional)
# ---------------------------------------------------------------------------

class OsAutoSuspendAction(str, Enum):
    """Action mapped from active power manager. `ignore` = no auto-suspend."""
    SUSPEND = "suspend"
    HIBERNATE = "hibernate"
    IGNORE = "ignore"


class OsAutoSuspendResponse(BaseModel):
    """Read-out of auto-suspend setting from the currently active power manager."""
    supported: bool = Field(..., description="False on Windows / when no backend selectable")
    source: Literal["kde", "gnome", "logind", "none"] = Field(..., description="Active backend")
    backend_label: str = Field(default="", description="Human label, e.g. 'KDE PowerDevil'")
    enabled: bool = Field(..., description="Derived: action != ignore AND timeout > 0")
    timeout_minutes: int = Field(..., ge=0, le=1440, description="0 only when supported=False")
    action: OsAutoSuspendAction


class OsAutoSuspendUpdate(BaseModel):
    """Bidirectional write. enabled=False writes 'ignore' (or removes section in KDE)."""
    enabled: bool
    timeout_minutes: int = Field(ge=1, le=1440)
    action: OsAutoSuspendAction
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_sleep_schemas.py::TestOsAutoSuspendSchemas -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/schemas/sleep.py backend/tests/test_sleep_schemas.py
git commit -m "feat(sleep): add OsAutoSuspend schemas (response, update, action enum)"
```

---

### Task 2: Service module skeleton — protocol + value type

**Files:**
- Create: `backend/app/services/power/os_auto_suspend.py`
- Create: `backend/tests/services/power/test_os_auto_suspend_adapters.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/power/test_os_auto_suspend_adapters.py`:

```python
"""Tests for os_auto_suspend adapters and shared types."""
from app.services.power import os_auto_suspend as oas


class TestAutoSuspendValue:
    def test_construct_and_compare(self):
        v1 = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        v2 = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        assert v1 == v2
        assert v1.timeout_minutes == 15

    def test_frozen(self):
        import dataclasses
        v = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        try:
            v.timeout_minutes = 30  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("expected FrozenInstanceError")
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py -v
```
Expected: ImportError / ModuleNotFoundError on `os_auto_suspend`.

- [ ] **Step 3: Implement the module skeleton**

Create `backend/app/services/power/os_auto_suspend.py`:

```python
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
    name: Literal["kde", "gnome", "logind"]
    label: str

    def is_available(self) -> bool: ...
    def read(self) -> AutoSuspendValue: ...
    def write(self, value: AutoSuspendValue) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_adapters.py
git commit -m "feat(sleep): scaffold os_auto_suspend module with shared protocol"
```

---

### Task 3: LogindAdapter — read

**Files:**
- Modify: `backend/app/services/power/os_auto_suspend.py`
- Modify: `backend/tests/services/power/test_os_auto_suspend_adapters.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_os_auto_suspend_adapters.py`:

```python
class TestLogindAdapterRead:
    def _make_adapter(self, monkeypatch, tmp_path, conf_text=""):
        conf = tmp_path / "logind.conf"
        conf.write_text(conf_text)
        monkeypatch.setattr(oas, "_LOGIND_CONF", conf)
        monkeypatch.setattr(oas, "_LOGIND_DROPIN_DIRS", (tmp_path / "logind.conf.d",))
        return oas.LogindAdapter()

    def test_read_empty_file_means_disabled(self, monkeypatch, tmp_path):
        a = self._make_adapter(monkeypatch, tmp_path, "")
        v = a.read()
        assert v.enabled is False
        assert v.action == "ignore"

    def test_read_idle_action_suspend(self, monkeypatch, tmp_path):
        a = self._make_adapter(
            monkeypatch, tmp_path,
            "[Login]\nIdleAction=suspend\nIdleActionSec=15min\n",
        )
        v = a.read()
        assert v.enabled is True
        assert v.action == "suspend"
        assert v.timeout_minutes == 15

    def test_read_idle_action_sec_raw_seconds(self, monkeypatch, tmp_path):
        a = self._make_adapter(
            monkeypatch, tmp_path,
            "[Login]\nIdleAction=hibernate\nIdleActionSec=900\n",
        )
        v = a.read()
        assert v.action == "hibernate"
        assert v.timeout_minutes == 15

    def test_read_idle_action_sec_seconds_suffix(self, monkeypatch, tmp_path):
        a = self._make_adapter(
            monkeypatch, tmp_path,
            "[Login]\nIdleAction=suspend\nIdleActionSec=900s\n",
        )
        v = a.read()
        assert v.timeout_minutes == 15

    def test_read_drop_in_overrides_base(self, monkeypatch, tmp_path):
        conf = tmp_path / "logind.conf"
        conf.write_text("[Login]\nIdleAction=ignore\n")
        drop_dir = tmp_path / "logind.conf.d"
        drop_dir.mkdir()
        (drop_dir / "30-baluhost.conf").write_text(
            "[Login]\nIdleAction=suspend\nIdleActionSec=10min\n"
        )
        monkeypatch.setattr(oas, "_LOGIND_CONF", conf)
        monkeypatch.setattr(oas, "_LOGIND_DROPIN_DIRS", (drop_dir,))
        v = oas.LogindAdapter().read()
        assert v.action == "suspend"
        assert v.timeout_minutes == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestLogindAdapterRead -v
```
Expected: 5 failures (no `LogindAdapter` yet).

- [ ] **Step 3: Implement LogindAdapter.read + INI helpers**

Append to `backend/app/services/power/os_auto_suspend.py`:

```python
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
    """Parse '15min', '900s', or '900' → minutes (int). Returns 0 on parse error."""
    s = raw.strip().lower()
    if not s:
        return 0
    if s.endswith("min"):
        try:
            return int(s[:-3])
        except ValueError:
            return 0
    if s.endswith("s"):
        try:
            return int(s[:-1]) // 60
        except ValueError:
            return 0
    try:
        return int(s) // 60
    except ValueError:
        return 0


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
        raise NotImplementedError  # implemented in Task 4
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestLogindAdapterRead -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_adapters.py
git commit -m "feat(sleep): LogindAdapter.read with drop-in merge"
```

---

### Task 4: LogindAdapter — write via sudo helper

**Files:**
- Modify: `backend/app/services/power/os_auto_suspend.py`
- Modify: `backend/tests/services/power/test_os_auto_suspend_adapters.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_os_auto_suspend_adapters.py`:

```python
class TestLogindAdapterWrite:
    def test_write_invokes_sudo_helper_with_correct_args(self, monkeypatch):
        captured: dict = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        oas.LogindAdapter().write(
            oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        )
        assert captured["args"] == [
            "sudo", "-n", oas._HELPER_PATH,
            "--timeout", "900", "--action", "suspend",
        ]
        assert captured["kwargs"]["check"] is True
        assert captured["kwargs"]["timeout"] == oas._SUDO_TIMEOUT_SECONDS

    def test_write_disabled_passes_ignore(self, monkeypatch):
        captured: dict = {}
        def fake_run(args, **kwargs):
            captured["args"] = args
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        oas.LogindAdapter().write(
            oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore")
        )
        assert "--action" in captured["args"]
        assert captured["args"][captured["args"].index("--action") + 1] == "ignore"

    def test_write_raises_on_helper_failure(self, monkeypatch):
        def fake_run(args, **kwargs):
            raise subprocess.CalledProcessError(2, args, stderr="bad args")
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        import pytest
        with pytest.raises(RuntimeError, match="logind helper failed"):
            oas.LogindAdapter().write(
                oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
            )
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestLogindAdapterWrite -v
```
Expected: 3 failures (`NotImplementedError`).

- [ ] **Step 3: Implement LogindAdapter.write**

Replace the `NotImplementedError` body of `LogindAdapter.write` in `os_auto_suspend.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestLogindAdapterWrite -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_adapters.py
git commit -m "feat(sleep): LogindAdapter.write via sudo helper"
```

---

### Task 5: KdeAdapter — read

**Files:**
- Modify: `backend/app/services/power/os_auto_suspend.py`
- Modify: `backend/tests/services/power/test_os_auto_suspend_adapters.py`

**Context:** KDE Plasma 6 stores PowerDevil config in `~/.config/powerdevilrc` using nested `[GroupA][GroupB]` headers. The section we care about is `[AC][SuspendSession]` with `idleTime` (ms) and `suspendType` (int: 1=suspend, 2=hibernate, other=non-sleep).

- [ ] **Step 1: Write the failing tests**

Append to `test_os_auto_suspend_adapters.py`:

```python
class TestKdeAdapterRead:
    def _make_adapter(self, monkeypatch, tmp_path, rc_text=None):
        rc = tmp_path / "powerdevilrc"
        if rc_text is not None:
            rc.write_text(rc_text)
        monkeypatch.setattr(oas, "_KDE_POWERDEVIL_RC", rc)
        return oas.KdeAdapter()

    def test_read_file_missing_returns_defaults(self, monkeypatch, tmp_path):
        a = self._make_adapter(monkeypatch, tmp_path, rc_text=None)
        v = a.read()
        assert v.enabled is False
        assert v.action == "suspend"
        assert v.timeout_minutes == 15

    def test_read_basic_suspend_15min(self, monkeypatch, tmp_path):
        rc = "[AC][SuspendSession]\nidleTime=900000\nsuspendType=1\n"
        a = self._make_adapter(monkeypatch, tmp_path, rc)
        v = a.read()
        assert v.enabled is True
        assert v.action == "suspend"
        assert v.timeout_minutes == 15

    def test_read_hibernate(self, monkeypatch, tmp_path):
        rc = "[AC][SuspendSession]\nidleTime=1800000\nsuspendType=2\n"
        a = self._make_adapter(monkeypatch, tmp_path, rc)
        v = a.read()
        assert v.action == "hibernate"
        assert v.timeout_minutes == 30

    def test_read_section_missing_means_disabled(self, monkeypatch, tmp_path):
        rc = "[Migration]\nMigratedProfilesToPlasma6=powerdevilrc\n"
        a = self._make_adapter(monkeypatch, tmp_path, rc)
        v = a.read()
        assert v.enabled is False

    def test_read_unknown_suspend_type_maps_to_ignore(self, monkeypatch, tmp_path, caplog):
        rc = "[AC][SuspendSession]\nidleTime=900000\nsuspendType=32\n"
        a = self._make_adapter(monkeypatch, tmp_path, rc)
        with caplog.at_level("WARNING"):
            v = a.read()
        assert v.action == "ignore"
        assert any("KDE suspendType" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestKdeAdapterRead -v
```
Expected: 5 failures.

- [ ] **Step 3: Implement KdeAdapter.read**

Append to `os_auto_suspend.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestKdeAdapterRead -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_adapters.py
git commit -m "feat(sleep): KdeAdapter.read parses ~/.config/powerdevilrc"
```

---

### Task 6: KdeAdapter — write (read-modify-write, atomic)

**Files:**
- Modify: `backend/app/services/power/os_auto_suspend.py`
- Modify: `backend/tests/services/power/test_os_auto_suspend_adapters.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_os_auto_suspend_adapters.py`:

```python
class TestKdeAdapterWrite:
    def _adapter(self, monkeypatch, tmp_path):
        rc = tmp_path / "powerdevilrc"
        monkeypatch.setattr(oas, "_KDE_POWERDEVIL_RC", rc)
        monkeypatch.setattr(oas, "_kde_signal_reload", lambda: None)
        return oas.KdeAdapter(), rc

    def test_write_creates_file_when_missing(self, monkeypatch, tmp_path):
        a, rc = self._adapter(monkeypatch, tmp_path)
        a.write(oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend"))
        text = rc.read_text()
        assert "[AC][SuspendSession]" in text
        assert "idleTime=900000" in text
        assert "suspendType=1" in text

    def test_write_hibernate_writes_suspendtype_2(self, monkeypatch, tmp_path):
        a, rc = self._adapter(monkeypatch, tmp_path)
        a.write(oas.AutoSuspendValue(enabled=True, timeout_minutes=30, action="hibernate"))
        assert "suspendType=2" in rc.read_text()
        assert "idleTime=1800000" in rc.read_text()

    def test_write_disabled_removes_section_only(self, monkeypatch, tmp_path):
        a, rc = self._adapter(monkeypatch, tmp_path)
        rc.write_text(
            "[Battery][SuspendSession]\nidleTime=300000\nsuspendType=1\n"
            "[AC][SuspendSession]\nidleTime=900000\nsuspendType=1\n"
        )
        a.write(oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore"))
        text = rc.read_text()
        assert "[AC][SuspendSession]" not in text
        assert "[Battery][SuspendSession]" in text
        assert "idleTime=300000" in text

    def test_write_preserves_other_sections(self, monkeypatch, tmp_path):
        a, rc = self._adapter(monkeypatch, tmp_path)
        rc.write_text(
            "[Migration]\nMigratedProfilesToPlasma6=powerdevilrc\n"
            "[Battery][SuspendSession]\nidleTime=300000\nsuspendType=1\n"
        )
        a.write(oas.AutoSuspendValue(enabled=True, timeout_minutes=20, action="suspend"))
        text = rc.read_text()
        assert "MigratedProfilesToPlasma6=powerdevilrc" in text
        assert "[Battery][SuspendSession]" in text
        assert "idleTime=300000" in text
        assert "[AC][SuspendSession]" in text
        assert "idleTime=1200000" in text

    def test_write_reload_failure_does_not_raise(self, monkeypatch, tmp_path):
        rc = tmp_path / "powerdevilrc"
        monkeypatch.setattr(oas, "_KDE_POWERDEVIL_RC", rc)
        def boom():
            raise RuntimeError("dbus down")
        monkeypatch.setattr(oas, "_kde_signal_reload", boom)
        oas.KdeAdapter().write(
            oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        )
        assert rc.exists()  # write itself succeeded
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestKdeAdapterWrite -v
```
Expected: 5 failures.

- [ ] **Step 3: Implement KdeAdapter.write**

In `os_auto_suspend.py`, add helpers and replace the `NotImplementedError`:

```python
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
```

Replace `KdeAdapter.write`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestKdeAdapterWrite -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_adapters.py
git commit -m "feat(sleep): KdeAdapter.write (atomic, preserves other sections)"
```

---

### Task 7: GnomeAdapter — read + write

**Files:**
- Modify: `backend/app/services/power/os_auto_suspend.py`
- Modify: `backend/tests/services/power/test_os_auto_suspend_adapters.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_os_auto_suspend_adapters.py`:

```python
class TestGnomeAdapter:
    def test_read_basic(self, monkeypatch):
        from types import SimpleNamespace
        calls: list = []
        def fake_run(args, **kwargs):
            calls.append(args)
            if "sleep-inactive-ac-timeout" in args:
                return SimpleNamespace(returncode=0, stdout="900\n", stderr="")
            if "sleep-inactive-ac-type" in args:
                return SimpleNamespace(returncode=0, stdout="'suspend'\n", stderr="")
            raise AssertionError(f"unexpected gsettings call: {args}")
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        v = oas.GnomeAdapter().read()
        assert v.enabled is True
        assert v.timeout_minutes == 15
        assert v.action == "suspend"

    def test_read_unknown_action_maps_to_ignore(self, monkeypatch, caplog):
        from types import SimpleNamespace
        def fake_run(args, **kwargs):
            if "timeout" in args[-1]:
                return SimpleNamespace(returncode=0, stdout="600\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="'blank'\n", stderr="")
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        with caplog.at_level("WARNING"):
            v = oas.GnomeAdapter().read()
        assert v.action == "ignore"
        assert any("GNOME sleep-inactive-ac-type" in r.message for r in caplog.records)

    def test_read_zero_timeout_means_disabled(self, monkeypatch):
        from types import SimpleNamespace
        def fake_run(args, **kwargs):
            if "timeout" in args[-1]:
                return SimpleNamespace(returncode=0, stdout="0\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="'suspend'\n", stderr="")
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        v = oas.GnomeAdapter().read()
        assert v.enabled is False

    def test_write_calls_both_gsettings_set(self, monkeypatch):
        calls: list = []
        def fake_run(args, **kwargs):
            calls.append(args)
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        oas.GnomeAdapter().write(
            oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        )
        assert len(calls) == 2
        timeout_call = next(c for c in calls if "sleep-inactive-ac-timeout" in c)
        type_call = next(c for c in calls if "sleep-inactive-ac-type" in c)
        assert timeout_call[-1] == "900"
        assert type_call[-1] == "suspend"

    def test_write_disabled_uses_nothing(self, monkeypatch):
        calls: list = []
        def fake_run(args, **kwargs):
            calls.append(args)
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        oas.GnomeAdapter().write(
            oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore")
        )
        type_call = next(c for c in calls if "sleep-inactive-ac-type" in c)
        assert type_call[-1] == "nothing"
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestGnomeAdapter -v
```
Expected: 5 failures.

- [ ] **Step 3: Implement GnomeAdapter**

Append to `os_auto_suspend.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_adapters.py::TestGnomeAdapter -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_adapters.py
git commit -m "feat(sleep): GnomeAdapter via gsettings"
```

---

### Task 8: ActivePmDetector

**Files:**
- Modify: `backend/app/services/power/os_auto_suspend.py`
- Create: `backend/tests/services/power/test_os_auto_suspend_detector.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/power/test_os_auto_suspend_detector.py`:

```python
"""Tests for ActivePmDetector."""
import sys
from app.services.power import os_auto_suspend as oas


class TestDetector:
    def setup_method(self):
        oas._detector_cache_clear()  # reset cache before each test

    def test_returns_none_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert oas.detect_active_backend() is None

    def test_prefers_kde_when_dbus_says_yes(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: svc == "org.kde.Solid.PowerManagement")
        b = oas.detect_active_backend()
        assert b is not None
        assert b.name == "kde"

    def test_falls_back_to_gnome(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: svc == "org.gnome.SettingsDaemon.Power")
        b = oas.detect_active_backend()
        assert b is not None
        assert b.name == "gnome"

    def test_falls_back_to_logind_when_no_de(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: False)
        etc_systemd = tmp_path / "systemd"
        etc_systemd.mkdir()
        monkeypatch.setattr(oas, "_SYSTEMD_DIR", etc_systemd)
        b = oas.detect_active_backend()
        assert b is not None
        assert b.name == "logind"

    def test_returns_none_when_nothing_detected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: False)
        monkeypatch.setattr(oas, "_SYSTEMD_DIR", tmp_path / "nope")
        assert oas.detect_active_backend() is None

    def test_dbus_timeout_treated_as_unavailable(self, monkeypatch):
        import subprocess as sp
        monkeypatch.setattr(sys, "platform", "linux")
        def fake_run(args, **kwargs):
            raise sp.TimeoutExpired(args, timeout=2.0)
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        # Should not raise; should return None or fall through to logind
        oas.detect_active_backend()  # just no exception

    def test_cache_within_ttl(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        calls = {"n": 0}
        def probe(svc):
            calls["n"] += 1
            return svc == "org.kde.Solid.PowerManagement"
        monkeypatch.setattr(oas, "_probe_dbus_service", probe)
        oas.detect_active_backend()
        oas.detect_active_backend()
        oas.detect_active_backend()
        # one call set, second probe attempted (gnome), then KDE wins
        # but with caching, the second/third top-level calls should skip probing.
        # Strict: total probe calls after 3 detect calls should equal the count from 1 detect.
        first_run_count = calls["n"]
        assert first_run_count > 0
        # Force-call once more to confirm no growth
        prev = calls["n"]
        oas.detect_active_backend()
        assert calls["n"] == prev
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_detector.py -v
```
Expected: 7 failures (no `_probe_dbus_service`, `detect_active_backend`, `_SYSTEMD_DIR`, `_detector_cache_clear`).

- [ ] **Step 3: Implement the detector**

Append to `os_auto_suspend.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_detector.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_detector.py
git commit -m "feat(sleep): ActivePmDetector with D-Bus probes and 30s cache"
```

---

### Task 9: Service-layer functions

**Files:**
- Modify: `backend/app/services/power/os_auto_suspend.py`
- Create: `backend/tests/services/power/test_os_auto_suspend_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/power/test_os_auto_suspend_service.py`:

```python
"""Tests for os_auto_suspend service-layer helpers."""
from app.services.power import os_auto_suspend as oas
from app.schemas.sleep import OsAutoSuspendUpdate, OsAutoSuspendAction


class FakeBackend:
    name = "kde"
    label = "KDE PowerDevil"
    def __init__(self, value):
        self._value = value
        self.writes = []
    def is_available(self): return True
    def read(self): return self._value
    def write(self, v):
        self.writes.append(v)
        self._value = v


class TestServiceLayer:
    def test_get_unsupported_when_no_backend(self, monkeypatch):
        monkeypatch.setattr(oas, "detect_active_backend", lambda: None)
        resp = oas.get_os_auto_suspend()
        assert resp.supported is False
        assert resp.source == "none"
        assert resp.timeout_minutes == 0

    def test_get_reads_from_active_backend(self, monkeypatch):
        fb = FakeBackend(oas.AutoSuspendValue(enabled=True, timeout_minutes=20, action="suspend"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        resp = oas.get_os_auto_suspend()
        assert resp.supported is True
        assert resp.source == "kde"
        assert resp.backend_label == "KDE PowerDevil"
        assert resp.enabled is True
        assert resp.timeout_minutes == 20

    def test_set_writes_and_returns_readback(self, monkeypatch):
        fb = FakeBackend(oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="suspend"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        update = OsAutoSuspendUpdate(
            enabled=True, timeout_minutes=30, action=OsAutoSuspendAction.HIBERNATE
        )
        resp = oas.set_os_auto_suspend(update)
        assert len(fb.writes) == 1
        assert fb.writes[0].timeout_minutes == 30
        assert fb.writes[0].action == "hibernate"
        assert resp.enabled is True
        assert resp.action == "hibernate"

    def test_set_raises_when_no_backend(self, monkeypatch):
        monkeypatch.setattr(oas, "detect_active_backend", lambda: None)
        import pytest
        with pytest.raises(RuntimeError, match="no active power manager"):
            oas.set_os_auto_suspend(OsAutoSuspendUpdate(
                enabled=True, timeout_minutes=15, action=OsAutoSuspendAction.SUSPEND
            ))
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_service.py -v
```
Expected: 4 failures.

- [ ] **Step 3: Implement service-layer functions**

Append to `os_auto_suspend.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_auto_suspend_service.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_auto_suspend.py backend/tests/services/power/test_os_auto_suspend_service.py
git commit -m "feat(sleep): os_auto_suspend service-layer get/set"
```

---

### Task 10: API routes (GET + PUT)

**Files:**
- Modify: `backend/app/api/routes/sleep.py` (append new routes at end)
- Create: `backend/tests/api/test_os_auto_suspend_route.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_os_auto_suspend_route.py`. Look at `backend/tests/api/test_sleep_os_settings_route.py` for the fixture pattern in use, but the core skeleton is:

```python
"""Integration tests for /api/system/sleep/os-auto-suspend routes."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.power import os_auto_suspend as oas
from app.schemas.sleep import OsAutoSuspendResponse, OsAutoSuspendAction


@pytest.fixture
def admin_headers(admin_token):  # admin_token fixture exists in conftest.py
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def user_headers(user_token):  # ditto
    return {"Authorization": f"Bearer {user_token}"}


class TestOsAutoSuspendGet:
    def test_requires_auth(self):
        with TestClient(app) as c:
            r = c.get("/api/system/sleep/os-auto-suspend")
            assert r.status_code in (401, 403)

    def test_requires_admin(self, user_headers):
        with TestClient(app) as c:
            r = c.get("/api/system/sleep/os-auto-suspend", headers=user_headers)
            assert r.status_code == 403

    def test_get_returns_supported_false_when_no_backend(self, monkeypatch, admin_headers):
        monkeypatch.setattr(oas, "get_os_auto_suspend", lambda: OsAutoSuspendResponse(
            supported=False, source="none", backend_label="",
            enabled=False, timeout_minutes=0, action=OsAutoSuspendAction.IGNORE,
        ))
        with TestClient(app) as c:
            r = c.get("/api/system/sleep/os-auto-suspend", headers=admin_headers)
            assert r.status_code == 200
            body = r.json()
            assert body["supported"] is False
            assert body["source"] == "none"


class TestOsAutoSuspendPut:
    def test_requires_admin(self, user_headers):
        with TestClient(app) as c:
            r = c.put(
                "/api/system/sleep/os-auto-suspend",
                headers=user_headers,
                json={"enabled": True, "timeout_minutes": 15, "action": "suspend"},
            )
            assert r.status_code == 403

    def test_validates_timeout_zero(self, admin_headers):
        with TestClient(app) as c:
            r = c.put(
                "/api/system/sleep/os-auto-suspend",
                headers=admin_headers,
                json={"enabled": True, "timeout_minutes": 0, "action": "suspend"},
            )
            assert r.status_code == 422

    def test_validates_timeout_too_large(self, admin_headers):
        with TestClient(app) as c:
            r = c.put(
                "/api/system/sleep/os-auto-suspend",
                headers=admin_headers,
                json={"enabled": True, "timeout_minutes": 2000, "action": "suspend"},
            )
            assert r.status_code == 422

    def test_happy_path_returns_readback(self, monkeypatch, admin_headers):
        def fake_set(update):
            return OsAutoSuspendResponse(
                supported=True, source="kde", backend_label="KDE PowerDevil",
                enabled=update.enabled, timeout_minutes=update.timeout_minutes,
                action=update.action,
            )
        monkeypatch.setattr(oas, "set_os_auto_suspend", fake_set)
        with TestClient(app) as c:
            r = c.put(
                "/api/system/sleep/os-auto-suspend",
                headers=admin_headers,
                json={"enabled": True, "timeout_minutes": 20, "action": "suspend"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["timeout_minutes"] == 20
            assert body["source"] == "kde"

    def test_returns_503_when_no_backend(self, monkeypatch, admin_headers):
        def fake_set(update):
            raise RuntimeError("no active power manager detected")
        monkeypatch.setattr(oas, "set_os_auto_suspend", fake_set)
        with TestClient(app) as c:
            r = c.put(
                "/api/system/sleep/os-auto-suspend",
                headers=admin_headers,
                json={"enabled": True, "timeout_minutes": 15, "action": "suspend"},
            )
            assert r.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/api/test_os_auto_suspend_route.py -v
```
Expected: 7 failures (404 or 405 because routes don't exist).

- [ ] **Step 3: Implement routes**

In `backend/app/api/routes/sleep.py`, add the imports if missing (`OsAutoSuspendResponse`, `OsAutoSuspendUpdate`) and append the two routes after the existing `get_os_sleep_settings` route:

```python
from app.schemas.sleep import OsAutoSuspendResponse, OsAutoSuspendUpdate  # add to existing import block
from app.services.power import os_auto_suspend  # add new import


@router.get("/os-auto-suspend", response_model=OsAutoSuspendResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_os_auto_suspend_route(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
) -> OsAutoSuspendResponse:
    """Read OS-level auto-suspend setting from the active power manager (admin)."""
    return os_auto_suspend.get_os_auto_suspend()


@router.put("/os-auto-suspend", response_model=OsAutoSuspendResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_os_auto_suspend_route(
    request: Request, response: Response,
    body: OsAutoSuspendUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> OsAutoSuspendResponse:
    """Write OS-level auto-suspend setting to the active power manager (admin)."""
    try:
        previous = os_auto_suspend.get_os_auto_suspend()
        result = os_auto_suspend.set_os_auto_suspend(body)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    get_audit_logger_db().log_security_event(
        action="os_auto_suspend_update",
        user=current_user.username,
        resource=result.source,
        details={
            "previous": {
                "enabled": previous.enabled,
                "timeout_minutes": previous.timeout_minutes,
                "action": previous.action.value,
            },
            "new": {
                "enabled": result.enabled,
                "timeout_minutes": result.timeout_minutes,
                "action": result.action.value,
            },
        },
        success=True,
        db=db,
    )
    logger.info("OS auto-suspend updated by %s (source=%s)", current_user.username, result.source)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/api/test_os_auto_suspend_route.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add backend/app/api/routes/sleep.py backend/tests/api/test_os_auto_suspend_route.py
git commit -m "feat(sleep): add GET/PUT /os-auto-suspend routes with audit log"
```

---

### Task 11: Sudoers template

**Files:**
- Create: `deploy/install/templates/sudoers-baluhost-power`

- [ ] **Step 1: Create the template**

Create `deploy/install/templates/sudoers-baluhost-power` with content:

```
# BaluHost: allow the baluhost service user to write logind idle settings
# via the locked-down helper script. Scoped to one binary; args wildcard
# allowed but the helper validates strictly.
#
# Installed by deploy/install/modules/13-power-helpers.sh; uses %BALUHOST_USER%
# template variable replaced by process_template().

%BALUHOST_USER% ALL=(root) NOPASSWD: /usr/local/lib/baluhost/baluhost-write-logind-idle *
```

- [ ] **Step 2: Verify with visudo locally (if Linux available; on Windows skip)**

On Linux:
```
visudo -cf deploy/install/templates/sudoers-baluhost-power
```
Expected (after template substitution): `parsed OK`.

On Windows / no Linux: defer to actual installer run on prod.

- [ ] **Step 3: Commit**

```
git add deploy/install/templates/sudoers-baluhost-power
git commit -m "feat(deploy): sudoers template for baluhost power helper"
```

---

### Task 12: Helper script

**Files:**
- Create: `deploy/install/scripts/baluhost-write-logind-idle.sh`

- [ ] **Step 1: Create the helper script**

Create `deploy/install/scripts/baluhost-write-logind-idle.sh`:

```bash
#!/bin/bash
# BaluHost: write logind idle-action settings via systemd drop-in.
#
# Usage: baluhost-write-logind-idle --timeout <seconds> --action <suspend|hibernate|ignore>
#
# Run as root via sudo NOPASSWD. Validates all inputs strictly. Writes
# /etc/systemd/logind.conf.d/baluhost-idle.conf atomically and reloads
# systemd-logind. On failure, restores the previous file (if any).

set -euo pipefail

CONF_PATH="/etc/systemd/logind.conf.d/baluhost-idle.conf"
CONF_DIR="$(dirname "$CONF_PATH")"
MIN_TIMEOUT=60
MAX_TIMEOUT=86400

usage() {
    echo "Usage: $0 --timeout <seconds> --action <suspend|hibernate|ignore>" >&2
    exit 2
}

TIMEOUT=""
ACTION=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout)
            shift
            [[ $# -eq 0 ]] && usage
            TIMEOUT="$1"
            ;;
        --action)
            shift
            [[ $# -eq 0 ]] && usage
            ACTION="$1"
            ;;
        *)
            echo "ERROR: unexpected argument: $1" >&2
            usage
            ;;
    esac
    shift
done

# Validate timeout
if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --timeout must be a positive integer (seconds)" >&2
    exit 2
fi
if (( TIMEOUT < MIN_TIMEOUT || TIMEOUT > MAX_TIMEOUT )); then
    echo "ERROR: --timeout must be between $MIN_TIMEOUT and $MAX_TIMEOUT seconds" >&2
    exit 2
fi

# Validate action
case "$ACTION" in
    suspend|hibernate|ignore) ;;
    *)
        echo "ERROR: --action must be one of: suspend, hibernate, ignore" >&2
        exit 2
        ;;
esac

# Ensure target dir exists
mkdir -p "$CONF_DIR"

# Back up current config if it exists (for rollback)
BACKUP=""
if [[ -f "$CONF_PATH" ]]; then
    BACKUP="$(mktemp --tmpdir baluhost-idle-backup.XXXXXX)"
    cp "$CONF_PATH" "$BACKUP"
fi

# Atomic write via temp file in same FS
TMP="$(mktemp "${CONF_DIR}/.baluhost-idle.XXXXXX")"
cat > "$TMP" <<EOF
# Managed by BaluHost — do not edit by hand.
# Written by /usr/local/lib/baluhost/baluhost-write-logind-idle
[Login]
IdleAction=$ACTION
IdleActionSec=${TIMEOUT}s
EOF
chmod 644 "$TMP"
mv "$TMP" "$CONF_PATH"

# Reload logind
if ! systemctl reload systemd-logind 2>/dev/null; then
    # Rollback if reload fails
    if [[ -n "$BACKUP" ]]; then
        mv "$BACKUP" "$CONF_PATH"
        systemctl reload systemd-logind || true
    else
        rm -f "$CONF_PATH"
    fi
    echo "ERROR: systemctl reload systemd-logind failed; rolled back" >&2
    exit 1
fi

# Success: discard backup
[[ -n "$BACKUP" ]] && rm -f "$BACKUP"
exit 0
```

Make executable:
```
chmod +x deploy/install/scripts/baluhost-write-logind-idle.sh
```

- [ ] **Step 2: Smoke-test the script's arg parsing locally with a mocked systemctl**

Create a tiny shell sanity check (run from repo root):

```bash
# Create a temporary stub for systemctl
TMP=$(mktemp -d)
cat > "$TMP/systemctl" <<'EOF'
#!/bin/bash
echo "stub-systemctl $*" >&2
exit 0
EOF
chmod +x "$TMP/systemctl"

# Try a happy path with a fake config path
PATH="$TMP:$PATH" \
    CONF_PATH=/tmp/baluhost-idle-test.conf \
    bash -c '
        # Override CONF_PATH by patching the script copy in a tmpdir
        cp deploy/install/scripts/baluhost-write-logind-idle.sh /tmp/h.sh
        sed -i "s|/etc/systemd/logind.conf.d/baluhost-idle.conf|/tmp/baluhost-idle-test.conf|" /tmp/h.sh
        bash /tmp/h.sh --timeout 900 --action suspend
        cat /tmp/baluhost-idle-test.conf
    '
```
Expected: `parsed OK` and the file contents containing `IdleAction=suspend\nIdleActionSec=900s`.

(This is only a manual smoke. The exhaustive automated tests come in Task 13.)

- [ ] **Step 3: Commit**

```
git add deploy/install/scripts/baluhost-write-logind-idle.sh
git commit -m "feat(deploy): sudo-helper to write logind idle settings"
```

---

### Task 13: Helper script automated tests

**Files:**
- Create: `deploy/install/scripts/test-baluhost-write-logind-idle.sh`

- [ ] **Step 1: Create the test runner**

Create `deploy/install/scripts/test-baluhost-write-logind-idle.sh`:

```bash
#!/bin/bash
# Automated tests for baluhost-write-logind-idle. Runs in CI on
# ubuntu-latest; no real root needed because we override the config
# path and PATH-stub systemctl.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL="$SCRIPT_DIR/baluhost-write-logind-idle.sh"

if [[ ! -f "$ORIGINAL" ]]; then
    echo "FAIL: helper script not found at $ORIGINAL" >&2
    exit 1
fi

FAILS=0
PASSES=0

# Each case runs the helper with a patched copy that writes to /tmp.
prepare() {
    local conf="$1"
    HELPER="$(mktemp)"
    sed "s|/etc/systemd/logind.conf.d/baluhost-idle.conf|$conf|g" "$ORIGINAL" > "$HELPER"
    chmod +x "$HELPER"
    # Stub systemctl
    STUB_DIR="$(mktemp -d)"
    cat > "$STUB_DIR/systemctl" <<'EOF'
#!/bin/bash
exit 0
EOF
    chmod +x "$STUB_DIR/systemctl"
    export PATH="$STUB_DIR:$PATH"
}

cleanup() {
    rm -f "$HELPER" "$1"
    rm -rf "$STUB_DIR"
    # Restore PATH (CI restarts shell anyway)
}

assert_exit() {
    local name="$1"; shift
    local expected="$1"; shift
    "$@"
    local rc=$?
    if [[ $rc -eq $expected ]]; then
        echo "PASS: $name (exit=$rc)"
        PASSES=$((PASSES+1))
    else
        echo "FAIL: $name (expected exit=$expected, got $rc)"
        FAILS=$((FAILS+1))
    fi
}

# Case 1: no args
prepare "/tmp/h1.conf"
assert_exit "no-args" 2 bash "$HELPER"
cleanup "/tmp/h1.conf"

# Case 2: non-integer timeout
prepare "/tmp/h2.conf"
assert_exit "non-int-timeout" 2 bash "$HELPER" --timeout abc --action suspend
cleanup "/tmp/h2.conf"

# Case 3: too-small timeout
prepare "/tmp/h3.conf"
assert_exit "small-timeout" 2 bash "$HELPER" --timeout 30 --action suspend
cleanup "/tmp/h3.conf"

# Case 4: invalid action
prepare "/tmp/h4.conf"
assert_exit "bad-action" 2 bash "$HELPER" --timeout 900 --action poweroff
cleanup "/tmp/h4.conf"

# Case 5: happy path
prepare "/tmp/h5.conf"
assert_exit "happy-suspend" 0 bash "$HELPER" --timeout 900 --action suspend
if grep -q "IdleAction=suspend" /tmp/h5.conf && grep -q "IdleActionSec=900s" /tmp/h5.conf; then
    echo "PASS: happy-suspend file content"
    PASSES=$((PASSES+1))
else
    echo "FAIL: happy-suspend file content"
    cat /tmp/h5.conf
    FAILS=$((FAILS+1))
fi
cleanup "/tmp/h5.conf"

# Case 6: happy hibernate
prepare "/tmp/h6.conf"
assert_exit "happy-hibernate" 0 bash "$HELPER" --timeout 1800 --action hibernate
grep -q "IdleAction=hibernate" /tmp/h6.conf && grep -q "IdleActionSec=1800s" /tmp/h6.conf \
    && { echo "PASS: happy-hibernate file content"; PASSES=$((PASSES+1)); } \
    || { echo "FAIL: happy-hibernate file content"; FAILS=$((FAILS+1)); }
cleanup "/tmp/h6.conf"

echo
echo "Total: $PASSES passed, $FAILS failed"
[[ $FAILS -eq 0 ]]
```

Make executable:
```
chmod +x deploy/install/scripts/test-baluhost-write-logind-idle.sh
```

- [ ] **Step 2: Run tests**

```
bash deploy/install/scripts/test-baluhost-write-logind-idle.sh
```
Expected: `Total: 7 passed, 0 failed` (or comparable; exit code 0).

If on Windows: skip — runs only on Linux. Mark as "verified-on-prod-or-CI".

- [ ] **Step 3: Commit**

```
git add deploy/install/scripts/test-baluhost-write-logind-idle.sh
git commit -m "test(deploy): bash test runner for logind idle helper"
```

---

### Task 14: Installer module 13-power-helpers

**Files:**
- Create: `deploy/install/modules/13-power-helpers.sh`
- Modify: `deploy/install/install.sh` (add `13-power-helpers` to MODULES array)

- [ ] **Step 1: Create the module**

Create `deploy/install/modules/13-power-helpers.sh`:

```bash
#!/bin/bash
# BaluHost Install - Module 13: Power Helpers
# Installs the logind idle helper + sudoers entry for the BaluHost service user.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

HELPER_SRC="$SCRIPT_DIR/scripts/baluhost-write-logind-idle.sh"
HELPER_DEST_DIR="/usr/local/lib/baluhost"
HELPER_DEST="$HELPER_DEST_DIR/baluhost-write-logind-idle"
SUDOERS_TEMPLATE="$SCRIPT_DIR/templates/sudoers-baluhost-power"
SUDOERS_DEST="/etc/sudoers.d/baluhost-power"

log_step "Power Helpers"

require_root

# Install helper
log_info "Installing $HELPER_DEST..."
mkdir -p "$HELPER_DEST_DIR"
cp "$HELPER_SRC" "$HELPER_DEST"
chmod 0755 "$HELPER_DEST"
chown root:root "$HELPER_DEST"

# Install sudoers (template-substituted)
log_info "Installing $SUDOERS_DEST..."
process_template "$SUDOERS_TEMPLATE" "$SUDOERS_DEST" \
    "BALUHOST_USER=$BALUHOST_USER"
chmod 0440 "$SUDOERS_DEST"
chown root:root "$SUDOERS_DEST"

# Validate
if ! visudo -cf "$SUDOERS_DEST" >/dev/null; then
    log_error "Generated sudoers file failed validation: $SUDOERS_DEST"
    rm -f "$SUDOERS_DEST"
    exit 1
fi

log_info "Power helpers installed successfully."
```

Make executable:
```
chmod +x deploy/install/modules/13-power-helpers.sh
```

- [ ] **Step 2: Register the module in install.sh**

In `deploy/install/install.sh`, find the `MODULES=(...)` array (around line 19) and add `"13-power-helpers"` after `"12-start-services"`:

```bash
readonly -a MODULES=(
    "01-preflight"
    "02-system-packages"
    "03-user-setup"
    "04-app-deploy"
    "05-python-venv"
    "06-postgresql"
    "07-env-generate"
    "08-database-migrate"
    "09-frontend-build"
    "10-systemd-services"
    "11-nginx"
    "12-start-services"
    "13-power-helpers"
)
```

**Important:** Check that the accidental empty line at the top of `install.sh` (above the shebang) is removed in the same edit, OR leave a clean restore separately.

- [ ] **Step 3: Dry-run / lint**

On Linux:
```
bash -n deploy/install/modules/13-power-helpers.sh
bash -n deploy/install/install.sh
```
Expected: no output (no syntax errors).

- [ ] **Step 4: Commit**

```
git add deploy/install/modules/13-power-helpers.sh deploy/install/install.sh
git commit -m "feat(deploy): install module 13-power-helpers (helper + sudoers)"
```

---

### Task 15: Inspector extension — surface KDE/GNOME idle as issues

**Files:**
- Modify: `backend/app/services/power/os_sleep_inspector.py`
- Create: `backend/tests/services/power/test_os_sleep_inspector_idle_backends.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/power/test_os_sleep_inspector_idle_backends.py`:

```python
"""Tests for the inspector's new KDE/GNOME idle-suspend surfacing."""
from app.services.power import os_sleep_inspector as ins
from app.services.power import os_auto_suspend as oas


class FakeBackend:
    def __init__(self, name, value, available=True):
        self.name = name
        self.label = f"fake-{name}"
        self._value = value
        self._available = available
    def is_available(self): return self._available
    def read(self): return self._value
    def write(self, v): pass


class TestInspectorIdleBackendIntegration:
    def test_kde_idle_suspend_emits_info_issue(self, monkeypatch):
        ins._cache_clear()
        fb = FakeBackend("kde", oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        # Make sure the inspector doesn't actually try to read systemd files
        monkeypatch.setattr(ins, "_SYSTEMD_DIR", __import__("pathlib").Path("/etc/systemd"))
        # In CI on ubuntu /etc/systemd exists, so we patch the reads to return empty
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        kde_issues = [i for i in report.issues if i.key.startswith("pm.kde")]
        assert len(kde_issues) == 1
        assert kde_issues[0].severity == "info"
        assert "15" in kde_issues[0].message or "15" in (kde_issues[0].detail or "")

    def test_gnome_idle_emits_info_issue(self, monkeypatch):
        ins._cache_clear()
        fb = FakeBackend("gnome", oas.AutoSuspendValue(enabled=True, timeout_minutes=20, action="hibernate"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        gnome_issues = [i for i in report.issues if i.key.startswith("pm.gnome")]
        assert len(gnome_issues) == 1
        assert "hibernate" in gnome_issues[0].message.lower() or "hibernate" in (gnome_issues[0].detail or "").lower()

    def test_logind_active_no_pm_issue(self, monkeypatch):
        ins._cache_clear()
        fb = FakeBackend("logind", oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        pm_issues = [i for i in report.issues if i.key.startswith("pm.")]
        assert pm_issues == []

    def test_disabled_pm_no_issue(self, monkeypatch):
        ins._cache_clear()
        fb = FakeBackend("kde", oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        pm_issues = [i for i in report.issues if i.key.startswith("pm.")]
        assert pm_issues == []
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_idle_backends.py -v
```
Expected: 2-4 failures (`assert len(kde_issues) == 1`).

- [ ] **Step 3: Implement inspector extension**

In `backend/app/services/power/os_sleep_inspector.py`:

1. At the top of the `inspect_os_sleep` function (after `if sys.platform != "linux"` early-return), keep the existing logic untouched.
2. After `issues = _classify(...)` and before `report = OsSleepReport(...)`, append:

```python
        # Surface KDE/GNOME idle suspend (logind is already covered by _classify)
        try:
            from app.services.power import os_auto_suspend as _oas  # noqa: PLC0415
            backend = _oas.detect_active_backend()
            if backend is not None and backend.name in ("kde", "gnome"):
                value = backend.read()
                if value.enabled:
                    issues.append(OsSleepIssue(
                        severity="info",
                        key=f"pm.{backend.name}.idle_suspend",
                        message=f"{backend.label}: idle suspend in {value.timeout_minutes} min ({value.action})",
                        detail=f"Managed via {backend.label} — BaluHost can edit it via OS-Auto-Suspend card",
                    ))
        except Exception as exc:
            logger.warning("inspector: failed to query auto-suspend backend: %s", exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_idle_backends.py -v
```
Expected: 4 passed.

Then re-run existing inspector tests to make sure nothing broke:

```
cd backend && python -m pytest tests/services/power/test_os_sleep_inspector_classifier.py tests/services/power/test_os_sleep_inspector_helpers.py tests/services/power/test_os_sleep_inspector_integration.py -v
```
Expected: all pre-existing tests still pass.

- [ ] **Step 5: Commit**

```
git add backend/app/services/power/os_sleep_inspector.py backend/tests/services/power/test_os_sleep_inspector_idle_backends.py
git commit -m "feat(sleep): inspector surfaces KDE/GNOME idle suspend as info issue"
```

---

### Task 16: Frontend API client

**Files:**
- Modify: `client/src/api/sleep.ts`

- [ ] **Step 1: Add types and API functions**

In `client/src/api/sleep.ts`, append after the existing `getOsSleepSettings` function (around line 263):

```typescript
// ============================================================================
// OS Auto-Suspend (bidirectional)
// ============================================================================

export type OsAutoSuspendAction = 'suspend' | 'hibernate' | 'ignore';
export type OsAutoSuspendSource = 'kde' | 'gnome' | 'logind' | 'none';

export interface OsAutoSuspendResponse {
  supported: boolean;
  source: OsAutoSuspendSource;
  backend_label: string;
  enabled: boolean;
  timeout_minutes: number;
  action: OsAutoSuspendAction;
}

export interface OsAutoSuspendUpdate {
  enabled: boolean;
  timeout_minutes: number;
  action: OsAutoSuspendAction;
}

export async function getOsAutoSuspend(): Promise<OsAutoSuspendResponse> {
  const response = await apiClient.get<OsAutoSuspendResponse>(
    '/api/system/sleep/os-auto-suspend',
  );
  return response.data;
}

export async function setOsAutoSuspend(
  body: OsAutoSuspendUpdate,
): Promise<OsAutoSuspendResponse> {
  const response = await apiClient.put<OsAutoSuspendResponse>(
    '/api/system/sleep/os-auto-suspend',
    body,
  );
  return response.data;
}
```

- [ ] **Step 2: Type-check**

```
cd client && npm run -s build
```
Expected: build passes. If there are type errors related to other code, leave them; only confirm the new file has no errors. Run `npx tsc --noEmit src/api/sleep.ts` for an isolated check (or `npx tsc --noEmit` for the whole project).

- [ ] **Step 3: Commit**

```
git add client/src/api/sleep.ts
git commit -m "feat(client): sleep.ts adds getOsAutoSuspend / setOsAutoSuspend"
```

---

### Task 17: i18n keys (de + en)

**Files:**
- Modify: `client/src/i18n/locales/de/system.json`
- Modify: `client/src/i18n/locales/en/system.json`

- [ ] **Step 1: Inspect existing namespace**

Open both files and find the existing `sleep` object. Look for `sleep.osSettings.*` keys (used by `OsSleepSettingsBanner.tsx`); the new keys go alongside under `sleep.osAutoSuspend.*`.

- [ ] **Step 2: Add German keys**

In `client/src/i18n/locales/de/system.json`, inside the `sleep` object next to `osSettings`:

```json
"osAutoSuspend": {
  "title": "Automatisches Aussetzen bei Inaktivität",
  "subtitle": "Wird vom aktiven Energiemanager verwaltet ({{source}}). Änderungen wirken sowohl hier als auch im OS-Panel.",
  "enabledLabel": "Aktiviert",
  "timeoutLabel": "Inaktivität (Minuten)",
  "actionLabel": "Aktion",
  "actionSuspend": "Aussetzen (Suspend)",
  "actionHibernate": "Ruhezustand (Hibernate)",
  "actionIgnore": "Nichts",
  "saveButton": "Speichern",
  "saving": "Speichern…",
  "saved": "Gespeichert",
  "loadError": "OS-Auto-Suspend konnte nicht gelesen werden",
  "saveError": "Speichern fehlgeschlagen",
  "unsupportedHidden": "",
  "badgeSource": {
    "kde": "KDE PowerDevil",
    "gnome": "GNOME gsd-power",
    "logind": "systemd-logind",
    "none": "Nicht verfügbar"
  }
}
```

- [ ] **Step 3: Add English keys**

Mirror in `client/src/i18n/locales/en/system.json`:

```json
"osAutoSuspend": {
  "title": "Auto-suspend on idle",
  "subtitle": "Managed by the active power manager ({{source}}). Edits apply both here and in the OS panel.",
  "enabledLabel": "Enabled",
  "timeoutLabel": "Idle timeout (minutes)",
  "actionLabel": "Action",
  "actionSuspend": "Suspend",
  "actionHibernate": "Hibernate",
  "actionIgnore": "Do nothing",
  "saveButton": "Save",
  "saving": "Saving…",
  "saved": "Saved",
  "loadError": "Failed to load OS auto-suspend setting",
  "saveError": "Save failed",
  "unsupportedHidden": "",
  "badgeSource": {
    "kde": "KDE PowerDevil",
    "gnome": "GNOME gsd-power",
    "logind": "systemd-logind",
    "none": "Not available"
  }
}
```

- [ ] **Step 4: Validate JSON**

```
cd client && node -e "require('./src/i18n/locales/de/system.json'); require('./src/i18n/locales/en/system.json'); console.log('OK')"
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```
git add client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json
git commit -m "feat(client): i18n keys for OsAutoSuspend (de + en)"
```

---

### Task 18: Frontend component — OsAutoSuspendCard

**Files:**
- Create: `client/src/components/power/OsAutoSuspendCard.tsx`

- [ ] **Step 1: Create the component**

Create `client/src/components/power/OsAutoSuspendCard.tsx`:

```tsx
/**
 * OS Auto-Suspend Card
 *
 * Bidirectional read/write of the currently active power manager's
 * idle-suspend setting (KDE PowerDevil, GNOME gsd-power, or systemd-logind).
 * Hidden on unsupported platforms.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Moon, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';

import {
  getOsAutoSuspend,
  setOsAutoSuspend,
  type OsAutoSuspendAction,
  type OsAutoSuspendResponse,
} from '../../api/sleep';

export function OsAutoSuspendCard() {
  const { t } = useTranslation('system');
  const [data, setData] = useState<OsAutoSuspendResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [timeoutMinutes, setTimeoutMinutes] = useState(15);
  const [action, setAction] = useState<OsAutoSuspendAction>('suspend');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getOsAutoSuspend();
      setData(res);
      setEnabled(res.enabled);
      setTimeoutMinutes(res.timeout_minutes || 15);
      setAction(res.action === 'ignore' ? 'suspend' : res.action);
    } catch {
      toast.error(t('sleep.osAutoSuspend.loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSave = async () => {
    setSaving(true);
    try {
      const res = await setOsAutoSuspend({
        enabled,
        timeout_minutes: timeoutMinutes,
        action,
      });
      setData(res);
      setEnabled(res.enabled);
      setTimeoutMinutes(res.timeout_minutes || 15);
      setAction(res.action === 'ignore' ? 'suspend' : res.action);
      toast.success(t('sleep.osAutoSuspend.saved'));
    } catch {
      toast.error(t('sleep.osAutoSuspend.saveError'));
    } finally {
      setSaving(false);
    }
  };

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

  if (!data || !data.supported) return null;

  const badgeLabel = t(`sleep.osAutoSuspend.badgeSource.${data.source}`);

  return (
    <div
      className="card border-slate-700/50 p-4 sm:p-6 space-y-3"
      data-testid="os-auto-suspend-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-medium text-white flex items-center gap-2">
            <Moon className="h-4 w-4 text-slate-300" />
            {t('sleep.osAutoSuspend.title')}
          </h4>
          <p className="text-xs text-slate-400 mt-1">
            {t('sleep.osAutoSuspend.subtitle', { source: data.backend_label })}
          </p>
        </div>
        <span
          className="inline-flex items-center rounded bg-slate-700/40 text-slate-300 text-xs px-2 py-0.5"
          data-testid="os-auto-suspend-source-badge"
        >
          {badgeLabel}
        </span>
      </div>

      <div className="space-y-3 pt-2">
        <label className="flex items-center gap-2 text-sm text-slate-200">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="rounded"
            data-testid="os-auto-suspend-enabled"
          />
          {t('sleep.osAutoSuspend.enabledLabel')}
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-sm text-slate-300">
            <span className="block mb-1">{t('sleep.osAutoSuspend.timeoutLabel')}</span>
            <input
              type="number"
              min={1}
              max={1440}
              value={timeoutMinutes}
              onChange={(e) => setTimeoutMinutes(Math.max(1, Math.min(1440, Number(e.target.value))))}
              disabled={!enabled}
              className="w-full rounded bg-slate-900/60 border border-slate-700 px-2 py-1 text-slate-100 disabled:opacity-50"
              data-testid="os-auto-suspend-timeout"
            />
          </label>

          <label className="block text-sm text-slate-300">
            <span className="block mb-1">{t('sleep.osAutoSuspend.actionLabel')}</span>
            <select
              value={action}
              onChange={(e) => setAction(e.target.value as OsAutoSuspendAction)}
              disabled={!enabled}
              className="w-full rounded bg-slate-900/60 border border-slate-700 px-2 py-1 text-slate-100 disabled:opacity-50"
              data-testid="os-auto-suspend-action"
            >
              <option value="suspend">{t('sleep.osAutoSuspend.actionSuspend')}</option>
              <option value="hibernate">{t('sleep.osAutoSuspend.actionHibernate')}</option>
            </select>
          </label>
        </div>

        <div className="flex items-center gap-2 pt-2">
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded bg-blue-600/80 hover:bg-blue-600 disabled:opacity-60 text-white text-sm px-3 py-1"
            data-testid="os-auto-suspend-save"
          >
            {saving ? t('sleep.osAutoSuspend.saving') : t('sleep.osAutoSuspend.saveButton')}
          </button>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading || saving}
            className="inline-flex items-center gap-1 rounded text-xs text-slate-400 hover:text-slate-200"
            aria-label="Reload"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + build**

```
cd client && npm run -s build
```
Expected: build succeeds (no errors in the new file).

- [ ] **Step 3: Commit**

```
git add client/src/components/power/OsAutoSuspendCard.tsx
git commit -m "feat(client): OsAutoSuspendCard component"
```

---

### Task 19: Frontend component tests

**Files:**
- Create: `client/src/components/power/__tests__/OsAutoSuspendCard.test.tsx`

- [ ] **Step 1: Write the tests**

Create `client/src/components/power/__tests__/OsAutoSuspendCard.test.tsx`:

```tsx
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../../../api/sleep', () => ({
  getOsAutoSuspend: vi.fn(),
  setOsAutoSuspend: vi.fn(),
}));
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, opts?: Record<string, unknown>) => {
    if (opts && 'source' in opts) return `${k}:${String(opts.source)}`;
    return k;
  } }),
}));

import { OsAutoSuspendCard } from '../OsAutoSuspendCard';
import * as sleepApi from '../../../api/sleep';

describe('OsAutoSuspendCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when supported=false', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: false,
      source: 'none',
      backend_label: '',
      enabled: false,
      timeout_minutes: 0,
      action: 'ignore',
    });
    const { container } = render(<OsAutoSuspendCard />);
    await waitFor(() => {
      expect(container.querySelector('[data-testid="os-auto-suspend-card"]')).toBeNull();
    });
  });

  it('renders source badge from response', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: true,
      timeout_minutes: 15,
      action: 'suspend',
    });
    render(<OsAutoSuspendCard />);
    await waitFor(() => {
      expect(screen.getByTestId('os-auto-suspend-source-badge')).toBeTruthy();
    });
    expect(screen.getByTestId('os-auto-suspend-source-badge').textContent).toContain('badgeSource.kde');
  });

  it('disables timeout/action when not enabled', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: false,
      timeout_minutes: 15,
      action: 'suspend',
    });
    render(<OsAutoSuspendCard />);
    await waitFor(() => {
      const t = screen.getByTestId('os-auto-suspend-timeout') as HTMLInputElement;
      expect(t.disabled).toBe(true);
    });
  });

  it('calls setOsAutoSuspend on save with current form values', async () => {
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: true,
      timeout_minutes: 15,
      action: 'suspend',
    });
    (sleepApi.setOsAutoSuspend as ReturnType<typeof vi.fn>).mockResolvedValue({
      supported: true,
      source: 'kde',
      backend_label: 'KDE PowerDevil',
      enabled: true,
      timeout_minutes: 20,
      action: 'hibernate',
    });
    render(<OsAutoSuspendCard />);
    await waitFor(() => screen.getByTestId('os-auto-suspend-save'));
    const timeoutInput = screen.getByTestId('os-auto-suspend-timeout') as HTMLInputElement;
    fireEvent.change(timeoutInput, { target: { value: '20' } });
    const actionSelect = screen.getByTestId('os-auto-suspend-action') as HTMLSelectElement;
    fireEvent.change(actionSelect, { target: { value: 'hibernate' } });
    fireEvent.click(screen.getByTestId('os-auto-suspend-save'));
    await waitFor(() => {
      expect(sleepApi.setOsAutoSuspend).toHaveBeenCalledWith({
        enabled: true,
        timeout_minutes: 20,
        action: 'hibernate',
      });
    });
  });

  it('shows error toast on load failure', async () => {
    const toast = (await import('react-hot-toast')).default;
    (sleepApi.getOsAutoSuspend as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    render(<OsAutoSuspendCard />);
    await waitFor(() => {
      expect((toast.error as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0);
    });
  });
});
```

- [ ] **Step 2: Run tests**

```
cd client && npx vitest run src/components/power/__tests__/OsAutoSuspendCard.test.tsx
```
Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```
git add client/src/components/power/__tests__/OsAutoSuspendCard.test.tsx
git commit -m "test(client): OsAutoSuspendCard component tests"
```

---

### Task 20: Integrate card into Sleep page

**Files:**
- Modify: `client/src/pages/SleepMode.tsx`

- [ ] **Step 1: Add the import + render**

In `client/src/pages/SleepMode.tsx` around line 9, add the import next to `OsSleepSettingsBanner`:

```tsx
import { OsAutoSuspendCard } from '../components/power/OsAutoSuspendCard';
```

And around line 19-20 (right after the existing `<OsSleepSettingsBanner />`), add:

```tsx
<OsSleepSettingsBanner />
<OsAutoSuspendCard />
```

- [ ] **Step 2: Build to verify**

```
cd client && npm run -s build
```
Expected: no errors.

- [ ] **Step 3: Manual visual check (dev mode if convenient)**

If a dev backend is available locally (`python start_dev.py`), open `http://localhost:5173`, log in as admin, go to Sleep page, confirm the new card renders next to the OS Sleep Settings banner. On Windows dev mode `supported=False` is likely → card is hidden (correct).

- [ ] **Step 4: Commit**

```
git add client/src/pages/SleepMode.tsx
git commit -m "feat(client): render OsAutoSuspendCard on Sleep page"
```

---

### Task 21: Full backend test suite

- [ ] **Step 1: Run all sleep/power tests**

```
cd backend && python -m pytest tests/test_sleep_schemas.py tests/services/power/ tests/api/test_os_auto_suspend_route.py tests/api/test_sleep_os_settings_route.py -v
```
Expected: all green.

- [ ] **Step 2: Run full pytest as a regression check**

```
cd backend && python -m pytest -x -q
```
Expected: all green. Any failures unrelated to this feature must be investigated separately — do NOT mark this task complete with red.

- [ ] **Step 3: No commit needed (verification only).** If failures appear in unrelated tests, open an issue and proceed.

---

### Task 22: Helper script test on Linux + frontend build verification

- [ ] **Step 1: Helper script tests (Linux)**

If working on Linux:
```
bash deploy/install/scripts/test-baluhost-write-logind-idle.sh
```
Expected: exit 0.

On Windows dev: skip; the same script runs in CI.

- [ ] **Step 2: Frontend full test suite**

```
cd client && npx vitest run
```
Expected: all green.

- [ ] **Step 3: Frontend build**

```
cd client && npm run -s build
```
Expected: build succeeds.

- [ ] **Step 4: Bash lint on installer files (if shellcheck available)**

```
shellcheck deploy/install/scripts/baluhost-write-logind-idle.sh deploy/install/modules/13-power-helpers.sh deploy/install/scripts/test-baluhost-write-logind-idle.sh
```
Expected: no errors. If shellcheck not installed: skip (CI may run it).

- [ ] **Step 5: No commit needed (verification).**

---

### Task 23: Prod smoke test + memory update

This task requires running commands on the production box (BaluNode). The implementer should ASK THE USER to run them and report back.

- [ ] **Step 1: Prep the installer run on prod**

Ask the user to deploy the new build via the normal deploy-production flow (PR → merge → workflow_dispatch). After deploy:

```
# As root on BaluNode:
sudo /opt/baluhost/deploy/install/install.sh --module 13-power-helpers
ls -l /usr/local/lib/baluhost/baluhost-write-logind-idle
ls -l /etc/sudoers.d/baluhost-power
sudo visudo -cf /etc/sudoers.d/baluhost-power
```
Expected: helper executable as root:root 0755; sudoers file 0440 root:root; `visudo -cf` says parsed OK.

- [ ] **Step 2: API smoke**

```
# As user sven on BaluNode:
TOKEN=<admin JWT>
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/system/sleep/os-auto-suspend | jq
```
Expected: `supported=true, source="kde", backend_label="KDE PowerDevil", enabled=false` (or whatever current KDE state).

- [ ] **Step 3: Bidirectional verification (5 minutes)**

```
# Set in KDE first via System Settings → Energieverwaltung → 30 min suspend, save.

# Read from BaluHost:
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/system/sleep/os-auto-suspend | jq
# → expect timeout_minutes=30, enabled=true

# Set via BaluHost:
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"enabled":true,"timeout_minutes":10,"action":"suspend"}' \
  http://localhost:8000/api/system/sleep/os-auto-suspend | jq
# → expect 200, timeout_minutes=10

# Verify KDE picked it up:
cat ~/.config/powerdevilrc
# → expect [AC][SuspendSession] section with idleTime=600000, suspendType=1

# Reopen KDE Energieverwaltung panel → must show 10 min.
```

- [ ] **Step 4: Disable verification**

```
curl -s -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"enabled":false,"timeout_minutes":15,"action":"ignore"}' \
  http://localhost:8000/api/system/sleep/os-auto-suspend | jq
cat ~/.config/powerdevilrc
# → expect [AC][SuspendSession] section to be GONE; other sections intact
```

- [ ] **Step 5: Update memory file**

Append to `memory/project_balunode_kde_gaming.md` (or create a new memory entry) noting that the OS Auto-Suspend feature is now live and verified on prod, including the actual KDE reload mechanism that worked (KConfigWatcher inotify alone, or qdbus6 reparseConfiguration).

Update the spec's "Open Items for Implementation" section if any item was resolved during this run (KDE section format, reload incantation).

```
git add memory/project_balunode_kde_gaming.md docs/superpowers/specs/2026-05-19-os-auto-suspend-bidirectional-design.md
git commit -m "docs(sleep): record prod verification of OS auto-suspend feature"
```

---

## Self-Review Checklist

The plan author ran this checklist after writing. Findings logged here for transparency:

**1. Spec coverage:**
| Spec section | Task |
|---|---|
| Pydantic schemas | Task 1 |
| Adapter protocol + types | Task 2 |
| LogindAdapter.read | Task 3 |
| LogindAdapter.write + sudo helper | Task 4 (write) + Task 12 (helper) |
| KdeAdapter.read | Task 5 |
| KdeAdapter.write (atomic, preserve sections) | Task 6 |
| GnomeAdapter | Task 7 |
| ActivePmDetector + cache | Task 8 |
| Service-layer get/set | Task 9 |
| Routes GET/PUT + audit + rate limit + admin auth | Task 10 |
| Sudoers template | Task 11 |
| Helper script | Task 12 |
| Helper script tests | Task 13 |
| Installer module | Task 14 |
| Inspector extension | Task 15 |
| Frontend API client | Task 16 |
| i18n keys de + en | Task 17 |
| Frontend card | Task 18 |
| Frontend tests | Task 19 |
| Page integration | Task 20 |
| Verification + smoke test | Tasks 21–23 |

All spec sections mapped.

**2. Placeholder scan:** No TBDs, no "handle edge cases" without code, no "similar to Task N" without inline code. The Open Items in the spec are explicitly deferred to Task 23 (prod smoke).

**3. Type consistency:** 
- `AutoSuspendValue` (dataclass) and `OsAutoSuspendResponse` (Pydantic) are the only two value types. Adapters return `AutoSuspendValue`; service layer translates to `OsAutoSuspendResponse`. The translation point is `get_os_auto_suspend` / `set_os_auto_suspend` in Task 9.
- Action vocabulary: backend uses `Literal["suspend", "hibernate", "ignore"]` (string) internally; Pydantic enum `OsAutoSuspendAction(str, Enum)` exposes the same values. Frontend `OsAutoSuspendAction` TS type uses the same three strings.
- URL prefix: `/api/system/sleep/os-auto-suspend` in all places (backend route registration confirmed at `routes/__init__.py:68`, frontend client uses the full path).

No inconsistencies found.
