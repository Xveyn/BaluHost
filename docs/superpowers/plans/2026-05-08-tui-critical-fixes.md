# TUI Critical Fixes & Recovery Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the auth-bypass bug in the TUI and add the three highest-recovery-value 🔴 "Pflicht" screens (Power Actions, Service Health, SMART) per `backend/baluhost_tui/TUI_FEATURE_AUDIT.md`.

**Architecture:** All new screens go through the existing HTTP API (`/api/sleep/*`, `/api/admin/services*`, `/api/system/smart`) via the existing `BaluHostContext.get_api_client()`. The login flow is extended to also acquire a JWT via `/api/auth/login` so the new admin screens have an authenticated client. Direct-DB fallback in `login.py` stays as the recovery path when the API is offline (no token then → admin-only screens disabled with a clear message).

**Tech Stack:** Python 3.11+, Textual (TUI framework), httpx (HTTP client), pytest + pytest-asyncio for tests, FastAPI backend.

**Out of scope (follow-up plan):** HTTP-only refactor of `users.py`/`dashboard.py`, System-Logs live tail, Telemetry-Detail screen, Settings screen, RAID-widget dev-mode mock, `sys.path.insert` cleanup. See `TUI_FEATURE_AUDIT.md` for full backlog.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/baluhost_tui/app.py` | App-level bindings + screen actions | Modify (remove dup `action_logs`, add 3 new actions/bindings) |
| `backend/baluhost_tui/screens/login.py` | Login + token acquisition | Modify (add API login → store token on app) |
| `backend/baluhost_tui/screens/power.py` | Power Actions screen (sleep/wake/suspend/WoL) | Create |
| `backend/baluhost_tui/screens/services.py` | Service Health + Restart screen | Create |
| `backend/baluhost_tui/screens/smart.py` | SMART/Disk-Health screen | Create |
| `backend/tests/tui/__init__.py` | Test package init | Create |
| `backend/tests/tui/conftest.py` | Shared test fixtures (mock httpx client, app stub) | Create |
| `backend/tests/tui/test_app_actions.py` | Auth-guard tests for `action_logs` and new actions | Create |
| `backend/tests/tui/test_login_token.py` | API token acquisition test | Create |
| `backend/tests/tui/test_power_screen.py` | Power screen unit tests | Create |
| `backend/tests/tui/test_services_screen.py` | Service screen unit tests | Create |
| `backend/tests/tui/test_smart_screen.py` | SMART screen unit tests | Create |

Each new screen exposes a pure data-fetching method (`fetch_*(client)`) that takes an `httpx.Client` so tests can drive it with a `respx`-style mock or a hand-rolled fake client without spinning up a Textual event loop.

---

### Task 1: Fix `action_logs` auth-bypass bug

The bug: `app.py:143-152` defines `action_logs` twice. The second definition has no `current_user` check — it overrides the first and lets unauthenticated users open the audit log viewer.

**Files:**
- Modify: `backend/baluhost_tui/app.py:143-152`
- Create: `backend/tests/tui/__init__.py`
- Create: `backend/tests/tui/conftest.py`
- Create: `backend/tests/tui/test_app_actions.py`

- [ ] **Step 1: Create empty test package init**

Create `backend/tests/tui/__init__.py` with a single comment:

```python
"""TUI tests."""
```

- [ ] **Step 2: Create shared test fixtures**

Create `backend/tests/tui/conftest.py`:

```python
"""Shared fixtures for TUI tests."""
from __future__ import annotations

from typing import Any
import pytest


class FakeNotify:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, message: Any, severity: str = "information", **kwargs: Any) -> None:
        self.calls.append((str(message), severity))


class FakePushScreen:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def __call__(self, screen: Any) -> None:
        self.calls.append(screen)


@pytest.fixture
def fake_app_io():
    """Returns (notify, push_screen) recorder pair for patching app methods."""
    return FakeNotify(), FakePushScreen()
```

- [ ] **Step 3: Write failing test for `action_logs` auth-guard**

Create `backend/tests/tui/test_app_actions.py`:

```python
"""Tests for BaluHostApp action methods (auth guards)."""
from __future__ import annotations

import inspect

import pytest


def test_action_logs_defined_only_once():
    """Regression: app.py had a duplicate action_logs that bypassed the auth check."""
    from baluhost_tui import app as app_module

    src = inspect.getsource(app_module.BaluHostApp)
    assert src.count("def action_logs(") == 1, (
        "BaluHostApp has more than one action_logs definition — the second one "
        "overrides the auth check (regression of TUI_FEATURE_AUDIT issue #1)."
    )


def test_action_logs_blocks_unauthenticated(fake_app_io, monkeypatch):
    """Unauthenticated users must not be able to open the audit log viewer."""
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)  # bypass __init__ (Textual side-effects)
    app.current_user = None
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_logs()

    assert push_screen.calls == [], "push_screen must NOT be called without login"
    assert notify.calls, "notify must be called with an auth-error message"
    assert notify.calls[0][1] == "error"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/tui/test_app_actions.py -v`
Expected: `test_action_logs_defined_only_once` FAILS (count == 2), the second test may also fail or error because the duplicate definition silently runs without the guard.

- [ ] **Step 5: Remove the duplicate definition**

Edit `backend/baluhost_tui/app.py` — delete lines 150-152 (the second `action_logs` block, including its blank-line separator). After the edit the only `action_logs` in the class body is the one at lines 143-148:

```python
    def action_logs(self) -> None:
        """Show audit logs."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        self.push_screen(AuditLogViewerScreen())
```

(No new method follows it; the file ends after this method.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/tui/test_app_actions.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/baluhost_tui/app.py backend/tests/tui/__init__.py backend/tests/tui/conftest.py backend/tests/tui/test_app_actions.py
git commit -m "fix(tui): remove duplicate action_logs that bypassed auth check"
```

---

### Task 2: Acquire JWT token on login (for API-driven screens)

Today `LoginScreen.attempt_login()` only does direct-DB auth and never sets `self.app.token`. The new admin screens need a token. Extend the login flow: when the HTTP backend is reachable, call `/api/auth/login` and store the access token on the app. When only the local DB is reachable, fall back as today (token stays `None`; new screens will refuse to open with a clear message).

**Files:**
- Modify: `backend/baluhost_tui/screens/login.py`
- Create: `backend/tests/tui/test_login_token.py`

- [ ] **Step 1: Write failing test for token acquisition**

Create `backend/tests/tui/test_login_token.py`:

```python
"""Tests for LoginScreen API-token acquisition."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


class _Resp:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_acquire_token_returns_jwt_on_success(monkeypatch):
    """On API login success, _acquire_api_token must return the access_token string."""
    from baluhost_tui.screens import login as login_mod

    captured: dict[str, Any] = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp(200, {"access_token": "jwt-abc123", "token_type": "bearer"})

    monkeypatch.setattr(login_mod.httpx, "post", fake_post)

    token = login_mod._acquire_api_token("http://localhost:8000", "admin", "pw")

    assert token == "jwt-abc123"
    assert captured["url"].endswith("/api/auth/login")
    assert captured["json"] == {"username": "admin", "password": "pw"}


def test_acquire_token_returns_none_on_http_failure(monkeypatch):
    """On any HTTP error, _acquire_api_token must return None (graceful fallback)."""
    from baluhost_tui.screens import login as login_mod

    def fake_post(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(login_mod.httpx, "post", fake_post)

    assert login_mod._acquire_api_token("http://localhost:8000", "admin", "pw") is None


def test_acquire_token_returns_none_on_4xx(monkeypatch):
    """4xx must be treated as no-token (caller falls back to local-only mode)."""
    from baluhost_tui.screens import login as login_mod

    def fake_post(*args, **kwargs):
        return _Resp(401, {"detail": "invalid credentials"})

    monkeypatch.setattr(login_mod.httpx, "post", fake_post)

    assert login_mod._acquire_api_token("http://localhost:8000", "admin", "pw") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/tui/test_login_token.py -v`
Expected: FAIL with `AttributeError: module 'baluhost_tui.screens.login' has no attribute '_acquire_api_token'`.

- [ ] **Step 3: Add `_acquire_api_token` helper**

Edit `backend/baluhost_tui/screens/login.py`. After the imports block (after line 17, `from app.services.users import get_user_by_username, verify_password`), add:

```python


def _acquire_api_token(server_url: str, username: str, password: str) -> str | None:
    """Try to log in via HTTP API and return the access_token, or None on any failure.

    Falls back silently so the existing direct-DB login path keeps working when
    the backend is offline.
    """
    try:
        resp = httpx.post(
            f"{server_url}/api/auth/login",
            json={"username": username, "password": password},
            timeout=5.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        token = data.get("access_token")
        return token if isinstance(token, str) and token else None
    except Exception:
        return None
```

- [ ] **Step 4: Wire helper into `attempt_login` (after admin/active checks pass)**

Still in `backend/baluhost_tui/screens/login.py`: in `attempt_login`, immediately after the existing `# Login successful` block sets `self.app.current_user`, add (before `self.notify(...)`):

```python
                # Best-effort: also acquire an API token for screens that need it.
                server_url = getattr(self.app, "server", "http://localhost:8000")
                api_token = _acquire_api_token(server_url, username, password)
                if api_token:
                    self.app.token = api_token
```

- [ ] **Step 5: Run all login tests**

Run: `cd backend && python -m pytest tests/tui/test_login_token.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/baluhost_tui/screens/login.py backend/tests/tui/test_login_token.py
git commit -m "feat(tui): acquire JWT on login to authenticate API-driven screens"
```

---

### Task 3: Power Actions screen

Lets the operator trigger soft sleep, wake, suspend, and WoL via `/api/sleep/*`. This is the smallest-scope / highest-recovery-value 🔴 Pflicht feature per `TUI_FEATURE_AUDIT.md`.

**Files:**
- Create: `backend/baluhost_tui/screens/power.py`
- Modify: `backend/baluhost_tui/app.py` (binding + action)
- Create: `backend/tests/tui/test_power_screen.py`

- [ ] **Step 1: Write failing tests for the data-fetch + action helpers**

Create `backend/tests/tui/test_power_screen.py`:

```python
"""Tests for PowerActionsScreen API helpers (logic only, no Textual loop)."""
from __future__ import annotations

from typing import Any

import pytest


class _FakeResp:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self.responses: dict[tuple[str, str], _FakeResp] = {}

    def get(self, path: str, **_: Any) -> _FakeResp:
        self.requests.append(("GET", path, None))
        return self.responses[("GET", path)]

    def post(self, path: str, json: dict[str, Any] | None = None, **_: Any) -> _FakeResp:
        self.requests.append(("POST", path, json))
        return self.responses.get(("POST", path), _FakeResp(200, {"success": True}))


def test_fetch_status_returns_normalized_dict():
    from baluhost_tui.screens.power import fetch_status

    client = _FakeClient()
    client.responses[("GET", "/api/sleep/status")] = _FakeResp(200, {
        "state": "awake",
        "since": "2026-05-08T10:00:00Z",
        "always_awake_enabled": False,
    })

    status = fetch_status(client)

    assert status["state"] == "awake"
    assert client.requests == [("GET", "/api/sleep/status", None)]


def test_fetch_status_returns_none_on_failure():
    from baluhost_tui.screens.power import fetch_status

    class _Boom:
        def get(self, *_: Any, **__: Any) -> _FakeResp:
            raise RuntimeError("offline")

    assert fetch_status(_Boom()) is None


def test_perform_action_sends_correct_endpoint():
    from baluhost_tui.screens.power import perform_action

    client = _FakeClient()
    ok, msg = perform_action(client, "soft")
    assert ok is True
    assert client.requests == [("POST", "/api/sleep/soft", {})]

    ok, msg = perform_action(client, "wake")
    assert ok is True
    assert client.requests[-1] == ("POST", "/api/sleep/wake", {})

    ok, msg = perform_action(client, "suspend")
    assert ok is True
    assert client.requests[-1] == ("POST", "/api/sleep/suspend", {})


def test_perform_action_rejects_unknown():
    from baluhost_tui.screens.power import perform_action

    ok, msg = perform_action(_FakeClient(), "explode")
    assert ok is False
    assert "unknown" in msg.lower()


def test_perform_action_reports_http_error():
    from baluhost_tui.screens.power import perform_action

    client = _FakeClient()
    client.responses[("POST", "/api/sleep/soft")] = _FakeResp(409, {"detail": "already sleeping"})

    ok, msg = perform_action(client, "soft")
    assert ok is False
    assert "409" in msg or "already" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/tui/test_power_screen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'baluhost_tui.screens.power'`.

- [ ] **Step 3: Create the power screen module with helpers + Textual screen**

Create `backend/baluhost_tui/screens/power.py`:

```python
"""Power Actions screen — sleep / wake / suspend / WoL via /api/sleep/*."""
from __future__ import annotations

from typing import Any

import httpx
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Button, Label, Static
from textual.binding import Binding

from baluhost_tui.context import get_context


_ACTIONS: dict[str, str] = {
    "soft": "/api/sleep/soft",
    "wake": "/api/sleep/wake",
    "suspend": "/api/sleep/suspend",
    "wol": "/api/sleep/wol",
}


def fetch_status(client: httpx.Client) -> dict[str, Any] | None:
    """GET /api/sleep/status. Returns parsed dict or None on any failure."""
    try:
        resp = client.get("/api/sleep/status")
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def perform_action(client: httpx.Client, action: str) -> tuple[bool, str]:
    """POST a sleep action. Returns (ok, message)."""
    path = _ACTIONS.get(action)
    if path is None:
        return False, f"unknown action: {action}"
    try:
        resp = client.post(path, json={})
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
            return False, f"HTTP {resp.status_code}: {detail}".strip()
        return True, resp.json().get("message", "ok")
    except Exception as exc:
        return False, f"request failed: {exc}"


class PowerActionsScreen(Screen):
    """Sleep / Wake / Suspend / WoL — admin only, requires API token."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    #power-container { padding: 1 2; }
    #power-status { margin-bottom: 1; }
    .power-row { height: auto; margin-bottom: 1; }
    Button { margin: 0 1; }
    """

    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="power-container"):
            yield Label("⚡ Power Actions", id="power-title")
            yield Static("Loading...", id="power-status")
            with Horizontal(classes="power-row"):
                yield Button("Sleep", id="btn-soft", variant="primary")
                yield Button("Wake", id="btn-wake", variant="success")
                yield Button("Suspend", id="btn-suspend", variant="warning")
                yield Button("WoL", id="btn-wol", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        if not self.token:
            self.query_one("#power-status", Static).update(
                "[red]No API token — admin actions disabled. Login with backend online.[/red]"
            )
            for btn_id in ("btn-soft", "btn-wake", "btn-suspend", "btn-wol"):
                try:
                    self.query_one(f"#{btn_id}", Button).disabled = True
                except Exception:
                    pass
            return
        self.refresh_status()

    def refresh_status(self) -> None:
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            status = fetch_status(ctx.get_api_client())
        if status is None:
            self.query_one("#power-status", Static).update("[red]Failed to load status[/red]")
            return
        state = status.get("state", "?")
        since = status.get("since", "?")
        always = status.get("always_awake_enabled", False)
        self.query_one("#power-status", Static).update(
            f"State: [cyan]{state}[/cyan]   Since: {since}   Always-Awake: {'on' if always else 'off'}"
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.refresh_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action_map = {"btn-soft": "soft", "btn-wake": "wake", "btn-suspend": "suspend", "btn-wol": "wol"}
        action = action_map.get(event.button.id or "")
        if not action:
            return
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            ok, msg = perform_action(ctx.get_api_client(), action)
        self.notify(msg, severity="information" if ok else "error")
        if ok:
            self.refresh_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/tui/test_power_screen.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Wire the screen into the app (binding + action + auth guard)**

Edit `backend/baluhost_tui/app.py`:

a) Add the import next to the other screen imports (after line 15):

```python
from baluhost_tui.screens.power import PowerActionsScreen
```

b) Add to the `BINDINGS` list (after the `R` raid binding):

```python
        Binding("p", "power", "Power"),
```

c) Append a new action method after `action_logs`:

```python
    def action_power(self) -> None:
        """Show power actions (sleep/wake/suspend/WoL)."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        if (self.current_user or {}).get("role") != "admin":
            self.notify("Admin role required", severity="error")
            return
        self.push_screen(PowerActionsScreen(mode=self.mode, server=self.server, token=self.token))
```

- [ ] **Step 6: Add an auth-guard test for `action_power`**

Append to `backend/tests/tui/test_app_actions.py`:

```python


def test_action_power_blocks_unauthenticated(fake_app_io):
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)
    app.current_user = None
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_power()

    assert push_screen.calls == []
    assert notify.calls and notify.calls[0][1] == "error"


def test_action_power_blocks_non_admin(fake_app_io):
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)
    app.current_user = {"id": 1, "username": "u", "role": "user", "email": ""}
    app.mode = "remote"
    app.server = "http://localhost:8000"
    app.token = "t"
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_power()

    assert push_screen.calls == []
    assert notify.calls and "admin" in notify.calls[0][0].lower()
```

- [ ] **Step 7: Run all TUI tests**

Run: `cd backend && python -m pytest tests/tui/ -v`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/baluhost_tui/screens/power.py backend/baluhost_tui/app.py backend/tests/tui/test_power_screen.py backend/tests/tui/test_app_actions.py
git commit -m "feat(tui): add Power Actions screen (sleep/wake/suspend/WoL)"
```

---

### Task 4: Service Health & Restart screen

Lists background services (`/api/admin/services`) with state + uptime, plus per-service `restart` button calling `/api/admin/services/{name}/restart`. Admin only, requires the API token from Task 2.

**Files:**
- Create: `backend/baluhost_tui/screens/services.py`
- Modify: `backend/baluhost_tui/app.py` (binding + action)
- Create: `backend/tests/tui/test_services_screen.py`

- [ ] **Step 1: Write failing tests for fetch + restart helpers**

Create `backend/tests/tui/test_services_screen.py`:

```python
"""Tests for ServiceHealthScreen API helpers."""
from __future__ import annotations

from typing import Any

import pytest


class _FakeResp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.responses: dict[tuple[str, str], _FakeResp] = {}

    def get(self, path: str, **_: Any) -> _FakeResp:
        self.requests.append(("GET", path))
        return self.responses[("GET", path)]

    def post(self, path: str, **_: Any) -> _FakeResp:
        self.requests.append(("POST", path))
        return self.responses.get(("POST", path), _FakeResp(200, {"success": True, "current_state": "running"}))


def test_fetch_services_returns_list():
    from baluhost_tui.screens.services import fetch_services

    client = _FakeClient()
    client.responses[("GET", "/api/admin/services")] = _FakeResp(200, [
        {"name": "telemetry", "state": "running", "uptime_seconds": 123},
        {"name": "disk_monitor", "state": "stopped", "uptime_seconds": None},
    ])

    services = fetch_services(client)

    assert isinstance(services, list)
    assert len(services) == 2
    assert services[0]["name"] == "telemetry"


def test_fetch_services_returns_empty_on_failure():
    from baluhost_tui.screens.services import fetch_services

    class _Boom:
        def get(self, *_: Any, **__: Any) -> _FakeResp:
            raise RuntimeError("offline")

    assert fetch_services(_Boom()) == []


def test_restart_service_posts_correct_path():
    from baluhost_tui.screens.services import restart_service

    client = _FakeClient()
    ok, msg = restart_service(client, "telemetry")

    assert ok is True
    assert ("POST", "/api/admin/services/telemetry/restart") in client.requests


def test_restart_service_returns_failure_on_4xx():
    from baluhost_tui.screens.services import restart_service

    client = _FakeClient()
    client.responses[("POST", "/api/admin/services/foo/restart")] = _FakeResp(404, {"detail": "not found"})

    ok, msg = restart_service(client, "foo")
    assert ok is False
    assert "404" in msg or "not found" in msg.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/tui/test_services_screen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'baluhost_tui.screens.services'`.

- [ ] **Step 3: Create the service health screen**

Create `backend/baluhost_tui/screens/services.py`:

```python
"""Service Health & Restart screen — /api/admin/services + /restart."""
from __future__ import annotations

from typing import Any

import httpx
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, Label, DataTable
from textual.binding import Binding

from baluhost_tui.context import get_context


def fetch_services(client: httpx.Client) -> list[dict[str, Any]]:
    """GET /api/admin/services. Returns [] on any failure."""
    try:
        resp = client.get("/api/admin/services")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def restart_service(client: httpx.Client, name: str) -> tuple[bool, str]:
    """POST /api/admin/services/{name}/restart. Returns (ok, message)."""
    try:
        resp = client.post(f"/api/admin/services/{name}/restart")
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
            return False, f"HTTP {resp.status_code}: {detail}".strip()
        body = resp.json()
        return bool(body.get("success", True)), body.get("message", "restarted")
    except Exception as exc:
        return False, f"request failed: {exc}"


class ServiceHealthScreen(Screen):
    """List services with state + uptime; press Enter to restart."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    #services-container { padding: 1 2; }
    #services-title { text-style: bold; color: $accent; margin-bottom: 1; }
    """

    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="services-container"):
            yield Label("🛠️  Services (Enter = restart)", id="services-title")
            yield DataTable(id="services-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#services-table", DataTable)
        table.add_columns("Name", "State", "Uptime (s)", "Errors")
        table.cursor_type = "row"
        if not self.token:
            self.notify("No API token — service actions unavailable", severity="warning")
            return
        self.load_services()

    def load_services(self) -> None:
        table = self.query_one("#services-table", DataTable)
        table.clear()
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            services = fetch_services(ctx.get_api_client())
        if not services:
            table.add_row("(none)", "-", "-", "-", key="__empty__")
            return
        for svc in services:
            name = svc.get("name", "?")
            state = svc.get("state", "?")
            uptime = svc.get("uptime_seconds")
            uptime_str = "-" if uptime is None else str(int(uptime))
            errors = svc.get("error_count", 0)
            table.add_row(name, state, uptime_str, str(errors), key=name)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_services()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if not self.token:
            self.notify("No API token", severity="error")
            return
        key = event.row_key
        name = key.value if hasattr(key, "value") else str(key)
        if name in ("__empty__", ""):
            return
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            ok, msg = restart_service(ctx.get_api_client(), name)
        self.notify(f"{name}: {msg}", severity="information" if ok else "error")
        if ok:
            self.load_services()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/tui/test_services_screen.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Wire the screen into the app**

Edit `backend/baluhost_tui/app.py`:

a) Add import (next to power import):

```python
from baluhost_tui.screens.services import ServiceHealthScreen
```

b) Add binding (next to the `p` power binding):

```python
        Binding("s", "services", "Services"),
```

c) Append new action after `action_power`:

```python
    def action_services(self) -> None:
        """Show service health & restart."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        if (self.current_user or {}).get("role") != "admin":
            self.notify("Admin role required", severity="error")
            return
        self.push_screen(ServiceHealthScreen(mode=self.mode, server=self.server, token=self.token))
```

- [ ] **Step 6: Add auth-guard test for `action_services`**

Append to `backend/tests/tui/test_app_actions.py`:

```python


def test_action_services_blocks_unauthenticated(fake_app_io):
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)
    app.current_user = None
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_services()

    assert push_screen.calls == []
    assert notify.calls and notify.calls[0][1] == "error"
```

- [ ] **Step 7: Run all TUI tests**

Run: `cd backend && python -m pytest tests/tui/ -v`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/baluhost_tui/screens/services.py backend/baluhost_tui/app.py backend/tests/tui/test_services_screen.py backend/tests/tui/test_app_actions.py
git commit -m "feat(tui): add Service Health & Restart screen"
```

---

### Task 5: SMART / Disk-Health screen

Single-disk health overview via `/api/system/smart` — closes the gap that the existing RAID screen only shows array-level state. Admin only.

**Files:**
- Create: `backend/baluhost_tui/screens/smart.py`
- Modify: `backend/baluhost_tui/app.py` (binding + action)
- Create: `backend/tests/tui/test_smart_screen.py`

- [ ] **Step 1: Write failing tests for the SMART fetch helper**

Create `backend/tests/tui/test_smart_screen.py`:

```python
"""Tests for SmartScreen API helper."""
from __future__ import annotations

from typing import Any


class _FakeResp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self) -> None:
        self.responses: dict[str, _FakeResp] = {}

    def get(self, path: str, **_: Any) -> _FakeResp:
        return self.responses[path]


def test_fetch_smart_returns_list_of_disks():
    from baluhost_tui.screens.smart import fetch_smart

    client = _FakeClient()
    client.responses["/api/system/smart"] = _FakeResp(200, {
        "disks": [
            {"device": "/dev/sda", "health": "PASSED", "temperature": 38, "power_on_hours": 12345},
            {"device": "/dev/sdb", "health": "FAILED", "temperature": 55, "power_on_hours": 30000},
        ]
    })

    disks = fetch_smart(client)

    assert len(disks) == 2
    assert disks[0]["device"] == "/dev/sda"
    assert disks[1]["health"] == "FAILED"


def test_fetch_smart_handles_top_level_list():
    """Some backends return a bare list — accept both shapes."""
    from baluhost_tui.screens.smart import fetch_smart

    client = _FakeClient()
    client.responses["/api/system/smart"] = _FakeResp(200, [
        {"device": "/dev/sda", "health": "PASSED"},
    ])

    disks = fetch_smart(client)
    assert len(disks) == 1


def test_fetch_smart_returns_empty_on_failure():
    from baluhost_tui.screens.smart import fetch_smart

    class _Boom:
        def get(self, *_: Any, **__: Any) -> _FakeResp:
            raise RuntimeError("nope")

    assert fetch_smart(_Boom()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/tui/test_smart_screen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'baluhost_tui.screens.smart'`.

- [ ] **Step 3: Create the SMART screen**

Create `backend/baluhost_tui/screens/smart.py`:

```python
"""SMART / Disk-Health screen — /api/system/smart."""
from __future__ import annotations

from typing import Any

import httpx
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, Label, DataTable
from textual.binding import Binding

from baluhost_tui.context import get_context


def fetch_smart(client: httpx.Client) -> list[dict[str, Any]]:
    """GET /api/system/smart. Accepts either {disks: [...]} or [...]. Returns [] on failure."""
    try:
        resp = client.get("/api/system/smart")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            disks = data.get("disks")
            return disks if isinstance(disks, list) else []
        return []
    except Exception:
        return []


def _health_color(health: str) -> str:
    h = (health or "").upper()
    if h in ("PASSED", "OK", "PASS"):
        return "green"
    if h in ("FAILED", "FAIL", "ERROR"):
        return "red"
    return "yellow"


class SmartScreen(Screen):
    """Per-disk SMART overview."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    #smart-container { padding: 1 2; }
    #smart-title { text-style: bold; color: $accent; margin-bottom: 1; }
    """

    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="smart-container"):
            yield Label("💽 SMART / Disk Health", id="smart-title")
            yield DataTable(id="smart-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#smart-table", DataTable)
        table.add_columns("Device", "Health", "Temp °C", "Power-On h", "Reallocated")
        table.cursor_type = "row"
        if not self.token:
            self.notify("No API token — SMART data unavailable", severity="warning")
            return
        self.load_smart()

    def load_smart(self) -> None:
        table = self.query_one("#smart-table", DataTable)
        table.clear()
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            disks = fetch_smart(ctx.get_api_client())
        if not disks:
            table.add_row("(none)", "-", "-", "-", "-", key="__empty__")
            return
        for d in disks:
            device = d.get("device") or d.get("name") or "?"
            health = d.get("health") or d.get("smart_status") or "?"
            color = _health_color(str(health))
            temp = d.get("temperature")
            poh = d.get("power_on_hours")
            realloc = d.get("reallocated_sectors", "-")
            table.add_row(
                device,
                f"[{color}]{health}[/{color}]",
                "-" if temp is None else str(temp),
                "-" if poh is None else str(poh),
                str(realloc),
                key=str(device),
            )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_smart()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/tui/test_smart_screen.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Wire the screen into the app**

Edit `backend/baluhost_tui/app.py`:

a) Add import:

```python
from baluhost_tui.screens.smart import SmartScreen
```

b) Add binding:

```python
        Binding("S", "smart", "SMART"),
```

c) Append new action after `action_services`:

```python
    def action_smart(self) -> None:
        """Show SMART / disk-health screen."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        if (self.current_user or {}).get("role") != "admin":
            self.notify("Admin role required", severity="error")
            return
        self.push_screen(SmartScreen(mode=self.mode, server=self.server, token=self.token))
```

- [ ] **Step 6: Add auth-guard test for `action_smart`**

Append to `backend/tests/tui/test_app_actions.py`:

```python


def test_action_smart_blocks_unauthenticated(fake_app_io):
    from baluhost_tui.app import BaluHostApp

    notify, push_screen = fake_app_io
    app = BaluHostApp.__new__(BaluHostApp)
    app.current_user = None
    app.notify = notify  # type: ignore[assignment]
    app.push_screen = push_screen  # type: ignore[assignment]

    app.action_smart()

    assert push_screen.calls == []
    assert notify.calls and notify.calls[0][1] == "error"
```

- [ ] **Step 7: Run the full TUI test suite + the related backend services test**

Run: `cd backend && python -m pytest tests/tui/ tests/services/test_service_status.py -v`
Expected: every TUI test PASSES; the existing service-status test continues to PASS (sanity check we didn't break the API surface they depend on).

- [ ] **Step 8: Commit**

```bash
git add backend/baluhost_tui/screens/smart.py backend/baluhost_tui/app.py backend/tests/tui/test_smart_screen.py backend/tests/tui/test_app_actions.py
git commit -m "feat(tui): add SMART / disk-health screen"
```

---

## Final verification

- [ ] **Step 1: Full backend test sweep**

Run: `cd backend && python -m pytest tests/tui/ -v && python -m pytest tests/ -x -q --ignore=tests/tui`
Expected: all TUI tests pass; the existing suite still passes (no regressions).

- [ ] **Step 2: Smoke-test the TUI manually**

Run: `cd backend && python -m baluhost_tui dashboard --mode auto --server http://localhost:8000`
Login as `admin / DevMode2024`. Press `p` (Power), `s` (Services), `S` (SMART). Each screen should open and either show data or — if backend is offline — a clear "no API token" message. Press `l` (Logs) WITHOUT logging in; the auth error must appear and the audit log viewer must NOT open.

- [ ] **Step 3: Update `TUI_FEATURE_AUDIT.md`**

Edit `backend/baluhost_tui/TUI_FEATURE_AUDIT.md` — under "Bestehende Issues / Tech-Debt" mark issue #1 (`action_logs` duplicate) as **FIXED**, and under the 🔴 roadmap mark Service-Health, Power-Actions, and SMART as **DONE**. Do not delete anything else; the remaining items are valid follow-ups.

- [ ] **Step 4: Final commit**

```bash
git add backend/baluhost_tui/TUI_FEATURE_AUDIT.md
git commit -m "docs(tui): mark action_logs bug + 3 critical screens as done in audit"
```
