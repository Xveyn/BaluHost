# Plugin-Backend-Isolation Phase 4 — Request-Proxy + PluginManager-Dual-Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing Phase 1–3 sandbox machinery into the real request path so external/marketplace plugins run isolated in a subprocess instead of `exec_module` in the host.

**Architecture:** `PluginManager` gains a dual path — bundled plugins keep the in-process `exec_module` path; external plugins spawn a `SandboxSupervisor` (one subprocess per uvicorn worker) and are served through a FastAPI catch-all proxy that forwards token-free, header-allowlisted requests over RPC. The host-side `CapabilityRouter` (default-deny) enforces `storage.*`/`core.*` scopes from the already-existing `granted_api_scopes` DB column.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, asyncio, msgpack RPC (already built in `app/plugins/sandbox/`), pytest.

## Global Constraints

- **No migration / no new column.** `InstalledPlugin.granted_api_scopes` and its migration (`1ab0b6db5b1c`) already exist (Track A). Phase 4 only consumes the value.
- **`exec_module` for external plugins runs ONLY in the worker subprocess, NEVER in the host.** `load_plugin(external)` must raise instead of executing.
- **Token never leaves the host.** The `Authorization` and `Cookie` headers must never appear in the `http_request` forwarded to a plugin.
- **All plugin failures are scrubbed host-side:** crash → 502, timeout → 504, supervisor disabled/unreachable → 503. Detail only in server logs, never in the client response (ties into Posten 2 / error-leakage work).
- **One subprocess per uvicorn worker.** No cross-worker IPC. The current 1:1 transport (`WorkerListener` listens, worker connects back once) is unchanged.
- **Caps (constants):** request body ≤ 10 MiB → 413; per-request timeout 30 s → 504; max in-flight requests per plugin = 10 → 503.
- **TDD, frequent commits.** Run `cd backend && python -m pytest <path> -v` for each task. Follow existing async test patterns; new tests live under `backend/tests/plugins/sandbox/`.
- **Windows/CRLF:** repo uses `core.autocrlf=true`. Write LF; git normalizes.
- Spec: `docs/superpowers/specs/2026-06-28-plugin-backend-isolation-phase4-design.md`.

---

## File Structure

- **Create** `backend/app/plugins/sandbox/host_capabilities.py` — builds a production-wired `CapabilityRouter` (session factory, metrics reader, notifier, audit logger).
- **Create** `backend/app/plugins/sandbox/proxy.py` — the catch-all proxy handler + caps + header allowlist + error scrubbing.
- **Modify** `backend/app/plugins/sandbox/transport.py` — unique per-spawn UDS socket name so one subprocess per uvicorn worker does not collide on a shared socket path.
- **Modify** `backend/app/plugins/sandbox/supervisor.py` — `dispatch()` forwards `query` + `headers`, honours a per-request timeout and a max-in-flight semaphore.
- **Modify** `backend/app/plugins/manager.py` — `_sandboxes` registry, dual-path `enable_plugin`/`disable_plugin`/`shutdown_all`, `load_plugin(external)` guard, `granted_api_scopes` threading, catch-all wired into `get_router()`.
- **Modify** `backend/app/api/routes/plugins.py` — toggle/details/list branch onto the manifest path for external (no `load_plugin` exec).
- **Tests:** `backend/tests/plugins/sandbox/test_host_capabilities.py`, `test_proxy.py`, `test_supervisor.py` (extend), `backend/tests/plugins/test_plugin_manager_dualpath.py`, `backend/tests/plugins/sandbox/test_phase4_e2e.py`, plus a fixture plugin under `backend/tests/plugins/sandbox/fixtures/`.

---

## Task 1: Production-wired CapabilityRouter factory

Builds a `CapabilityRouter` with real host dependencies. The router itself (Phase 3) already takes these by injection; this task supplies the concrete ones.

**Files:**
- Create: `backend/app/plugins/sandbox/host_capabilities.py`
- Test: `backend/tests/plugins/sandbox/test_host_capabilities.py`

**Interfaces:**
- Consumes: `CapabilityRouter`, `CapabilityContext` from `app.plugins.sandbox.capabilities`; `SessionLocal` from `app.core.database`; `read_shm`, `TELEMETRY_FILE` from `app.services.monitoring.shm`; `get_notification_service` from `app.services.notifications.service`; `get_audit_logger_db` from `app.services.audit.logger_db`.
- Produces: `build_capability_router(plugin_name: str, granted_scopes: "set[str] | frozenset[str]") -> CapabilityRouter`. Used by Task 4 (manager) when spawning an external plugin.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/sandbox/test_host_capabilities.py
"""Phase 4: production-wired CapabilityRouter factory."""
import asyncio

from app.plugins.sandbox.capabilities import CapabilityContext, CapabilityRouter
from app.plugins.sandbox.host_capabilities import build_capability_router


def test_build_returns_capability_router_with_filtered_scopes():
    router = build_capability_router("weather", {"storage", "core.notify", "bogus"})
    assert isinstance(router, CapabilityRouter)
    # Unknown scope strings are dropped; known ones survive.
    assert router._granted_scopes == frozenset({"storage", "core.notify"})


def test_metrics_reader_projects_telemetry(monkeypatch):
    import app.plugins.sandbox.host_capabilities as hc

    # Stub with the REAL telemetry SHM shape (latest_cpu_usage + latest_memory_sample.percent).
    monkeypatch.setattr(
        hc,
        "read_shm",
        lambda *_a, **_k: {
            "latest_cpu_usage": 12.5,
            "latest_memory_sample": {"percent": 40.0, "used": 1, "total": 2},
            "cpu": [],
        },
    )
    router = build_capability_router("weather", {"core.system_metrics"})
    ctx = CapabilityContext(user_id=1, username="u", role="user")
    result = asyncio.run(router.dispatch("core.system_metrics", {}, ctx))
    assert result == {"result": {"cpu_usage": 12.5, "memory_percent": 40.0}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_host_capabilities.py -v`
Expected: FAIL — `ModuleNotFoundError: app.plugins.sandbox.host_capabilities`.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/plugins/sandbox/host_capabilities.py
"""Production wiring for the sandbox CapabilityRouter.

The Phase 3 CapabilityRouter takes its host dependencies by injection so it
stays testable. This module supplies the real ones — a DB session factory,
a read-only metrics reader, an in-app notifier, and the audit logger — and
filters the plugin's granted scopes down to the known host catalog.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.database import SessionLocal
from app.plugins.sandbox.capabilities import (
    CAPABILITY_SCOPE,
    CapabilityContext,
    CapabilityRouter,
)
from app.services.audit.logger_db import get_audit_logger_db
from app.services.monitoring.shm import TELEMETRY_FILE, read_shm
from app.services.notifications.service import get_notification_service

logger = logging.getLogger(__name__)

# The full set of scope strings the host knows how to enforce. Anything a
# plugin was granted that is not in here is silently dropped (defensive).
KNOWN_SCOPES: frozenset[str] = frozenset(CAPABILITY_SCOPE.values())

def _read_metrics() -> dict:
    """Curated read-only system metrics from the monitoring SHM snapshot.

    The telemetry SHM (telemetry.py) exposes ``latest_cpu_usage`` and a
    ``latest_memory_sample`` dict with a ``percent`` field — NOT top-level
    ``cpu_percent``/``memory_percent``. Project a small, stable subset.
    """
    snapshot = read_shm(TELEMETRY_FILE) or {}
    mem = snapshot.get("latest_memory_sample") or {}
    out: dict = {}
    if snapshot.get("latest_cpu_usage") is not None:
        out["cpu_usage"] = snapshot["latest_cpu_usage"]
    if isinstance(mem, dict) and mem.get("percent") is not None:
        out["memory_percent"] = mem["percent"]
    return out


async def _notify(context: CapabilityContext, payload: dict) -> None:
    """Create an in-app notification for the request's acting user only."""
    service = get_notification_service()
    with SessionLocal() as db:
        await service.create(
            db,
            user_id=context.user_id,
            category="plugin",
            notification_type=payload["type"],
            title=payload["title"],
            message=payload["message"],
        )


def build_capability_router(
    plugin_name: str, granted_scopes: "set[str] | frozenset[str]"
) -> CapabilityRouter:
    """Build a CapabilityRouter with production host dependencies."""
    filtered = frozenset(granted_scopes) & KNOWN_SCOPES
    return CapabilityRouter(
        plugin_name=plugin_name,
        granted_scopes=filtered,
        session_factory=SessionLocal,
        metrics_reader=_read_metrics,
        notifier=_notify,
        audit_logger=get_audit_logger_db(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_host_capabilities.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run ruff**

Run: `cd backend && ruff check app/plugins/sandbox/host_capabilities.py tests/plugins/sandbox/test_host_capabilities.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/sandbox/host_capabilities.py backend/tests/plugins/sandbox/test_host_capabilities.py
git commit -m "feat(plugin-sandbox): production-wired CapabilityRouter factory (Phase 4)"
```

---

## Task 2: Supervisor.dispatch forwards query + headers, honours timeout + in-flight cap

`dispatch()` currently sends only `request_id/method/path/body/context`. Phase 4 forwards `query` and the (already-allowlisted) `headers`, applies a per-request timeout, and bounds concurrent in-flight requests per plugin.

**Files:**
- Modify: `backend/app/plugins/sandbox/supervisor.py`
- Test: `backend/tests/plugins/sandbox/test_supervisor.py` (append)

**Interfaces:**
- Produces: `SandboxSupervisor.dispatch(method, path, body, context, *, query=None, headers=None, timeout=30.0) -> dict`. New exception `SupervisorTimeout(SupervisorError)`. New ctor kwarg `max_inflight: int = 10`. `dispatch` raises `SupervisorError` ("too many in-flight requests") when the cap is hit, `SupervisorTimeout` on per-request timeout.
- Consumes: existing `RpcChannel.call(msg_type, body, timeout=...)`, `MsgType.HTTP_REQUEST`, `CapabilityContext`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/plugins/sandbox/test_supervisor.py
import asyncio
import pytest

from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.supervisor import (
    SandboxSupervisor,
    SupervisorTimeout,
)


class _FakeChannel:
    """Records the last HTTP_REQUEST body; returns a canned response."""

    def __init__(self):
        self.last_body = None

    async def call(self, msg_type, body, timeout=None):
        self.last_body = body
        return Message(id="x", type=MsgType.HTTP_RESPONSE, body={"status": 200, "headers": {}, "body": {"ok": True}})


def _supervisor_with_channel(channel):
    sup = SandboxSupervisor("weather", ".")
    sup._channel = channel
    return sup


def test_dispatch_forwards_query_and_headers():
    channel = _FakeChannel()
    sup = _supervisor_with_channel(channel)
    ctx = {"user_id": 1, "username": "u", "role": "user"}
    asyncio.run(
        sup.dispatch("GET", "status", b"", ctx, query={"a": "1"}, headers={"content-type": "application/json"})
    )
    assert channel.last_body["query"] == {"a": "1"}
    assert channel.last_body["headers"] == {"content-type": "application/json"}
    assert "authorization" not in channel.last_body["headers"]


def test_dispatch_timeout_raises_supervisor_timeout():
    class _SlowChannel:
        async def call(self, msg_type, body, timeout=None):
            raise asyncio.TimeoutError

    sup = _supervisor_with_channel(_SlowChannel())
    with pytest.raises(SupervisorTimeout):
        asyncio.run(sup.dispatch("GET", "x", b"", {"user_id": 1, "username": "u", "role": "user"}, timeout=0.01))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_supervisor.py -k "forwards_query or timeout_raises" -v`
Expected: FAIL — `dispatch()` has no `query`/`headers`/`timeout` kwargs; `SupervisorTimeout` undefined.

- [ ] **Step 3: Edit `supervisor.py` — add exception + ctor field**

After the `SupervisorError` class (line ~37), add:

```python
class SupervisorTimeout(SupervisorError):
    """Raised when a single dispatched request exceeds its timeout."""
```

In `__init__`, add the parameter `max_inflight: int = 10,` (next to `capability_router`) and, in the body, set:

```python
        self._inflight_sem = asyncio.Semaphore(max_inflight)
```

- [ ] **Step 4: Replace the `dispatch` method**

Replace the existing `dispatch` (lines ~85-118) with:

```python
    async def dispatch(
        self,
        method: str,
        path: str,
        body: bytes,
        context: dict,
        *,
        query: "dict | None" = None,
        headers: "dict | None" = None,
        timeout: float = 30.0,
    ) -> dict:
        """Proxy one HTTP request into the worker and return its response dict.

        ``headers`` must already be allowlist-filtered by the caller — this
        method forwards them verbatim and never adds Authorization/Cookie.
        """
        if self._disabled:
            raise SupervisorError(f"plugin {self.plugin_name} is disabled")
        channel = self._channel
        if channel is None:
            raise SupervisorError(f"plugin {self.plugin_name} is not running")
        if self._inflight_sem.locked():
            raise SupervisorError(f"plugin {self.plugin_name}: too many in-flight requests")
        request_id = secrets.token_hex(16)
        self._inflight[request_id] = CapabilityContext(
            user_id=context["user_id"],
            username=context["username"],
            role=context["role"],
        )
        worker_context = {
            "user_id": context["user_id"],
            "username": context["username"],
            "role": context["role"],
        }
        async with self._inflight_sem:
            try:
                resp = await channel.call(
                    MsgType.HTTP_REQUEST,
                    {
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "query": query or {},
                        "headers": headers or {},
                        "body": body,
                        "context": worker_context,
                    },
                    timeout=timeout,
                )
            except asyncio.TimeoutError as exc:
                raise SupervisorTimeout(
                    f"plugin {self.plugin_name} request timed out"
                ) from exc
            finally:
                self._inflight.pop(request_id, None)
        return resp.body
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_supervisor.py -v`
Expected: PASS (all prior supervisor tests + the 2 new ones).

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/sandbox/supervisor.py backend/tests/plugins/sandbox/test_supervisor.py
git commit -m "feat(plugin-sandbox): dispatch forwards query+headers, timeout + in-flight cap (Phase 4)"
```

---

## Task 3: Unique per-spawn worker socket path (prod-only collision fix)

`WorkerListener` binds a **fixed** path `plugin_dir/plugin.sock` (`transport.py:48`).
With one subprocess per uvicorn worker, the 4 prod workers each start a listener for
the same plugin and collide on that path (unlink/rebind race → cross-wiring). Dev uses
an ephemeral TCP port so this is **invisible in Windows tests but breaks Linux prod**.
Fix: make the UDS socket filename unique per `WorkerListener` instance.

**Files:**
- Modify: `backend/app/plugins/sandbox/transport.py`
- Test: `backend/tests/plugins/sandbox/test_transport.py` (append)

**Interfaces:**
- Produces: `WorkerListener(socket_dir)` now binds a unique `plugin-<pid>-<token>.sock`; `connect_address` still a `unix:<path>` / `tcp:<host>:<port>` string consumed unchanged by `connect_to_host`.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/plugins/sandbox/test_transport.py
import sys

import pytest

from app.plugins.sandbox.transport import WorkerListener, _use_unix_socket


@pytest.mark.skipif(not _use_unix_socket(), reason="UDS only (Linux/macOS)")
def test_two_listeners_same_dir_get_distinct_sockets(tmp_path):
    """Two WorkerListeners on the same plugin dir must not share a socket path."""
    import asyncio

    async def run():
        a = WorkerListener(tmp_path)
        b = WorkerListener(tmp_path)
        addr_a = await a.start()
        addr_b = await b.start()
        try:
            assert addr_a != addr_b
            assert addr_a.startswith("unix:") and addr_b.startswith("unix:")
        finally:
            await a.close()
            await b.close()

    asyncio.run(run())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_transport.py -k distinct_sockets -v`
Expected: FAIL on Linux/macOS (both bind `plugin.sock` → equal paths or bind error). On Windows it is skipped — run this task's verification on a Linux box or trust the code review.

- [ ] **Step 3: Edit `transport.py` — unique socket name**

Add the imports at the top (next to `import os`):

```python
import secrets
```

In `WorkerListener.start()`, replace the fixed-path line:

```python
            path = str(self._socket_dir / "plugin.sock")
```

with a per-instance unique name:

```python
            path = str(self._socket_dir / f"plugin-{os.getpid()}-{secrets.token_hex(4)}.sock")
```

The existing `os.unlink(path)` stale-cleanup stays (harmless for a fresh unique name). `close()` already stops the server; the unique file is cleaned on the next process restart via the dir lifecycle (no extra unlink needed — leftover empty socket files are inert).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_transport.py -v`
Expected: PASS (existing transport tests + the new distinct-socket test on UDS platforms).

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/sandbox/transport.py backend/tests/plugins/sandbox/test_transport.py
git commit -m "fix(plugin-sandbox): unique per-spawn UDS socket path (no collision across workers)"
```

---

## Task 4: PluginManager dual-path (external enable/disable, load_plugin guard, scope threading)

**Files:**
- Modify: `backend/app/plugins/manager.py`
- Test: `backend/tests/plugins/test_plugin_manager_dualpath.py`

**Interfaces:**
- Consumes: `build_capability_router` (Task 1); `SandboxSupervisor` (Task 2); `DiscoveredPlugin.source`/`.manifest`.
- Produces:
  - `PluginManager._sandboxes: Dict[str, SandboxSupervisor]`
  - `enable_plugin(name, granted_permissions, db, start_background_tasks=True, granted_api_scopes=None)` — external branch spawns a supervisor.
  - `PluginManager._supervisor_factory(plugin_name, plugin_dir, capability_router)` — overridable hook returning a started-capable supervisor (tests inject a fake).
  - `is_sandboxed(name) -> bool`, `get_sandbox(name) -> "SandboxSupervisor | None"`.
  - `load_plugin(external)` raises `PluginLoadError`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/test_plugin_manager_dualpath.py
"""Phase 4: PluginManager external dual-path (no exec_module in host)."""
import asyncio

import pytest

from app.plugins.manager import DiscoveredPlugin, PluginLoadError, PluginManager


class _FakeSupervisor:
    def __init__(self, plugin_name, plugin_dir, capability_router=None):
        self.plugin_name = plugin_name
        self.started = False
        self.stopped = False
        self.capability_router = capability_router

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


@pytest.fixture
def manager(tmp_path, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    # Pretend an external plugin "weather" was discovered with a parsed manifest.
    plugin_dir = tmp_path / "weather"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("raise RuntimeError('must never exec in host')\n")

    class _M:
        api_scopes = ["storage", "core.notify"]
        version = "1.0.0"
        display_name = "Weather"

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=plugin_dir, source="external", manifest=_M()),
    }
    mgr._supervisor_factory = _FakeSupervisor
    return mgr


def test_load_plugin_external_refuses_to_exec(manager):
    with pytest.raises(PluginLoadError):
        manager.load_plugin("weather")


def test_enable_external_spawns_supervisor_without_exec(manager):
    ok = asyncio.run(
        manager.enable_plugin("weather", [], db=None, granted_api_scopes=["storage", "core.notify"])
    )
    assert ok is True
    sup = manager.get_sandbox("weather")
    assert sup is not None and sup.started is True
    assert sup.capability_router is not None
    assert manager.is_enabled("weather") is True
    # The external plugin was never instantiated in-process.
    assert manager.get_plugin("weather") is None


def test_disable_external_stops_supervisor(manager):
    asyncio.run(manager.enable_plugin("weather", [], db=None, granted_api_scopes=["storage"]))
    sup = manager.get_sandbox("weather")
    asyncio.run(manager.disable_plugin("weather"))
    assert sup.stopped is True
    assert manager.is_enabled("weather") is False
    assert manager.get_sandbox("weather") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_manager_dualpath.py -v`
Expected: FAIL — no `_sandboxes`/`_supervisor_factory`/`get_sandbox`; `enable_plugin` has no `granted_api_scopes`; external not guarded.

- [ ] **Step 3: Edit `manager.py` — registry + factory + accessors**

In `__init__`, after `self._background_tasks` init, add:

```python
        self._sandboxes: Dict[str, Any] = {}
```

Add an overridable factory method and accessors to the class:

```python
    def _supervisor_factory(self, plugin_name: str, plugin_dir: Path, capability_router: Any):
        """Build a SandboxSupervisor (overridable in tests)."""
        from app.plugins.sandbox.supervisor import SandboxSupervisor  # noqa: PLC0415
        return SandboxSupervisor(plugin_name, plugin_dir, capability_router=capability_router)

    def is_sandboxed(self, name: str) -> bool:
        return name in self._sandboxes

    def get_sandbox(self, name: str) -> Any:
        return self._sandboxes.get(name)
```

- [ ] **Step 4: Edit `load_plugin` — guard external**

In `load_plugin`, immediately after `source` is resolved (right before the `init_file = plugin_path / "__init__.py"` line, ~310), add:

```python
        if source == "external":
            raise PluginLoadError(
                f"External plugin '{name}' must not be loaded in-process; "
                "it runs in a sandboxed subprocess."
            )
```

- [ ] **Step 5: Edit `enable_plugin` — signature + external branch**

Change the signature to add the new keyword:

```python
    async def enable_plugin(
        self,
        name: str,
        granted_permissions: List[str],
        db: Session,
        start_background_tasks: bool = True,
        granted_api_scopes: Optional[List[str]] = None,
    ) -> bool:
```

At the very start of the method body (before the `if name not in self._plugins:` block), add the external branch:

```python
        discovered = self.get_discovered(name)
        if discovered is not None and discovered.source == "external":
            return await self._enable_external(name, discovered, granted_api_scopes or [])
```

Then add the helper method:

```python
    async def _enable_external(
        self, name: str, discovered: "DiscoveredPlugin", granted_api_scopes: List[str]
    ) -> bool:
        """Enable an external plugin as a sandboxed subprocess (no in-host exec).

        Spawned on every uvicorn worker (no primary-only gating) so the catch-all
        proxy can serve the plugin regardless of which worker handles the request.
        """
        if name in self._sandboxes:
            return True
        from app.plugins.sandbox.host_capabilities import build_capability_router  # noqa: PLC0415

        router = build_capability_router(name, set(granted_api_scopes))
        supervisor = self._supervisor_factory(name, discovered.path, router)
        try:
            await supervisor.start()
        except Exception:
            logger.exception("Failed to start sandbox for external plugin %s", name)
            return False
        self._sandboxes[name] = supervisor
        self._enabled.add(name)
        logger.info("Enabled external (sandboxed) plugin: %s", name)
        return True
```

- [ ] **Step 6: Edit `disable_plugin` — external branch**

At the start of `disable_plugin`, before the `if name not in self._enabled:` check, add:

```python
        if name in self._sandboxes:
            supervisor = self._sandboxes.pop(name)
            try:
                await supervisor.stop()
            except Exception:
                logger.exception("Error stopping sandbox for %s", name)
            self._enabled.discard(name)
            logger.info("Disabled external (sandboxed) plugin: %s", name)
            return True
```

- [ ] **Step 7: Edit `shutdown_all` + `load_enabled_plugins`**

`shutdown_all` already iterates `self._enabled` and calls `disable_plugin`, which now handles sandboxes — no change needed there. In `load_enabled_plugins`, thread the scopes by replacing the `await self.enable_plugin(...)` call with:

```python
            await self.enable_plugin(
                record.name,
                record.granted_permissions or [],
                db,
                start_background_tasks=start_background_tasks,
                granted_api_scopes=record.granted_api_scopes or [],
            )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_manager_dualpath.py -v`
Expected: PASS (3 passed).

- [ ] **Step 9: Regression — existing manager tests**

Run: `cd backend && python -m pytest tests/plugins/test_plugin_manager.py tests/plugins/test_plugin_manager_multipath.py tests/plugins/test_plugins.py -v`
Expected: PASS (bundled path unchanged).

- [ ] **Step 10: Commit**

```bash
git add backend/app/plugins/manager.py backend/tests/plugins/test_plugin_manager_dualpath.py
git commit -m "feat(plugin-sandbox): PluginManager dual-path — external spawns supervisor, no host exec (Phase 4)"
```

---

## Task 5: Catch-all proxy route (auth, caps, header allowlist, error scrubbing)

**Files:**
- Create: `backend/app/plugins/sandbox/proxy.py`
- Modify: `backend/app/plugins/manager.py` (wire catch-all into `get_router()`)
- Test: `backend/tests/plugins/sandbox/test_proxy.py`

**Interfaces:**
- Consumes: `SandboxSupervisor.dispatch` (Task 2), `SupervisorError`/`SupervisorTimeout`, `PluginManager.get_sandbox`.
- Produces: `proxy_request(name, path, request, current_user, manager) -> Response`; module constants `REQUEST_BODY_MAX`, `REQUEST_TIMEOUT`; `ALLOWED_REQUEST_HEADERS`. `PluginManager.get_router()` includes a catch-all route `/{name}/{path:path}` for all methods.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/sandbox/test_proxy.py
"""Phase 4: catch-all proxy — auth gating, header allowlist, error scrubbing."""
import asyncio
import types

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.plugins.sandbox import proxy
from app.plugins.sandbox.supervisor import SupervisorError, SupervisorTimeout


def _make_request(method="GET", headers=None, body=b"", query=b""):
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http", "method": method, "path": "/api/plugins/weather/status",
        "query_string": query, "headers": hdrs,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


class _Sup:
    def __init__(self, **kw):
        self.kw = None
        self._resp = kw.get("resp", {"status": 200, "headers": {"content-type": "application/json"}, "body": {"ok": True}})
        self._raise = kw.get("raise_exc")

    async def dispatch(self, method, path, body, context, *, query=None, headers=None, timeout=30.0):
        if self._raise:
            raise self._raise
        self.kw = dict(method=method, path=path, body=body, context=context, query=query, headers=headers)
        return self._resp


class _Mgr:
    def __init__(self, sup):
        self._sup = sup

    def get_sandbox(self, name):
        return self._sup


_USER = types.SimpleNamespace(id=7, username="alice", role="user")


def test_proxy_forwards_without_token_headers():
    sup = _Sup()
    req = _make_request(headers={"authorization": "Bearer x", "cookie": "s=1", "content-type": "application/json"}, query=b"a=1")
    resp = asyncio.run(proxy.proxy_request("weather", "status", req, _USER, _Mgr(sup)))
    assert resp.status_code == 200
    assert "authorization" not in sup.kw["headers"]
    assert "cookie" not in sup.kw["headers"]
    assert sup.kw["headers"] == {"content-type": "application/json"}
    assert sup.kw["query"] == {"a": "1"}
    assert sup.kw["context"] == {"user_id": 7, "username": "alice", "role": "user"}


def test_proxy_unknown_plugin_404():
    class _Empty:
        def get_sandbox(self, name):
            return None

    req = _make_request()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("nope", "x", req, _USER, _Empty()))
    assert ei.value.status_code == 404


def test_proxy_body_too_large_413():
    req = _make_request(method="POST", body=b"x" * (proxy.REQUEST_BODY_MAX + 1))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup())))
    assert ei.value.status_code == 413


def test_proxy_timeout_504():
    req = _make_request()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup(raise_exc=SupervisorTimeout("t")))))
    assert ei.value.status_code == 504


def test_proxy_crash_scrubbed_502():
    req = _make_request()
    with pytest.raises(HTTPException) as ei:
        asyncio.run(proxy.proxy_request("weather", "x", req, _USER, _Mgr(_Sup(raise_exc=SupervisorError("boom")))))
    assert ei.value.status_code == 502
    assert "boom" not in str(ei.value.detail)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_proxy.py -v`
Expected: FAIL — `app.plugins.sandbox.proxy` does not exist.

- [ ] **Step 3: Write `proxy.py`**

```python
# backend/app/plugins/sandbox/proxy.py
"""FastAPI catch-all proxy for external (sandboxed) plugins.

Forwards a token-free, header-allowlisted request to the plugin's worker over
RPC and turns the worker's response back into a FastAPI Response. Every plugin
failure is scrubbed: crash -> 502, timeout -> 504, unreachable/disabled -> 503.
The Authorization and Cookie headers are never forwarded.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.plugins.sandbox.supervisor import SupervisorError, SupervisorTimeout

logger = logging.getLogger(__name__)

REQUEST_BODY_MAX = 10 * 1024 * 1024  # 10 MiB
REQUEST_TIMEOUT = 30.0
# Request headers forwarded to the plugin. NEVER includes authorization/cookie.
ALLOWED_REQUEST_HEADERS = frozenset({"content-type", "accept"})
# Response headers passed back to the client.
ALLOWED_RESPONSE_HEADERS = frozenset({"content-type"})


def _filter_request_headers(request: Request) -> dict:
    return {
        k.lower(): v
        for k, v in request.headers.items()
        if k.lower() in ALLOWED_REQUEST_HEADERS
    }


def _build_response(payload: dict) -> Response:
    status_code = int(payload.get("status", 200))
    body = payload.get("body")
    headers = {
        k.lower(): v
        for k, v in (payload.get("headers") or {}).items()
        if k.lower() in ALLOWED_RESPONSE_HEADERS
    }
    if isinstance(body, (bytes, bytearray)):
        return Response(content=bytes(body), status_code=status_code, headers=headers)
    return JSONResponse(content=body, status_code=status_code, headers=headers)


async def proxy_request(
    name: str, path: str, request: Request, current_user: Any, manager: Any
) -> Response:
    """Proxy one request to an external plugin's sandbox worker."""
    supervisor = manager.get_sandbox(name)
    if supervisor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")

    # Reject oversized bodies BEFORE buffering them into memory. The
    # Content-Length header can lie, so we also guard after the read.
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > REQUEST_BODY_MAX:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Request body too large",
                )
        except ValueError:
            pass  # malformed header — fall through to the post-read guard
    body = await request.body()
    if len(body) > REQUEST_BODY_MAX:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Request body too large",
        )

    context = {
        "user_id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
    }
    try:
        result = await supervisor.dispatch(
            request.method,
            path,
            body,
            context,
            query=dict(request.query_params),
            headers=_filter_request_headers(request),
            timeout=REQUEST_TIMEOUT,
        )
    except SupervisorTimeout:
        logger.warning("Plugin %s request timed out", name)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Plugin timed out")
    except SupervisorError as exc:
        logger.warning("Plugin %s unavailable: %s", name, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Plugin error")
    except Exception:
        logger.exception("Unexpected error proxying to plugin %s", name)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Plugin error")

    return _build_response(result)
```

- [ ] **Step 4: Run proxy unit tests**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_proxy.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Wire the catch-all into `manager.get_router()`**

Replace `get_router` in `manager.py` with (bundled routers first, catch-all last):

```python
    def get_router(self) -> APIRouter:
        """Combined router: bundled plugin routes + a catch-all for sandboxed ones."""
        from fastapi import Request  # noqa: PLC0415
        from app.api.deps import get_current_user  # noqa: PLC0415
        from app.plugins.sandbox.proxy import proxy_request  # noqa: PLC0415

        router = APIRouter(prefix="/plugins", tags=["plugins"])

        # Bundled plugins: explicit routers, registered FIRST so they win.
        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin:
                plugin_router = plugin.get_router()
                if plugin_router:
                    router.include_router(
                        plugin_router, prefix=f"/{name}", tags=[f"plugin:{name}"]
                    )

        # Catch-all for external/sandboxed plugins, registered LAST.
        manager = self

        @router.api_route(
            "/{name}/{path:path}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            include_in_schema=False,
        )
        async def _sandbox_proxy(
            name: str,
            path: str,
            request: Request,
            current_user=Depends(get_current_user),
        ):
            return await proxy_request(name, path, request, current_user, manager)

        return router
```

Add the FastAPI `Depends` import at the top of `manager.py`:

```python
from fastapi import APIRouter, Depends
```

- [ ] **Step 6: Mount-condition note (no code change, verify)**

`lifespan.py:583` mounts the router only `if plugin_router.routes`. The catch-all is always added, so `routes` is non-empty even with zero enabled plugins → the proxy is always mounted. Confirm by reading `lifespan.py:582-585`; no edit required.

- [ ] **Step 7: Commit**

```bash
git add backend/app/plugins/sandbox/proxy.py backend/app/plugins/manager.py backend/tests/plugins/sandbox/test_proxy.py
git commit -m "feat(plugin-sandbox): catch-all proxy route with caps + header allowlist + scrubbing (Phase 4)"
```

---

## Task 6: Toggle/details/list route dual-path for external plugins

The toggle, details, and list routes currently call `load_plugin`/`get_plugin` which now raises for external. Branch them onto the manifest path (`DiscoveredPlugin.manifest`) so external plugins are manageable without exec.

**Files:**
- Modify: `backend/app/api/routes/plugins.py`
- Test: `backend/tests/plugins/test_external_plugin_routes.py`

**Interfaces:**
- Consumes: `PluginManager.get_discovered(name)`, `manager.enable_plugin(..., granted_api_scopes=...)`, `manager.disable_plugin`, `plugin_service.enable_plugin`/`disable_plugin_record`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/test_external_plugin_routes.py
"""Phase 4: toggling an external plugin uses the manifest path (no exec)."""
import asyncio
import types

from app.api.routes import plugins as plugins_route
from app.plugins.manager import DiscoveredPlugin, PluginManager


def test_toggle_enable_external_uses_manifest(tmp_path, db_session, monkeypatch):
    PluginManager.reset_instance()
    mgr = PluginManager(plugins_dir=tmp_path)
    pdir = tmp_path / "weather"
    pdir.mkdir()

    class _M:
        api_scopes = ["storage"]
        version = "2.0.0"
        display_name = "Weather"
        required_permissions = []

    mgr._discovered = {
        "weather": DiscoveredPlugin(name="weather", path=pdir, source="external", manifest=_M()),
    }

    enabled = {}

    async def fake_enable(name, perms, db, start_background_tasks=True, granted_api_scopes=None):
        enabled["scopes"] = granted_api_scopes
        return True

    monkeypatch.setattr(mgr, "enable_plugin", fake_enable)

    body = plugins_route.PluginToggleRequest(enabled=True, grant_permissions=[])
    user = types.SimpleNamespace(id=1, username="admin", role="admin")
    resp = asyncio.run(
        plugins_route.toggle_plugin(
            request=None, response=None, name="weather", body=body,
            db=db_session, current_user=user, plugin_manager=mgr,
        )
    )
    assert resp.is_enabled is True
    assert enabled["scopes"] == ["storage"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_external_plugin_routes.py -v`
Expected: FAIL — `toggle_plugin` calls `load_plugin("weather")` which raises `PluginLoadError` → 404.

- [ ] **Step 3: Edit `toggle_plugin` — branch external before load_plugin**

At the very start of `toggle_plugin` (before the `try: plugin = plugin_manager.get_plugin(name)` block, ~218), add:

```python
    discovered = plugin_manager.get_discovered(name)
    if discovered is not None and discovered.source == "external":
        return await _toggle_external(
            name, body, db, current_user, plugin_manager, discovered
        )
```

Add the helper function (module level, after `toggle_plugin`):

```python
async def _toggle_external(
    name, body, db, current_user, plugin_manager, discovered,
):
    """Enable/disable an external sandboxed plugin via its manifest (no exec)."""
    manifest = discovered.manifest
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plugin not found")

    if body.enabled:
        api_scopes = list(getattr(manifest, "api_scopes", []) or [])
        plugin_service.enable_plugin(
            db,
            name=name,
            version=manifest.version,
            display_name=manifest.display_name,
            permissions=body.grant_permissions,
            default_config={},
            installed_by=current_user.username,
            api_scopes=api_scopes,
        )
        success = await plugin_manager.enable_plugin(
            name, body.grant_permissions, db, granted_api_scopes=api_scopes
        )
        if not success:
            plugin_service.rollback_enable(db, name)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to enable plugin",
            )
        invalidate_plugin_cache(name)
        logger.info("External plugin %s enabled by %s", name, current_user.username)
        return PluginToggleResponse(
            name=name, is_enabled=True,
            message=f"Plugin '{manifest.display_name}' enabled successfully",
        )

    success = await plugin_manager.disable_plugin(name)
    plugin_service.disable_plugin_record(db, name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable plugin",
        )
    invalidate_plugin_cache(name)
    logger.info("External plugin %s disabled by %s", name, current_user.username)
    return PluginToggleResponse(
        name=name, is_enabled=False,
        message=f"Plugin '{manifest.display_name}' disabled successfully",
    )
```

- [ ] **Step 4: Guard `get_all_plugins` against external exec**

In `manager.py` `get_all_plugins`, replace the `try:` body's `if name not in self._plugins: self.load_plugin(name)` region with a source check that uses the manifest for external. Replace the loop body with:

```python
        for name in discovered:
            info = self.get_discovered(name)
            if info is not None and info.source == "external" and info.manifest is not None:
                m = info.manifest
                result[name] = {
                    "name": m.name,
                    "version": m.version,
                    "display_name": m.display_name,
                    "description": m.description,
                    "author": m.author,
                    "category": m.category,
                    "required_permissions": list(m.required_permissions),
                    "is_enabled": name in self._enabled,
                    "has_ui": m.ui is not None,
                    "has_routes": True,
                    "dangerous_permissions": PermissionManager.get_dangerous_permissions(
                        list(m.required_permissions)
                    ),
                }
                continue
            try:
                if name not in self._plugins:
                    self.load_plugin(name)
                plugin = self._plugins[name]
                meta = plugin.metadata
                result[name] = {
                    "name": meta.name,
                    "version": meta.version,
                    "display_name": meta.display_name,
                    "description": meta.description,
                    "author": meta.author,
                    "category": meta.category,
                    "required_permissions": meta.required_permissions,
                    "is_enabled": name in self._enabled,
                    "has_ui": plugin.get_ui_manifest() is not None,
                    "has_routes": plugin.get_router() is not None,
                    "dangerous_permissions": PermissionManager.get_dangerous_permissions(
                        meta.required_permissions
                    ),
                }
            except PluginLoadError as e:
                result[name] = {"name": name, "error": str(e), "is_enabled": False}
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/plugins/test_external_plugin_routes.py tests/plugins/test_plugins.py -v`
Expected: PASS (external toggle + bundled list regression).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/plugins.py backend/app/plugins/manager.py backend/tests/plugins/test_external_plugin_routes.py
git commit -m "feat(plugin-sandbox): route dual-path — manage external plugins via manifest, no exec (Phase 4)"
```

---

## Task 7: End-to-end — sample external plugin through the full proxy→RPC→capability path

A real subprocess test (mirrors `test_phase3_e2e.py`) proving an external plugin's own route + a `storage.*` call + a `core.*` call work, and a non-granted scope is denied.

**Files:**
- Create: `backend/tests/plugins/sandbox/fixtures/e2e_plugin/__init__.py`
- Create: `backend/tests/plugins/sandbox/fixtures/e2e_plugin/plugin.json`
- Create: `backend/tests/plugins/sandbox/test_phase4_e2e.py`

**Interfaces:**
- Consumes: real `SandboxSupervisor` (Task 2), `build_capability_router` (Task 1), the worker entrypoint.

- [ ] **Step 1: Write the fixture plugin**

```python
# backend/tests/plugins/sandbox/fixtures/e2e_plugin/__init__.py
"""E2E fixture: a route that reads+writes storage and returns it."""


def register(host):
    @host.route("POST", "echo")
    async def echo(request):
        await host.storage.set("last", request["body"])
        value = await host.storage.get("last")
        return {"status": 200, "body": {"stored": value, "user": request["user"]}}
```

```json
{
  "manifest_version": 1,
  "name": "e2e_plugin",
  "version": "1.0.0",
  "display_name": "E2E Plugin",
  "description": "phase 4 e2e fixture",
  "author": "tests",
  "api_scopes": ["storage"],
  "entrypoint": "__init__.py"
}
```

- [ ] **Step 2: Write the failing E2E test**

```python
# backend/tests/plugins/sandbox/test_phase4_e2e.py
"""Phase 4 E2E: external plugin through supervisor.dispatch -> RPC -> capability."""
import asyncio
from pathlib import Path

import msgpack
import pytest

from app.plugins.sandbox.host_capabilities import build_capability_router
from app.plugins.sandbox.supervisor import SandboxSupervisor

FIXTURE = Path(__file__).parent / "fixtures" / "e2e_plugin"


@pytest.mark.timeout(30)
def test_external_plugin_storage_roundtrip(monkeypatch):
    # Stub the storage capability's DB so the test needs no real database.
    import app.plugins.sandbox.capabilities as caps

    store: dict = {}

    def fake_get(db, plugin, uid, key):
        k = (plugin, uid, key)
        return (k in store, store.get(k))

    def fake_set(db, plugin, uid, key, value):
        store[(plugin, uid, key)] = value

    monkeypatch.setattr(caps.plugin_storage_service, "get_value", fake_get)
    monkeypatch.setattr(caps.plugin_storage_service, "set_value", fake_set)

    async def run():
        router = build_capability_router("e2e_plugin", {"storage"})
        sup = SandboxSupervisor("e2e_plugin", FIXTURE, capability_router=router)
        await sup.start()
        try:
            ctx = {"user_id": 42, "username": "alice", "role": "user"}
            resp = await sup.dispatch("POST", "echo", msgpack.packb({"hi": 1}), ctx)
            assert resp["status"] == 200
            assert resp["body"]["user"]["user_id"] == 42
        finally:
            await sup.stop()

    asyncio.run(run())
```

- [ ] **Step 3: Run E2E test to verify it fails, then passes**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_phase4_e2e.py -v`
Expected first run: should PASS once Tasks 1–2 are in place (it exercises real code). If it fails, debug the supervisor/worker wiring before proceeding — do not stub past a real failure.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/plugins/sandbox/fixtures/e2e_plugin backend/tests/plugins/sandbox/test_phase4_e2e.py
git commit -m "test(plugin-sandbox): Phase 4 e2e — external plugin storage roundtrip through real subprocess"
```

---

## Task 8: Full sandbox + plugin suite regression

**Files:** none (verification only).

- [ ] **Step 1: Run the whole sandbox + plugin suite**

Run: `cd backend && python -m pytest tests/plugins -v`
Expected: PASS. Investigate any failure; the bundled path and existing sandbox tests must remain green.

- [ ] **Step 2: ruff on all touched files**

Run: `cd backend && ruff check app/plugins/sandbox app/plugins/manager.py app/api/routes/plugins.py`
Expected: no errors.

- [ ] **Step 3: Commit (if ruff made fixes)**

```bash
git add -A
git commit -m "chore(plugin-sandbox): ruff clean-up for Phase 4"
```

---

## Accepted limitations & authoring constraints (document, do not fix here)

- **Runtime-enable is per-worker.** Each uvicorn worker owns its own subprocess and there is no cross-worker IPC, so an external plugin **enabled at runtime** via the toggle route only spawns a worker on the uvicorn process that handled the toggle; the other workers serve it after the next restart (their startup `load_enabled_plugins` spawns it). This matches the existing bundled-plugin behaviour (runtime route changes need a restart).
- **Idle process count = workers × external plugins.** With 4 workers and N external plugins, 4N subprocesses run idle. Acceptable for a home NAS with few plugins. **Lazy-spawn-on-first-request** (spawn in the catch-all handler when `get_sandbox(name)` is None but the DB says enabled) would remove idle processes and fix the per-worker runtime-enable gap — tracked as a future optimization, out of scope for Phase 4.
- **Reserved top-level route names.** An external plugin cannot expose a root route named `toggle`, `config`, `ui`, or `dashboard-panel` (shadowed by the management routes in `routes/plugins.py`, registered before the catch-all), and no plugin may be named `marketplace` or `permissions` (`PluginGate._LIST_PATHS`). Surface this in the Phase 5 authoring docs.
- **Multi-value query params collapse.** `dict(request.query_params)` keeps only the last value per key. Fine for v1; note in authoring docs.
- **Raw request body.** The plugin receives the raw request bytes (no JSON-parsing convenience in the SDK). Deliberate for v1.
- **Body-size DoS depends on the edge for truly-malicious clients.** The proxy rejects via `Content-Length` precheck then a post-read guard, but a client that streams a huge body while lying about (or omitting) `Content-Length` is only fully bounded by nginx `client_max_body_size`. Verify the prod nginx limit covers `/api/plugins/`.

## Self-Review Notes (coverage vs. spec)

- Scope-storage → Task 1 (consume existing column; filter to known catalog) + Task 4/6 (thread `granted_api_scopes`). No migration (column exists).
- Dual-path / no host exec → Task 4 (`load_plugin` guard, `_enable_external`) + Task 6 (routes).
- core.* catalog (system_metrics + notify) → Task 1 wires both; `storage.*` via existing CapabilityRouter.
- One subprocess per worker → Task 3 (unique socket path, prevents cross-worker collision) + Task 4 `_enable_external` (no primary-only gating) + accepted-limitation note.
- Proxy + header allowlist + caps + scrubbing → Task 5.
- Token never forwarded → Task 5 (`ALLOWED_REQUEST_HEADERS`) + tests (positive assertion).
- Capability deps wired → Task 1.
- Testing matrix (dual-path, no-exec, proxy auth/headers/caps/scrub, scope enforcement, e2e) → Tasks 4,5,7.
