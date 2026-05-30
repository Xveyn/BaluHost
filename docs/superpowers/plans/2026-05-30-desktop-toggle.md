# Desktop (KDE/SDDM) Toggle under Sleep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a BaluHost "Desktop" control under the Sleep feature that can stop/start the KDE desktop (SDDM) at runtime so the AMD GPU can drop to idle, and make the existing `display-switch` script auto-restart the desktop whenever the user switches displays.

**Architecture:** A new `DesktopBackend` (dev + linux) mirrors the existing sleep backend pattern (`sleep_backend_dev.py` / `sleep_backend_linux.py`). The linux backend wraps `systemctl start/stop/is-active sddm.service` via a narrow sudoers rule. A thin `DesktopService` exposes status/enable/disable, surfaced through three endpoints included under the `/sleep/desktop` prefix and a small panel on the existing Sleep page. Separately, `display-switch` gains a guard: before switching outputs it ensures the desktop is running (start SDDM + wait for the Wayland socket), because switching a display only makes sense with KDE up.

**Tech Stack:** Python 3.13 / FastAPI / Pydantic v2 / SQLAlchemy (backend), React 18 + TypeScript + axios (frontend), bash + systemd + sddm + kscreen-doctor (host), pytest (tests).

---

## Context for the implementer (read first)

This repo is **BaluHost**, a NAS management platform. You are adding a feature, not fixing a bug. Key facts verified on the production host (`BaluNode`, Debian 13) on 2026-05-30:

- The desktop is **KDE Plasma (Wayland)** started by **`sddm.service`** (system display manager). `systemctl get-default` is `graphical.target`.
- The machine runs the BaluHost backend as system user **`sven`** (systemd `User=sven`), and `/opt/baluhost` is owned by `sven:sven`. There is **no** `baluhost` user on this host.
- One **AMD Radeon RX 7900 XT** dGPU (`amdgpu`, `card0`). BaluHost's GPU power manager (`backend/app/services/power/gpu/manager.py`) only drops the GPU to STANDBY/DEEP_IDLE when `display_count == 0` (it counts DRM connectors that are `connected` AND `enabled`). With KDE up, at least one connector is `enabled`, so `display_count >= 1` and the GPU never idles. Stopping SDDM is what lets `display_count` reach 0.
- The existing sleep feature is the closest analog and the pattern to copy:
  - Service: `backend/app/services/power/sleep.py`, accessed via `get_sleep_manager()` (returns None if not running). Backends: `sleep_backend_dev.py` + `sleep_backend_linux.py`.
  - `LinuxSleepBackend` shells out with `subprocess.run(cmd, capture_output=True, text=True, timeout=...)` using **list args** and returns a `(ok, message)`-style result. Sleep's suspend uses `["sudo", "systemctl", "suspend"]`.
  - Route: `backend/app/api/routes/sleep.py` declares a bare `router = APIRouter()` (NO prefix in the file). It is registered in `backend/app/api/routes/__init__.py` (~line 120) as:
    `api_router.include_router(sleep.router, prefix="/sleep", tags=["sleep"])`
    The prefix is applied at include time. Endpoints use `@user_limiter.limit(get_limit("admin_operations"))` and `Depends(get_current_user)` / `Depends(get_current_admin)`.
  - Schemas: `backend/app/schemas/sleep.py`.
  - Frontend page: `client/src/pages/SleepMode.tsx`; API client `client/src/api/sleep.ts` (`import { api } from '../lib/api';`); panels under `client/src/components/power/`.
- The audit logger signature (verified): `log_event(event_type, user, action, resource=None, details=None, success=True, error_message=None, ip_address=None, user_agent=None, db=None)`. **`db` defaults to None** and `user` accepts `None`, so the keyword-argument calls in this plan are valid and need no DB session.
- Sudoers are templated, **not** hand-edited: `deploy/install/templates/sudoers.d/baluhost-power.j2` is rendered by the installer (Jinja2) with `BALUHOST_USER`. It already grants `systemctl suspend` etc. CODEOWNERS protects `deploy/`. The prod box currently has **no** rule for `sddm.service` — Task 5 adds it.
- `display-switch` lives at `~/.local/bin/display-switch` and is **not** versioned in this repo. It already has a `__test` self-test (fixtures) and a `--dry-run` mode. Constants: `TV_OUTPUT="DP-3"`, `MON_OUTPUT="HDMI-A-1"`. It always activates exactly one output, so it can never produce `display_count == 0` on its own — that is why the desktop toggle (not display-switch) is what enables GPU idle. Task 7 vendors the script into the repo and adds the desktop guard.

**Conventions to follow:**
- Backend: async I/O, type hints on every function, Pydantic models for request/response (never raw `dict` for request bodies), business logic in services (routes only do HTTP), audit-log security-relevant actions, rate-limit new endpoints with `@user_limiter.limit(get_limit("..."))`, auth via `Depends(get_current_admin)` for state-changing ops.
- Subprocess: **list args only, never `shell=True`**, always a timeout.
- Tests: `backend/tests/`, pytest, mock subprocess — never actually stop SDDM in a test.

**Run all backend commands from `/opt/baluhost/backend` using the venv:** prefix Python/pytest with `.venv/bin/` (e.g. `.venv/bin/python -m pytest ...`). Do NOT use the system `python3` — it resolves a stale editable install and crashes on import.

**Commit discipline:** one commit per task (after its tests pass). Branch is `feat/desktop-toggle-sleep`.

---

## File Structure

**New files:**
- `backend/app/schemas/desktop.py` — Pydantic models: `DesktopState` enum, `DesktopStatus`.
- `backend/app/services/power/desktop_backend.py` — backend protocol + `DevDesktopBackend` + `LinuxDesktopBackend` (one small file, like the sleep backends).
- `backend/app/services/power/desktop.py` — `DesktopService` + `get_desktop_service()` singleton.
- `backend/app/api/routes/desktop.py` — bare `APIRouter()` with three endpoints (included under `/sleep/desktop`).
- `backend/tests/test_desktop_backend.py` — schema + backend unit tests (mock subprocess).
- `backend/tests/test_desktop_service.py` — service unit tests.
- `backend/tests/test_desktop_routes.py` — API tests (dev backend, no real systemctl).
- `client/src/api/desktop.ts` — typed axios client.
- `client/src/components/power/DesktopTogglePanel.tsx` — the UI panel.
- `deploy/scripts/display-switch` — versioned copy of the host script + desktop guard.

**Modified files:**
- `backend/app/api/routes/__init__.py` — register the desktop router with `prefix="/sleep/desktop"`.
- `deploy/install/templates/sudoers.d/baluhost-power.j2` — add three `systemctl ... sddm.service` rules.
- `client/src/pages/SleepMode.tsx` — render `<DesktopTogglePanel />`.

---

## Task 1: Desktop schemas

**Files:**
- Create: `backend/app/schemas/desktop.py`
- Test: `backend/tests/test_desktop_backend.py` (created here; reused by Task 2)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_desktop_backend.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_desktop_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.desktop'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/schemas/desktop.py`:

```python
"""Schemas for the desktop (display-manager) toggle feature."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DesktopState(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class DesktopStatus(BaseModel):
    """Current state of the desktop display manager."""

    state: DesktopState
    display_manager: str = Field(description="Name of the display-manager unit, e.g. 'sddm'")
    detail: Optional[str] = Field(default=None, description="Optional human-readable detail")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_desktop_backend.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/desktop.py backend/tests/test_desktop_backend.py
git commit -m "feat(desktop): add DesktopState/DesktopStatus schemas"
```

---

## Task 2: Desktop backends (dev + linux)

**Files:**
- Create: `backend/app/services/power/desktop_backend.py`
- Test: `backend/tests/test_desktop_backend.py` (extend)

**Design notes:** Mirror `sleep_backend_linux.py`. The linux backend wraps `systemctl` with list-args and a timeout. `get_status` maps `systemctl is-active sddm.service` stdout to a `DesktopState`: `active` -> RUNNING; `inactive`/`failed`/`deactivating`/`activating` -> STOPPED; anything else -> UNKNOWN. **For the status path, capture stdout regardless of return code** — `is-active` returns non-zero (3) when inactive, which is normal, not an error. `disable()` runs `sudo systemctl stop`, `enable()` runs `sudo systemctl start`; both treat non-zero as failure and return stderr.

- [ ] **Step 1: Write the failing test (append to `backend/tests/test_desktop_backend.py`)**

```python
import asyncio
from unittest.mock import patch, MagicMock

from app.services.power.desktop_backend import (
    DevDesktopBackend,
    LinuxDesktopBackend,
)
from app.schemas.desktop import DesktopState


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_desktop_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.power.desktop_backend'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/power/desktop_backend.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_desktop_backend.py -v`
Expected: PASS (8 tests total: 2 schema + 6 backend)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/desktop_backend.py backend/tests/test_desktop_backend.py
git commit -m "feat(desktop): add dev + linux desktop control backends"
```

---

## Task 3: DesktopService singleton

**Files:**
- Create: `backend/app/services/power/desktop.py`
- Test: `backend/tests/test_desktop_service.py`

**Design notes:** Pick the backend by `settings.is_dev_mode` (dev -> `DevDesktopBackend`, else `LinuxDesktopBackend`). Expose `get_status()`, `enable()`, `disable()` delegating to the backend. Module-level singleton via `get_desktop_service()`. Allow injecting a backend in the constructor for tests.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_desktop_service.py`:

```python
import asyncio

from app.services.power.desktop import DesktopService, get_desktop_service
from app.services.power.desktop_backend import DevDesktopBackend
from app.schemas.desktop import DesktopState


def test_service_delegates_to_backend():
    svc = DesktopService(backend=DevDesktopBackend())
    assert asyncio.run(svc.get_status()).state is DesktopState.RUNNING
    ok, _ = asyncio.run(svc.disable())
    assert ok
    assert asyncio.run(svc.get_status()).state is DesktopState.STOPPED


def test_get_desktop_service_is_singleton():
    a = get_desktop_service()
    b = get_desktop_service()
    assert a is b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_desktop_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.power.desktop'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/power/desktop.py`:

```python
"""Desktop (display-manager) control service."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from app.core.config import settings
from app.schemas.desktop import DesktopStatus
from app.services.power.desktop_backend import (
    DesktopBackend,
    DevDesktopBackend,
    LinuxDesktopBackend,
)

logger = logging.getLogger(__name__)

_service: Optional["DesktopService"] = None


class DesktopService:
    def __init__(self, backend: Optional[DesktopBackend] = None) -> None:
        if backend is not None:
            self._backend = backend
        elif getattr(settings, "is_dev_mode", False):
            self._backend = DevDesktopBackend()
        else:
            self._backend = LinuxDesktopBackend()

    async def get_status(self) -> DesktopStatus:
        return await self._backend.get_status()

    async def enable(self) -> Tuple[bool, str]:
        logger.info("Desktop enable requested")
        return await self._backend.enable()

    async def disable(self) -> Tuple[bool, str]:
        logger.info("Desktop disable requested")
        return await self._backend.disable()


def get_desktop_service() -> DesktopService:
    global _service
    if _service is None:
        _service = DesktopService()
    return _service
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_desktop_service.py -v`
Expected: PASS (2 tests). The singleton picks a backend from `settings.is_dev_mode`; the test only checks identity, so it works in either mode.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/desktop.py backend/tests/test_desktop_service.py
git commit -m "feat(desktop): add DesktopService singleton"
```

---

## Task 4: API endpoints

**Files:**
- Create: `backend/app/api/routes/desktop.py`
- Modify: `backend/app/api/routes/__init__.py`
- Test: `backend/tests/test_desktop_routes.py`

**Design notes:** Status is a read (any authenticated user). enable/disable are state-changing -> `Depends(get_current_admin)`, rate-limited, audit-logged. The route module declares a **bare `router = APIRouter()`** (no prefix in the file — matching `sleep.py`); the `/sleep/desktop` prefix is applied at include time in `__init__.py`. `@user_limiter.limit(...)` requires `request: Request` in the signature (slowapi reads it).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_desktop_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import deps
from app.services.power.desktop import DesktopService
from app.services.power.desktop_backend import DevDesktopBackend


@pytest.fixture
def client():
    class _User:
        id = 1
        username = "admin"
        role = "admin"
    app.dependency_overrides[deps.get_current_user] = lambda: _User()
    app.dependency_overrides[deps.get_current_admin] = lambda: _User()
    import app.services.power.desktop as desktop_mod
    desktop_mod._service = DesktopService(backend=DevDesktopBackend())
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    desktop_mod._service = None


def test_status_endpoint(client):
    r = client.get("/api/sleep/desktop/status")
    assert r.status_code == 200
    assert r.json()["state"] == "running"


def test_disable_then_status(client):
    r = client.post("/api/sleep/desktop/disable")
    assert r.status_code == 200
    assert r.json()["success"] is True
    r = client.get("/api/sleep/desktop/status")
    assert r.json()["state"] == "stopped"


def test_enable_endpoint(client):
    client.post("/api/sleep/desktop/disable")
    r = client.post("/api/sleep/desktop/enable")
    assert r.status_code == 200
    assert r.json()["success"] is True
    r = client.get("/api/sleep/desktop/status")
    assert r.json()["state"] == "running"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_desktop_routes.py -v`
Expected: FAIL (404 on the new routes — router not created/registered yet).

- [ ] **Step 3a: Write the route module**

Create `backend/app/api/routes/desktop.py`:

```python
"""Desktop (display-manager) control endpoints.

Registered under the /sleep/desktop prefix in routes/__init__.py.
"""
import logging

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user, get_current_admin
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.desktop import DesktopStatus
from app.services.power.desktop import get_desktop_service
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=DesktopStatus)
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_status(
    request: Request,
    current_user=Depends(get_current_user),
) -> DesktopStatus:
    """Return whether the KDE desktop (display manager) is running."""
    return await get_desktop_service().get_status()


@router.post("/disable")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_disable(
    request: Request,
    current_user=Depends(get_current_admin),
) -> dict:
    """Stop the KDE desktop so the GPU can drop to idle. Admin only."""
    ok, message = await get_desktop_service().disable()
    get_audit_logger_db().log_event(
        event_type="POWER",
        action="desktop_disable",
        user=current_user.username,
        resource="desktop",
        success=ok,
        details={"message": message},
    )
    return {"success": ok, "message": message}


@router.post("/enable")
@user_limiter.limit(get_limit("admin_operations"))
async def desktop_enable(
    request: Request,
    current_user=Depends(get_current_admin),
) -> dict:
    """Start the KDE desktop. Admin only."""
    ok, message = await get_desktop_service().enable()
    get_audit_logger_db().log_event(
        event_type="POWER",
        action="desktop_enable",
        user=current_user.username,
        resource="desktop",
        success=ok,
        details={"message": message},
    )
    return {"success": ok, "message": message}
```

- [ ] **Step 3b: Register the router**

In `backend/app/api/routes/__init__.py`, find the sleep registration line (~120):
`api_router.include_router(sleep.router, prefix="/sleep", tags=["sleep"])`
Add `desktop` to the imports at the top of the file (next to where `sleep` is imported), and add directly below the sleep line:

```python
    api_router.include_router(desktop.router, prefix="/sleep/desktop", tags=["sleep"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_desktop_routes.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/desktop.py backend/app/api/routes/__init__.py backend/tests/test_desktop_routes.py
git commit -m "feat(desktop): add /sleep/desktop status/enable/disable endpoints"
```

---

## Task 5: Sudoers rule for sddm control

**Files:**
- Modify: `deploy/install/templates/sudoers.d/baluhost-power.j2`

**Design notes:** The linux backend runs `sudo systemctl start/stop sddm.service`. Without a NOPASSWD rule the backend cannot control SDDM (the prod box currently has no such rule — verified). Keep rules narrow: exact unit, exact verbs. `is-active` does not need sudo. CODEOWNERS protects `deploy/` — this goes through PR review. **This file is a Jinja2 template; do not render it as part of the source change.** The installer renders `{{ BALUHOST_USER }}`.

- [ ] **Step 1: Add the rules**

Append to `deploy/install/templates/sudoers.d/baluhost-power.j2` (after the existing rules):

```jinja
{{ BALUHOST_USER }} ALL=(root) NOPASSWD: /usr/bin/systemctl start sddm.service
{{ BALUHOST_USER }} ALL=(root) NOPASSWD: /usr/bin/systemctl stop sddm.service
{{ BALUHOST_USER }} ALL=(root) NOPASSWD: /usr/bin/systemctl restart sddm.service
```

- [ ] **Step 2: Validate the rendered output parses as valid sudoers**

Run from repo root:

```bash
.venv/bin/python - <<'PY'
text = open("deploy/install/templates/sudoers.d/baluhost-power.j2").read()
rendered = text.replace("{{ BALUHOST_USER }}", "sven")
open("/tmp/baluhost-power.rendered", "w").write(rendered)
assert "{{" not in rendered, "unrendered Jinja remains"
assert rendered.count("sddm.service") == 3, "expected 3 sddm rules"
print(rendered)
PY
visudo -cf /tmp/baluhost-power.rendered
```

Expected: `visudo` prints `/tmp/baluhost-power.rendered: parsed OK`. (If `visudo` is unavailable on the dev machine, the two Python asserts above are the minimum gate.)

- [ ] **Step 3: Clean up + commit**

```bash
rm -f /tmp/baluhost-power.rendered
git add deploy/install/templates/sudoers.d/baluhost-power.j2
git commit -m "feat(desktop): allow service user to start/stop/restart sddm via sudoers"
```

> **Operator note (not a code step):** On the running prod box the rule must be installed for the backend to control SDDM without a password. Either re-run the installer's sudoers step, or hand-create `/etc/sudoers.d/baluhost-power` from the rendered output and validate with `visudo -c`. Until then, `disable`/`enable` fail with a sudo password prompt and the endpoint returns `success: false`.

---

## Task 6: Frontend — API client + toggle panel

**Files:**
- Create: `client/src/api/desktop.ts`
- Create: `client/src/components/power/DesktopTogglePanel.tsx`
- Modify: `client/src/pages/SleepMode.tsx`

**Design notes:** `client/src/api/sleep.ts` uses `import { api } from '../lib/api';` (verified) — match it. Follow an existing panel under `client/src/components/power/` (e.g. `SleepModePanel.tsx`) for styling and loading/error conventions. There is no frontend unit-test harness (`npm run test` is a placeholder per dev docs), so verification is `npm run build` (type-check) plus the manual smoke in Task 8.

- [ ] **Step 1: Create the API client**

Create `client/src/api/desktop.ts`:

```typescript
import { api } from '../lib/api';

export type DesktopState = 'running' | 'stopped' | 'unknown';

export interface DesktopStatus {
  state: DesktopState;
  display_manager: string;
  detail: string | null;
}

export interface DesktopActionResult {
  success: boolean;
  message: string;
}

export async function getDesktopStatus(): Promise<DesktopStatus> {
  const { data } = await api.get<DesktopStatus>('/sleep/desktop/status');
  return data;
}

export async function disableDesktop(): Promise<DesktopActionResult> {
  const { data } = await api.post<DesktopActionResult>('/sleep/desktop/disable');
  return data;
}

export async function enableDesktop(): Promise<DesktopActionResult> {
  const { data } = await api.post<DesktopActionResult>('/sleep/desktop/enable');
  return data;
}
```

> Before writing, open `client/src/api/sleep.ts` and confirm base-path handling: if the axios instance already prefixes `/api`, the paths above are correct (`/sleep/...`). If sleep.ts includes `/api` explicitly in its URLs, add `/api` here to match. Mirror whatever sleep.ts does.

- [ ] **Step 2: Create the panel component**

Create `client/src/components/power/DesktopTogglePanel.tsx`:

```tsx
import { useEffect, useState } from 'react';
import {
  DesktopStatus,
  getDesktopStatus,
  disableDesktop,
  enableDesktop,
} from '../../api/desktop';

export default function DesktopTogglePanel() {
  const [status, setStatus] = useState<DesktopStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setStatus(await getDesktopStatus());
      setError(null);
    } catch {
      setError('Konnte Desktop-Status nicht laden');
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onToggle() {
    if (!status) return;
    setBusy(true);
    setError(null);
    try {
      const result =
        status.state === 'running' ? await disableDesktop() : await enableDesktop();
      if (!result.success) setError(result.message || 'Aktion fehlgeschlagen');
      await refresh();
    } catch {
      setError('Aktion fehlgeschlagen');
    } finally {
      setBusy(false);
    }
  }

  const running = status?.state === 'running';

  return (
    <div className="rounded-lg border border-gray-700 bg-gray-800 p-4">
      <h3 className="mb-2 text-lg font-semibold">Desktop (KDE)</h3>
      <p className="mb-3 text-sm text-gray-400">
        Beendet die KDE-Sitzung, damit die GPU in den Ruhezustand wechseln kann.
        Beim Anschalten startet der Desktop neu.
      </p>
      <div className="mb-3 text-sm">
        Status:{' '}
        <span className={running ? 'text-green-400' : 'text-yellow-400'}>
          {status ? (running ? 'Läuft' : 'Gestoppt') : '…'}
        </span>
        {status?.detail ? <span className="text-gray-500"> ({status.detail})</span> : null}
      </div>
      {error ? <div className="mb-3 text-sm text-red-400">{error}</div> : null}
      <button
        onClick={onToggle}
        disabled={busy || !status}
        className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {busy ? '…' : running ? 'Desktop deaktivieren' : 'Desktop aktivieren'}
      </button>
    </div>
  );
}
```

> Style note: the Tailwind classes above match a generic dark panel. If the surrounding `power/` panels use shared UI primitives (e.g. a `Card`/`Button` from `client/src/components/ui/`), prefer those to stay consistent — adapt the markup but keep the same state logic.

- [ ] **Step 3: Mount the panel on the Sleep page**

In `client/src/pages/SleepMode.tsx`: add `import DesktopTogglePanel from '../components/power/DesktopTogglePanel';` near the other power-component imports, and render `<DesktopTogglePanel />` in the page's main column next to the existing sleep panels. Match the surrounding JSX layout (grid/stack).

- [ ] **Step 4: Type-check / build**

Run from `client/`: `npm run build`
Expected: build succeeds, no TypeScript errors. A wrong `api` import or path shows up here as a TS error in `desktop.ts` — fix to match `sleep.ts`.

- [ ] **Step 5: Commit**

```bash
git add client/src/api/desktop.ts client/src/components/power/DesktopTogglePanel.tsx client/src/pages/SleepMode.tsx
git commit -m "feat(desktop): add Desktop toggle panel to Sleep page"
```

---

## Task 7: display-switch desktop-guard

**Files:**
- Create: `deploy/scripts/display-switch` (versioned copy + guard)
- Test: the script's own `__test` subcommand (extended with new fixtures)

**Why:** Switching displays only makes sense with KDE up. If the user previously ran "Desktop deaktivieren" (SDDM stopped) and then runs `display-switch tv|monitor`, the script must first restart the desktop, wait until the Wayland session is back, then drive `kscreen-doctor`. Otherwise `kscreen-doctor` has no compositor and fails.

**Important:** The current `display-switch` is NOT in the repo — it lives only at `~/.local/bin/display-switch`. Step 1 imports it verbatim, then later steps add the guard. Keep its existing structure (`set -Eeuo pipefail`, `run()` dry-run wrapper, `__test` harness, `log/die`, the `main()` dispatch that already exports `XDG_RUNTIME_DIR`/`WAYLAND_DISPLAY` for SSH sessions). The script runs as user `sven`; starting SDDM needs `sudo systemctl start sddm.service` (Task 5 sudoers rule covers this).

**Behaviour spec for `ensure_desktop_up`:**
- If `systemctl is-active sddm.service` prints `active` -> desktop already up, return immediately (no sudo, no wait).
- Else -> `sudo systemctl start sddm.service`, then poll up to `DESKTOP_WAIT_S` (default 20s) for the Wayland socket `"$XDG_RUNTIME_DIR/wayland-0"`; return 0 once present, `die` on timeout.
- Pure helper `desktop_state_from_isactive <stdout>` maps systemd `is-active` stdout -> `up`/`down` (testable in `__test`).
- `cmd_tv` and `cmd_monitor` call `ensure_desktop_up` as their first action (after the opening `log "Wechsle ..."`). In `--dry-run` mode, `ensure_desktop_up` only logs what it would do (via the `run()` wrapper / DRY_RUN check) and never starts SDDM or waits.

- [ ] **Step 1: Import the current script into the repo**

```bash
mkdir -p deploy/scripts
cp ~/.local/bin/display-switch deploy/scripts/display-switch
chmod +x deploy/scripts/display-switch
git add deploy/scripts/display-switch
git commit -m "chore(display-switch): vendor current script into repo before changes"
```

This baseline commit makes the guard diff reviewable.

- [ ] **Step 2: Confirm the baseline self-test passes**

Run: `deploy/scripts/display-switch __test`
Expected: `OK: alle Parser-Tests bestanden`, exit 0. (Sanity check before editing.)

- [ ] **Step 3: Add the failing parser test (inside `cmd_test()`)**

In `deploy/scripts/display-switch`, inside `cmd_test()` (before the final `if [ "$fail" = 0 ]` block), add:

```bash
    # Test 7: desktop_state_from_isactive maps systemd output
    got=$(desktop_state_from_isactive "active")
    if [ "$got" != "up" ]; then log "FAIL desktop_state up: got='$got' want='up'"; fail=1; fi
    got=$(desktop_state_from_isactive "inactive")
    if [ "$got" != "down" ]; then log "FAIL desktop_state down(inactive): got='$got' want='down'"; fail=1; fi
    got=$(desktop_state_from_isactive "failed")
    if [ "$got" != "down" ]; then log "FAIL desktop_state down(failed): got='$got' want='down'"; fail=1; fi
    got=$(desktop_state_from_isactive "")
    if [ "$got" != "down" ]; then log "FAIL desktop_state down(empty): got='$got' want='down'"; fail=1; fi
```

- [ ] **Step 4: Run the self-test to verify it fails**

Run: `deploy/scripts/display-switch __test`
Expected: FAIL — `command not found: desktop_state_from_isactive` (non-zero exit via the ERR trap).

- [ ] **Step 5: Add the guard implementation**

In the constants block (near `AUDIO_SINK_TIMEOUT_S=3`), add:

```bash
DM_UNIT="sddm.service"
DESKTOP_WAIT_S=20
```

After the existing parser helpers (the `# ---------- Parser ----------` section), add the pure mapper:

```bash
# desktop_state_from_isactive <isactive-stdout>
# Maps `systemctl is-active sddm.service` stdout to up|down (pure, testable).
desktop_state_from_isactive() {
    case "${1:-}" in
        active) printf 'up\n' ;;
        *)      printf 'down\n' ;;
    esac
}
```

Add a `# ---------- Desktop ----------` section above `cmd_tv`:

```bash
# ensure_desktop_up — make sure the KDE session is running before driving kscreen.
# Starts sddm if stopped and waits for the Wayland socket. Honours DRY_RUN.
ensure_desktop_up() {
    local state
    state=$(desktop_state_from_isactive "$(systemctl is-active "$DM_UNIT" 2>/dev/null || true)")
    if [ "$state" = "up" ]; then
        log "Desktop läuft bereits ($DM_UNIT)"
        return 0
    fi

    log "Desktop ist aus — starte $DM_UNIT"
    run sudo systemctl start "$DM_UNIT"

    if [ "$DRY_RUN" = 1 ]; then
        log "(dry-run) würde auf Wayland-Socket warten (max ${DESKTOP_WAIT_S}s)"
        return 0
    fi

    local sock="$XDG_RUNTIME_DIR/wayland-0"
    local end=$(( SECONDS + DESKTOP_WAIT_S ))
    while [ "$SECONDS" -lt "$end" ]; do
        if [ -S "$sock" ]; then
            log "Desktop ist bereit (Wayland-Socket vorhanden)"
            return 0
        fi
        sleep 0.5
    done
    die "Desktop kam nicht innerhalb ${DESKTOP_WAIT_S}s hoch (kein $sock)"
}
```

Add `ensure_desktop_up` as the **first line** inside both `cmd_tv()` and `cmd_monitor()` — immediately after their opening `log "Wechsle ..."` line, before the `kscreen-doctor` call:

```bash
    ensure_desktop_up
```

- [ ] **Step 6: Run the self-test to verify it passes**

Run: `deploy/scripts/display-switch __test`
Expected: `OK: alle Parser-Tests bestanden`, exit 0 (10 checks now).

- [ ] **Step 7: Verify dry-run wiring without touching the system**

Run: `deploy/scripts/display-switch tv --dry-run`
Expected: stderr shows it checks the desktop and (if down) prints `+ sudo systemctl start sddm.service`, then the existing `+ kscreen-doctor ...` lines. It must NOT actually start SDDM or call kscreen-doctor. (If the desktop is currently up, you'll instead see `Desktop läuft bereits` — also correct.)

- [ ] **Step 8: Commit**

```bash
git add deploy/scripts/display-switch
git commit -m "feat(display-switch): start desktop before switching outputs"
```

> **Operator note (not a code step):** After merge, sync the repo copy to the live location: `cp /opt/baluhost/deploy/scripts/display-switch ~/.local/bin/display-switch && chmod +x ~/.local/bin/display-switch`. The repo copy is the source of truth from now on.

---

## Task 8: Full regression + manual smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the desktop test suite**

Run from `backend/`: `.venv/bin/python -m pytest tests/test_desktop_backend.py tests/test_desktop_service.py tests/test_desktop_routes.py -v`
Expected: all desktop tests PASS.

- [ ] **Step 2: Run the broader suite to catch regressions**

Run from `backend/`: `.venv/bin/python -m pytest -q`
Expected: no new failures introduced by this branch. (If unsure whether a failure pre-existed, compare against a clean checkout of `main`.)

- [ ] **Step 3: Frontend build**

Run from `client/`: `npm run build`
Expected: success, no TS errors.

- [ ] **Step 4: Manual smoke (operator, on the prod box — after deploy + sudoers install)**

1. With the Task 5 sudoers rule installed, open BaluHost -> Sleep page. The "Desktop (KDE)" panel shows **Läuft**.
2. Click **Desktop deaktivieren**. Within a few seconds the KDE session ends and the panel shows **Gestoppt**. Verify the GPU can now idle: after the GPU idle window, `cat /sys/class/drm/card0/device/power_dpm_force_performance_level` should eventually read `low` (DEEP_IDLE).
3. From a TTY/SSH run `display-switch tv`: it should start SDDM, wait for the session, then switch to the TV. The Sleep panel shows **Läuft** again.
4. Alternatively click **Desktop aktivieren** to bring KDE back.

---

## Self-Review

**Spec coverage:**
- "KDE deaktivieren können" -> Tasks 2-6 (backend + endpoint + UI `disable`). OK
- "weiterhin Desktop UI nutzen können" -> `enable` endpoint + panel button, and Task 7 auto-restart on display switch. OK
- "soll als Feature nach BaluHost unter Sleep" -> router included under `/sleep/desktop`, panel mounted on `SleepMode.tsx`. OK
- "display-switch aktiviert KDE wenn es aus ist" -> Task 7 `ensure_desktop_up`. OK
- GPU can sleep once desktop is off -> relies on existing `display_count == 0` path; documented + smoke-tested in Task 8. OK

**Placeholder scan:** No TBD/TODO; every code step has full code.

**Type consistency:** `DesktopState`/`DesktopStatus` defined in Task 1, reused unchanged in Tasks 2-4 and mirrored in TS in Task 6 (`running|stopped|unknown`). Backend methods `get_status`/`enable`/`disable` consistent across backend (Task 2), service (Task 3), route (Task 4). `desktop_state_from_isactive` returns `up`/`down` consistently in Task 7. Endpoint response shape `{success, message}` matches the TS `DesktopActionResult`.

## Resolved facts (verified 2026-05-30, no longer open)
1. `get_audit_logger_db().log_event(...)` has `db: Optional[Session] = None` and `user: Optional[str]` — the keyword calls in Task 4 are valid with no DB session.
2. `client/src/api/sleep.ts` uses `import { api } from '../lib/api';` — matched in Task 6.
3. Route registration style in `__init__.py`: prefix applied at include time (`include_router(sleep.router, prefix="/sleep", ...)`) — desktop router is a bare `APIRouter()` included with `prefix="/sleep/desktop"`.
4. Endpoints in `sleep.py` use `user_limiter` (not `limiter`) — matched in Task 4.

## One thing to confirm during execution
- Run `deploy/scripts/display-switch __test` right after Task 7 Step 1 to confirm the vendored baseline self-test passes on the execution machine before adding the guard (Task 7 Step 2 does this).
