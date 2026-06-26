# Plugin-Backend-Isolation — Phase 3: Capability-Layer + Plugin-SDK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sandbox worker's echo handler with a real default-deny capability layer: a host-side `CapabilityRouter` (storage.* + core.system_metrics + core.notify) and a worker-side Plugin-SDK that loads an external plugin via `exec_module` *only inside the worker* and routes its requests + capability calls over the existing RPC channel.

**Architecture:** The host `SandboxSupervisor` already proxies `http_request` to the worker and supervises it (Phase 2b). Phase 3 adds: (1) a `CapabilityRouter` that gates every `cap_call` against the plugin's granted scopes and runs a narrow validated host handler; (2) supervisor plumbing that stamps each `http_request` with a host-owned `request_id`, tracks `request_id → context`, and routes inbound `cap_call`s to the router with the *host-resolved* user context (never a plugin-supplied user_id); (3) a worker Plugin-SDK (`PluginHost`) exposing `host.route(...)`, `host.storage.*`, `host.scopes.*`, plus a loader that `exec_module`s the plugin entrypoint and calls its `register(host)`. FastAPI catch-all + `PluginManager` dual-path stay in Phase 4; the router's host-side dependencies (DB session factory, metrics reader, notifier) are **injected**, so Phase 3 is fully unit-testable without app wiring.

**Tech Stack:** Python 3.11+ (asyncio, importlib), msgpack RPC (Phase 1), pytest (`asyncio_mode="auto"`), ruff. Cross-platform transport from Phase 2a (UDS prod / loopback-TCP dev).

## Global Constraints

- **Default-deny is the enforcement point.** A `cap_call` whose required scope is not in the plugin's `granted_scopes` returns `{"error": "denied", ...}` and is audit-logged. This replaces the old purely-declarative permission check. No capability runs before the scope check passes.
- **User-binding invariant.** The `user_id` used by any capability handler comes **only** from the host-resolved `CapabilityContext` (looked up by `request_id` in the supervisor's in-flight map), **never** from plugin-supplied `cap_call` args. A plugin cannot address another user's storage bucket or send a notification as another user.
- **Token never crosses the boundary.** The worker receives only `context {user_id, username, role}` — never `Authorization`/`Cookie`/JWT. (Already true in Phase 2b; do not regress.)
- **`exec_module` of an external plugin runs ONLY in the worker process**, never in the host. The host imports nothing from the plugin.
- **Grantable scope strings** (live in `InstalledPlugin.granted_api_scopes`, a JSON list): exactly `"storage"`, `"core.system_metrics"`, `"core.notify"` in v1. Capability→scope map: `storage.get|set|delete|list → "storage"`; `core.system_metrics → "core.system_metrics"`; `core.notify → "core.notify"`.
- **Storage values are JSON-serializable** (the `plugin_storage` table column is `JSON`); quota is `StorageQuotaError` (64 KB / 100 keys) from `plugin_storage_service` — map it to `{"error": "storage_quota"}`, never raw-leak.
- **No host-global coupling in the router.** `CapabilityRouter` takes its `session_factory`, `metrics_reader`, `notifier`, and `audit_logger` as constructor injections. Phase 4 wires the production ones; Phase 3 tests inject fakes.
- **Sync DB / blocking work runs in `asyncio.to_thread`** so an untrusted plugin's capability call cannot stall the host event loop.
- **pytest**: `asyncio_mode="auto"` — async tests need NO `@pytest.mark.asyncio`. Tests live under `backend/tests/plugins/sandbox/`.
- **Commit message trailer (every commit):**
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FCigCPSwBQRnmwTWbpfRzc
  ```
  Use the Write-to-file + `git commit -F <file>` pattern (here-strings fail in PowerShell).
- **Windows**: repo `core.autocrlf=true`; do not fight line endings. Local dev transport = loopback-TCP; UDS path runs in Linux CI.
- **Branch**: `feat/plugin-backend-isolation-phase2b` is the current branch (Phase 2b, PR #283). Confirm with the controller whether Phase 3 stacks on it or starts a fresh branch off `main` after #283 merges. Do NOT start implementation on `main`.

---

## File Structure

- **Create** `backend/app/plugins/sandbox/capabilities.py` — `CapabilityContext`, `CapabilityError`, `CapabilityRouter` (host-side default-deny dispatch + handlers). [Tasks 1–2]
- **Modify** `backend/app/plugins/sandbox/supervisor.py` — in-flight `request_id → context` map, `request_id` stamping into `http_request`, host RpcChannel `request_handler` routing `cap_call` → router. [Task 3]
- **Create** `backend/app/plugins/sandbox/sdk.py` — `PluginHost` (route registry, `storage`, `scopes`), `Request`/`Response` helpers, the `register(host)` authoring contract. [Task 4]
- **Create** `backend/app/plugins/sandbox/loader.py` — `load_plugin_module(plugin_dir, entrypoint, plugin_name, host)` exec_module + `register(host)`. [Task 4]
- **Modify** `backend/app/plugins/sandbox/worker.py` — argv (`--plugin-dir/--plugin-name/--entrypoint`), boot-time load, `http_request` → route-table dispatch with per-request `request_id` contextvar. [Task 4]
- **Create** `backend/tests/plugins/sandbox/test_capabilities.py` — router unit tests. [Tasks 1–2]
- **Create** `backend/tests/plugins/sandbox/test_sdk.py` — SDK + loader unit tests (fake channel). [Task 4]
- **Modify** `backend/tests/plugins/sandbox/test_supervisor.py` — cap-dispatch integration via a scripted worker. [Task 3]
- **Create** `backend/tests/plugins/sandbox/fixtures/sample_plugin/__init__.py` — fixture sandbox plugin for the e2e test. [Task 5]
- **Create** `backend/tests/plugins/sandbox/test_phase3_e2e.py` — full proxy→RPC→capability path through a real subprocess. [Task 5]

---

## Task 1: `CapabilityRouter` — scope-gating + `storage.*`

**Files:**
- Create: `backend/app/plugins/sandbox/capabilities.py`
- Test: `backend/tests/plugins/sandbox/test_capabilities.py`

**Interfaces:**
- Consumes: `app.services.plugin_storage_service.{get_value,set_value,delete_value,list_keys,StorageQuotaError}` (all sync, `(db, plugin_name, user_id, key[, value])`); `app.services.audit.get_audit_logger_db`.
- Produces:
  - `@dataclass(frozen=True) CapabilityContext(user_id: int, username: str, role: str)`
  - `class CapabilityError(Exception)` with `.code: str` (used internally to map to `{"error": code}`)
  - `CAPABILITY_SCOPE: dict[str, str]` (capability → required scope)
  - `class CapabilityRouter` with:
    - `__init__(self, *, plugin_name: str, granted_scopes: frozenset[str], session_factory: Callable[[], Session], metrics_reader: Callable[[], dict] | None = None, notifier: Callable[[CapabilityContext, dict], Awaitable[None]] | None = None, audit_logger=None)`
    - `async def dispatch(self, capability: str, args: dict, context: CapabilityContext) -> dict` — returns the **cap_result body**: `{"result": <value>}` on success or `{"error": <code>, ...}` on failure. Never raises for plugin-caused errors.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/plugins/sandbox/test_capabilities.py
import pytest

from app.plugins.sandbox.capabilities import (
    CapabilityContext,
    CapabilityRouter,
)


class _FakeStorage:
    """In-memory stand-in for plugin_storage_service, keyed (plugin, user, key)."""

    def __init__(self):
        self.data: dict[tuple[str, int, str], object] = {}

    def get_value(self, db, plugin_name, user_id, key):
        k = (plugin_name, user_id, key)
        return (k in self.data, self.data.get(k))

    def set_value(self, db, plugin_name, user_id, key, value):
        self.data[(plugin_name, user_id, key)] = value

    def delete_value(self, db, plugin_name, user_id, key):
        return self.data.pop((plugin_name, user_id, key), _MISSING) is not _MISSING

    def list_keys(self, db, plugin_name, user_id):
        return sorted(k for (p, u, k) in self.data if p == plugin_name and u == user_id)


_MISSING = object()
CTX = CapabilityContext(user_id=7, username="alice", role="user")


def _router(monkeypatch, *, scopes, storage=None, audit=None):
    storage = storage or _FakeStorage()
    monkeypatch.setattr("app.plugins.sandbox.capabilities.plugin_storage_service", storage)
    return CapabilityRouter(
        plugin_name="demo",
        granted_scopes=frozenset(scopes),
        session_factory=lambda: object(),  # fake "db"; _FakeStorage ignores it
        audit_logger=audit,
    )


async def test_denied_when_scope_not_granted(monkeypatch):
    audited = []
    audit = type("A", (), {"log_security_event": lambda self, **kw: audited.append(kw)})()
    r = _router(monkeypatch, scopes=set(), audit=audit)
    out = await r.dispatch("storage.get", {"key": "x"}, CTX)
    assert out == {"error": "denied"}
    assert audited and audited[0]["success"] is False
    assert audited[0]["details"]["capability"] == "storage.get"


async def test_unknown_capability(monkeypatch):
    r = _router(monkeypatch, scopes={"storage"})
    out = await r.dispatch("storage.nuke", {}, CTX)
    assert out == {"error": "unknown_capability"}


async def test_storage_set_get_roundtrip_bound_to_context_user(monkeypatch):
    store = _FakeStorage()
    r = _router(monkeypatch, scopes={"storage"}, storage=store)
    assert await r.dispatch("storage.set", {"key": "k", "value": {"n": 1}}, CTX) == {"result": None}
    assert await r.dispatch("storage.get", {"key": "k"}, CTX) == {"result": {"n": 1}}
    # bound to user 7, not whatever the plugin might pass:
    assert ("demo", 7, "k") in store.data


async def test_storage_get_missing_returns_null(monkeypatch):
    r = _router(monkeypatch, scopes={"storage"})
    assert await r.dispatch("storage.get", {"key": "nope"}, CTX) == {"result": None}


async def test_storage_list_and_delete(monkeypatch):
    store = _FakeStorage()
    r = _router(monkeypatch, scopes={"storage"}, storage=store)
    await r.dispatch("storage.set", {"key": "b", "value": 1}, CTX)
    await r.dispatch("storage.set", {"key": "a", "value": 2}, CTX)
    assert await r.dispatch("storage.list", {}, CTX) == {"result": ["a", "b"]}
    assert await r.dispatch("storage.delete", {"key": "a"}, CTX) == {"result": True}
    assert await r.dispatch("storage.delete", {"key": "a"}, CTX) == {"result": False}


async def test_storage_quota_error_is_scrubbed(monkeypatch):
    from app.services.plugin_storage_service import StorageQuotaError

    class _QuotaStorage(_FakeStorage):
        def set_value(self, db, plugin_name, user_id, key, value):
            raise StorageQuotaError("too big")

    r = _router(monkeypatch, scopes={"storage"}, storage=_QuotaStorage())
    assert await r.dispatch("storage.set", {"key": "k", "value": "x"}, CTX) == {"error": "storage_quota"}


async def test_storage_set_rejects_non_string_key(monkeypatch):
    r = _router(monkeypatch, scopes={"storage"})
    assert await r.dispatch("storage.set", {"key": 5, "value": 1}, CTX) == {"error": "invalid_args"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_capabilities.py -v`
Expected: FAIL with `ModuleNotFoundError: app.plugins.sandbox.capabilities`.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/plugins/sandbox/capabilities.py
"""Host-side capability layer for the plugin sandbox (Phase 3).

Every ``cap_call`` from an untrusted worker is dispatched here. The router is
the *enforcement* point: default-deny against the plugin's granted scopes, then
a narrow, validated host handler that runs with host privileges and returns
only a curated result. The acting ``user_id`` is taken from the host-resolved
``CapabilityContext`` (never from plugin args) so a plugin can never address a
foreign user's data.

The router takes its host dependencies (DB session factory, metrics reader,
notifier, audit logger) by injection; Phase 4 wires the production ones.
"""
import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from app.services import plugin_storage_service
from app.services.plugin_storage_service import StorageQuotaError


@dataclass(frozen=True)
class CapabilityContext:
    """Host-resolved identity of the request a cap_call is serving."""

    user_id: int
    username: str
    role: str


class CapabilityError(Exception):
    """Internal: a plugin-caused failure mapped to a cap_result error code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# capability (operation) -> required grantable scope string
CAPABILITY_SCOPE: dict[str, str] = {
    "storage.get": "storage",
    "storage.set": "storage",
    "storage.delete": "storage",
    "storage.list": "storage",
    "core.system_metrics": "core.system_metrics",
    "core.notify": "core.notify",
}


class CapabilityRouter:
    """Default-deny dispatcher for a single sandboxed plugin."""

    def __init__(
        self,
        *,
        plugin_name: str,
        granted_scopes: frozenset[str],
        session_factory: Callable[[], Any],
        metrics_reader: Optional[Callable[[], dict]] = None,
        notifier: Optional[Callable[[CapabilityContext, dict], Awaitable[None]]] = None,
        audit_logger: Any = None,
    ):
        self._plugin_name = plugin_name
        self._granted_scopes = granted_scopes
        self._session_factory = session_factory
        self._metrics_reader = metrics_reader
        self._notifier = notifier
        self._audit_logger = audit_logger

    async def dispatch(self, capability: str, args: dict, context: CapabilityContext) -> dict:
        scope = CAPABILITY_SCOPE.get(capability)
        if scope is None:
            return {"error": "unknown_capability"}
        if scope not in self._granted_scopes:
            self._audit_denied(capability, context)
            return {"error": "denied"}
        try:
            if capability.startswith("storage."):
                return {"result": await self._storage(capability, args, context)}
            if capability == "core.system_metrics":
                return {"result": await self._system_metrics()}
            if capability == "core.notify":
                return {"result": await self._notify(args, context)}
        except CapabilityError as exc:
            return {"error": exc.code}
        return {"error": "unknown_capability"}

    # --- storage.* -------------------------------------------------------

    async def _storage(self, capability: str, args: dict, context: CapabilityContext) -> Any:
        op = capability.split(".", 1)[1]
        key = args.get("key")
        if op in ("get", "set", "delete") and not isinstance(key, str):
            raise CapabilityError("invalid_args")

        def run() -> Any:
            db = self._session_factory()
            try:
                if op == "get":
                    found, value = plugin_storage_service.get_value(
                        db, self._plugin_name, context.user_id, key
                    )
                    return value if found else None
                if op == "set":
                    plugin_storage_service.set_value(
                        db, self._plugin_name, context.user_id, key, args.get("value")
                    )
                    return None
                if op == "delete":
                    return plugin_storage_service.delete_value(
                        db, self._plugin_name, context.user_id, key
                    )
                if op == "list":
                    return plugin_storage_service.list_keys(
                        db, self._plugin_name, context.user_id
                    )
                raise CapabilityError("unknown_capability")
            finally:
                close = getattr(db, "close", None)
                if callable(close):
                    close()

        try:
            return await asyncio.to_thread(run)
        except StorageQuotaError:
            raise CapabilityError("storage_quota")

    # --- core.* (filled in Task 2) --------------------------------------

    async def _system_metrics(self) -> dict:
        raise CapabilityError("unknown_capability")

    async def _notify(self, args: dict, context: CapabilityContext) -> None:
        raise CapabilityError("unknown_capability")

    # --- audit ----------------------------------------------------------

    def _audit_denied(self, capability: str, context: CapabilityContext) -> None:
        logger = self._audit_logger
        if logger is None:
            return
        try:
            logger.log_security_event(
                action="plugin_capability_denied",
                user=context.username,
                resource=f"plugin:{self._plugin_name}",
                details={"capability": capability, "scope": CAPABILITY_SCOPE.get(capability)},
                success=False,
            )
        except Exception:
            pass  # auditing must never break dispatch
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_capabilities.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Lint**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m ruff check app/plugins/sandbox/capabilities.py tests/plugins/sandbox/test_capabilities.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/sandbox/capabilities.py backend/tests/plugins/sandbox/test_capabilities.py
git commit -F <message-file>
# Subject: feat(plugin-sandbox): CapabilityRouter default-deny + storage.* (Track B Phase 3)
```

---

## Task 2: `CapabilityRouter` — `core.system_metrics` + `core.notify`

**Files:**
- Modify: `backend/app/plugins/sandbox/capabilities.py`
- Test: `backend/tests/plugins/sandbox/test_capabilities.py`

**Interfaces:**
- Consumes (Task 1): `CapabilityRouter`, `CapabilityContext`, `CapabilityError`.
- Produces: working `core.system_metrics` (returns the injected `metrics_reader()` output, off-thread) and `core.notify` (validates `title`/`message`/`type`, then awaits the injected `notifier(context, {"title","message","type"})`). Missing injected dependency → `{"error": "unavailable"}`. Notify field caps: `title` ≤ 200 chars, `message` ≤ 2000 chars, `type ∈ {"info","warning"}` (default `"info"`).

- [ ] **Step 1: Write the failing tests** (append to `test_capabilities.py`)

```python
async def test_system_metrics_returns_reader_snapshot(monkeypatch):
    r = _router(monkeypatch, scopes={"core.system_metrics"})
    r._metrics_reader = lambda: {"cpu_usage": 12.5, "memory": {"used": 1, "total": 4, "percent": 25.0}}
    out = await r.dispatch("core.system_metrics", {}, CTX)
    assert out == {"result": {"cpu_usage": 12.5, "memory": {"used": 1, "total": 4, "percent": 25.0}}}


async def test_system_metrics_unavailable_without_reader(monkeypatch):
    r = _router(monkeypatch, scopes={"core.system_metrics"})  # no metrics_reader injected
    assert await r.dispatch("core.system_metrics", {}, CTX) == {"error": "unavailable"}


async def test_notify_calls_notifier_with_context_user(monkeypatch):
    sent = []
    async def notifier(ctx, payload):
        sent.append((ctx, payload))
    r = _router(monkeypatch, scopes={"core.notify"})
    r._notifier = notifier
    out = await r.dispatch("core.notify", {"title": "Hi", "message": "Body", "type": "warning"}, CTX)
    assert out == {"result": None}
    ctx, payload = sent[0]
    assert ctx.user_id == 7  # host context, not plugin-supplied
    assert payload == {"title": "Hi", "message": "Body", "type": "warning"}


async def test_notify_defaults_type_info_and_rejects_bad_type(monkeypatch):
    sent = []
    async def notifier(ctx, payload):
        sent.append(payload)
    r = _router(monkeypatch, scopes={"core.notify"})
    r._notifier = notifier
    await r.dispatch("core.notify", {"title": "T", "message": "M"}, CTX)
    assert sent[0]["type"] == "info"
    assert await r.dispatch("core.notify", {"title": "T", "message": "M", "type": "critical"}, CTX) == {"error": "invalid_args"}


async def test_notify_rejects_missing_or_oversized_fields(monkeypatch):
    r = _router(monkeypatch, scopes={"core.notify"})
    r._notifier = lambda ctx, payload: None  # not awaited; rejected before call
    assert await r.dispatch("core.notify", {"message": "M"}, CTX) == {"error": "invalid_args"}
    assert await r.dispatch("core.notify", {"title": "x" * 201, "message": "M"}, CTX) == {"error": "invalid_args"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_capabilities.py -k "system_metrics or notify" -v`
Expected: FAIL (`_system_metrics`/`_notify` currently raise `unknown_capability` → assertions mismatch).

- [ ] **Step 3: Replace the two stub handlers in `capabilities.py`**

```python
    async def _system_metrics(self) -> dict:
        if self._metrics_reader is None:
            raise CapabilityError("unavailable")
        return await asyncio.to_thread(self._metrics_reader)

    async def _notify(self, args: dict, context: CapabilityContext) -> None:
        if self._notifier is None:
            raise CapabilityError("unavailable")
        title = args.get("title")
        message = args.get("message")
        ntype = args.get("type", "info")
        if (
            not isinstance(title, str)
            or not isinstance(message, str)
            or not (1 <= len(title) <= 200)
            or not (1 <= len(message) <= 2000)
            or ntype not in ("info", "warning")
        ):
            raise CapabilityError("invalid_args")
        await self._notifier(context, {"title": title, "message": message, "type": ntype})
```

Note: `core.notify` validates BEFORE the grant has already been checked in `dispatch`; an `unavailable` (no notifier wired) is distinct from `denied` (scope absent).

- [ ] **Step 4: Run to verify pass**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_capabilities.py -v`
Expected: PASS (all, ~13 tests).

- [ ] **Step 5: Lint**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m ruff check app/plugins/sandbox/capabilities.py tests/plugins/sandbox/test_capabilities.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/sandbox/capabilities.py backend/tests/plugins/sandbox/test_capabilities.py
git commit -F <message-file>
# Subject: feat(plugin-sandbox): core.system_metrics + core.notify capabilities (Track B Phase 3)
```

---

## Task 3: Supervisor host-side cap dispatch (request_id ↔ context)

**Files:**
- Modify: `backend/app/plugins/sandbox/supervisor.py`
- Test: `backend/tests/plugins/sandbox/test_supervisor.py`

**Interfaces:**
- Consumes: `CapabilityRouter`, `CapabilityContext` (Task 1); `RpcChannel(reader, writer, *, request_handler=...)` (Phase 1); `MsgType.{CAP_CALL,CAP_RESULT,ERROR,HTTP_REQUEST}`.
- Produces:
  - `SandboxSupervisor.__init__` gains `capability_router: CapabilityRouter | None = None`.
  - `dispatch(method, path, body, context)` now mints a host-owned `request_id`, records `self._inflight[request_id] = context`, includes `"request_id"` in the `http_request` body, and pops it in `finally`.
  - The supervisor's host-side `RpcChannel` is created **with a `request_handler`** that, on `CAP_CALL`, reads `body["request_id"]` → looks up `self._inflight` → `await router.dispatch(body["capability"], body.get("args") or {}, context)` → replies `CAP_RESULT`. Unknown `request_id` or no router → `CAP_RESULT {"error": "no_context"}` / `{"error": "unavailable"}`.

**Context for the implementer:** `_spawn_and_connect` currently builds `RpcChannel(reader, writer)` with no handler (Phase 2b, ~line 140). The `context` arg to `dispatch` is the dict `{"user_id","username","role"}` the host already passes. Convert it to `CapabilityContext` when storing. Use a monotonic `itertools.count` for `request_id` (not the RPC message id — keep correlation independent of `RpcChannel`'s internal ids). Guard `_inflight` access — it's read from the read-loop's dispatch task and written from `dispatch()`, both on the same event loop (no lock needed), but a `cap_call` referencing a popped/unknown id must return an error, not raise.

- [ ] **Step 1: Write the failing test** (append to `test_supervisor.py`)

This test drives the real supervisor against a **scripted worker** that, on its first `http_request`, fires a `cap_call` back and returns the capability result in its `http_response`. Reuse the existing real-subprocess test harness in this file — but here we need a custom worker, so spawn a tiny inline worker script via the supervisor's `spawn_hook`. Study the existing `_spawn` / `spawn_hook` injection and the `connect_to_host` address handling already used by passing tests in this file before writing.

```python
async def test_cap_call_roundtrips_with_host_resolved_context(tmp_path):
    """Worker issues a storage.set+get cap_call while serving a request;
    the host resolves user_id from its in-flight map, not from the worker."""
    from app.plugins.sandbox.capabilities import CapabilityContext, CapabilityRouter

    # A fake storage the router writes through; assert the bound user_id later.
    writes: dict = {}

    class _Store:
        def set_value(self, db, plugin_name, user_id, key, value):
            writes[(plugin_name, user_id, key)] = value
        def get_value(self, db, plugin_name, user_id, key):
            k = (plugin_name, user_id, key)
            return (k in writes, writes.get(k))
        def list_keys(self, db, plugin_name, user_id):
            return []
        def delete_value(self, db, plugin_name, user_id, key):
            return False

    import app.plugins.sandbox.capabilities as caps
    caps_orig = caps.plugin_storage_service
    caps.plugin_storage_service = _Store()
    try:
        router = CapabilityRouter(
            plugin_name="demo",
            granted_scopes=frozenset({"storage"}),
            session_factory=lambda: object(),
        )
        # ... spawn a scripted worker (see worker script below) via the supervisor,
        #     dispatch an http_request with context user_id=42, and assert the
        #     response carries the value the worker read back through storage,
        #     AND writes[("demo", 42, "k")] == "v"  (host-bound user, not worker-chosen).
        supervisor = _make_supervisor_with_scripted_worker(tmp_path, router)
        await supervisor.start()
        try:
            resp = await supervisor.dispatch(
                "GET", "/ping", b"", {"user_id": 42, "username": "bob", "role": "user"}
            )
            assert resp["status"] == 200
            assert resp["body"]["stored"] == "v"
            assert writes[("demo", 42, "k")] == "v"
        finally:
            await supervisor.stop()
    finally:
        caps.plugin_storage_service = caps_orig
```

Implement `_make_supervisor_with_scripted_worker` as a test helper that writes a small worker script to `tmp_path` and injects a `spawn_hook` running `python <script> --connect <addr>`. The script (a string in the test) connects with `RpcChannel`, and its request handler — on `http_request` — does:
```
await channel.call(CAP_CALL, {"capability": "storage.set", "request_id": body["request_id"], "args": {"key": "k", "value": "v"}})
got = await channel.call(CAP_CALL, {"capability": "storage.get", "request_id": body["request_id"], "args": {"key": "k"}})
return HTTP_RESPONSE {status:200, headers:{}, body:{"stored": got.body["result"]}}
```
plus the standard `lifecycle: health → lifecycle_result{status:ok}`. (Model the script on `worker.py`'s `build_worker_handler`.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_supervisor.py -k cap_call -v --timeout=60`
Expected: FAIL — supervisor has no `request_handler`, so the worker's `cap_call` never resolves → handshake/dispatch hangs until timeout (or `capability_router` arg rejected).

- [ ] **Step 3: Implement the supervisor changes**

In `supervisor.py`:
1. Add imports: `import itertools`, `from app.plugins.sandbox.capabilities import CapabilityContext, CapabilityRouter`.
2. `__init__`: add `capability_router: CapabilityRouter | None = None`; store it. Init `self._inflight: dict[int, CapabilityContext] = {}` and `self._request_ids = itertools.count(1)`.
3. Add the host request handler:
```python
    async def _handle_worker_request(self, msg: Message) -> Message:
        if msg.type == MsgType.CAP_CALL:
            return await self._handle_cap_call(msg)
        return Message(id=msg.id, type=MsgType.ERROR, body={"error": "unsupported"})

    async def _handle_cap_call(self, msg: Message) -> Message:
        if self._capability_router is None:
            return Message(id=msg.id, type=MsgType.CAP_RESULT, body={"error": "unavailable"})
        request_id = msg.body.get("request_id")
        context = self._inflight.get(request_id) if isinstance(request_id, int) else None
        if context is None:
            return Message(id=msg.id, type=MsgType.CAP_RESULT, body={"error": "no_context"})
        result = await self._capability_router.dispatch(
            msg.body.get("capability", ""), msg.body.get("args") or {}, context
        )
        return Message(id=msg.id, type=MsgType.CAP_RESULT, body=result)
```
4. In `_spawn_and_connect`, build the channel WITH the handler:
   `self._channel = RpcChannel(reader, writer, request_handler=self._handle_worker_request)`
5. In `dispatch(...)`, mint and track the request_id:
```python
    async def dispatch(self, method, path, body, context):
        # ... existing running/disabled guards ...
        request_id = next(self._request_ids)
        self._inflight[request_id] = CapabilityContext(
            user_id=context["user_id"], username=context["username"], role=context["role"]
        )
        try:
            resp = await self._channel.call(
                MsgType.HTTP_REQUEST,
                {
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "body": body,
                    "context": context,
                },
                timeout=...,  # keep existing timeout handling
            )
        finally:
            self._inflight.pop(request_id, None)
        return resp.body
```
(Preserve whatever the existing `dispatch` already does for timeouts / error wrapping — only ADD the request_id minting, the body field, and the `_inflight` bookkeeping.)

- [ ] **Step 4: Run to verify pass + no regression**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_supervisor.py -v --timeout=60`
Expected: PASS (all prior supervisor tests + the new cap_call test). Confirm no leaked worker subprocesses.

- [ ] **Step 5: Lint**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m ruff check app/plugins/sandbox/supervisor.py tests/plugins/sandbox/test_supervisor.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/sandbox/supervisor.py backend/tests/plugins/sandbox/test_supervisor.py
git commit -F <message-file>
# Subject: feat(plugin-sandbox): supervisor routes cap_call to CapabilityRouter via in-flight context (Track B Phase 3)
```

---

## Task 4: Worker Plugin-SDK + plugin loader + authoring contract

**Files:**
- Create: `backend/app/plugins/sandbox/sdk.py`
- Create: `backend/app/plugins/sandbox/loader.py`
- Modify: `backend/app/plugins/sandbox/worker.py`
- Test: `backend/tests/plugins/sandbox/test_sdk.py`

**Interfaces:**
- Consumes: `RpcChannel.call(type, body, *, timeout=None)`; `MsgType.{CAP_CALL,HTTP_RESPONSE,ERROR}`.
- Produces (the **external-plugin authoring contract**):
  - `sdk.py`:
    - `class PluginHost`: `__init__(self)`; `route(self, method: str, path: str) -> Callable` (decorator registering `async handler(request) -> dict|Response`); `storage` (a `_Storage` facade with async `get(key)/set(key,value)/delete(key)/list()`); `scopes` (a `_Scopes` facade with async `system_metrics()` and `notify(title, message, type="info")`); `routes` (read-only mapping `(METHOD, path) → handler`); `bind_channel(channel)`; `set_request_id(request_id)` / a contextvar the facades read; `async handle_request(body: dict) -> dict` (look up route, build `request`, run handler under the request_id contextvar, normalize the return into `{status, headers, body}`).
    - The plugin entrypoint module MUST define `def register(host: PluginHost) -> None` and register its routes there. (Route registration must NOT perform capability calls — the channel isn't connected yet.)
    - `Request` passed to handlers: a simple object/dict `{method, path, query, headers, body, user}` where `user = {"user_id","username","role"}` from the host context.
  - `loader.py`: `def load_plugin(plugin_dir: str, entrypoint: str, plugin_name: str) -> PluginHost` — builds a `PluginHost`, `exec_module`s `<plugin_dir>/<entrypoint>` under a unique module name (`baluhost_sandbox_plugin_<plugin_name>`), calls `module.register(host)`, returns the host. Raises `PluginLoadError` if the entrypoint is missing or has no `register`.
  - `worker.py`: argv adds `--plugin-dir`, `--plugin-name`, `--entrypoint` (default `__init__.py`). `run_worker` loads the plugin BEFORE connecting; on load failure exits non-zero (supervisor sees an unhealthy/crashed worker). The `http_request` handler calls `host.handle_request(body)` and wraps it as `HTTP_RESPONSE`. Health/shutdown lifecycle stays as in Phase 2b.

**Context for the implementer:** capability calls are reentrant — the worker's request handler runs in its own task (Phase 1 reentrancy), so `await self._channel.call(CAP_CALL, ...)` from inside a route handler works while the host awaits the `http_response`. Use a `contextvars.ContextVar[int]` for the current `request_id` so `host.storage`/`host.scopes` stamp the right id without threading it through the plugin's handler signature. A `cap_result` body is `{"result": ...}` or `{"error": code}`; the SDK raises a `CapabilityDenied`/`PluginCapabilityError` on `error` so plugin code sees a normal exception.

- [ ] **Step 1: Write the failing tests** (`test_sdk.py`)

```python
# backend/tests/plugins/sandbox/test_sdk.py
import pytest

from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.sdk import PluginHost, PluginCapabilityError


class _FakeChannel:
    """Captures cap_calls and returns scripted cap_results."""

    def __init__(self, responses):
        self._responses = responses  # list of body dicts
        self.calls = []

    async def call(self, mtype, body, *, timeout=None):
        assert mtype == MsgType.CAP_CALL
        self.calls.append(body)
        return Message(id=0, type=MsgType.CAP_RESULT, body=self._responses.pop(0))


async def test_route_registration_and_dispatch():
    host = PluginHost()

    @host.route("GET", "/hello")
    async def hello(request):
        return {"status": 200, "body": {"who": request["user"]["username"]}}

    host.bind_channel(_FakeChannel([]))
    out = await host.handle_request(
        {"request_id": 1, "method": "GET", "path": "/hello", "body": b"",
         "context": {"user_id": 3, "username": "kim", "role": "user"}}
    )
    assert out["status"] == 200
    assert out["body"] == {"who": "kim"}


async def test_unknown_route_returns_404():
    host = PluginHost()
    host.bind_channel(_FakeChannel([]))
    out = await host.handle_request(
        {"request_id": 1, "method": "GET", "path": "/nope", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    assert out["status"] == 404


async def test_storage_facade_stamps_request_id_and_returns_result():
    host = PluginHost()
    ch = _FakeChannel([{"result": {"v": 1}}])

    @host.route("GET", "/r")
    async def r(request):
        value = await host.storage.get("k")
        return {"status": 200, "body": value}

    host.bind_channel(ch)
    out = await host.handle_request(
        {"request_id": 99, "method": "GET", "path": "/r", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    assert out["body"] == {"v": 1}
    assert ch.calls[0] == {"capability": "storage.get", "request_id": 99, "args": {"key": "k"}}


async def test_scopes_notify_and_metrics_capabilities():
    host = PluginHost()
    ch = _FakeChannel([{"result": {"cpu_usage": 5.0}}, {"result": None}])

    @host.route("POST", "/do")
    async def do(request):
        m = await host.scopes.system_metrics()
        await host.scopes.notify("T", "M", type="warning")
        return {"status": 200, "body": m}

    host.bind_channel(ch)
    out = await host.handle_request(
        {"request_id": 7, "method": "POST", "path": "/do", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    assert out["body"] == {"cpu_usage": 5.0}
    assert ch.calls[0]["capability"] == "core.system_metrics"
    assert ch.calls[1] == {"capability": "core.notify", "request_id": 7, "args": {"title": "T", "message": "M", "type": "warning"}}


async def test_denied_capability_raises_in_plugin_code():
    host = PluginHost()
    ch = _FakeChannel([{"error": "denied"}])

    @host.route("GET", "/x")
    async def x(request):
        await host.storage.get("k")  # should raise
        return {"status": 200}

    host.bind_channel(ch)
    out = await host.handle_request(
        {"request_id": 1, "method": "GET", "path": "/x", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    # an unhandled PluginCapabilityError inside the handler becomes a 500
    assert out["status"] == 500


def test_loader_loads_register_and_routes(tmp_path):
    from app.plugins.sandbox.loader import load_plugin

    plugin = tmp_path / "p"
    plugin.mkdir()
    (plugin / "__init__.py").write_text(
        "def register(host):\n"
        "    @host.route('GET', '/hi')\n"
        "    async def hi(request):\n"
        "        return {'status': 200, 'body': {'ok': True}}\n",
        encoding="utf-8",
    )
    host = load_plugin(str(plugin), "__init__.py", "p")
    assert ("GET", "/hi") in host.routes


def test_loader_missing_register_raises(tmp_path):
    from app.plugins.sandbox.loader import load_plugin, PluginLoadError

    plugin = tmp_path / "p"
    plugin.mkdir()
    (plugin / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(PluginLoadError):
        load_plugin(str(plugin), "__init__.py", "p")
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_sdk.py -v`
Expected: FAIL (`app.plugins.sandbox.sdk` / `loader` missing).

- [ ] **Step 3: Implement `sdk.py`**

```python
# backend/app/plugins/sandbox/sdk.py
"""Plugin-facing SDK that runs INSIDE the sandbox worker.

A plugin's entrypoint defines ``def register(host: PluginHost)`` and declares
routes with ``@host.route(method, path)``. Inside a route handler the plugin
uses ``host.storage`` and ``host.scopes`` — each call is forwarded to the host
over RPC as a ``cap_call`` and gated there (default-deny). The plugin writes no
raw msgpack and never sees a token.
"""
import contextvars
from typing import Any, Awaitable, Callable

from app.plugins.sandbox.protocol import Message, MsgType

_current_request_id: contextvars.ContextVar[int] = contextvars.ContextVar("plugin_request_id")

RouteHandler = Callable[[dict], Awaitable[Any]]


class PluginCapabilityError(Exception):
    """Raised in plugin code when a capability call is denied or errors."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _Caps:
    def __init__(self, host: "PluginHost"):
        self._host = host

    async def _call(self, capability: str, args: dict) -> Any:
        body = {
            "capability": capability,
            "request_id": _current_request_id.get(),
            "args": args,
        }
        resp = await self._host._channel.call(MsgType.CAP_CALL, body)
        if "error" in resp.body:
            raise PluginCapabilityError(resp.body["error"])
        return resp.body.get("result")


class _Storage(_Caps):
    async def get(self, key: str) -> Any:
        return await self._call("storage.get", {"key": key})

    async def set(self, key: str, value: Any) -> None:
        await self._call("storage.set", {"key": key, "value": value})

    async def delete(self, key: str) -> bool:
        return await self._call("storage.delete", {"key": key})

    async def list(self) -> list:
        return await self._call("storage.list", {})


class _Scopes(_Caps):
    async def system_metrics(self) -> dict:
        return await self._call("core.system_metrics", {})

    async def notify(self, title: str, message: str, type: str = "info") -> None:
        await self._call("core.notify", {"title": title, "message": message, "type": type})


class PluginHost:
    def __init__(self):
        self._routes: dict[tuple[str, str], RouteHandler] = {}
        self._channel = None
        self.storage = _Storage(self)
        self.scopes = _Scopes(self)

    @property
    def routes(self) -> dict[tuple[str, str], RouteHandler]:
        return dict(self._routes)

    def route(self, method: str, path: str) -> Callable[[RouteHandler], RouteHandler]:
        key = (method.upper(), path)

        def decorator(fn: RouteHandler) -> RouteHandler:
            self._routes[key] = fn
            return fn

        return decorator

    def bind_channel(self, channel) -> None:
        self._channel = channel

    async def handle_request(self, body: dict) -> dict:
        handler = self._routes.get((str(body.get("method", "")).upper(), body.get("path", "")))
        if handler is None:
            return {"status": 404, "headers": {}, "body": {"error": "not_found"}}
        request = {
            "method": body.get("method"),
            "path": body.get("path"),
            "query": body.get("query") or {},
            "headers": body.get("headers") or {},
            "body": body.get("body"),
            "user": body.get("context") or {},
        }
        token = _current_request_id.set(body.get("request_id"))
        try:
            result = await handler(request)
        except PluginCapabilityError:
            return {"status": 500, "headers": {}, "body": {"error": "capability_error"}}
        except Exception:
            return {"status": 500, "headers": {}, "body": {"error": "plugin_error"}}
        finally:
            _current_request_id.reset(token)
        return _normalize_response(result)


def _normalize_response(result: Any) -> dict:
    if not isinstance(result, dict):
        return {"status": 200, "headers": {}, "body": result}
    return {
        "status": int(result.get("status", 200)),
        "headers": result.get("headers") or {},
        "body": result.get("body"),
    }
```

- [ ] **Step 4: Implement `loader.py`**

```python
# backend/app/plugins/sandbox/loader.py
"""Load an external plugin's entrypoint INSIDE the worker process.

exec_module happens here and nowhere else — never in the host. The loaded
module must expose ``register(host)``.
"""
import importlib.util
import os

from app.plugins.sandbox.sdk import PluginHost


class PluginLoadError(Exception):
    """Raised when the plugin entrypoint is missing or has no register()."""


def load_plugin(plugin_dir: str, entrypoint: str, plugin_name: str) -> PluginHost:
    path = os.path.join(plugin_dir, entrypoint)
    if not os.path.isfile(path):
        raise PluginLoadError(f"entrypoint not found: {path}")
    module_name = f"baluhost_sandbox_plugin_{plugin_name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"cannot load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # plugin module-level code blew up
        raise PluginLoadError(f"plugin import failed: {exc}") from exc
    register = getattr(module, "register", None)
    if not callable(register):
        raise PluginLoadError("plugin entrypoint defines no register(host)")
    host = PluginHost()
    register(host)
    return host
```

- [ ] **Step 5: Run SDK/loader tests to verify pass**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_sdk.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Wire the worker to the loader + SDK** (`worker.py`)

Replace `build_worker_handler` usage with a handler that delegates `http_request` to a loaded `PluginHost`, and extend argv/boot:

```python
def build_worker_handler(host) -> RequestHandler:
    async def handler(msg: Message) -> Message:
        if msg.type == MsgType.LIFECYCLE:
            action = msg.body.get("action")
            status = {"health": "ok", "shutdown": "stopping"}.get(action, "unknown_action")
            return Message(id=msg.id, type=MsgType.LIFECYCLE_RESULT, body={"status": status})
        if msg.type == MsgType.HTTP_REQUEST:
            resp = await host.handle_request(msg.body)
            return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body=resp)
        return Message(id=msg.id, type=MsgType.ERROR, body={"error": "unsupported"})
    return handler


async def run_worker(address: str, host) -> None:
    reader, writer = await connect_to_host(address)
    channel = RpcChannel(reader, writer, request_handler=build_worker_handler(host))
    host.bind_channel(channel)
    channel.start()
    try:
        await channel.wait_closed()
    finally:
        await channel.close()


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="plugin-sandbox-worker")
    parser.add_argument("--connect", required=True, help="host callback: 'unix:<path>' or 'tcp:<host>:<port>'")
    parser.add_argument("--plugin-dir", required=True)
    parser.add_argument("--plugin-name", required=True)
    parser.add_argument("--entrypoint", default="__init__.py")
    args = parser.parse_args(argv)
    from app.plugins.sandbox.loader import load_plugin
    host = load_plugin(args.plugin_dir, args.entrypoint, args.plugin_name)  # raises -> non-zero exit
    asyncio.run(run_worker(args.connect, host))
```

Note: loading happens BEFORE `connect_to_host`, so a bad plugin exits non-zero and the supervisor sees a failed spawn/handshake (Phase 2b auto-disable). The existing Phase-2b supervisor tests pass `--connect` only; **Task 3's supervisor already builds argv** — update the supervisor's `_spawn_and_connect` argv (in Task 3 or here) to pass `--plugin-dir/--plugin-name/--entrypoint` from `self._plugin_dir`/`self.plugin_name`. If Phase-2b supervisor tests used a worker that doesn't accept these args, they inject their own `spawn_hook` and are unaffected; only the default argv changes.

- [ ] **Step 7: Run the full sandbox suite**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/ -q --timeout=60`
Expected: PASS (all). Confirm no leaked subprocesses. If a Phase-2b default-argv test breaks because the worker now requires `--plugin-dir`, update that test to pass a trivial fixture plugin dir (or confirm it injects its own spawn_hook).

- [ ] **Step 8: Lint**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m ruff check app/plugins/sandbox/sdk.py app/plugins/sandbox/loader.py app/plugins/sandbox/worker.py tests/plugins/sandbox/test_sdk.py`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add backend/app/plugins/sandbox/sdk.py backend/app/plugins/sandbox/loader.py backend/app/plugins/sandbox/worker.py backend/tests/plugins/sandbox/test_sdk.py
git commit -F <message-file>
# Subject: feat(plugin-sandbox): worker Plugin-SDK + loader + register(host) authoring contract (Track B Phase 3)
```

---

## Task 5: End-to-end — fixture plugin through the full path

**Files:**
- Create: `backend/tests/plugins/sandbox/fixtures/sample_plugin/__init__.py`
- Create: `backend/tests/plugins/sandbox/test_phase3_e2e.py`

**Interfaces:**
- Consumes: everything above — real `SandboxSupervisor` (Task 3) spawning the real `worker.py` (Task 4) as a subprocess, with a real `CapabilityRouter` (Tasks 1–2) wired with test-injected deps (in-memory storage, a stub metrics reader, a capturing notifier).

**Context for the implementer:** This is the isolation/contract proof. The fixture plugin uses ONLY the SDK. The router is wired with a fake storage (assert user-binding), a metrics reader returning a fixed dict, and a notifier appending to a list. Spawn via the supervisor's default argv (real `worker.py`), pointing `--plugin-dir` at the fixture dir. Run a granted-scope path and a denied-scope path.

- [ ] **Step 1: Write the fixture plugin**

```python
# backend/tests/plugins/sandbox/fixtures/sample_plugin/__init__.py
def register(host):
    @host.route("POST", "/save")
    async def save(request):
        await host.storage.set("note", request["body"])
        return {"status": 200, "body": {"saved": True}}

    @host.route("GET", "/load")
    async def load(request):
        return {"status": 200, "body": {"note": await host.storage.get("note")}}

    @host.route("GET", "/metrics")
    async def metrics(request):
        return {"status": 200, "body": await host.scopes.system_metrics()}

    @host.route("GET", "/forbidden")
    async def forbidden(request):
        # 'core.notify' scope is NOT granted in the denied-path test
        await host.scopes.notify("t", "m")
        return {"status": 200}
```

- [ ] **Step 2: Write the failing e2e test**

```python
# backend/tests/plugins/sandbox/test_phase3_e2e.py
import os

from app.plugins.sandbox.capabilities import CapabilityRouter
import app.plugins.sandbox.capabilities as caps

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_plugin")
CTX = {"user_id": 11, "username": "ann", "role": "user"}


class _MemStore:
    def __init__(self): self.d = {}
    def set_value(self, db, p, u, k, v): self.d[(p, u, k)] = v
    def get_value(self, db, p, u, k):
        key = (p, u, k); return (key in self.d, self.d.get(key))
    def list_keys(self, db, p, u): return sorted(k for (pp, uu, k) in self.d if pp == p and uu == u)
    def delete_value(self, db, p, u, k): return self.d.pop((p, u, k), None) is not None


async def test_e2e_storage_and_metrics_granted(tmp_path):
    store = _MemStore()
    orig = caps.plugin_storage_service
    caps.plugin_storage_service = store
    notifications = []
    try:
        router = CapabilityRouter(
            plugin_name="sample",
            granted_scopes=frozenset({"storage", "core.system_metrics"}),
            session_factory=lambda: object(),
            metrics_reader=lambda: {"cpu_usage": 9.0, "memory": {"used": 1, "total": 2, "percent": 50.0}},
            notifier=lambda ctx, payload: notifications.append(payload),
        )
        sup = _make_supervisor(tmp_path, router, plugin_dir=FIXTURE, plugin_name="sample")
        await sup.start()
        try:
            assert (await sup.dispatch("POST", "/save", "hello", CTX))["body"] == {"saved": True}
            assert (await sup.dispatch("GET", "/load", b"", CTX))["body"] == {"note": "hello"}
            assert store.d[("sample", 11, "note")] == "hello"  # bound to host user
            assert (await sup.dispatch("GET", "/metrics", b"", CTX))["body"]["cpu_usage"] == 9.0
        finally:
            await sup.stop()
    finally:
        caps.plugin_storage_service = orig


async def test_e2e_denied_scope_returns_500_and_does_not_notify(tmp_path):
    notifications = []
    router = CapabilityRouter(
        plugin_name="sample",
        granted_scopes=frozenset({"storage"}),  # core.notify NOT granted
        session_factory=lambda: object(),
        notifier=lambda ctx, payload: notifications.append(payload),
    )
    sup = _make_supervisor(tmp_path, router, plugin_dir=FIXTURE, plugin_name="sample")
    await sup.start()
    try:
        resp = await sup.dispatch("GET", "/forbidden", b"", CTX)
        assert resp["status"] == 500  # PluginCapabilityError(denied) -> 500
        assert notifications == []
    finally:
        await sup.stop()
```

Implement `_make_supervisor(tmp_path, router, *, plugin_dir, plugin_name)` to construct a real `SandboxSupervisor` with `capability_router=router` and the default spawn (real `worker.py`) — reuse the construction the passing Phase-2b tests use, adding the `capability_router` and the plugin-dir argv.

- [ ] **Step 3: Run to verify it fails, then passes once wiring is correct**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/test_phase3_e2e.py -v --timeout=90`
Expected: PASS after the supervisor default argv passes `--plugin-dir/--plugin-name/--entrypoint` (Task 4 Step 6). If FAIL, inspect whether the worker subprocess loaded the fixture (stderr surfaces via the supervisor logs).

- [ ] **Step 4: Full sandbox suite + leak check**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m pytest tests/plugins/sandbox/ -q --timeout=90`
Expected: PASS (all phases). No leaked `python` worker processes (check Task Manager / `Get-Process python`).

- [ ] **Step 5: Lint**

Run: `cd "D:/Programme (x86)/Baluhost/backend" ; python -m ruff check tests/plugins/sandbox/test_phase3_e2e.py tests/plugins/sandbox/fixtures/sample_plugin/__init__.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/plugins/sandbox/test_phase3_e2e.py backend/tests/plugins/sandbox/fixtures/
git commit -F <message-file>
# Subject: test(plugin-sandbox): Phase 3 e2e — fixture plugin through proxy→RPC→capability path (Track B Phase 3)
```

---

## Out of Scope (Phase 4 / 5)

- FastAPI catch-all `PluginProxyRouter` + `PluginManager` dual-path (bundled in-process vs external → supervisor) and the production wiring of the router's `session_factory` (app `SessionLocal`), `metrics_reader` (`telemetry.get_latest_cpu_usage` + `get_latest_memory_sample`), and `notifier` (`NotificationService.create` with `category=SYSTEM`) — **Phase 4**.
- Per-request timeout → 504, body-size caps, max in-flight per plugin, error-scrubbing at the FastAPI boundary — **Phase 4** (the supervisor already has a per-call timeout; HTTP semantics land with the proxy).
- OS hardening (low-priv user, netns), worker import-isolation enforcement — **Phase 5**. (Dev does not block `import app.*` in the worker; prod's low-priv user + no-read enforces it.)
- Frontend `PluginDocumentation.tsx` + `plugins` locale rewrite (two trust tiers, scope model) — **Phase 5**.
- Growing the `core.*` catalog beyond `system_metrics` + `notify` — each new scope is a host-code change + review.

## Self-Review Notes

- **Spec coverage:** default-deny dispatch ✅ (Task 1), `storage.*` user-bound reuse of `plugin_storage_service` ✅ (Task 1), `core.*` starter catalog = `system_metrics` + `notify` ✅ (Task 2), reentrant `cap_call` during open `http_request` ✅ (Tasks 3–4 + e2e), real `exec_module` only in worker ✅ (Task 4 loader), SDK wraps RPC into `host.storage`/`host.scopes`/routes ✅ (Task 4), isolation smoke (denied scope) ✅ (Task 5).
- **User-binding** is asserted three ways: router unit test (context user, not args), supervisor integration (host-resolved from in-flight map), e2e (`store.d[("sample", 11, "note")]`).
- **Type consistency:** `CapabilityContext`, `CAPABILITY_SCOPE`, the `{"result"|"error"}` cap_result shape, and the `register(host)` + `@host.route` contract are used identically across host (Task 3) and worker (Task 4).
