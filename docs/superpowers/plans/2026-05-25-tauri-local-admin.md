# Tauri Companion App + Local-Channel Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Unix-socket-bound second backend process plus a thin Tauri shell that consumes it, then gate ~13 destructive admin endpoints (RAID destroy/create/format, plugin install/uninstall, VPN key sync, user bulk-delete, setup wizard) behind a `require_local_admin` dependency that requires both admin JWT AND local-channel origin.

**Architecture:** One Python codebase, two systemd units. The TCP-bound unit serves the Web UI (`channel=remote`), the UDS-bound unit serves the Tauri Companion (`channel=local`). A new `ChannelMarkerMiddleware` sets `request.state.channel` from `settings.channel`. A new `require_local_admin` dependency composes `get_current_admin` + a channel check. The Tauri Rust shell is a 50-line reverse-proxy from `127.0.0.1:<random-port>` to the Unix socket; the React build is shared with the Web UI.

**Tech Stack:** FastAPI / Starlette / Pydantic v2 (backend), systemd socket activation, Uvicorn, React 18 + TypeScript + Vite (frontend), Tauri 2.x (Rust shell), hyper + hyperlocal (Rust proxy), pytest + Vitest + Playwright (tests).

**Spec:** `docs/superpowers/specs/2026-05-25-tauri-local-admin-design.md`

---

## File Structure

### Backend (new files)
- `backend/app/middleware/channel_marker.py` — ChannelMarkerMiddleware
- `backend/tests/middleware/test_channel_marker.py`
- `backend/tests/api/test_require_local_admin.py`

### Backend (modified files)
- `backend/app/core/config.py` — `channel`, `local_loopback_fallback` fields + validator
- `backend/app/main.py` — register middleware
- `backend/app/api/deps.py` — `require_local_admin`, `require_local_or_setup_secret`
- `backend/app/api/routes/system.py` — `/channel-status` endpoint
- `backend/app/schemas/system.py` — `ChannelStatusResponse`
- `backend/app/api/routes/system_raid.py` — promote 3 endpoints
- `backend/app/api/routes/plugins.py` — promote `uninstall_plugin`
- `backend/app/api/routes/plugins_marketplace.py` — promote `install_plugin`, `uninstall_plugin`
- `backend/app/api/routes/vpn.py` — promote `sync_server_keys`
- `backend/app/api/routes/users.py` — promote `bulk_delete_users`
- `backend/app/api/routes/setup.py` — promote 5 endpoints, remove inline IP check
- `backend/app/middleware/CLAUDE.md` — document new middleware
- `backend/tests/conftest.py` — env default + `remote_client` fixture
- `start_dev.py` — set `BALUHOST_LOCAL_LOOPBACK_FALLBACK=true` for dev

### Frontend (new files)
- `client/src/api/channelStatus.ts`
- `client/src/hooks/useChannelStatus.ts`
- `client/src/hooks/__tests__/useChannelStatus.test.tsx`
- `client/src/components/LocalOnlyAction.tsx`
- `client/src/components/__tests__/LocalOnlyAction.test.tsx`
- `client/tests/e2e/local-only.spec.ts`

### Frontend (modified files)
- `client/src/lib/api.ts` — `getApiBase()` with Tauri branch
- `client/src/pages/RaidManagement.tsx` — wrap 3 buttons
- `client/src/components/VpnManagement.tsx` — wrap sync-server-keys button (locate during impl)
- `client/src/components/user-management/UserTable.tsx` — bulk-delete handling
- Plugin admin component(s) — locate during Task 18 (start at `client/src/components/PluginPage.tsx`)
- `client/src/components/setup/*.tsx` — banner when channel=remote during setup
- `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json`
- `client/package.json` — Tauri scripts + devDeps

### Tauri shell (new files)
- `client/src-tauri/Cargo.toml`
- `client/src-tauri/build.rs`
- `client/src-tauri/tauri.conf.json`
- `client/src-tauri/icons/icon.png` (placeholder)
- `client/src-tauri/src/main.rs`
- `client/src-tauri/src/proxy.rs`
- `client/src-tauri/tests/proxy_test.rs`

### Deploy (new files)
- `deploy/install/templates/baluhost-backend-local.socket`
- `deploy/install/templates/baluhost-backend-local.service`
- `deploy/install/templates/tmpfiles-baluhost.conf`

### CI/Docs (modified files)
- `.github/workflows/tauri-build.yml` — new
- `.github/CODEOWNERS` — add `/client/src-tauri/`, `/.github/workflows/tauri-build.yml`
- `.claude/rules/ci-cd-security.md` — Layer 1 inventory list
- `docs/companion-app-install.md` — new

---

## Task ordering rationale

Tasks are ordered so that **after each commit, the application still works**. Backend infrastructure lands first with NO endpoint promotions (zero behavior change). The first behavior change is the setup-wizard (least-frequently-clicked path; safe blast radius). Then progressively wider endpoints. Then frontend. Tauri shell last — by then all backend & web changes have shipped and Tauri is purely additive.

---

### Task 1: Backend — Settings fields for channel identity

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Locate the Settings class**

Open `backend/app/core/config.py`. Find the `class Settings(BaseSettings):` definition. Identify a place near other env-var-backed fields (next to `is_dev_mode` is a good landmark).

- [ ] **Step 2: Add the two new fields plus validator**

Add these fields inside the `Settings` class (placement near other simple fields is fine, but keep them above any `model_validator`):

```python
    channel: Literal["local", "remote"] = Field(
        default="remote",
        validation_alias="BALUHOST_CHANNEL",
        description=(
            "Trust channel of this backend process. Set to 'local' only in the "
            "UDS-bound systemd unit (baluhost-backend-local.service)."
        ),
    )
    local_loopback_fallback: bool = Field(
        default=False,
        validation_alias="BALUHOST_LOCAL_LOOPBACK_FALLBACK",
        description=(
            "Dev-only escape hatch: treat 127.0.0.1 TCP as local when no UDS is "
            "bound. Validator blocks this in production."
        ),
    )
```

Add `Literal` to the existing imports from `typing` if missing.

- [ ] **Step 3: Add the model validator that blocks loopback-fallback in prod**

Add after any existing `@field_validator`/`@model_validator` methods inside `Settings`:

```python
    @model_validator(mode="after")
    def _validate_loopback_fallback_only_in_dev(self) -> "Settings":
        if self.local_loopback_fallback and not self.is_dev_mode:
            raise ValueError(
                "BALUHOST_LOCAL_LOOPBACK_FALLBACK is dev-only — "
                "never set this in production"
            )
        return self
```

Add `model_validator` to the existing `from pydantic import ...` line if missing.

- [ ] **Step 4: Run a quick import-smoke**

Run: `cd backend && python -c "from app.core.config import settings; print(settings.channel)"`

Expected: prints `remote`.

- [ ] **Step 5: Verify prod-block of fallback**

Run:
```bash
cd backend && BALUHOST_LOCAL_LOOPBACK_FALLBACK=true NAS_MODE=prod python -c "from app.core.config import Settings; Settings()"
```

Expected: ValidationError mentioning "dev-only".

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(backend): add channel + loopback-fallback settings fields"
```

---

### Task 2: Backend — ChannelMarkerMiddleware

**Files:**
- Create: `backend/app/middleware/channel_marker.py`
- Create: `backend/tests/middleware/test_channel_marker.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/middleware/test_channel_marker.py`:

```python
"""Tests for ChannelMarkerMiddleware."""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.channel_marker import ChannelMarkerMiddleware


def _make_app(channel_provider, loopback_fallback=False, dev_mode=False):
    """Create a tiny FastAPI app with the middleware and a status endpoint."""
    app = FastAPI()
    app.add_middleware(
        ChannelMarkerMiddleware,
        channel_provider=channel_provider,
        loopback_fallback_provider=lambda: loopback_fallback,
        is_dev_provider=lambda: dev_mode,
    )

    @app.get("/x")
    async def x(request: Request):
        return {"channel": request.state.channel}

    return app


def test_channel_local_sets_request_state():
    app = _make_app(lambda: "local")
    client = TestClient(app)
    resp = client.get("/x")
    assert resp.status_code == 200
    assert resp.json() == {"channel": "local"}


def test_channel_remote_sets_request_state():
    app = _make_app(lambda: "remote")
    client = TestClient(app)
    resp = client.get("/x")
    assert resp.json() == {"channel": "remote"}


def test_loopback_fallback_treats_localhost_as_local_when_enabled_and_dev():
    app = _make_app(
        lambda: "remote", loopback_fallback=True, dev_mode=True
    )
    client = TestClient(app)
    # TestClient sets client host to "testclient" by default; override via header
    # is not possible — instead we verify the fallback path via direct call.
    # TestClient uses 'testclient' as scope['client'][0]; for loopback testing
    # we set the host explicitly using the headers approach below.
    resp = client.get("/x", headers={"host": "testserver"})
    # client.host == 'testclient' which is NOT loopback, so channel stays remote
    assert resp.json() == {"channel": "remote"}


def test_loopback_fallback_not_applied_when_disabled():
    app = _make_app(lambda: "remote", loopback_fallback=False)
    client = TestClient(app)
    resp = client.get("/x")
    assert resp.json() == {"channel": "remote"}


def test_invalid_channel_value_raises_at_request_time():
    app = _make_app(lambda: "foobar")
    client = TestClient(app)
    with pytest.raises(ValueError, match="Invalid channel"):
        client.get("/x")
```

- [ ] **Step 2: Run tests to verify they fail (module missing)**

Run: `cd backend && python -m pytest tests/middleware/test_channel_marker.py -v`

Expected: ImportError / "No module named 'app.middleware.channel_marker'".

- [ ] **Step 3: Implement the middleware**

Create `backend/app/middleware/channel_marker.py`:

```python
"""Marks each incoming request with its trust channel (local|remote).

The channel value comes from a provider callable (in production wired to
settings.channel via main.py). Using a callable instead of a fixed __init__
value lets tests monkeypatch settings without rebuilding the app.

An attacker on the TCP-bound process cannot spoof local-channel status
regardless of headers — the channel value is taken from server-side config,
not the request.
"""
import logging
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

VALID_CHANNELS = {"local", "remote"}


class ChannelMarkerMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        channel_provider: Callable[[], str],
        loopback_fallback_provider: Callable[[], bool] = lambda: False,
        is_dev_provider: Callable[[], bool] = lambda: False,
    ):
        super().__init__(app)
        self._channel_provider = channel_provider
        self._loopback_fallback_provider = loopback_fallback_provider
        self._is_dev_provider = is_dev_provider

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        channel = self._channel_provider()
        if channel not in VALID_CHANNELS:
            raise ValueError(
                f"Invalid channel '{channel}' — must be one of {VALID_CHANNELS}"
            )

        # Dev-only loopback fallback
        if (
            channel == "remote"
            and self._loopback_fallback_provider()
            and self._is_dev_provider()
        ):
            host = request.client.host if request.client else None
            if host in {"127.0.0.1", "::1"} or (host or "").startswith("::ffff:127."):
                channel = "local"

        request.state.channel = channel
        return await call_next(request)
```

Also create the package init if missing — verify `backend/tests/middleware/__init__.py` exists; if not, create empty file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/middleware/test_channel_marker.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/channel_marker.py backend/tests/middleware/test_channel_marker.py
# include __init__.py if newly created
git commit -m "feat(backend): add ChannelMarkerMiddleware with provider injection"
```

---

### Task 3: Backend — Register middleware in main.py

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Locate the middleware registration block**

Open `backend/app/main.py`. Find the section that calls `app.add_middleware(...)` for the existing middlewares (security_headers, error_counter, etc.). Note the ordering convention.

- [ ] **Step 2: Add the import**

In the imports section near other middleware imports, add:

```python
from app.middleware.channel_marker import ChannelMarkerMiddleware
```

- [ ] **Step 3: Add the registration**

Add this `add_middleware` call near the other middleware registrations. Order does not matter functionally (channel marker only sets state, doesn't short-circuit), but place it BEFORE any middleware that might read `request.state.channel` — for now nothing else does, so placement near the top of the middleware chain is fine:

```python
app.add_middleware(
    ChannelMarkerMiddleware,
    channel_provider=lambda: settings.channel,
    loopback_fallback_provider=lambda: settings.local_loopback_fallback,
    is_dev_provider=lambda: settings.is_dev_mode,
)
```

Verify `settings` is already imported (it should be; it's used everywhere).

- [ ] **Step 4: Boot the app and verify nothing breaks**

Run: `cd backend && python -c "from app.main import app; print('OK')"`

Expected: `OK` (no errors).

- [ ] **Step 5: Run all existing backend tests to ensure no regressions**

Run: `cd backend && python -m pytest -x --timeout=60`

Expected: All existing tests still pass. The channel middleware sets request.state.channel but no test consumes it yet, so behavior is unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(backend): wire ChannelMarkerMiddleware into app factory"
```

---

### Task 4: Backend — ChannelStatusResponse schema + `/api/system/channel-status` endpoint

**Files:**
- Modify: `backend/app/schemas/system.py`
- Modify: `backend/app/api/routes/system.py`
- Create: `backend/tests/api/test_channel_status_route.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_channel_status_route.py`:

```python
"""Tests for GET /api/system/channel-status."""
import pytest
from app.core.config import settings


def test_channel_status_returns_remote_by_default(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    resp = client.get("/api/system/channel-status", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"channel": "remote"}


def test_channel_status_returns_local_when_configured(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "channel", "local")
    resp = client.get("/api/system/channel-status", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"channel": "local"}


def test_channel_status_requires_auth(client):
    resp = client.get("/api/system/channel-status")
    assert resp.status_code == 401


def test_channel_status_works_for_non_admin_user(client, user_headers, monkeypatch):
    """Channel status is visible to any authenticated user (not sensitive)."""
    monkeypatch.setattr(settings, "channel", "local")
    resp = client.get("/api/system/channel-status", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json() == {"channel": "local"}
```

- [ ] **Step 2: Run tests to verify they fail (404 endpoint missing)**

Run: `cd backend && python -m pytest tests/api/test_channel_status_route.py -v`

Expected: tests fail because the endpoint doesn't exist (404 instead of expected status).

- [ ] **Step 3: Add the response schema**

Open `backend/app/schemas/system.py`. Find a sensible location near other small response models (e.g., near `SystemHealthResponse`). Add:

```python
class ChannelStatusResponse(BaseModel):
    channel: Literal["local", "remote"]
```

Add `Literal` to existing `from typing import ...` if not already imported.

- [ ] **Step 4: Add the endpoint**

Open `backend/app/api/routes/system.py`. Add the import for the new schema near other system schema imports:

```python
from app.schemas.system import ChannelStatusResponse
```

Add the endpoint. Place it near other simple status-style endpoints in the file:

```python
@router.get("/channel-status", response_model=ChannelStatusResponse)
async def get_channel_status(
    request: Request,
    _: UserPublic = Depends(deps.get_current_user),
) -> ChannelStatusResponse:
    """Returns whether the current connection is via the local channel.

    Used by the web UI to disable destructive-action buttons and show a
    hint that the Companion app is required. Auth: any authenticated user.
    """
    return ChannelStatusResponse(channel=getattr(request.state, "channel", "remote"))
```

Verify `Request`, `Depends`, `deps`, `UserPublic` are already imported in this file — they will be (the file has many endpoints already).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_channel_status_route.py -v`

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/system.py backend/app/api/routes/system.py backend/tests/api/test_channel_status_route.py
git commit -m "feat(backend): add GET /api/system/channel-status endpoint"
```

---

### Task 5: Backend — `require_local_admin` dependency

**Files:**
- Modify: `backend/app/api/deps.py`
- Create: `backend/tests/api/test_require_local_admin.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_require_local_admin.py`:

```python
"""Tests for the require_local_admin dependency.

We exercise it via a temporary endpoint mounted in the test app so we don't
have to pick one of the real category-S endpoints (those get gated later).
"""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import settings
from app.middleware.channel_marker import ChannelMarkerMiddleware
from app.schemas.user import UserPublic


def _wire(app: FastAPI):
    """Mount a tiny endpoint that uses require_local_admin."""
    @app.post("/test/locally-gated")
    async def locally_gated(
        current_admin: UserPublic = Depends(deps.require_local_admin),
    ):
        return {"username": current_admin.username, "ok": True}


def test_local_admin_passes(client, admin_headers, monkeypatch):
    """channel=local + admin token → 200."""
    monkeypatch.setattr(settings, "channel", "local")
    _wire(client.app)
    resp = client.post("/test/locally-gated", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_remote_admin_blocked_with_structured_error(client, admin_headers, monkeypatch):
    """channel=remote + admin token → 403 local_channel_required."""
    monkeypatch.setattr(settings, "channel", "remote")
    _wire(client.app)
    resp = client.post("/test/locally-gated", headers=admin_headers)
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["error"] == "local_channel_required"


def test_unauth_returns_401_not_403(client, monkeypatch):
    """No token → 401 (auth fires first), not 403 local_channel_required."""
    monkeypatch.setattr(settings, "channel", "remote")
    _wire(client.app)
    resp = client.post("/test/locally-gated")
    assert resp.status_code == 401


def test_non_admin_user_blocked_with_admin_required(client, user_headers, monkeypatch):
    """User token + channel=local → 403 (admin gate fires before channel check)."""
    monkeypatch.setattr(settings, "channel", "local")
    _wire(client.app)
    resp = client.post("/test/locally-gated", headers=user_headers)
    assert resp.status_code == 403
    # Existing get_current_admin returns the legacy string detail
    assert "Admin" in str(resp.json()["detail"])


def test_audit_log_written_on_remote_block(client, admin_headers, monkeypatch, db_session):
    """A remote-blocked admin call writes an audit log entry with the username."""
    from app.models.audit_log import AuditLog
    monkeypatch.setattr(settings, "channel", "remote")
    _wire(client.app)

    before = db_session.query(AuditLog).filter(
        AuditLog.action == "local_channel_required_denied"
    ).count()

    client.post("/test/locally-gated", headers=admin_headers)

    after = db_session.query(AuditLog).filter(
        AuditLog.action == "local_channel_required_denied"
    ).count()
    assert after == before + 1

    entry = db_session.query(AuditLog).filter(
        AuditLog.action == "local_channel_required_denied"
    ).order_by(AuditLog.id.desc()).first()
    assert entry.user == settings.admin_username
```

- [ ] **Step 2: Run tests to verify they fail (dependency missing)**

Run: `cd backend && python -m pytest tests/api/test_require_local_admin.py -v`

Expected: AttributeError "module 'app.api.deps' has no attribute 'require_local_admin'".

- [ ] **Step 3: Implement the dependency**

Open `backend/app/api/deps.py`. Append at the end (after the other `get_current_*` deps):

```python
async def require_local_admin(
    request: Request,
    user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> UserPublic:
    """Combined gate: admin role AND local channel.

    Returns the authenticated admin user on success. On failure:
      - 401 if no JWT (handled by the get_current_admin → get_current_user chain)
      - 403 "Admin required" if user is not admin (get_current_admin)
      - 403 with structured local_channel_required detail if admin but remote

    Failed local-channel checks are audit-logged with the resolved username.
    """
    channel = getattr(request.state, "channel", "remote")
    if channel != "local":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="local_channel_required_denied",
            user=user.username,
            details={"path": request.url.path, "role": user.role},
            success=False,
            db=db,
        )
        logger.warning(
            "local_channel_required: user=%s path=%s client=%s",
            user.username,
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "local_channel_required",
                "message": (
                    "This operation can only be performed from the BaluHost "
                    "Companion app running on the server itself."
                ),
            },
        )
    return user
```

Verify these imports exist in `deps.py`: `Request`, `Depends`, `HTTPException`, `status`, `Session`, `get_db`, `get_current_admin`, `UserPublic`, `get_audit_logger_db`, `logger`. Add any that are missing — most should already be present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_require_local_admin.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/deps.py backend/tests/api/test_require_local_admin.py
git commit -m "feat(backend): add require_local_admin dependency with audit logging"
```

---

### Task 6: Backend — `require_local_or_setup_secret` dependency

**Files:**
- Modify: `backend/app/api/deps.py`
- Create: `backend/tests/api/test_require_local_or_setup_secret.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_require_local_or_setup_secret.py`:

```python
"""Tests for require_local_or_setup_secret (used by setup wizard)."""
import pytest
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.api import deps
from app.core.config import settings


class _Payload(BaseModel):
    setup_secret: str | None = None


def _wire(app: FastAPI):
    @app.post("/test/setup-gated")
    async def setup_gated(
        payload: _Payload,
        _: None = Depends(deps.require_local_or_setup_secret),
    ):
        return {"ok": True}


def test_passes_on_local_channel(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "local")
    monkeypatch.setattr(settings, "setup_secret", "")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={})
    assert resp.status_code == 200


def test_blocked_on_remote_without_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={})
    assert resp.status_code == 403


def test_passes_on_remote_with_matching_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "s3cret")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={"setup_secret": "s3cret"})
    assert resp.status_code == 200


def test_blocked_on_remote_with_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "channel", "remote")
    monkeypatch.setattr(settings, "setup_secret", "s3cret")
    _wire(client.app)
    resp = client.post("/test/setup-gated", json={"setup_secret": "wrong"})
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_require_local_or_setup_secret.py -v`

Expected: AttributeError "module 'app.api.deps' has no attribute 'require_local_or_setup_secret'".

- [ ] **Step 3: Implement the dependency**

Append to `backend/app/api/deps.py`:

```python
async def require_local_or_setup_secret(
    request: Request,
) -> None:
    """Setup-wizard gate: requires local channel OR a matching setup_secret.

    The setup secret is read from the JSON body field 'setup_secret' (also
    looked up under settings.setup_secret server-side). This lets the wizard
    work over the local channel (Tauri app) by default while preserving an
    Ansible/provisioning bypass when an operator sets BALUHOST_SETUP_SECRET.
    """
    channel = getattr(request.state, "channel", "remote")
    if channel == "local":
        return

    # Remote: require setup_secret in body
    body_secret: str | None = None
    if settings.setup_secret:
        try:
            body = await request.json()
            if isinstance(body, dict):
                body_secret = body.get("setup_secret")
        except Exception:
            body_secret = None

        if body_secret and body_secret == settings.setup_secret:
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "local_channel_required",
            "message": (
                "Initial setup is only available from the BaluHost Companion app "
                "or with a valid BALUHOST_SETUP_SECRET."
            ),
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_require_local_or_setup_secret.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/deps.py backend/tests/api/test_require_local_or_setup_secret.py
git commit -m "feat(backend): add require_local_or_setup_secret for setup wizard"
```

---

### Task 7: Backend — conftest.py default channel + `remote_client` fixture

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Set the env default at the very top of conftest.py**

Open `backend/tests/conftest.py`. **Before any `from app.*` import**, add:

```python
import os
# Ensure existing tests see channel=local by default (Tauri-like environment).
# Tests that verify the local-channel gate use the `remote_client` fixture
# below, which monkeypatches settings.channel to "remote".
os.environ.setdefault("BALUHOST_CHANNEL", "local")
```

If the very first lines are imports like `import pytest`, put this block right after the stdlib imports but BEFORE any `from app.*`.

- [ ] **Step 2: Add the remote_client fixture**

Find the `client` fixture (line ~158). Add this immediately after it:

```python
@pytest.fixture
def remote_client(client, monkeypatch):
    """TestClient with channel=remote — for verifying the local-channel gate.

    Uses the existing `client` fixture but monkeypatches settings.channel to
    'remote' for the lifetime of the test. Combine with `admin_headers` to
    verify that destructive endpoints return 403 local_channel_required when
    called via the (simulated) TCP path.
    """
    from app.core.config import settings as _settings
    monkeypatch.setattr(_settings, "channel", "remote")
    yield client
```

- [ ] **Step 3: Verify settings re-reads env at test start**

Open `backend/app/core/config.py`. The `settings` singleton is typically instantiated at module-import time. Confirm:

```python
settings = Settings()
```

near the bottom. This means env var `BALUHOST_CHANNEL=local` set in conftest.py is read at the first `from app.core.config import settings` import. Run a sanity check:

```bash
cd backend && python -m pytest tests/middleware/test_channel_marker.py -v
```

Expected: 5 passed (still — the existing middleware tests don't depend on env defaults).

- [ ] **Step 4: Run a smoke of an existing destructive endpoint test**

Run: `cd backend && python -m pytest tests/api/test_users_routes.py::TestUsersRoutes::test_bulk_delete_returns_stats -v`

Expected: PASS. Bulk-delete isn't gated yet, and channel=local fixture ensures it would pass even after gating.

- [ ] **Step 5: Run all backend tests to confirm zero regressions**

Run: `cd backend && python -m pytest -x --timeout=60`

Expected: All existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test(backend): default channel=local in tests + add remote_client fixture"
```

---

### Task 8: Deploy — systemd templates (socket + service + tmpfiles)

**Files:**
- Create: `deploy/install/templates/baluhost-backend-local.socket`
- Create: `deploy/install/templates/baluhost-backend-local.service`
- Create: `deploy/install/templates/tmpfiles-baluhost.conf`

- [ ] **Step 1: Create the socket unit**

Create `deploy/install/templates/baluhost-backend-local.socket`:

```ini
[Unit]
Description=BaluHost local-channel socket (Tauri Companion)

[Socket]
ListenStream=/run/baluhost/local.sock
SocketMode=0660
SocketUser=baluhost
SocketGroup=baluhost
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
```

- [ ] **Step 2: Create the service unit**

Create `deploy/install/templates/baluhost-backend-local.service`:

```ini
[Unit]
Description=BaluHost backend (local channel, Unix socket)
Requires=baluhost-backend-local.socket
After=baluhost-backend-local.socket network.target postgresql.service

[Service]
Type=simple
User=baluhost
Group=baluhost
WorkingDirectory=/opt/baluhost/backend
EnvironmentFile=/etc/baluhost/.env.production
Environment="BALUHOST_CHANNEL=local"
ExecStart=/opt/baluhost/venv/bin/uvicorn app.main:app \
    --fd 3 \
    --workers 2 \
    --log-level info
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Create the tmpfiles.d snippet**

Create `deploy/install/templates/tmpfiles-baluhost.conf`:

```
# Ensure /run/baluhost exists and is owned by the baluhost user.
# Installed to /etc/tmpfiles.d/baluhost.conf at deploy time.
d /run/baluhost 0755 baluhost baluhost - -
```

- [ ] **Step 4: Commit**

```bash
git add deploy/install/templates/baluhost-backend-local.socket \
        deploy/install/templates/baluhost-backend-local.service \
        deploy/install/templates/tmpfiles-baluhost.conf
git commit -m "deploy: systemd templates for baluhost-backend-local (UDS)"
```

> **Note:** Installer scripts that copy these templates to `/etc/systemd/system/` are out of scope for V1 — they're applied manually for the first deploy. The next BaluHost installer-script PR can pick them up.

---

### Task 9: Backend — Promote Setup-Wizard endpoints (remove inline IP check)

**Files:**
- Modify: `backend/app/api/routes/setup.py`
- Create: `backend/tests/setup/test_setup_local_channel_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/setup/test_setup_local_channel_gate.py`:

```python
"""Tests verifying the setup wizard uses the local-channel gate."""
import pytest
from app.core.config import settings


def test_setup_admin_blocked_on_remote_without_secret(remote_client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "setup_secret", "")
    # Ensure no users exist (setup-required state)
    from app.models.user import User
    db_session.query(User).delete()
    db_session.commit()

    resp = remote_client.post(
        "/api/setup/admin",
        json={"username": "admin2", "password": "Strong123!"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_setup_admin_passes_on_local(client, monkeypatch, db_session):
    """Default channel in test suite is 'local' — endpoint passes."""
    monkeypatch.setattr(settings, "setup_secret", "")
    from app.models.user import User
    db_session.query(User).delete()
    db_session.commit()

    resp = client.post(
        "/api/setup/admin",
        json={"username": "admin2", "password": "Strong123!"},
    )
    assert resp.status_code == 201


def test_setup_admin_passes_on_remote_with_secret(remote_client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "setup_secret", "ansible-go")
    from app.models.user import User
    db_session.query(User).delete()
    db_session.commit()

    resp = remote_client.post(
        "/api/setup/admin",
        json={
            "username": "admin2",
            "password": "Strong123!",
            "setup_secret": "ansible-go",
        },
    )
    assert resp.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/setup/test_setup_local_channel_gate.py -v`

Expected: First test fails (current inline `is_private_or_local_ip` check accepts the testclient IP).

- [ ] **Step 3: Patch `setup.py` — `create_admin`**

Open `backend/app/api/routes/setup.py`. Find the `create_admin` function (line ~77). Make these changes:

(a) Add import for the new dep at the top of the file imports (the `from app.api import deps` line already exists):

No new import needed — use `deps.require_local_or_setup_secret`.

(b) In the function signature, add the dependency:

```python
@router.post("/admin", response_model=SetupAdminResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_limit("setup_admin"))
async def create_admin(
    request: Request,
    payload: SetupAdminRequest,
    _: None = Depends(deps.require_local_or_setup_secret),
    db: Session = Depends(get_db),
) -> SetupAdminResponse:
    """Create the initial admin account (Step 1). Gated by local channel
    OR BALUHOST_SETUP_SECRET (see require_local_or_setup_secret)."""
    _require_setup_mode(db)
    # ... keep the rest of the function
```

(c) Remove the now-obsolete inline IP check (currently lines ~88-111 — the `if settings.setup_secret:` / `else:` block doing `is_private_or_local_ip`). The new dep handles both paths.

Specifically delete this block (current `setup.py:88-111`):

```python
    # Setup secret check
    if settings.setup_secret:
        if payload.setup_secret != settings.setup_secret:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid setup secret",
            )
    else:
        # No secret configured — enforce local-network-only access (production only).
        if not settings.is_dev_mode:
            client_ip = request.client.host if request.client else None
            if client_ip is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Setup is only available from the local network",
                )
            from app.core.network_utils import is_private_or_local_ip
            if not is_private_or_local_ip(client_ip):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Setup is only available from the local network",
                )
```

- [ ] **Step 4: Patch the four other setup endpoints**

For each of these (lines ~150, ~185, ~207, ~242), add `_: None = Depends(deps.require_local_or_setup_secret)` before the existing `_setup_user=Depends(deps.get_setup_user)`:

- `create_user` (POST /users)
- `delete_setup_user` (DELETE /users/{user_id})
- `configure_file_access` (POST /file-access)
- `complete_setup` (POST /complete)

Example for `create_user`:

```python
@router.post("/users", response_model=SetupUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: SetupUserRequest,
    _: None = Depends(deps.require_local_or_setup_secret),
    _setup_user=Depends(deps.get_setup_user),
    db: Session = Depends(get_db),
) -> SetupUserResponse:
    ...
```

Note: `delete_setup_user` does not take a body payload, so the `setup_secret`-in-body bypass won't work for it from a remote channel. That's acceptable — operators using the secret bypass should call `/admin` to get the setup-token first, then chain through the same provisioning script via that token.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/setup/test_setup_local_channel_gate.py tests/setup/ -v`

Expected: New tests pass; existing setup tests also pass (they use the default-`local` channel).

- [ ] **Step 6: Run the broader test suite**

Run: `cd backend && python -m pytest tests/setup/ tests/api/ -x --timeout=60`

Expected: All green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/setup.py backend/tests/setup/test_setup_local_channel_gate.py
git commit -m "feat(setup): gate wizard endpoints via require_local_or_setup_secret"
```

---

### Task 10: Backend — Promote Plugin install/uninstall endpoints

**Files:**
- Modify: `backend/app/api/routes/plugins.py`
- Modify: `backend/app/api/routes/plugins_marketplace.py`
- Create: `backend/tests/api/test_plugin_local_channel_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_plugin_local_channel_gate.py`:

```python
"""Tests verifying plugin install/uninstall require local channel."""
import pytest


def test_plugins_uninstall_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.delete("/api/plugins/some-plugin", headers=admin_headers)
    # Either 403 local_channel_required OR 404 if the local-channel check fires
    # first (it should). Verify the structured error format.
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_marketplace_install_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/plugins/marketplace/some-plugin/install",
        json={"version": "1.0.0"},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_marketplace_uninstall_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.delete(
        "/api/plugins/marketplace/some-plugin",
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
```

Note: the marketplace router prefix might be `/api/plugins/marketplace` or `/api/plugins` depending on `routes/__init__.py`. If tests 404 instead of 403, check the actual mount prefix in `backend/app/api/routes/__init__.py` and adjust the test URLs.

- [ ] **Step 2: Run tests to verify they fail (endpoints not yet gated)**

Run: `cd backend && python -m pytest tests/api/test_plugin_local_channel_gate.py -v`

Expected: All three fail with 200/404/400 (or whatever the current handlers return for nonexistent plugins) instead of 403 local_channel_required.

- [ ] **Step 3: Patch `plugins.py:503` (`uninstall_plugin`)**

Open `backend/app/api/routes/plugins.py`. Find `uninstall_plugin` (line ~503). Change:

```python
async def uninstall_plugin(
    request: Request, response: Response,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
):
```

to:

```python
async def uninstall_plugin(
    request: Request, response: Response,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_local_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
):
```

Verify the import path: the file already imports `from app.api.deps import get_current_admin` etc. Either replace that with `from app.api import deps` (and update all the `get_current_admin` usages to `deps.get_current_admin`), or add a targeted import: `from app.api.deps import require_local_admin`. Choose the lower-blast-radius option (targeted import) unless the file already uses the `deps.*` qualifier.

- [ ] **Step 4: Patch `plugins_marketplace.py:116` (`install_plugin`) and `:186` (`uninstall_plugin`)**

Open `backend/app/api/routes/plugins_marketplace.py`. For both endpoints, swap `Depends(get_current_admin)` → `Depends(deps.require_local_admin)` (or `Depends(require_local_admin)` with the targeted import).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_plugin_local_channel_gate.py -v`

Expected: 3 passed.

- [ ] **Step 6: Run existing plugin tests**

Run: `cd backend && python -m pytest tests/plugins/ tests/api/test_plugin_*_routes.py -x --timeout=60`

Expected: All pass (default-channel-local in conftest keeps existing tests green).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/plugins.py backend/app/api/routes/plugins_marketplace.py \
        backend/tests/api/test_plugin_local_channel_gate.py
git commit -m "feat(plugins): gate install/uninstall via require_local_admin"
```

---

### Task 11: Backend — Promote RAID destructive endpoints

**Files:**
- Modify: `backend/app/api/routes/system_raid.py`
- Create: `backend/tests/api/test_raid_local_channel_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_raid_local_channel_gate.py`:

```python
"""Tests verifying destructive RAID endpoints require local channel."""


def test_delete_array_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/system/raid/delete-array",
        json={"array": "md0"},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_create_array_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/system/raid/create-array",
        json={"name": "md_test", "level": "raid1", "devices": ["sdc", "sdd"]},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_format_disk_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/system/raid/format-disk",
        json={"device": "sdc"},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_raid_local_channel_gate.py -v`

Expected: All three fail (current endpoints return 200/400/500 in dev mode).

- [ ] **Step 3: Patch `system_raid.py`**

Open `backend/app/api/routes/system_raid.py`. Find the three handlers: `delete_array` (line ~225), `create_array`, `format_disk`. For each, swap `Depends(deps.get_current_admin)` → `Depends(deps.require_local_admin)`. Example for `delete_array`:

```python
async def delete_array(
    request: Request,
    response: Response,
    payload: DeleteArrayRequest,
    current_admin: UserPublic = Depends(deps.require_local_admin),
) -> RaidActionResponse:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_raid_local_channel_gate.py -v`

Expected: 3 passed.

- [ ] **Step 5: Run existing RAID tests**

Run: `cd backend && python -m pytest tests/services/test_raid* tests/api/test_system_raid* tests/test_dev_mode.py -x --timeout=60`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/system_raid.py backend/tests/api/test_raid_local_channel_gate.py
git commit -m "feat(raid): gate destructive array operations via require_local_admin"
```

---

### Task 12: Backend — Promote VPN sync-server-keys

**Files:**
- Modify: `backend/app/api/routes/vpn.py`
- Create: `backend/tests/api/test_vpn_local_channel_gate.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_vpn_local_channel_gate.py`:

```python
def test_sync_server_keys_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post("/api/vpn/sync-server-keys", headers=admin_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_vpn_local_channel_gate.py -v`

Expected: 1 failure (endpoint currently returns 200 or 500).

- [ ] **Step 3: Patch `vpn.py:419` (`sync_server_keys`)**

In `backend/app/api/routes/vpn.py`, find `sync_server_keys` and swap `Depends(get_current_admin)` → `Depends(deps.require_local_admin)` (use a targeted import or `deps.*` qualifier consistent with existing patterns in the file).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_vpn_local_channel_gate.py -v`

Expected: 1 passed.

- [ ] **Step 5: Run existing VPN tests**

Run: `cd backend && python -m pytest tests/test_vpn* tests/api/test_vpn* -x --timeout=60`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/vpn.py backend/tests/api/test_vpn_local_channel_gate.py
git commit -m "feat(vpn): gate sync-server-keys via require_local_admin"
```

---

### Task 13: Backend — Promote User bulk-delete

**Files:**
- Modify: `backend/app/api/routes/users.py`
- Create: `backend/tests/api/test_users_local_channel_gate.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_users_local_channel_gate.py`:

```python
def test_bulk_delete_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/users/bulk-delete",
        json=["99999"],
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/api/test_users_local_channel_gate.py -v`

Expected: fails (currently returns 200 with deletion stats).

- [ ] **Step 3: Patch `users.py:194` (`bulk_delete_users`)**

In `backend/app/api/routes/users.py`, find `bulk_delete_users`. Swap `current_admin: UserPublic = Depends(deps.get_current_admin)` → `current_admin: UserPublic = Depends(deps.require_local_admin)`.

- [ ] **Step 4: Verify test passes**

Run: `cd backend && python -m pytest tests/api/test_users_local_channel_gate.py -v`

Expected: 1 passed.

- [ ] **Step 5: Existing user tests still green**

Run: `cd backend && python -m pytest tests/api/test_users_routes.py -x`

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/users.py backend/tests/api/test_users_local_channel_gate.py
git commit -m "feat(users): gate bulk-delete via require_local_admin"
```

---

### Task 14: Frontend — getChannelStatus API client

**Files:**
- Create: `client/src/api/channelStatus.ts`

- [ ] **Step 1: Create the API module**

Create `client/src/api/channelStatus.ts`:

```typescript
import { api } from '@/lib/api';

export interface ChannelStatusResponse {
  channel: 'local' | 'remote';
}

export async function getChannelStatus(): Promise<ChannelStatusResponse> {
  const res = await api.get<ChannelStatusResponse>('/system/channel-status');
  return res.data;
}
```

If the project's import alias is `~/lib/api` instead of `@/lib/api`, use that. Check `client/tsconfig.json` `compilerOptions.paths` if unsure — most likely `@/` based on Vite defaults.

- [ ] **Step 2: Sanity-check the import resolves**

Run: `cd client && npx tsc --noEmit -p tsconfig.json 2>&1 | head -20`

Expected: no errors mentioning `channelStatus.ts`.

- [ ] **Step 3: Commit**

```bash
git add client/src/api/channelStatus.ts
git commit -m "feat(client): add getChannelStatus API client"
```

---

### Task 15: Frontend — useChannelStatus hook + tests

**Files:**
- Create: `client/src/hooks/useChannelStatus.ts`
- Create: `client/src/hooks/__tests__/useChannelStatus.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `client/src/hooks/__tests__/useChannelStatus.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { useChannelStatus } from '../useChannelStatus';

vi.mock('@/api/channelStatus', () => ({
  getChannelStatus: vi.fn(),
}));

import { getChannelStatus } from '@/api/channelStatus';

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe('useChannelStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns isLocal=true when API says local', async () => {
    vi.mocked(getChannelStatus).mockResolvedValue({ channel: 'local' });
    const { result } = renderHook(() => useChannelStatus(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isLocal).toBe(true);
    expect(result.current.channel).toBe('local');
  });

  it('returns isLocal=false when API says remote', async () => {
    vi.mocked(getChannelStatus).mockResolvedValue({ channel: 'remote' });
    const { result } = renderHook(() => useChannelStatus(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isLocal).toBe(false);
    expect(result.current.channel).toBe('remote');
  });

  it('defaults to remote (fail-safe) while loading', () => {
    vi.mocked(getChannelStatus).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useChannelStatus(), { wrapper: makeWrapper() });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isLocal).toBe(false);
    expect(result.current.channel).toBe('remote');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail (hook missing)**

Run: `cd client && npx vitest run src/hooks/__tests__/useChannelStatus.test.tsx`

Expected: Module not found error.

- [ ] **Step 3: Implement the hook**

Create `client/src/hooks/useChannelStatus.ts`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { getChannelStatus } from '@/api/channelStatus';

export function useChannelStatus() {
  const { data, isLoading } = useQuery({
    queryKey: ['channel-status'],
    queryFn: getChannelStatus,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });

  return {
    channel: data?.channel ?? ('remote' as const),
    isLocal: data?.channel === 'local',
    isLoading,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/hooks/__tests__/useChannelStatus.test.tsx`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useChannelStatus.ts client/src/hooks/__tests__/useChannelStatus.test.tsx
git commit -m "feat(client): add useChannelStatus hook"
```

---

### Task 16: Frontend — LocalOnlyAction component + tests + i18n

**Files:**
- Create: `client/src/components/LocalOnlyAction.tsx`
- Create: `client/src/components/__tests__/LocalOnlyAction.test.tsx`
- Modify: `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json`

- [ ] **Step 1: Add i18n keys**

In `client/src/i18n/locales/de/common.json`, add inside the root object (or appropriate nested namespace if the file uses one):

```json
"local_only_action_hint": "Nur über die BaluHost-Companion-App am Server selbst möglich.",
"local_only_banner": "Diese Aktion erfordert physische Anwesenheit am BaluNode."
```

In `client/src/i18n/locales/en/common.json`:

```json
"local_only_action_hint": "Only available via the BaluHost Companion app running on the server itself.",
"local_only_banner": "This action requires physical presence at the BaluNode."
```

Inspect the file structure before pasting — keys may need to live under a nested key like `"common": { ... }` depending on the namespace convention. Match the surrounding pattern.

- [ ] **Step 2: Write the failing tests**

Create `client/src/components/__tests__/LocalOnlyAction.test.tsx`:

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

import { LocalOnlyAction } from '../LocalOnlyAction';

vi.mock('@/hooks/useChannelStatus', () => ({
  useChannelStatus: vi.fn(),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

import { useChannelStatus } from '@/hooks/useChannelStatus';

describe('<LocalOnlyAction>', () => {
  it('renders the child unchanged when channel is local', () => {
    vi.mocked(useChannelStatus).mockReturnValue({
      channel: 'local', isLocal: true, isLoading: false,
    });
    render(
      <LocalOnlyAction>
        <button data-testid="b">Click</button>
      </LocalOnlyAction>
    );
    const btn = screen.getByTestId('b') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it('disables the child when channel is remote', () => {
    vi.mocked(useChannelStatus).mockReturnValue({
      channel: 'remote', isLocal: false, isLoading: false,
    });
    render(
      <LocalOnlyAction>
        <button data-testid="b">Click</button>
      </LocalOnlyAction>
    );
    const btn = screen.getByTestId('b') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('renders the child unchanged while loading (no flicker)', () => {
    vi.mocked(useChannelStatus).mockReturnValue({
      channel: 'remote', isLocal: false, isLoading: true,
    });
    render(
      <LocalOnlyAction>
        <button data-testid="b">Click</button>
      </LocalOnlyAction>
    );
    const btn = screen.getByTestId('b') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd client && npx vitest run src/components/__tests__/LocalOnlyAction.test.tsx`

Expected: Module not found error.

- [ ] **Step 4: Implement the component**

Create `client/src/components/LocalOnlyAction.tsx`:

```tsx
import React from 'react';
import { Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChannelStatus } from '@/hooks/useChannelStatus';

interface LocalOnlyActionProps {
  children: React.ReactElement<{ disabled?: boolean }>;
  hint?: string;
}

/**
 * Wraps an interactive element (typically a Button). When the current channel
 * is remote, the child is rendered with disabled=true and shown alongside a
 * Lock icon plus a native browser tooltip explaining why.
 *
 * While the channel status is still loading, the child renders unchanged to
 * avoid a layout flicker. The backend remains the authoritative gate (403).
 */
export function LocalOnlyAction({ children, hint }: LocalOnlyActionProps) {
  const { t } = useTranslation('common');
  const { isLocal, isLoading } = useChannelStatus();

  if (isLocal || isLoading) return children;

  const disabledChild = React.cloneElement(children, { disabled: true });
  const tooltip = hint ?? t('local_only_action_hint');

  return (
    <span className="inline-flex items-center gap-1" title={tooltip}>
      {disabledChild}
      <Lock className="h-3 w-3 text-slate-400" aria-hidden="true" />
    </span>
  );
}
```

If the project doesn't use the namespace `'common'` (some i18n setups use a single bundle), adjust the `useTranslation` call to whichever namespace contains the new keys.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd client && npx vitest run src/components/__tests__/LocalOnlyAction.test.tsx`

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/LocalOnlyAction.tsx \
        client/src/components/__tests__/LocalOnlyAction.test.tsx \
        client/src/i18n/locales/de/common.json \
        client/src/i18n/locales/en/common.json
git commit -m "feat(client): add LocalOnlyAction component + i18n keys"
```

---

### Task 17: Frontend — Wire LocalOnlyAction into RAID Management page

**Files:**
- Modify: `client/src/pages/RaidManagement.tsx`

- [ ] **Step 1: Locate the destructive buttons**

Open `client/src/pages/RaidManagement.tsx`. Find the three buttons that call:
- The delete-array action (search for `delete-array` or `deleteArray`)
- The create-array action (search for `create-array` or `createArray`)
- The format-disk action (search for `format-disk` or `formatDisk`)

- [ ] **Step 2: Add the import**

Near the top of the file, with other component imports:

```tsx
import { LocalOnlyAction } from '@/components/LocalOnlyAction';
```

- [ ] **Step 3: Wrap each destructive button**

For each of the three buttons, wrap the JSX element with `<LocalOnlyAction>...</LocalOnlyAction>`. Example pattern:

```tsx
// Before
<button onClick={handleDeleteArray} className="...">
  Delete Array
</button>

// After
<LocalOnlyAction>
  <button onClick={handleDeleteArray} className="...">
    Delete Array
  </button>
</LocalOnlyAction>
```

Repeat for create and format buttons. The wrap is non-invasive — when channel=local the child renders identically.

- [ ] **Step 4: Run the frontend type-check**

Run: `cd client && npx tsc --noEmit`

Expected: no new errors. Some files in the project may have pre-existing TS errors — only check that nothing new was introduced for `RaidManagement.tsx`.

- [ ] **Step 5: Smoke-test in dev**

Run: `python start_dev.py` (in a separate terminal). Open `http://localhost:5173/raid-management` (or wherever the route is mounted), log in as admin. Verify:

- All three buttons render and look the same as before (because dev mode has `BALUHOST_LOCAL_LOOPBACK_FALLBACK=true` — will be set in Task 21; until then dev mode might disable them, which is acceptable temporary state).

If the buttons are disabled because dev mode doesn't yet set the loopback fallback: that's expected and gets fixed in Task 21. Don't gate this task's commit on dev-mode click-through; rely on the unit tests.

- [ ] **Step 6: Commit**

```bash
git add client/src/pages/RaidManagement.tsx
git commit -m "feat(raid-ui): gate destructive buttons via LocalOnlyAction"
```

---

### Task 18: Frontend — Wire LocalOnlyAction into Plugin admin UI

**Files:**
- Modify: Plugin admin component(s) — locate in this task

- [ ] **Step 1: Locate the plugin install/uninstall UI**

Run a grep over the client to find where the install/uninstall API calls are made from the UI:

```bash
cd client && grep -rn "marketplace.*install\|/plugins/.*\bDELETE\|deletePlugin\|installPlugin" src/ | head -30
```

Most likely files: `client/src/pages/Plugins*.tsx`, `client/src/components/PluginPage.tsx`, or `client/src/components/plugins/*`. Pick the file(s) that render the actual install / uninstall buttons (not the plugin-rendering host).

- [ ] **Step 2: Add the import and wrap**

In each identified file with an install or uninstall button:

```tsx
import { LocalOnlyAction } from '@/components/LocalOnlyAction';

// ...
<LocalOnlyAction>
  <button onClick={handleInstall} className="...">Install</button>
</LocalOnlyAction>

<LocalOnlyAction>
  <button onClick={handleUninstall} className="...">Uninstall</button>
</LocalOnlyAction>
```

- [ ] **Step 3: TypeScript check**

Run: `cd client && npx tsc --noEmit`

Expected: no new errors in the touched files.

- [ ] **Step 4: Commit**

```bash
git add client/src/  # only the files actually modified
git commit -m "feat(plugins-ui): gate install/uninstall via LocalOnlyAction"
```

---

### Task 19: Frontend — Wire LocalOnlyAction into VPN sync-server-keys button

**Files:**
- Modify: `client/src/components/VpnManagement.tsx` (or wherever the sync-server-keys button lives — see Step 1)

- [ ] **Step 1: Locate the button**

Run: `cd client && grep -rn "sync-server-keys\|syncServerKeys" src/`

Identify the component that renders the button calling `/api/vpn/sync-server-keys`. If it doesn't exist yet in the UI (the endpoint may only be reachable via API), add a button to `client/src/components/VpnManagement.tsx` in the admin VPN section (gated by `LocalOnlyAction`).

If a button is missing, this task adds it (admin-only, advanced action). Use whatever pattern the surrounding admin VPN UI uses for destructive actions.

- [ ] **Step 2: Add the import**

```tsx
import { LocalOnlyAction } from '@/components/LocalOnlyAction';
```

- [ ] **Step 3: Wrap the button**

```tsx
<LocalOnlyAction>
  <button onClick={handleSyncServerKeys} className="...">
    Sync Server Keys
  </button>
</LocalOnlyAction>
```

- [ ] **Step 4: TypeScript check**

Run: `cd client && npx tsc --noEmit`

Expected: no new errors.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/VpnManagement.tsx
git commit -m "feat(vpn-ui): gate sync-server-keys via LocalOnlyAction"
```

---

### Task 20: Frontend — Wire LocalOnlyAction into Users page bulk-delete

**Files:**
- Modify: `client/src/components/user-management/UserTable.tsx` or wherever the bulk-delete trigger lives

- [ ] **Step 1: Locate the bulk-delete trigger**

Run: `cd client && grep -rn "bulk-delete\|bulkDelete\|deleteSelected" src/`

Identify the button (likely a "Delete Selected" or similar in the users management page).

- [ ] **Step 2: Add the import and wrap**

```tsx
import { LocalOnlyAction } from '@/components/LocalOnlyAction';

<LocalOnlyAction>
  <button onClick={handleBulkDelete} disabled={selectedIds.size === 0} className="...">
    Delete Selected
  </button>
</LocalOnlyAction>
```

Note: `LocalOnlyAction` adds `disabled=true` ONLY when channel is remote. If the button also has its own `disabled` logic (e.g., "no users selected"), keep that — `cloneElement` merges props, with the channel-based `disabled` winning when applied.

- [ ] **Step 3: TypeScript check**

Run: `cd client && npx tsc --noEmit`

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/user-management/  # adjust path if different
git commit -m "feat(users-ui): gate bulk-delete via LocalOnlyAction"
```

---

### Task 21: Dev mode — Set BALUHOST_LOCAL_LOOPBACK_FALLBACK in start_dev.py

**Files:**
- Modify: `start_dev.py`

- [ ] **Step 1: Find the env-setup section of `start_dev.py`**

Look for where it sets env vars like `NAS_MODE`, `BALUHOST_SKIP_SETUP`, etc.

- [ ] **Step 2: Add the fallback flag**

Add (preferably near other backend-related env vars):

```python
# Enable loopback fallback for the local-channel gate so the Tauri
# Companion can talk to the dev backend via plain HTTP without UDS.
# This is dev-only — settings validator blocks it in production.
os.environ.setdefault("BALUHOST_LOCAL_LOOPBACK_FALLBACK", "true")
```

- [ ] **Step 3: Manual smoke**

Run: `python start_dev.py`

In a browser at `http://localhost:5173`, log in as admin, open RAID Management. Expect the destructive buttons to be **enabled** (because loopback fallback marks the channel as local for 127.0.0.1).

Open DevTools → Network → click the Delete Array button (in dev mode, mdadm calls are mocked). Expect a 200 response (not 403 local_channel_required).

- [ ] **Step 4: Commit**

```bash
git add start_dev.py
git commit -m "dev: enable BALUHOST_LOCAL_LOOPBACK_FALLBACK in start_dev"
```

---

### Task 22: Frontend — api.ts Tauri integration

**Files:**
- Modify: `client/src/lib/api.ts`

- [ ] **Step 1: Inspect current api.ts**

Open `client/src/lib/api.ts`. Note how `api` (axios instance) is constructed and what its current `baseURL` source is.

- [ ] **Step 2: Add the Tauri-aware base URL resolver**

Refactor the existing `baseURL` config to use a function:

```typescript
// At the top with other imports, leave them as they are.

async function resolveApiBase(): Promise<string> {
  if (import.meta.env.VITE_TAURI === '1') {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      return await invoke<string>('get_api_base');
    } catch (err) {
      console.error('[api] Tauri get_api_base failed, falling back', err);
    }
  }
  return import.meta.env.VITE_API_BASE || '/api';
}

// Use it in the axios.create call. If the existing code uses
// `axios.create({ baseURL: ... })` at module load, switch to a deferred
// init pattern:

let _apiInstance: ReturnType<typeof axios.create> | null = null;
let _apiInit: Promise<void> | null = null;

async function initApi() {
  const baseURL = await resolveApiBase();
  _apiInstance = axios.create({
    baseURL,
    // ... copy any other settings from the original axios.create call
  });
  // Re-apply any request/response interceptors here if the original had them.
}

export function getApi() {
  if (!_apiInit) {
    _apiInit = initApi();
  }
  return _apiInit.then(() => {
    if (!_apiInstance) throw new Error('api init failed');
    return _apiInstance;
  });
}

// Backwards-compat shim: existing code uses `api.get(...)` etc. directly.
// Provide a Proxy that lazily awaits init.
export const api = new Proxy({} as ReturnType<typeof axios.create>, {
  get(_target, prop) {
    return async (...args: unknown[]) => {
      const instance = await getApi();
      // @ts-expect-error — passthrough call
      return instance[prop](...args);
    };
  },
});
```

**Important:** This refactor is invasive. If the codebase has many `api.get(...).then(...)` call sites that expect a synchronous axios instance, an alternative is to call `resolveApiBase()` synchronously by reading `VITE_API_BASE` at build time only and shipping a separate Tauri-only env file. The proxy approach above works but adds one microtask of latency per call.

**Simpler alternative — recommended if it fits:** Build with `VITE_TAURI=1` AND `VITE_API_BASE=__TAURI_INJECT__` for the Tauri build. The Tauri main.rs writes the actual port into the bundled `index.html` as a global before loading the React bundle. Then `api.ts` reads `window.__BALU_API_BASE__` synchronously at module load.

Pick whichever fits the existing code style best. Document the choice in a comment.

- [ ] **Step 3: TypeScript check**

Run: `cd client && npx tsc --noEmit`

Expected: no new errors. Existing call sites continue to work either via the Proxy (async path) or via the synchronous `window.__BALU_API_BASE__` path.

- [ ] **Step 4: Verify Web build still works**

Run: `cd client && npm run build`

Expected: build succeeds; bundle still calls `/api/...` (Tauri injection has no effect when `VITE_TAURI` is unset).

- [ ] **Step 5: Commit**

```bash
git add client/src/lib/api.ts
git commit -m "feat(client): Tauri-aware API base URL resolution"
```

---

### Task 23: Tauri shell — scaffold Cargo + tauri.conf

**Files:**
- Create: `client/src-tauri/Cargo.toml`
- Create: `client/src-tauri/build.rs`
- Create: `client/src-tauri/tauri.conf.json`
- Create: `client/src-tauri/icons/icon.png` (1024×1024 placeholder PNG — can be a solid color for now)
- Modify: `client/package.json` (add Tauri scripts + dev dep)

- [ ] **Step 1: Create Cargo.toml**

Create `client/src-tauri/Cargo.toml`:

```toml
[package]
name = "baluhost-companion"
version = "0.1.0"
edition = "2021"

[lib]
name = "baluhost_companion_lib"
crate-type = ["staticlib", "cdylib", "rlib"]

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
tauri-plugin-shell = "2"
hyper = { version = "1", features = ["server", "client", "http1"] }
hyper-util = { version = "0.1", features = ["tokio", "server", "client", "http1"] }
hyperlocal = "0.9"
http-body-util = "0.1"
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"

[profile.release]
panic = "abort"
codegen-units = 1
lto = true
opt-level = "s"
strip = true
```

- [ ] **Step 2: Create build.rs**

Create `client/src-tauri/build.rs`:

```rust
fn main() {
    tauri_build::build()
}
```

- [ ] **Step 3: Create tauri.conf.json**

Create `client/src-tauri/tauri.conf.json`:

```json
{
  "$schema": "https://schema.tauri.app/config/2.0.0",
  "productName": "BaluHost Companion",
  "version": "0.1.0",
  "identifier": "com.baluhost.companion",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "npm run dev -- --mode tauri",
    "beforeBuildCommand": "npm run build -- --mode tauri"
  },
  "app": {
    "windows": [
      {
        "title": "BaluHost Companion",
        "width": 1280,
        "height": 800,
        "minWidth": 1024,
        "minHeight": 600,
        "resizable": true
      }
    ],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' http://127.0.0.1:*; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["deb", "appimage"],
    "icon": ["icons/icon.png"],
    "category": "Utility"
  }
}
```

- [ ] **Step 4: Create the placeholder icon**

Create `client/src-tauri/icons/icon.png` — a 1024×1024 PNG. A blue square is fine. The icon can be replaced later. If no tooling is handy, use any small PNG file and commit it; Tauri requires the file to exist but accepts any reasonable PNG for bundling.

- [ ] **Step 5: Update package.json**

In `client/package.json`, add to the `scripts` block:

```json
"tauri:dev": "tauri dev",
"tauri:build": "tauri build"
```

Add to `devDependencies`:

```json
"@tauri-apps/cli": "^2.0.0",
"@tauri-apps/api": "^2.0.0"
```

Run: `cd client && npm install`

Expected: lockfile updates, no errors.

- [ ] **Step 6: Commit**

```bash
git add client/src-tauri/Cargo.toml client/src-tauri/build.rs \
        client/src-tauri/tauri.conf.json client/src-tauri/icons/icon.png \
        client/package.json client/package-lock.json
git commit -m "feat(tauri): scaffold src-tauri/ with Cargo + tauri.conf"
```

---

### Task 24: Tauri shell — proxy.rs (HTTP → Unix socket forwarder)

**Files:**
- Create: `client/src-tauri/src/proxy.rs`
- Create: `client/src-tauri/tests/proxy_test.rs`

- [ ] **Step 1: Write the proxy implementation**

Create `client/src-tauri/src/proxy.rs`:

```rust
//! HTTP → Unix-socket reverse proxy used by the Companion app.
//!
//! Binds to 127.0.0.1:0 (kernel-chosen free port). For every HTTP request
//! from the embedded webview, opens a new connection to the configured
//! Unix socket and forwards the request unchanged. Streams the response
//! back without buffering so SSE endpoints (upload progress, etc.) work.
//!
//! No header injection, no path rewriting — dumb forwarder.

use std::net::SocketAddr;
use std::path::PathBuf;

use http_body_util::{BodyExt, Full};
use hyper::body::{Bytes, Incoming};
use hyper::server::conn::http1 as server_http1;
use hyper::service::service_fn;
use hyper::{Request, Response, StatusCode};
use hyper_util::rt::TokioIo;
use hyperlocal::{UnixConnector, Uri as UnixUri};
use tokio::net::TcpListener;

#[derive(Clone)]
pub struct ProxyInfo {
    pub port: u16,
}

pub async fn start(uds_path: PathBuf) -> std::io::Result<(u16, tokio::task::JoinHandle<()>)> {
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let port = listener.local_addr()?.port();

    let handle = tokio::spawn(async move {
        loop {
            let (stream, _peer) = match listener.accept().await {
                Ok(pair) => pair,
                Err(e) => {
                    eprintln!("[proxy] accept error: {e}");
                    continue;
                }
            };
            let uds = uds_path.clone();
            tokio::spawn(async move {
                let io = TokioIo::new(stream);
                let svc = service_fn(move |req| forward(req, uds.clone()));
                if let Err(e) = server_http1::Builder::new().serve_connection(io, svc).await {
                    eprintln!("[proxy] connection error: {e}");
                }
            });
        }
    });

    Ok((port, handle))
}

async fn forward(
    req: Request<Incoming>,
    uds_path: PathBuf,
) -> Result<Response<Full<Bytes>>, hyper::Error> {
    let connector = UnixConnector;
    let path_and_query = req
        .uri()
        .path_and_query()
        .map(|p| p.as_str())
        .unwrap_or("/");
    let target_uri: hyper::Uri = UnixUri::new(&uds_path, path_and_query).into();

    let (parts, body) = req.into_parts();
    let body_bytes = match body.collect().await {
        Ok(c) => c.to_bytes(),
        Err(_) => Bytes::new(),
    };

    let mut new_req = Request::builder()
        .method(parts.method)
        .uri(target_uri);
    for (k, v) in parts.headers.iter() {
        new_req = new_req.header(k, v);
    }
    let new_req = match new_req.body(Full::new(body_bytes)) {
        Ok(r) => r,
        Err(_) => {
            return Ok(Response::builder()
                .status(StatusCode::BAD_GATEWAY)
                .body(Full::new(Bytes::from_static(b"proxy: bad request")))
                .unwrap())
        }
    };

    let client = hyper_util::client::legacy::Client::builder(hyper_util::rt::TokioExecutor::new())
        .build::<_, Full<Bytes>>(connector);

    match client.request(new_req).await {
        Ok(resp) => {
            let (parts, body) = resp.into_parts();
            let bytes = body.collect().await.map(|c| c.to_bytes()).unwrap_or_default();
            let mut out = Response::builder().status(parts.status);
            for (k, v) in parts.headers.iter() {
                out = out.header(k, v);
            }
            Ok(out.body(Full::new(bytes)).unwrap())
        }
        Err(e) => Ok(Response::builder()
            .status(StatusCode::BAD_GATEWAY)
            .body(Full::new(Bytes::from(format!(
                "proxy: UDS unreachable — is baluhost-backend-local.service running? ({e})"
            ))))
            .unwrap()),
    }
}

#[allow(dead_code)]
pub fn _ensure_used(_: SocketAddr) {} // keeps SocketAddr import live for future use
```

> **Note on streaming:** the implementation above collects the body in full before forwarding both ways. This is fine for normal JSON endpoints but breaks SSE / chunked streams (upload progress). For V1 this is acceptable — SSE is used only during file uploads from the Web UI, and the Tauri app's primary use case is destructive admin operations (no SSE). A follow-up task can switch to true streaming via `hyper::Body` once the basic flow is verified.

- [ ] **Step 2: Write a basic integration test**

Create `client/src-tauri/tests/proxy_test.rs`:

```rust
//! Integration test: start a fake UDS server, run the proxy, verify forwarding.

use std::path::PathBuf;

#[tokio::test]
async fn proxy_forwards_get_request() {
    use http_body_util::{BodyExt, Full};
    use hyper::body::Bytes;
    use hyper::server::conn::http1 as server_http1;
    use hyper::service::service_fn;
    use hyper::{Request, Response};
    use hyper_util::rt::TokioIo;
    use std::fs;
    use tokio::net::UnixListener;

    // Set up a temp UDS that serves a simple "hello" response.
    let tmpdir = tempfile::tempdir().unwrap();
    let sock_path: PathBuf = tmpdir.path().join("test.sock");
    let listener = UnixListener::bind(&sock_path).unwrap();

    let sock_path_clone = sock_path.clone();
    let server = tokio::spawn(async move {
        let (stream, _) = listener.accept().await.unwrap();
        let io = TokioIo::new(stream);
        let svc = service_fn(|_req: Request<hyper::body::Incoming>| async {
            Ok::<_, hyper::Error>(
                Response::new(Full::new(Bytes::from_static(b"hello from uds")))
            )
        });
        server_http1::Builder::new().serve_connection(io, svc).await.unwrap();
        let _ = sock_path_clone;
    });

    // Start the proxy
    let (port, _proxy_handle) = baluhost_companion_lib::proxy::start(sock_path).await.unwrap();

    // Hit the proxy with a real TCP client
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("http://127.0.0.1:{port}/anything"))
        .send()
        .await
        .unwrap();
    let body = resp.text().await.unwrap();
    assert_eq!(body, "hello from uds");

    let _ = server.await;
}
```

Add these dev dependencies to `client/src-tauri/Cargo.toml`:

```toml
[dev-dependencies]
tempfile = "3"
reqwest = { version = "0.12", default-features = false, features = ["rustls-tls"] }
```

- [ ] **Step 3: Run the test**

Run: `cd client/src-tauri && cargo test --test proxy_test`

Expected: 1 passed.

If `cargo` is not available on the dev machine, mark this test as `cfg(target_os = "linux")` and skip locally; CI will run it.

- [ ] **Step 4: Commit**

```bash
git add client/src-tauri/src/proxy.rs client/src-tauri/tests/proxy_test.rs client/src-tauri/Cargo.toml
git commit -m "feat(tauri): proxy.rs forwarding HTTP to /run/baluhost/local.sock"
```

---

### Task 25: Tauri shell — main.rs entry point with get_api_base command

**Files:**
- Create: `client/src-tauri/src/main.rs`
- Create: `client/src-tauri/src/lib.rs` (re-exports for tests)

- [ ] **Step 1: Create lib.rs**

Create `client/src-tauri/src/lib.rs`:

```rust
//! Library crate (used by integration tests under tests/).
pub mod proxy;
```

- [ ] **Step 2: Create main.rs**

Create `client/src-tauri/src/main.rs`:

```rust
//! BaluHost Companion App — Tauri entry point.
//!
//! 1. Boots a local HTTP-to-UDS proxy.
//! 2. Exposes `get_api_base` to the React webview so it can configure axios.
//! 3. Opens the main window which loads the bundled React build.

// Prevents additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod proxy;

use std::path::PathBuf;
use tauri::Manager;

#[tauri::command]
fn get_api_base(state: tauri::State<proxy::ProxyInfo>) -> String {
    format!("http://127.0.0.1:{}/api", state.port)
}

fn main() {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .expect("failed to build tokio runtime");

    let uds_path = PathBuf::from(
        std::env::var("BALUHOST_LOCAL_SOCKET")
            .unwrap_or_else(|_| "/run/baluhost/local.sock".to_string()),
    );

    let (proxy_port, _proxy_handle) = runtime
        .block_on(async { proxy::start(uds_path).await })
        .expect("proxy startup failed");

    tauri::Builder::default()
        .setup(move |app| {
            app.manage(proxy::ProxyInfo { port: proxy_port });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_api_base])
        .run(tauri::generate_context!())
        .expect("error while running BaluHost Companion");
}
```

- [ ] **Step 3: Verify the crate builds**

Run: `cd client/src-tauri && cargo build`

Expected: builds successfully (may take a while on first run — Tauri pulls in lots of deps).

- [ ] **Step 4: Smoke-test dev mode**

In one terminal: `python start_dev.py`
In another: `cd client && npm run tauri:dev`

Expected: a window opens, displays the React UI, login flow works.

If `get_api_base` returns a port that the webview can't reach (e.g. because the loopback fallback isn't enabled in the dev backend), this will fail — verify Task 21 was applied and `python start_dev.py` is the backend that's running.

- [ ] **Step 5: Commit**

```bash
git add client/src-tauri/src/main.rs client/src-tauri/src/lib.rs
git commit -m "feat(tauri): main.rs entry + get_api_base command"
```

---

### Task 26: CI — Tauri build workflow + CODEOWNERS

**Files:**
- Create: `.github/workflows/tauri-build.yml`
- Modify: `.github/CODEOWNERS`
- Modify: `.claude/rules/ci-cd-security.md`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/tauri-build.yml`:

```yaml
name: Tauri Build

on:
  push:
    branches: [main]
    tags: ['v*']
  workflow_dispatch:

jobs:
  build:
    # MUST stay on GitHub-hosted runner per .claude/rules/ci-cd-security.md
    # Layer 2 (no self-hosted for PR-touched code paths).
    runs-on: ubuntu-latest
    permissions:
      contents: write  # required for tag-triggered release uploads
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: client/package-lock.json

      - name: Setup Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Cache Cargo
        uses: Swatinem/rust-cache@v2
        with:
          workspaces: client/src-tauri

      - name: Install Tauri OS dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            libwebkit2gtk-4.1-dev \
            build-essential \
            curl wget file \
            libxdo-dev libssl-dev \
            libayatana-appindicator3-dev \
            librsvg2-dev

      - name: Install client deps
        working-directory: client
        run: npm ci

      - name: Build Tauri app
        working-directory: client
        run: npm run tauri:build -- --bundles deb,appimage
        env:
          VITE_TAURI: '1'

      - name: Upload artifacts (push to main)
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: actions/upload-artifact@v4
        with:
          name: baluhost-companion-dev
          path: |
            client/src-tauri/target/release/bundle/deb/*.deb
            client/src-tauri/target/release/bundle/appimage/*.AppImage
          retention-days: 14

      - name: Upload to release (tag)
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: |
            client/src-tauri/target/release/bundle/deb/*.deb
            client/src-tauri/target/release/bundle/appimage/*.AppImage
```

- [ ] **Step 2: Update CODEOWNERS**

In `.github/CODEOWNERS`, add (alphabetical/contextual placement to taste):

```
/client/src-tauri/             @Xveyn
/.github/workflows/tauri-build.yml @Xveyn
```

- [ ] **Step 3: Update ci-cd-security.md inventory**

In `.claude/rules/ci-cd-security.md`, find the Layer-1 CODEOWNERS section. Add to the owned-paths list:

```
- `/client/src-tauri/` — Tauri Companion app source (Rust shell + config)
- `/.github/workflows/tauri-build.yml` — Tauri build workflow
```

In the runner-trigger table, add a row:

```
| `tauri-build.yml` | `ubuntu-latest` | `push: main`, tag, `workflow_dispatch` |
```

- [ ] **Step 4: Verify YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/tauri-build.yml'))"`

Expected: no exceptions (YAML parses).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/tauri-build.yml .github/CODEOWNERS .claude/rules/ci-cd-security.md
git commit -m "ci: tauri-build workflow + CODEOWNERS + security-rule update"
```

---

### Task 27: Frontend — Setup wizard remote banner

**Files:**
- Modify: `client/src/components/setup/*.tsx` (locate the wizard entry component)

- [ ] **Step 1: Locate the setup wizard entry**

Run: `cd client && grep -rn "setup/status\|setup_required\|setupRequired" src/ | head -10`

The top-level wizard component will fetch `/api/setup/status` and render different steps based on `setup_required`. Likely candidates: `client/src/components/setup/SetupWizard.tsx` or `client/src/pages/SetupWizardPage.tsx`.

- [ ] **Step 2: Add the channel check + banner**

In the wizard component, import the hook:

```tsx
import { useChannelStatus } from '@/hooks/useChannelStatus';
import { useTranslation } from 'react-i18next';
```

Near the top of the rendering logic (after the `setup_required` check but before any input forms):

```tsx
const { isLocal, isLoading: channelLoading } = useChannelStatus();
const { t } = useTranslation('common');

if (!channelLoading && !isLocal) {
  return (
    <div className="card">
      <h2 className="text-xl font-semibold text-amber-300">
        {t('local_only_banner')}
      </h2>
      <p className="mt-2 text-slate-300">
        Please open the BaluHost Companion app on the BaluNode to complete setup.
      </p>
    </div>
  );
}
```

- [ ] **Step 3: TypeScript check**

Run: `cd client && npx tsc --noEmit`

Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/setup/ client/src/pages/SetupWizardPage.tsx  # adjust to actual paths
git commit -m "feat(setup-ui): show remote-channel banner when not local"
```

---

### Task 28: Docs — Companion app install guide

**Files:**
- Create: `docs/companion-app-install.md`

- [ ] **Step 1: Write the install doc**

Create `docs/companion-app-install.md`:

```markdown
# BaluHost Companion App — Install & Use

The BaluHost Companion is a small desktop app that runs **on the BaluNode itself** and is the only way to perform irreversible admin operations (RAID destroy, plugin install, VPN key rotation, user bulk-delete, initial setup wizard).

## Why it exists

A few admin endpoints are gated behind a **local channel** check — the request must arrive via the Unix socket `/run/baluhost/local.sock`, which is reachable only by processes running as the `baluhost` OS user. JWT auth is still required; this is a second factor that requires physical presence.

If you try one of these actions from the Web UI on a remote browser, the button is disabled with a lock icon and the tooltip "Only available via the BaluHost Companion app running on the server itself."

## Install

1. Download the `.deb` from the BaluHost Releases page (matching your BaluHost version).
2. Install: `sudo apt install ./baluhost-companion_*.deb`
3. Add your interactive user to the `baluhost` group: `sudo usermod -aG baluhost $USER`
4. **Log out and back in** for group membership to take effect.
5. Launch from the application menu (KDE: search for "BaluHost Companion") or from the terminal: `baluhost-companion`.

## First-time setup

If your BaluHost is freshly installed (no admin user yet), the Companion app opens directly into the setup wizard. Create the first admin, optionally a regular user, choose your file-sharing protocols (Samba/WebDAV), and finish. The Web UI on the same machine will then accept the new admin's login.

## Daily use

Open the Companion when you need to perform an irreversible operation. For everything else, the Web UI in your browser works fine and is the recommended interface.

## Troubleshooting

**"Cannot connect to baluhost-backend-local.service"** — verify the service is running:

```bash
systemctl status baluhost-backend-local.socket baluhost-backend-local.service
```

If the socket is up but the service hasn't started, that's normal — it's socket-activated and starts on first connection.

**"Channel: remote" in the Web UI even on the BaluNode browser** — that's expected. The Web UI uses the TCP port (via nginx); only the Companion app uses the Unix socket. To verify your install is OK, open the Companion app.

**Permission denied connecting to socket** — your user is not in the `baluhost` group, or you haven't logged out/in since `usermod`. Check: `groups | grep baluhost`.

## See also

- `.claude/rules/ci-cd-security.md` — the trust model behind the local channel
- `docs/superpowers/specs/2026-05-25-tauri-local-admin-design.md` — full design doc
```

- [ ] **Step 2: Commit**

```bash
git add docs/companion-app-install.md
git commit -m "docs: companion app install guide"
```

---

### Task 29: Playwright E2E — channel-status disables RAID button

**Files:**
- Create: `client/tests/e2e/local-only.spec.ts`

- [ ] **Step 1: Inspect existing Playwright setup**

Open one existing E2E spec (e.g., `client/tests/e2e/login.spec.ts`) to mirror its login + route-mocking pattern.

- [ ] **Step 2: Write the spec**

Create `client/tests/e2e/local-only.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test.describe('local-only action gating', () => {
  test('delete-array button is disabled when channel is remote', async ({ page }) => {
    await page.route('**/api/system/channel-status', (route) =>
      route.fulfill({ json: { channel: 'remote' } })
    );

    // Mock login + RAID status here using the same patterns as login.spec.ts.
    // Once on the RAID Management page:
    await page.goto('/raid-management');  // adjust to actual route

    const deleteBtn = page.getByRole('button', { name: /delete array/i });
    await expect(deleteBtn).toBeDisabled();

    // The lock icon should be visible alongside the disabled button
    await expect(page.locator('[aria-hidden="true"]').first()).toBeVisible();
  });

  test('delete-array button is enabled when channel is local', async ({ page }) => {
    await page.route('**/api/system/channel-status', (route) =>
      route.fulfill({ json: { channel: 'local' } })
    );

    // Same setup as above
    await page.goto('/raid-management');

    const deleteBtn = page.getByRole('button', { name: /delete array/i });
    await expect(deleteBtn).toBeEnabled();
  });
});
```

Fill in the login/route-mocking boilerplate based on the existing spec pattern.

- [ ] **Step 3: Run the spec**

Run: `cd client && npm run test:e2e -- local-only.spec.ts`

Expected: 2 passed (or whatever the project's E2E runner reports).

- [ ] **Step 4: Commit**

```bash
git add client/tests/e2e/local-only.spec.ts
git commit -m "test(e2e): channel-status disables destructive buttons"
```

---

### Task 30: Final smoke + middleware CLAUDE.md update

**Files:**
- Modify: `backend/app/middleware/CLAUDE.md`

- [ ] **Step 1: Update the middleware inventory**

In `backend/app/middleware/CLAUDE.md`, in the "Files" table, add a new row:

```
| `channel_marker.py` | Sets `request.state.channel` from `settings.channel`. The TCP-bound backend process gets `remote`; the UDS-bound process gets `local`. Used by `require_local_admin` to gate destructive admin endpoints behind physical presence | All requests |
```

- [ ] **Step 2: Run the full backend test suite**

Run: `cd backend && python -m pytest -x --timeout=120`

Expected: all green.

- [ ] **Step 3: Run the frontend test suite**

Run: `cd client && npm run test 2>&1 | tail -50`

Expected: Vitest passes; existing tests still green.

- [ ] **Step 4: Type-check the entire frontend**

Run: `cd client && npx tsc --noEmit`

Expected: no new errors (pre-existing errors may remain — verify nothing new in the files we touched).

- [ ] **Step 5: Run frontend build to catch bundling regressions**

Run: `cd client && npm run build`

Expected: builds cleanly.

- [ ] **Step 6: Commit**

```bash
git add backend/app/middleware/CLAUDE.md
git commit -m "docs(middleware): document channel_marker.py"
```

---

## Acceptance Verification

After all tasks are complete, verify the end-to-end story manually:

1. **Backend smoke (TCP):**
   ```bash
   ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"<password>"}' | jq -r .access_token)
   curl http://localhost:8000/api/system/channel-status \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   # Expected: {"channel":"remote"}
   ```

2. **Backend smoke (UDS — requires baluhost-backend-local.service installed):**
   ```bash
   sudo -u baluhost curl --unix-socket /run/baluhost/local.sock \
     http://x/api/system/channel-status \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   # Expected: {"channel":"local"}
   ```

3. **Endpoint gate:**
   ```bash
   curl -X POST http://localhost:8000/api/system/raid/delete-array \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"array":"md0"}'
   # Expected: 403 {"detail":{"error":"local_channel_required","message":"..."}}
   ```

4. **Audit log:** verify a new `audit_logs` row with `action=local_channel_required_denied`, `user=admin`, `details.path=/api/system/raid/delete-array`.

5. **Web UI:** open the Web UI as admin, navigate to RAID Management. Verify "Delete Array" is disabled with lock icon and tooltip.

6. **Tauri app:** install the `.deb`, log in as admin in the Companion app. Channel status shows `local`. Click "Delete Array" — action proceeds (or returns the expected dev-mock 200).

7. **Setup wizard:** wipe the DB, open the Web UI — banner says "Open Companion app". Open the Companion app — wizard renders, admin creation succeeds.

8. **CI:** `tauri-build.yml` produces `.deb` artifact on push to main.

---

## Self-Review Notes

- **Spec coverage**: every spec component has a task:
  - Channel-marker middleware → Task 2/3
  - require_local_admin → Task 5
  - require_local_or_setup_secret → Task 6
  - channel-status endpoint → Task 4
  - Settings fields → Task 1
  - Test fixture default → Task 7
  - 13 endpoint promotions → Tasks 9-13
  - systemd templates → Task 8
  - Tauri shell (Cargo, conf, proxy, main) → Tasks 23, 24, 25
  - Frontend hook + component + i18n → Tasks 14, 15, 16
  - Page wiring (5 areas) → Tasks 17-20, 27
  - api.ts Tauri integration → Task 22
  - Dev mode flag → Task 21
  - CI workflow + CODEOWNERS + security-rule → Task 26
  - Docs → Task 28
  - E2E test → Task 29
  - Final docs/smoke → Task 30
- **No placeholders**: every code step has actual code. Two "locate during impl" notes (Plugin admin page in Task 18, VPN button in Task 19) are honest acknowledgments that the engineer must `grep` to pin the exact file — the spec section already flagged this. Steps for those tasks describe what to grep for and what to do once located.
- **Type consistency**: `require_local_admin` returns `UserPublic`, used as that type everywhere it's consumed. `ChannelStatusResponse.channel` typed as `Literal["local","remote"]` in backend and `'local' | 'remote'` in frontend — matching.
- **Frequent commits**: every task ends with a commit. 30 commits total across the plan, each leaving the codebase in a working state.
