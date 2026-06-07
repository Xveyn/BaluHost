# TUI Companion Rebuild — Foundation Layer (Plan 1 of 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the additive foundation library for the rebuilt TUI — a single `BackendClient` that speaks to the backend over a Unix socket (prod) or TCP loopback (dev), plus typed `api/auth` + `api/system` wrappers — all unit-tested, with the existing TUI left untouched.

**Architecture:** New modules under `backend/baluhost_tui/`: `client.py` (transport selection UDS/TCP + JWT + httpx verb passthrough) and `api/` (typed request/response wrappers). Nothing is wired into `app.py`/screens in this plan — that cutover is Plan 2 — so there is zero regression risk and the current TUI keeps working.

**Tech Stack:** Python 3.11, httpx 0.27 (`httpx.HTTPTransport(uds=...)`, `httpx.MockTransport` for tests), pytest. Spec: `docs/superpowers/specs/2026-06-07-tui-companion-rebuild-design.md`.

---

## Why this is "working software" on its own

This plan ships a fully tested transport/auth library. The current TUI is **not modified**, so it continues to run exactly as before. Plan 2 performs the cutover (rewire `app.py`/`main.py`, JWT-only `LoginScreen`, port screens, `BaseScreen`, `ConfirmDialog`); Plan 3 adds the new screens (plugins, vpn, network, settings, live logs) and cleanup. The APIs defined here are the contract those plans consume.

## File Structure

| File | Responsibility |
|---|---|
| Create: `backend/baluhost_tui/client.py` | `BackendClient` + `resolve_transport()` + `build_client()`. Transport selection, JWT header, httpx verb passthrough (`get/post/put/delete`). |
| Create: `backend/baluhost_tui/api/__init__.py` | Package marker for the typed API layer. |
| Create: `backend/baluhost_tui/api/auth.py` | `login()` + `LoginError`/`TwoFactorRequired`. |
| Create: `backend/baluhost_tui/api/system.py` | `get_channel_status()`, `restart_app()`, `shutdown_app()`. |
| Create: `backend/tests/tui/test_client.py` | Tests for transport resolution + BackendClient passthrough/auth. |
| Create: `backend/tests/tui/test_api_auth.py` | Tests for `login()`. |
| Create: `backend/tests/tui/test_api_system.py` | Tests for system wrappers. |

`backend/tests/tui/conftest.py` already exists (FakeNotify/FakePushScreen). The existing `_FakeClient`/`_FakeResp` pattern lives inline in `test_services_screen.py` — this plan re-defines a small fake inline per test file to stay self-contained (matches the existing convention).

---

## Task 1: `resolve_transport()` — choose UDS vs TCP

**Files:**
- Create: `backend/baluhost_tui/client.py`
- Test: `backend/tests/tui/test_client.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tui/test_client.py`:

```python
"""Tests for the TUI BackendClient and transport resolution."""
from __future__ import annotations

from baluhost_tui.client import resolve_transport, DEFAULT_SOCKET, DEFAULT_SERVER


def test_explicit_server_wins_over_socket():
    mode, target = resolve_transport(
        socket_path="/run/baluhost/local.sock",
        server="http://127.0.0.1:3001",
        exists=lambda p: True,
    )
    assert mode == "tcp"
    assert target == "http://127.0.0.1:3001"


def test_explicit_socket_when_no_server():
    mode, target = resolve_transport(
        socket_path="/tmp/custom.sock", server=None, exists=lambda p: True
    )
    assert mode == "uds"
    assert target == "/tmp/custom.sock"


def test_default_socket_used_when_it_exists():
    mode, target = resolve_transport(
        socket_path=None, server=None, exists=lambda p: p == DEFAULT_SOCKET
    )
    assert mode == "uds"
    assert target == DEFAULT_SOCKET


def test_falls_back_to_tcp_default_when_no_socket():
    mode, target = resolve_transport(
        socket_path=None, server=None, exists=lambda p: False
    )
    assert mode == "tcp"
    assert target == DEFAULT_SERVER


def test_explicit_socket_path_used_even_if_missing():
    """An explicitly requested socket is honored regardless of existence —
    surfacing a connection error later is clearer than silently using TCP."""
    mode, target = resolve_transport(
        socket_path="/tmp/missing.sock", server=None, exists=lambda p: False
    )
    assert mode == "uds"
    assert target == "/tmp/missing.sock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/tui/test_client.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'baluhost_tui.client'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/baluhost_tui/client.py`:

```python
"""HTTP client for the rebuilt TUI.

Speaks to the backend over a Unix socket (production, channel=local) or
TCP loopback (dev, where BALUHOST_LOCAL_LOOPBACK_FALLBACK makes 127.0.0.1
count as local). One client, two bindings, identical API.
"""
from __future__ import annotations

import os
from typing import Any, Callable

import httpx

DEFAULT_SOCKET = "/run/baluhost/local.sock"
DEFAULT_SERVER = "http://127.0.0.1:3001"


def resolve_transport(
    socket_path: str | None,
    server: str | None,
    exists: Callable[[str], bool] = os.path.exists,
) -> tuple[str, str]:
    """Decide the transport binding.

    Precedence:
      1. explicit ``server``      -> ("tcp", server)
      2. explicit ``socket_path`` -> ("uds", socket_path)  (honored even if missing)
      3. default socket exists    -> ("uds", DEFAULT_SOCKET)
      4. otherwise                -> ("tcp", DEFAULT_SERVER)
    """
    if server is not None:
        return "tcp", server
    if socket_path is not None:
        return "uds", socket_path
    if exists(DEFAULT_SOCKET):
        return "uds", DEFAULT_SOCKET
    return "tcp", DEFAULT_SERVER
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/tui/test_client.py -v --no-cov`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tui/client.py backend/tests/tui/test_client.py
git commit -m "feat(tui): resolve_transport() for UDS/TCP selection"
```

---

## Task 2: `BackendClient` — httpx wrapper with JWT + verb passthrough

**Files:**
- Modify: `backend/baluhost_tui/client.py`
- Test: `backend/tests/tui/test_client.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/tui/test_client.py`:

```python
import httpx
from baluhost_tui.client import BackendClient


def _mock_backend_client(handler) -> BackendClient:
    """Build a BackendClient backed by an httpx.MockTransport for offline tests."""
    transport = httpx.MockTransport(handler)
    raw = httpx.Client(transport=transport, base_url="http://localhost")
    return BackendClient(_client=raw)


def test_get_passes_through_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"ok": True})

    client = _mock_backend_client(handler)
    resp = client.get("/api/admin/services")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert seen == {"method": "GET", "path": "/api/admin/services"}


def test_set_token_adds_authorization_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={})

    client = _mock_backend_client(handler)
    client.set_token("jwt-abc")
    client.get("/api/system/channel-status")

    assert seen["auth"] == "Bearer jwt-abc"


def test_post_sends_json_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content"] = request.content
        return httpx.Response(200, json={"created": True})

    client = _mock_backend_client(handler)
    resp = client.post("/api/users/bulk-delete", json=[1, 2, 3])

    assert resp.json() == {"created": True}
    assert seen["method"] == "POST"
    assert b"1" in seen["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/tui/test_client.py -v --no-cov`
Expected: FAIL with `ImportError: cannot import name 'BackendClient'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/baluhost_tui/client.py`:

```python
class BackendClient:
    """Thin wrapper over httpx.Client.

    Exposes ``get/post/put/delete`` that take API paths and return
    ``httpx.Response`` — drop-in for the FakeClient interface used by the
    existing screen helpers. Holds the JWT and injects the Authorization
    header on every request.
    """

    def __init__(
        self,
        socket_path: str | None = None,
        server: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        *,
        _client: httpx.Client | None = None,
    ) -> None:
        if _client is not None:
            # Injected transport (tests).
            self._client = _client
        else:
            mode, target = resolve_transport(socket_path, server)
            if mode == "uds":
                self._client = httpx.Client(
                    transport=httpx.HTTPTransport(uds=target),
                    base_url="http://localhost",
                    timeout=timeout,
                )
            else:
                self._client = httpx.Client(base_url=target, timeout=timeout)
        if token:
            self.set_token(token)

    def set_token(self, token: str) -> None:
        """Set/replace the bearer token used for all subsequent requests."""
        self._client.headers["Authorization"] = f"Bearer {token}"

    def clear_token(self) -> None:
        self._client.headers.pop("Authorization", None)

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.get(path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.post(path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.put(path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.delete(path, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BackendClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/tui/test_client.py -v --no-cov`
Expected: PASS (8 passed total).

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tui/client.py backend/tests/tui/test_client.py
git commit -m "feat(tui): BackendClient httpx wrapper with JWT + verb passthrough"
```

---

## Task 3: `api/auth.login()` — JWT acquisition

**Files:**
- Create: `backend/baluhost_tui/api/__init__.py`
- Create: `backend/baluhost_tui/api/auth.py`
- Test: `backend/tests/tui/test_api_auth.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tui/test_api_auth.py`:

```python
"""Tests for baluhost_tui.api.auth.login."""
from __future__ import annotations

from typing import Any

import pytest

from baluhost_tui.api.auth import login, LoginError, TwoFactorRequired


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp
        self.calls: list[tuple[str, Any]] = []

    def post(self, path: str, json: Any = None, **_: Any) -> _Resp:
        self.calls.append((path, json))
        return self._resp


def test_login_returns_access_token():
    client = _FakeClient(_Resp(200, {"access_token": "jwt-xyz", "user": {"role": "admin"}}))
    token = login(client, "admin", "pw")
    assert token == "jwt-xyz"
    assert client.calls == [("/api/auth/login", {"username": "admin", "password": "pw"})]


def test_login_raises_login_error_on_401():
    client = _FakeClient(_Resp(401, {"detail": "Invalid credentials"}))
    with pytest.raises(LoginError):
        login(client, "admin", "wrong")


def test_login_raises_two_factor_required_on_pending_token():
    client = _FakeClient(_Resp(200, {"pending_token": "pend-123"}))
    with pytest.raises(TwoFactorRequired):
        login(client, "admin", "pw")


def test_login_raises_login_error_on_unexpected_200_shape():
    client = _FakeClient(_Resp(200, {"something_else": 1}))
    with pytest.raises(LoginError):
        login(client, "admin", "pw")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/tui/test_api_auth.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'baluhost_tui.api'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/baluhost_tui/api/__init__.py`:

```python
"""Typed API wrappers for the TUI. Each module mirrors a backend route domain."""
```

Create `backend/baluhost_tui/api/auth.py`:

```python
"""Auth API wrapper: acquire a JWT over the BackendClient.

The backend's POST /api/auth/login returns either {access_token, user} or,
for 2FA-protected accounts, {pending_token}. This wrapper turns those into
a token string or a typed exception.
"""
from __future__ import annotations

from typing import Any, Protocol


class _Client(Protocol):
    def post(self, path: str, json: Any = ..., **kwargs: Any) -> Any: ...


class LoginError(Exception):
    """Login failed (bad credentials, network error, or unexpected response)."""


class TwoFactorRequired(Exception):
    """The account requires a second factor; carries the pending token."""

    def __init__(self, pending_token: str) -> None:
        super().__init__("two-factor authentication required")
        self.pending_token = pending_token


def login(client: _Client, username: str, password: str) -> str:
    """Log in and return the access token.

    Raises:
        TwoFactorRequired: account has 2FA enabled (carries pending_token).
        LoginError: invalid credentials, transport failure, or odd response.
    """
    try:
        resp = client.post(
            "/api/auth/login", json={"username": username, "password": password}
        )
    except Exception as exc:  # transport-level failure
        raise LoginError(f"request failed: {exc}") from exc

    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, dict):
            token = data.get("access_token")
            if isinstance(token, str) and token:
                return token
            pending = data.get("pending_token")
            if isinstance(pending, str) and pending:
                raise TwoFactorRequired(pending)
        raise LoginError("unexpected login response")

    if resp.status_code == 401:
        raise LoginError("invalid username or password")
    raise LoginError(f"login failed: HTTP {resp.status_code}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/tui/test_api_auth.py -v --no-cov`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tui/api/__init__.py backend/baluhost_tui/api/auth.py backend/tests/tui/test_api_auth.py
git commit -m "feat(tui): api.auth.login() with typed 2FA/error handling"
```

---

## Task 4: `api/system` — channel status + app restart/shutdown

**Files:**
- Create: `backend/baluhost_tui/api/system.py`
- Test: `backend/tests/tui/test_api_system.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/tui/test_api_system.py`:

```python
"""Tests for baluhost_tui.api.system wrappers."""
from __future__ import annotations

from typing import Any

from baluhost_tui.api.system import get_channel_status, restart_app, shutdown_app


class _Resp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.responses: dict[tuple[str, str], _Resp] = {}

    def get(self, path: str, **_: Any) -> _Resp:
        self.requests.append(("GET", path))
        return self.responses[("GET", path)]

    def post(self, path: str, **_: Any) -> _Resp:
        self.requests.append(("POST", path))
        return self.responses.get(("POST", path), _Resp(200, {"message": "scheduled"}))


def test_get_channel_status_returns_channel_string():
    client = _FakeClient()
    client.responses[("GET", "/api/system/channel-status")] = _Resp(200, {"channel": "local"})
    assert get_channel_status(client) == "local"


def test_get_channel_status_defaults_to_remote_on_failure():
    class _Boom:
        def get(self, *_: Any, **__: Any):
            raise RuntimeError("offline")

    assert get_channel_status(_Boom()) == "remote"


def test_restart_app_posts_correct_path_and_reports_ok():
    client = _FakeClient()
    ok, msg = restart_app(client)
    assert ok is True
    assert ("POST", "/api/system/restart") in client.requests
    assert "scheduled" in msg


def test_shutdown_app_reports_failure_on_4xx():
    client = _FakeClient()
    client.responses[("POST", "/api/system/shutdown")] = _Resp(403, {"detail": "nope"})
    ok, msg = shutdown_app(client)
    assert ok is False
    assert "403" in msg or "nope" in msg.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/tui/test_api_system.py -v --no-cov`
Expected: FAIL with `ModuleNotFoundError: No module named 'baluhost_tui.api.system'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/baluhost_tui/api/system.py`:

```python
"""System API wrappers: trust channel + app lifecycle (restart/shutdown).

These cover the app-process restart/shutdown endpoints (admin-only, any
channel). OS-level reboot/poweroff is an open item — no backend endpoint yet.
"""
from __future__ import annotations

from typing import Any, Protocol


class _Client(Protocol):
    def get(self, path: str, **kwargs: Any) -> Any: ...
    def post(self, path: str, **kwargs: Any) -> Any: ...


def get_channel_status(client: _Client) -> str:
    """GET /api/system/channel-status -> 'local' | 'remote'.

    Fails safe to 'remote' on any error so the UI defaults to the
    more-restricted view (destructive actions shown as unavailable).
    """
    try:
        resp = client.get("/api/system/channel-status")
        data = resp.json()
        channel = data.get("channel") if isinstance(data, dict) else None
        return channel if channel in ("local", "remote") else "remote"
    except Exception:
        return "remote"


def _post_action(client: _Client, path: str) -> tuple[bool, str]:
    try:
        resp = client.post(path, json={})
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
            return False, f"HTTP {resp.status_code}: {detail}".strip()
        try:
            message = resp.json().get("message", "ok")
        except Exception:
            message = "ok"
        return True, message
    except Exception as exc:
        return False, f"request failed: {exc}"


def restart_app(client: _Client) -> tuple[bool, str]:
    """POST /api/system/restart — restart the backend app process."""
    return _post_action(client, "/api/system/restart")


def shutdown_app(client: _Client) -> tuple[bool, str]:
    """POST /api/system/shutdown — stop the backend app process."""
    return _post_action(client, "/api/system/shutdown")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/tui/test_api_system.py -v --no-cov`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tui/api/system.py backend/tests/tui/test_api_system.py
git commit -m "feat(tui): api.system channel-status + app restart/shutdown"
```

---

## Task 5: Verify the whole TUI suite is green (no regressions)

**Files:** none changed.

- [ ] **Step 1: Run the full TUI test suite**

Run: `cd backend && python -m pytest tests/tui/ -v --no-cov`
Expected: all tests pass — the new `test_client.py` (8), `test_api_auth.py` (4), `test_api_system.py` (4), plus the pre-existing `test_app_actions.py`, `test_login_token.py`, `test_power_screen.py`, `test_services_screen.py`, `test_smart_screen.py` unchanged and green.

- [ ] **Step 2: Import-smoke the new modules**

Run: `cd backend && python -c "from baluhost_tui.client import BackendClient, resolve_transport; from baluhost_tui.api import auth, system; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Confirm the existing TUI still launches (manual, optional)**

The existing `app.py`/`main.py` are untouched in this plan, so `baluhost-tui` behaves exactly as before. No action required beyond noting it.

---

## Self-Review

**1. Spec coverage (this plan's slice — "Foundation"):**
- Spec "Transport — one client, two bindings" → Tasks 1+2 (`resolve_transport`, `BackendClient` UDS/TCP). ✓
- Spec "Auth — JWT still required" → Task 3 (`api.auth.login`, incl. 2FA-pending detection). ✓
- Spec "New foundation layer: client.py, api/" → Tasks 1–4. ✓
- Deferred to Plan 2 (explicitly out of this plan): `screens/base.py`, `widgets/ConfirmDialog`, `app.py`/`main.py` cutover, JWT `LoginScreen`, screen ports, removal of `context.py`/direct-DB/files screen. Stated in "Why this is working software".
- Deferred to Plan 3: plugins/vpn/network/settings/live-logs screens, final cleanup, `TUI_FEATURE_AUDIT.md` update.

**2. Placeholder scan:** No TBD/TODO; every code step has complete code; every test step has full assertions and exact run commands. ✓

**3. Type consistency:** `BackendClient.get/post/put/delete` return `httpx.Response`; the `api/*` wrappers accept any object with matching `get`/`post` (Protocol) and are tested against both `BackendClient` (via MockTransport) and the inline `_FakeClient`. `resolve_transport` returns `tuple[str, str]` consumed by `BackendClient.__init__`. `login` returns `str` / raises `LoginError`|`TwoFactorRequired`. `get_channel_status` returns `'local'|'remote'`; `restart_app`/`shutdown_app` return `tuple[bool, str]`. Consistent across tasks. ✓

**4. `--no-cov` note:** The repo's `pytest.ini` sets `--cov=app` which would report 0% on `baluhost_tui` and is irrelevant here; `--no-cov` keeps task runs fast and focused. The full CI suite still runs its own config.

---

## Next plans (outline — written after this one is approved/merged to avoid API drift)

**Plan 2 — App cutover + screen ports + destructive ops**
- `screens/base.py` (`BaseScreen`: `self.client`, common `q`/`r` bindings, error-toast helper).
- `widgets/confirm.py` (`ConfirmDialog` + pure `confirm_matches()` validator, type-to-confirm).
- Rewire `main.py` (`--socket`/`--server` replacing `--mode`) and `app.py` (single `self.client`, pass to screens).
- New JWT-only `LoginScreen` (remove direct-DB; show clear message on `403 local_channel_required`; handle `TwoFactorRequired`).
- Port `services`, `smart`, `power` (+ app-restart/shutdown actions) onto `BackendClient`.
- Port `dashboard`, `users` (remove direct-DB) + `users` **bulk-delete**.
- `RAID` **create-array/delete-array/format-disk** behind `ConfirmDialog`.
- Remove `context.py` usage + the file-browser screen; keep `reset-password`/`files-*` CLI.

**Plan 3 — New screens + cleanup**
- New screens: `plugins` (**install/uninstall**), `vpn` (read + **sync-server-keys**), `network`, `settings`, live system logs.
- Centralize the `sys.path` hack, fix the hardcoded welcome version, update `TUI_FEATURE_AUDIT.md`.
- Open items to settle here: live-logs source (journald endpoint vs existing logs API); OS reboot/poweroff decision.
