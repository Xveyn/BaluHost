# Plugin Backend Isolation — Phase 5a: Hardened Worker Spawn — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `_default_spawn` stub for external plugin workers with a production spawn hook that runs each worker as an unprivileged `baluhost-plugin` user, in a network namespace, under resource limits, with a scrubbed environment — and fail closed in production when the box is not yet provisioned.

**Architecture:** A new `backend/app/plugins/sandbox/spawn.py` provides `scrub_env()`, `hardened_spawn()`, and `select_spawn_hook()`. `select_spawn_hook()` returns `_default_spawn` for dev/non-Linux, `hardened_spawn` for a provisioned prod-Linux box, and `None` (→ fail closed) for prod-Linux that is not provisioned. `PluginManager._supervisor_factory` consults it and raises `SandboxHardeningUnavailable` on `None`; `_enable_external` catches that, audits, and returns `False`. `hardened_spawn` invokes a root-owned wrapper (`spawn-plugin-worker.sh`) via a narrowly-scoped sudoers entry; the wrapper validates its arguments and runs `prlimit … -- unshare --net -- setpriv --reuid baluhost-plugin … -- <venv python> -m app.plugins.sandbox.worker …`.

**Tech Stack:** Python 3.11, asyncio subprocess, FastAPI/SQLAlchemy (audit), pydantic-settings; Bash + util-linux (`prlimit`, `unshare`, `setpriv`, `realpath`); pytest.

## Global Constraints

- **Bundled (first-party) plugins are untouched** — only the external/sandboxed spawn path changes.
- **Dev (Windows / non-prod Linux) keeps `_default_spawn` byte-for-byte** — no sudo, no wrapper.
- **Fail closed in production:** prod + Linux + not provisioned → external plugins do NOT spawn (audit + `False`), never run unhardened.
- **Env-scrubbing is mandatory:** the worker must never inherit `os.environ` (which carries `.env.production` secrets) — only a fixed allowlist.
- **Isolation depth:** user-drop (`baluhost-plugin`) + `unshare --net` + `prlimit` resource limits. **No** mount/PID/IPC namespaces, no seccomp, no cgroups (deferred, fragility).
- **sudoers** grants exactly one fixed binary path with no pinned args; the wrapper (root:root, 0755) validates every caller-influenced argument. No `ALL`, no globs matching user paths.
- **util-linux order is load-bearing:** `prlimit` (sets limits, root) → `unshare --net` (creates netns, root) → `setpriv --reuid baluhost-plugin` (drops privilege inside the netns) → worker. `unshare --net` must run as root *before* the privilege drop; `setpriv` has no `--rlimit` flags, so `prlimit` carries the limits.
- **rlimit values:** `--cpu=60` (s), `--nproc=64`, `--as=536870912` (512 MiB), `--fsize=67108864` (64 MiB).
- **Worker UDS socket is a filesystem object** — reachable from inside the empty netns; do not assume any network is up in the worker.
- CRLF repo on Windows (`core.autocrlf=true`); the `.sh` files use LF — Git will warn, that is expected.

---

### Task 1: Config settings for the wrapper path and plugin user

**Files:**
- Modify: `backend/app/core/config.py` (add two fields near `plugins_external_dir`, around line 245–249)
- Modify: `backend/.env.example` (document the two new vars)
- Test: `backend/tests/test_config_validation.py` (append)

**Interfaces:**
- Produces: `settings.plugin_sandbox_user: str` (default `"baluhost-plugin"`), `settings.plugin_sandbox_wrapper_path: str` (default `"/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"`). Consumed by `spawn.select_spawn_hook()` / `spawn.hardened_spawn()` in Task 2.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_config_validation.py`, append:

```python
def test_plugin_sandbox_settings_defaults():
    s = Settings(environment="development", nas_mode="dev")
    assert s.plugin_sandbox_user == "baluhost-plugin"
    assert s.plugin_sandbox_wrapper_path == "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"


def test_plugin_sandbox_settings_overridable():
    s = Settings(
        environment="development",
        nas_mode="dev",
        plugin_sandbox_user="custom-plugin-user",
        plugin_sandbox_wrapper_path="/tmp/wrapper.sh",
    )
    assert s.plugin_sandbox_user == "custom-plugin-user"
    assert s.plugin_sandbox_wrapper_path == "/tmp/wrapper.sh"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python -m pytest tests/test_config_validation.py::test_plugin_sandbox_settings_defaults -v`
Expected: FAIL — `Settings` has no attribute `plugin_sandbox_user`.

- [ ] **Step 3: Add the fields**

In `backend/app/core/config.py`, immediately after the `plugins_marketplace_cache_ttl` field (line ~249) and before `model_config = SettingsConfigDict(`:

```python
    # Plugin sandbox (Track B, Phase 5a) — hardened worker spawn.
    # The unprivileged OS user the external-plugin worker runs as, and the
    # root-owned wrapper that drops to it. Only consulted on prod Linux; dev
    # and Windows ignore them and use the plain subprocess spawn.
    plugin_sandbox_user: str = "baluhost-plugin"
    plugin_sandbox_wrapper_path: str = "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_config_validation.py -k plugin_sandbox -v`
Expected: PASS (both new tests).

- [ ] **Step 5: Document in `.env.example`**

In `backend/.env.example`, add (under a plugin-related section, or at the end if none):

```bash
# Plugin sandbox (Track B Phase 5a) — hardened external-plugin worker spawn.
# Only used on production Linux. The worker runs as this unprivileged user via
# the root-owned wrapper. Leave defaults unless you renamed the user/path.
PLUGIN_SANDBOX_USER=baluhost-plugin
PLUGIN_SANDBOX_WRAPPER_PATH=/opt/baluhost/deploy/bin/spawn-plugin-worker.sh
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/.env.example backend/tests/test_config_validation.py
git commit -m "feat(plugin-sandbox): config for hardened worker spawn (user + wrapper path)"
```

---

### Task 2: `spawn.py` — scrub_env, hardened_spawn, select_spawn_hook

**Files:**
- Create: `backend/app/plugins/sandbox/spawn.py`
- Test: `backend/tests/plugins/sandbox/test_spawn_hook.py` (create)

**Interfaces:**
- Consumes: `settings.plugin_sandbox_user`, `settings.plugin_sandbox_wrapper_path`, `settings.environment` (Task 1); `SpawnHook` type and `_default_spawn` from `app.plugins.sandbox.supervisor`.
- Produces:
  - `scrub_env() -> dict[str, str]`
  - `async def hardened_spawn(argv: list[str], cwd: str) -> asyncio.subprocess.Process`
  - `def select_spawn_hook() -> SpawnHook | None` — `None` ⟺ prod+Linux+unprovisioned (the sole fail-closed signal Task 3 keys on).
  - Module-level probe helpers `_wrapper_ready() -> bool` and `_user_exists() -> bool` (monkeypatched in tests).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/plugins/sandbox/test_spawn_hook.py`:

```python
import asyncio
import sys
from unittest.mock import AsyncMock, patch

import pytest

from app.plugins.sandbox import spawn
from app.plugins.sandbox.supervisor import _default_spawn


# --- scrub_env -------------------------------------------------------------

def test_scrub_env_drops_secrets_keeps_path():
    fake_environ = {
        "PATH": "/opt/baluhost/backend/.venv/bin:/usr/bin",
        "LANG": "en_US.UTF-8",
        "SECRET_KEY": "supersecret",
        "VPN_ENCRYPTION_KEY": "key",
        "DATABASE_URL": "postgresql://u:p@h/db",
        "PYTHONUNBUFFERED": "1",
    }
    with patch.object(spawn.os, "environ", fake_environ):
        env = spawn.scrub_env()
    assert env["PATH"] == "/opt/baluhost/backend/.venv/bin:/usr/bin"
    assert env["LANG"] == "en_US.UTF-8"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert "SECRET_KEY" not in env
    assert "VPN_ENCRYPTION_KEY" not in env
    assert "DATABASE_URL" not in env


def test_scrub_env_supplies_path_when_missing():
    with patch.object(spawn.os, "environ", {}):
        env = spawn.scrub_env()
    assert env["PATH"]  # non-empty fallback


# --- hardened_spawn --------------------------------------------------------

@pytest.mark.asyncio
async def test_hardened_spawn_wraps_with_sudo_and_scrubbed_env():
    argv = [
        sys.executable, "-m", "app.plugins.sandbox.worker",
        "--connect", "/run/x.sock",
        "--plugin-dir", "/var/lib/baluhost/plugins/demo",
        "--plugin-name", "demo",
    ]
    fake_proc = object()
    with patch.object(spawn.settings, "plugin_sandbox_wrapper_path", "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"), \
         patch.object(spawn.asyncio, "create_subprocess_exec", new=AsyncMock(return_value=fake_proc)) as mock_exec, \
         patch.object(spawn, "scrub_env", return_value={"PATH": "/usr/bin"}):
        proc = await spawn.hardened_spawn(argv, "/var/lib/baluhost/plugins/demo")
    assert proc is fake_proc
    called_args = list(mock_exec.call_args.args)
    assert called_args[:3] == ["sudo", "-n", "/opt/baluhost/deploy/bin/spawn-plugin-worker.sh"]
    assert called_args[3:] == argv  # full argv forwarded; wrapper parses the flags it needs
    assert mock_exec.call_args.kwargs["cwd"] == "/var/lib/baluhost/plugins/demo"
    assert mock_exec.call_args.kwargs["env"] == {"PATH": "/usr/bin"}


# --- select_spawn_hook -----------------------------------------------------

def test_select_dev_returns_default():
    with patch.object(spawn.settings, "environment", "development"):
        assert spawn.select_spawn_hook() is _default_spawn


def test_select_non_linux_returns_default(monkeypatch):
    monkeypatch.setattr(spawn.sys, "platform", "win32")
    with patch.object(spawn.settings, "environment", "production"):
        assert spawn.select_spawn_hook() is _default_spawn


def test_select_prod_linux_provisioned_returns_hardened(monkeypatch):
    monkeypatch.setattr(spawn.sys, "platform", "linux")
    monkeypatch.setattr(spawn, "_wrapper_ready", lambda: True)
    monkeypatch.setattr(spawn, "_user_exists", lambda: True)
    with patch.object(spawn.settings, "environment", "production"):
        assert spawn.select_spawn_hook() is spawn.hardened_spawn


def test_select_prod_linux_unprovisioned_returns_none(monkeypatch):
    monkeypatch.setattr(spawn.sys, "platform", "linux")
    monkeypatch.setattr(spawn, "_wrapper_ready", lambda: False)
    monkeypatch.setattr(spawn, "_user_exists", lambda: True)
    with patch.object(spawn.settings, "environment", "production"):
        assert spawn.select_spawn_hook() is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_spawn_hook.py -v`
Expected: FAIL — `app.plugins.sandbox.spawn` does not exist.

- [ ] **Step 3: Implement `spawn.py`**

Create `backend/app/plugins/sandbox/spawn.py`:

```python
"""Production spawn hook for external plugin workers (Track B, Phase 5a).

Replaces the plain ``_default_spawn`` for external plugins on a provisioned
production Linux box: the worker runs as the unprivileged ``baluhost-plugin``
user, in its own network namespace, under resource limits, with a scrubbed
environment. Selection is automatic; an unprovisioned prod box fails closed
(``select_spawn_hook`` returns ``None``).
"""
import asyncio
import os
import sys
from typing import Optional

from app.core.config import settings
from app.plugins.sandbox.supervisor import SpawnHook, _default_spawn

# Environment keys the worker is allowed to inherit. Everything else — every
# secret loaded from .env.production — is dropped.
_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
)
_FALLBACK_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def scrub_env() -> dict:
    """Build a minimal environment for the worker from a fixed allowlist.

    Never returns secrets — only allowlisted keys present in ``os.environ``,
    with a sane ``PATH`` fallback so the wrapper/interpreter resolve.
    """
    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    if not env.get("PATH"):
        env["PATH"] = _FALLBACK_PATH
    return env


async def hardened_spawn(argv: list, cwd: str) -> asyncio.subprocess.Process:
    """Spawn the worker through the root-owned sudo wrapper with a scrubbed env.

    The full worker ``argv`` is forwarded; the wrapper parses only the
    ``--connect/--plugin-dir/--plugin-name`` flags it needs and reconstructs the
    privilege-dropping exec line from trusted constants.
    """
    wrapped = ["sudo", "-n", settings.plugin_sandbox_wrapper_path, *argv]
    return await asyncio.create_subprocess_exec(*wrapped, cwd=cwd, env=scrub_env())


def _wrapper_ready() -> bool:
    """True if the wrapper exists and is executable."""
    return os.access(settings.plugin_sandbox_wrapper_path, os.X_OK)


def _user_exists() -> bool:
    """True if the configured plugin user exists (POSIX only)."""
    try:
        import pwd  # POSIX-only; never reached on Windows (caller short-circuits)
        pwd.getpwnam(settings.plugin_sandbox_user)
        return True
    except (ImportError, KeyError):
        return False


def select_spawn_hook() -> Optional[SpawnHook]:
    """Pick the spawn hook for this host.

    - dev / non-prod, or any non-Linux platform → ``_default_spawn``
    - prod + Linux + wrapper present + plugin user exists → ``hardened_spawn``
    - prod + Linux + not provisioned → ``None`` (caller fails closed)
    """
    is_prod = str(settings.environment).lower() in ("production", "prod")
    if not is_prod or sys.platform != "linux":
        return _default_spawn
    if _wrapper_ready() and _user_exists():
        return hardened_spawn
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/sandbox/test_spawn_hook.py -v`
Expected: PASS (all). If `pytest.mark.asyncio` needs an event loop policy, the repo already uses `pytest-asyncio` (see other sandbox tests) — match their `@pytest.mark.asyncio` usage.

- [ ] **Step 5: Lint**

Run: `cd backend && python -m ruff check app/plugins/sandbox/spawn.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/sandbox/spawn.py backend/tests/plugins/sandbox/test_spawn_hook.py
git commit -m "feat(plugin-sandbox): hardened_spawn + scrub_env + select_spawn_hook (auto-detect, fail-closed)"
```

---

### Task 3: Wire the hook into PluginManager with fail-closed audit

**Files:**
- Modify: `backend/app/plugins/manager.py` (`_supervisor_factory` ~168–172; `_enable_external` ~496–518; add an exception class near `PluginPermissionError` ~65)
- Test: `backend/tests/plugins/test_manager_sandbox_failclosed.py` (create)

**Interfaces:**
- Consumes: `spawn.select_spawn_hook()` (Task 2). The `None` return is the fail-closed signal.
- Produces: `SandboxHardeningUnavailable(Exception)` raised by `_supervisor_factory`; `_enable_external` returns `False` + audits `plugin_sandbox_hardening_unavailable` when it is raised.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/plugins/test_manager_sandbox_failclosed.py`:

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from app.plugins.manager import PluginManager, DiscoveredPlugin


def _external_discovered(tmp_path: Path) -> DiscoveredPlugin:
    return DiscoveredPlugin(
        name="demo", path=tmp_path, source="external",
        manifest=object(),  # truthy manifest → external+manifest path
    )


@pytest.mark.asyncio
async def test_enable_external_fails_closed_when_hook_none(tmp_path):
    mgr = PluginManager(plugins_dir=tmp_path)
    disc = _external_discovered(tmp_path)
    with patch("app.plugins.sandbox.spawn.select_spawn_hook", return_value=None), \
         patch("app.plugins.manager.get_audit_logger_db") as audit:
        ok = await mgr._enable_external("demo", disc, [])
    assert ok is False
    assert "demo" not in mgr._sandboxes
    audit.return_value.log_security_event.assert_called_once()
    kwargs = audit.return_value.log_security_event.call_args.kwargs
    assert kwargs["action"] == "plugin_sandbox_hardening_unavailable"
    assert kwargs["success"] is False


@pytest.mark.asyncio
async def test_enable_external_uses_selected_hook(tmp_path):
    mgr = PluginManager(plugins_dir=tmp_path)
    disc = _external_discovered(tmp_path)

    captured = {}

    class _FakeSupervisor:
        def __init__(self, name, path, *, capability_router=None, spawn_hook=None):
            captured["spawn_hook"] = spawn_hook
        async def start(self):
            return None

    sentinel_hook = lambda argv, cwd: None  # noqa: E731
    with patch("app.plugins.sandbox.spawn.select_spawn_hook", return_value=sentinel_hook), \
         patch("app.plugins.sandbox.supervisor.SandboxSupervisor", _FakeSupervisor), \
         patch("app.plugins.sandbox.host_capabilities.build_capability_router", return_value=object()):
        ok = await mgr._enable_external("demo", disc, [])
    assert ok is True
    assert captured["spawn_hook"] is sentinel_hook
    assert "demo" in mgr._sandboxes
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_manager_sandbox_failclosed.py -v`
Expected: FAIL — `SandboxHardeningUnavailable` not raised / `_supervisor_factory` ignores the selected hook.

- [ ] **Step 3: Add the exception class**

In `backend/app/plugins/manager.py`, after the `PluginPermissionError` class (~line 65–68), add:

```python
class SandboxHardeningUnavailable(Exception):
    """Raised when prod hardening is required but the box is not provisioned.

    The signal is a ``None`` return from ``select_spawn_hook()`` — which only
    happens on prod Linux without the wrapper/plugin user. Callers fail closed.
    """

    pass
```

- [ ] **Step 4: Make `_supervisor_factory` consult the hook**

Replace the body of `_supervisor_factory` (currently lines ~168–172):

```python
    def _supervisor_factory(self, plugin_name: str, plugin_dir: Path, capability_router: Any) -> Any:
        """Build a SandboxSupervisor (overridable in tests).

        Selects the spawn hook (hardened on a provisioned prod-Linux box, plain
        otherwise). A ``None`` selection means hardening is required but the box
        is unprovisioned → raise so the caller can fail closed.
        """
        from app.plugins.sandbox.spawn import select_spawn_hook  # noqa: PLC0415
        from app.plugins.sandbox.supervisor import SandboxSupervisor  # noqa: PLC0415

        hook = select_spawn_hook()
        if hook is None:
            raise SandboxHardeningUnavailable(plugin_name)
        return SandboxSupervisor(
            plugin_name, plugin_dir, capability_router=capability_router, spawn_hook=hook
        )
```

- [ ] **Step 5: Make `_enable_external` fail closed + audit**

In `_enable_external` (lines ~496–518), wrap the factory call. Replace:

```python
        router = build_capability_router(name, set(granted_api_scopes))
        supervisor = self._supervisor_factory(name, discovered.path, router)
        try:
            await supervisor.start()
        except Exception:
            logger.exception("Failed to start sandbox for external plugin %s", name)
            return False
```

with:

```python
        router = build_capability_router(name, set(granted_api_scopes))
        try:
            supervisor = self._supervisor_factory(name, discovered.path, router)
        except SandboxHardeningUnavailable:
            logger.error(
                "Refusing to spawn external plugin %s: sandbox hardening required "
                "but baluhost-plugin user / spawn wrapper is not provisioned",
                name,
            )
            from app.services.audit.logger_db import get_audit_logger_db  # noqa: PLC0415
            get_audit_logger_db().log_security_event(
                action="plugin_sandbox_hardening_unavailable",
                resource=f"plugin:{name}",
                details={"reason": "baluhost-plugin user or spawn wrapper not provisioned"},
                success=False,
            )
            return False
        try:
            await supervisor.start()
        except Exception:
            logger.exception("Failed to start sandbox for external plugin %s", name)
            return False
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_manager_sandbox_failclosed.py -v`
Expected: PASS (both).

- [ ] **Step 7: Regression — manager + sandbox suites still green**

Run: `cd backend && python -m pytest tests/plugins/ -q`
Expected: PASS (Phase-4 count preserved: ~531 passed, 1 skipped on Windows). `ruff check app/plugins/manager.py` clean.

- [ ] **Step 8: Commit**

```bash
git add backend/app/plugins/manager.py backend/tests/plugins/test_manager_sandbox_failclosed.py
git commit -m "feat(plugin-sandbox): wire spawn-hook selection + fail-closed audit into PluginManager"
```

---

### Task 4: Fix-A (disable_plugin orphan guard) + Follow-up-B verification

**Files:**
- Modify: `backend/app/plugins/manager.py` (`disable_plugin` external branch ~529–537)
- Test: `backend/tests/plugins/test_manager_disable_orphan.py` (create)

**Interfaces:**
- Consumes: `SandboxSupervisor.stop()` / `_hard_kill()` (both exist, async, idempotent).
- Produces: `disable_plugin` that hard-kills and removes the sandbox entry even when `stop()` raises.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/plugins/test_manager_disable_orphan.py`:

```python
from pathlib import Path

import pytest

from app.plugins.manager import PluginManager


class _RaisingSupervisor:
    def __init__(self):
        self.hard_killed = False
    async def stop(self):
        raise RuntimeError("stop boom")
    async def _hard_kill(self):
        self.hard_killed = True


class _CleanSupervisor:
    def __init__(self):
        self.stopped = False
        self.hard_killed = False
    async def stop(self):
        self.stopped = True
    async def _hard_kill(self):
        self.hard_killed = True


@pytest.mark.asyncio
async def test_disable_hard_kills_when_stop_raises(tmp_path: Path):
    mgr = PluginManager(plugins_dir=tmp_path)
    sup = _RaisingSupervisor()
    mgr._sandboxes["demo"] = sup
    mgr._enabled.add("demo")

    ok = await mgr.disable_plugin("demo")

    assert ok is True
    assert sup.hard_killed is True          # no orphan
    assert "demo" not in mgr._sandboxes     # handle removed
    assert "demo" not in mgr._enabled


@pytest.mark.asyncio
async def test_disable_clean_path_does_not_hard_kill(tmp_path: Path):
    mgr = PluginManager(plugins_dir=tmp_path)
    sup = _CleanSupervisor()
    mgr._sandboxes["demo"] = sup
    mgr._enabled.add("demo")

    ok = await mgr.disable_plugin("demo")

    assert ok is True
    assert sup.stopped is True
    assert sup.hard_killed is False
    assert "demo" not in mgr._sandboxes
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_manager_disable_orphan.py -v`
Expected: FAIL — the raising-stop test orphans (no `_hard_kill`), `_RaisingSupervisor.hard_killed` stays False.

- [ ] **Step 3: Apply Fix-A**

In `backend/app/plugins/manager.py`, replace the external branch at the top of `disable_plugin` (currently ~529–537):

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

with (stop before pop; hard-kill on failure; remove in `finally`):

```python
        if name in self._sandboxes:
            supervisor = self._sandboxes[name]
            try:
                await supervisor.stop()
            except Exception:
                logger.exception("Error stopping sandbox for %s; forcing kill", name)
                try:
                    await supervisor._hard_kill()
                except Exception:
                    logger.exception("Hard-kill of sandbox %s also failed", name)
            finally:
                self._sandboxes.pop(name, None)
                self._enabled.discard(name)
            logger.info("Disabled external (sandboxed) plugin: %s", name)
            return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_manager_disable_orphan.py -v`
Expected: PASS (both).

- [ ] **Step 5: Verify Follow-up-B (no code unless a gap is found)**

Confirm `SandboxSupervisor.start()` leaves no child on handshake failure. Inspect `backend/app/plugins/sandbox/supervisor.py`: `_spawn_and_connect()` calls `_hard_kill()` on both the accept-timeout (`~217`) and the health-handshake-failure (`~232`, `~237`) paths, and `start()` only creates the supervise task *after* `_spawn_and_connect()` returns. Then run the existing supervisor tests to confirm the contract:

Run: `cd backend && python -m pytest tests/plugins/sandbox/ -q -k "supervisor or handshake or spawn"`
Expected: PASS. If — and only if — no existing test asserts the hard-kill-on-handshake-failure path, add one to `backend/tests/plugins/sandbox/test_supervisor.py`:

```python
@pytest.mark.asyncio
async def test_start_hard_kills_child_on_handshake_failure(monkeypatch):
    # A spawn hook that returns a live dummy process which never connects back;
    # the listener accept times out → _hard_kill must run, no orphan, start() raises.
    # (Mirror the existing supervisor test fixtures for the dummy process/listener.)
    ...
```

(Match the existing test module's fixtures for the dummy process and listener; do not invent new infrastructure. If coverage already exists, record that in the task report and skip adding a test.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/manager.py backend/tests/plugins/test_manager_disable_orphan.py
git commit -m "fix(plugin-sandbox): disable_plugin hard-kills on stop() failure (no orphaned worker)"
```

---

### Task 5: The root-owned spawn wrapper + argument-validation tests

**Files:**
- Create: `deploy/install/bin/spawn-plugin-worker.sh`
- Test: `backend/tests/plugins/sandbox/test_spawn_wrapper.py` (create; Linux-only, Windows-skip)

**Interfaces:**
- Consumes: worker argv flags `--connect`, `--plugin-dir`, `--plugin-name` (forwarded verbatim by `hardened_spawn`, mixed with the ignored `python -m app.plugins.sandbox.worker` tokens).
- Produces: a hardened wrapper that validates those three flags and execs `prlimit … -- unshare --net -- setpriv --reuid baluhost-plugin … -- <venv python> -m app.plugins.sandbox.worker …`. Exit codes: 64 (bad name), 65 (dir not resolvable), 66 (dir outside jail), 67 (bad connect).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/plugins/sandbox/test_spawn_wrapper.py`:

```python
"""Argument-validation tests for the root-owned spawn wrapper.

Linux-only: needs bash + coreutils realpath. The privilege-dropping chain
(prlimit/unshare/setpriv) is shimmed via PATH so the test asserts the wrapper's
*validation* and the *reconstructed exec line*, not real privilege drop.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash wrapper, POSIX only")

WRAPPER = Path(__file__).resolve().parents[4] / "deploy" / "install" / "bin" / "spawn-plugin-worker.sh"


def _run(args, extra_path: Path):
    """Invoke the wrapper with `prlimit` shimmed on PATH to echo its argv."""
    env = dict(os.environ)
    env["PATH"] = f"{extra_path}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(WRAPPER), *args],
        capture_output=True, text=True, env=env,
    )


@pytest.fixture
def prlimit_shim(tmp_path: Path) -> Path:
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir()
    shim = shim_dir / "prlimit"
    shim.write_text('#!/bin/bash\necho "$@"\nexit 0\n')
    shim.chmod(0o755)
    return shim_dir


def test_rejects_bad_plugin_name(prlimit_shim):
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", "/tmp", "--plugin-name", "../evil"], prlimit_shim)
    assert r.returncode == 64


def test_rejects_bad_connect(prlimit_shim):
    r = _run(["--connect", "a;b", "--plugin-dir", "/tmp", "--plugin-name", "demo"], prlimit_shim)
    assert r.returncode == 67


def test_rejects_unresolvable_dir(prlimit_shim):
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", "/nope/does/not/exist", "--plugin-name", "demo"], prlimit_shim)
    assert r.returncode == 65


def test_rejects_dir_outside_jail(prlimit_shim, tmp_path):
    outside = tmp_path / "demo"
    outside.mkdir()
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", str(outside), "--plugin-name", "demo"], prlimit_shim)
    assert r.returncode == 66


@pytest.mark.skipif(os.geteuid() != 0, reason="needs root to create the canonical jail dir")
def test_happy_path_builds_exec_chain(prlimit_shim):
    jail = Path("/var/lib/baluhost/plugins/demo")
    jail.mkdir(parents=True, exist_ok=True)
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", str(jail),
              "--plugin-name", "demo", "-m", "app.plugins.sandbox.worker"], prlimit_shim)
    assert r.returncode == 0
    out = r.stdout
    assert "unshare --net" in out
    assert "setpriv --reuid baluhost-plugin" in out
    assert "--plugin-dir /var/lib/baluhost/plugins/demo" in out
    assert "--plugin-name demo" in out
    assert "-m app.plugins.sandbox.worker" in out
```

- [ ] **Step 2: Run them to verify they fail**

Run (Linux): `cd backend && python -m pytest tests/plugins/sandbox/test_spawn_wrapper.py -v`
Expected: FAIL/ERROR — wrapper file does not exist. (On Windows the module is skipped — that is expected; this task's logic is validated on Linux CI.)

- [ ] **Step 3: Write the wrapper**

Create `deploy/install/bin/spawn-plugin-worker.sh` (LF line endings):

```bash
#!/bin/bash
# BaluHost plugin sandbox — hardened worker spawn wrapper.
#
# Invoked ONLY by the baluhost service user via a scoped sudoers entry:
#   baluhost ALL=(root) NOPASSWD: /opt/baluhost/deploy/bin/spawn-plugin-worker.sh
#
# Validates the caller-influenced flags, then drops privilege and isolates:
#   prlimit (limits, root) -> unshare --net (netns, root) ->
#   setpriv --reuid baluhost-plugin (drop) -> venv python -m worker
#
# Trusted constants below are NEVER taken from the caller.
set -euo pipefail

EXTERNAL_DIR="/var/lib/baluhost/plugins"
PLUGIN_USER="baluhost-plugin"
VENV_PYTHON="/opt/baluhost/backend/.venv/bin/python"
WORKER_MODULE="app.plugins.sandbox.worker"

# rlimits: CPU seconds, max processes, address space (bytes), max file size (bytes).
RL_CPU=60
RL_NPROC=64
RL_AS=536870912     # 512 MiB
RL_FSIZE=67108864   # 64 MiB

connect=""
plugin_dir=""
plugin_name=""

# Parse only the flags we use; ignore everything else (python, -m, module name).
while [[ $# -gt 0 ]]; do
  case "$1" in
    --connect)     connect="${2:-}";     shift 2 ;;
    --plugin-dir)  plugin_dir="${2:-}";  shift 2 ;;
    --plugin-name) plugin_name="${2:-}"; shift 2 ;;
    *)             shift ;;
  esac
done

# 1) plugin-name: strict allowlist.
[[ "$plugin_name" =~ ^[a-z0-9_]+$ ]] || { echo "bad plugin-name" >&2; exit 64; }

# 2) connect: UDS path or host:port, no shell metacharacters.
[[ "$connect" =~ ^[A-Za-z0-9_./:@-]+$ ]] || { echo "bad connect" >&2; exit 67; }

# 3) plugin-dir: must resolve, and canonicalize to exactly <EXTERNAL_DIR>/<name>.
real_dir="$(realpath -e -- "$plugin_dir" 2>/dev/null)" || { echo "dir not resolvable" >&2; exit 65; }
[[ "$real_dir" == "$EXTERNAL_DIR/$plugin_name" ]] || { echo "dir outside jail" >&2; exit 66; }

exec prlimit \
    "--cpu=$RL_CPU" "--nproc=$RL_NPROC" "--as=$RL_AS" "--fsize=$RL_FSIZE" -- \
  unshare --net -- \
  setpriv --reuid "$PLUGIN_USER" --regid "$PLUGIN_USER" --init-groups --no-new-privs -- \
    "$VENV_PYTHON" -m "$WORKER_MODULE" \
       --connect "$connect" --plugin-dir "$real_dir" --plugin-name "$plugin_name"
```

- [ ] **Step 4: Syntax-check + run the tests**

Run: `bash -n deploy/install/bin/spawn-plugin-worker.sh` (expect no output / exit 0).
Run (Linux): `cd backend && python -m pytest tests/plugins/sandbox/test_spawn_wrapper.py -v`
Expected: the four rejection tests PASS; the happy-path test PASSES under root (container CI) or is skipped otherwise.

- [ ] **Step 5: Commit**

```bash
git add deploy/install/bin/spawn-plugin-worker.sh backend/tests/plugins/sandbox/test_spawn_wrapper.py
git commit -m "feat(plugin-sandbox): root-owned hardened spawn wrapper + arg-validation tests"
```

---

### Task 6: Deploy provisioning — plugin user, sudoers, wrapper install

**Files:**
- Modify: `deploy/install/modules/03-user-setup.sh` (add `baluhost-plugin` user + plugins dir ownership)
- Create: `deploy/install/templates/baluhost-plugin-sudoers`
- Modify: `deploy/install/modules/10-systemd-services.sh` (install the sudoers rule + the wrapper binary, mirroring the existing sudoers blocks)

**Interfaces:**
- Consumes: `common.sh` helpers `log_step`/`log_info`/`log_warn`/`log_error`/`process_template`/`require_root`/`group_exists`/`user_exists`; env vars `$BALUHOST_USER`, `$BALUHOST_GROUP`, `$INSTALL_DIR`, `$SCRIPT_DIR`.
- Produces: provisioned `baluhost-plugin` system user/group; `/etc/sudoers.d/baluhost-plugin`; `/opt/baluhost/deploy/bin/spawn-plugin-worker.sh` (root:root 0755). After this runs, `spawn.select_spawn_hook()` returns `hardened_spawn` on the box.

> No unit test — these are install-time provisioning steps verified by `visudo -cf` and `bash -n` inside the module, plus the post-deploy manual smoke. This task is config wiring; its "test" is the syntax validation the module itself performs.

- [ ] **Step 1: Provision the plugin user + plugins dir in `03-user-setup.sh`**

In `deploy/install/modules/03-user-setup.sh`, after the existing "Ensure user is in group" block (after line ~40) and before "Create directories", add:

```bash
# --- Create unprivileged plugin-sandbox user (Track B Phase 5a) ---
PLUGIN_USER="baluhost-plugin"
PLUGIN_GROUP="baluhost-plugin"

if group_exists "$PLUGIN_GROUP"; then
    log_info "Group '$PLUGIN_GROUP' already exists, skipping."
else
    groupadd --system "$PLUGIN_GROUP"
    log_info "Created system group '$PLUGIN_GROUP'."
fi

if user_exists "$PLUGIN_USER"; then
    log_info "User '$PLUGIN_USER' already exists, skipping."
else
    useradd --system --no-create-home --shell /usr/sbin/nologin \
            --gid "$PLUGIN_GROUP" "$PLUGIN_USER"
    log_info "Created unprivileged system user '$PLUGIN_USER' (nologin)."
fi

# Defensive: the plugin user must NOT be in privileged groups or the baluhost
# group (no NAS-storage / secret read). Remove if a prior run added them.
for grp in sudo wheel docker "$BALUHOST_GROUP"; do
    if id -nG "$PLUGIN_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$grp"; then
        gpasswd -d "$PLUGIN_USER" "$grp" || true
        log_warn "Removed '$PLUGIN_USER' from group '$grp' (isolation requirement)."
    fi
done

# Let the backend (baluhost) create a group-connectable UDS socket the worker
# can reach: add baluhost to the plugin group.
if id -nG "$BALUHOST_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$PLUGIN_GROUP"; then
    log_info "User '$BALUHOST_USER' already in group '$PLUGIN_GROUP'."
else
    usermod -aG "$PLUGIN_GROUP" "$BALUHOST_USER"
    log_info "Added '$BALUHOST_USER' to group '$PLUGIN_GROUP'."
fi
```

Then add `/var/lib/baluhost/plugins` to the directory provisioning. After the existing `chown ... /var/lib/baluhost/update-status` block (~line 76), add:

```bash
# External plugins dir: baluhost owns it; plugin user gets r-x (traverse + read
# code + connect the socket). No world access. (Track B Phase 5a)
if [[ ! -d /var/lib/baluhost/plugins ]]; then
    mkdir -p /var/lib/baluhost/plugins
    log_info "Created directory: /var/lib/baluhost/plugins"
fi
chown "$BALUHOST_USER":"$PLUGIN_GROUP" /var/lib/baluhost/plugins
chmod 750 /var/lib/baluhost/plugins
log_info "Set /var/lib/baluhost/plugins to $BALUHOST_USER:$PLUGIN_GROUP (mode 750)"
```

- [ ] **Step 2: Verify the module still parses**

Run: `bash -n deploy/install/modules/03-user-setup.sh`
Expected: exit 0, no output.

- [ ] **Step 3: Create the sudoers template**

Create `deploy/install/templates/baluhost-plugin-sudoers`:

```
# BaluHost plugin sandbox (Track B Phase 5a)
# Allow the backend service user to invoke ONLY the hardened spawn wrapper as
# root. The wrapper validates every caller-influenced argument; no args pinned
# here because the worker's --connect/--plugin-dir/--plugin-name vary per spawn.
%BALUHOST_USER% ALL=(root) NOPASSWD: /opt/baluhost/deploy/bin/spawn-plugin-worker.sh
```

(`process_template` substitutes `%BALUHOST_USER%` — match the placeholder syntax of the existing `baluhost-*-sudoers` templates; if they use `@@BALUHOST_USER@@`, use that instead. Verify against `deploy/install/templates/baluhost-deploy-sudoers`.)

- [ ] **Step 4: Install the sudoers rule + wrapper in `10-systemd-services.sh`**

In `deploy/install/modules/10-systemd-services.sh`, after the "Install hardware sudoers rule" block (~line 115) and before the polkit block, add a new block that (a) copies the wrapper and (b) installs the sudoers rule with `visudo` validation:

```bash
# --- Install plugin-sandbox wrapper + sudoers rule (Track B Phase 5a) ---
log_step "Plugin Sandbox Spawn Wrapper"

WRAPPER_SRC="$SCRIPT_DIR/bin/spawn-plugin-worker.sh"
WRAPPER_DST_DIR="$INSTALL_DIR/deploy/bin"
WRAPPER_DST="$WRAPPER_DST_DIR/spawn-plugin-worker.sh"

if [[ -f "$WRAPPER_SRC" ]]; then
    mkdir -p "$WRAPPER_DST_DIR"
    install -o root -g root -m 0755 "$WRAPPER_SRC" "$WRAPPER_DST"
    if bash -n "$WRAPPER_DST"; then
        log_info "Installed plugin spawn wrapper: $WRAPPER_DST (root:root 0755)"
    else
        log_error "Spawn wrapper failed syntax check! Removing $WRAPPER_DST"
        rm -f "$WRAPPER_DST"
        exit 1
    fi

    PLUGIN_SUDOERS_TEMPLATE="$TEMPLATE_DIR/baluhost-plugin-sudoers"
    PLUGIN_SUDOERS_OUTPUT="/etc/sudoers.d/baluhost-plugin"
    if [[ -f "$PLUGIN_SUDOERS_TEMPLATE" ]]; then
        process_template "$PLUGIN_SUDOERS_TEMPLATE" "$PLUGIN_SUDOERS_OUTPUT" \
            "BALUHOST_USER=$BALUHOST_USER"
        chmod 440 "$PLUGIN_SUDOERS_OUTPUT"
        if visudo -cf "$PLUGIN_SUDOERS_OUTPUT" &>/dev/null; then
            log_info "Installed plugin sudoers rule: $PLUGIN_SUDOERS_OUTPUT"
        else
            log_error "Plugin sudoers syntax check failed! Removing $PLUGIN_SUDOERS_OUTPUT"
            rm -f "$PLUGIN_SUDOERS_OUTPUT"
            exit 1
        fi
    else
        log_warn "Plugin sudoers template not found: $PLUGIN_SUDOERS_TEMPLATE (skipping)"
    fi
else
    log_warn "Spawn wrapper source not found: $WRAPPER_SRC (skipping; external plugins will fail closed)"
fi
```

- [ ] **Step 5: Verify the module still parses**

Run: `bash -n deploy/install/modules/10-systemd-services.sh`
Expected: exit 0, no output.

- [ ] **Step 6: Update CI-CD security docs**

In `.claude/rules/ci-cd-security.md`, add a row to the sudoers context / "Known Gaps & Accepted Risks" reflecting the new scoped entry (mirror gap #9's framing): `baluhost` may invoke exactly one root-owned wrapper (`spawn-plugin-worker.sh`) that validates its args and only ever drops privilege to `baluhost-plugin` in a netns — no general command execution. Keep it to a few lines.

- [ ] **Step 7: Commit**

```bash
git add deploy/install/modules/03-user-setup.sh deploy/install/templates/baluhost-plugin-sudoers deploy/install/modules/10-systemd-services.sh .claude/rules/ci-cd-security.md
git commit -m "feat(plugin-sandbox): provision baluhost-plugin user, scoped sudoers, wrapper install"
```

---

## Final Verification

- [ ] Backend sandbox + manager suites: `cd backend && python -m pytest tests/plugins/ -q` → Phase-4 count preserved + the new spawn/fail-closed/orphan tests green.
- [ ] Spawn-hook unit suite: `cd backend && python -m pytest tests/plugins/sandbox/test_spawn_hook.py tests/plugins/test_manager_sandbox_failclosed.py tests/plugins/test_manager_disable_orphan.py -v` → all green.
- [ ] Wrapper validation (Linux/CI): `cd backend && python -m pytest tests/plugins/sandbox/test_spawn_wrapper.py -v` → rejections green; happy-path green-under-root or skipped.
- [ ] Lint: `cd backend && python -m ruff check app/plugins/sandbox/spawn.py app/plugins/manager.py` → clean.
- [ ] Shell syntax: `bash -n deploy/install/bin/spawn-plugin-worker.sh deploy/install/modules/03-user-setup.sh deploy/install/modules/10-systemd-services.sh` → all exit 0.
- [ ] Dev unchanged: on the Windows dev box, `select_spawn_hook()` returns `_default_spawn` (environment=development) — enabling an external fixture plugin still spawns via `_default_spawn` (existing Phase-4 e2e green).
- [ ] **Post-deploy manual smoke on BaluNode** (document, do not automate): enable a throwaway external fixture plugin; `ps -o user= -p <worker-pid>` shows `baluhost-plugin`; the worker's netns shows only `lo` (`nsenter -t <pid> -n ip addr`); `sudo -u baluhost-plugin cat /opt/baluhost/.env.production` is denied.

---

## Self-Review

**Spec coverage:**
- Env-scrubbing → Task 2 (`scrub_env`, test asserts secrets dropped).
- User-drop + netns + rlimits → Task 5 wrapper (`prlimit … unshare --net … setpriv …`), order corrected (rlimits via `prlimit`, not `setpriv`; `unshare` as root before drop).
- Auto-detect + fail-closed → Task 2 (`select_spawn_hook` matrix) + Task 3 (`SandboxHardeningUnavailable` + audit).
- Dev/Windows unchanged → Task 2 (non-prod/non-Linux → `_default_spawn`); Final Verification dev check.
- Fix-A → Task 4; Follow-up-B verify → Task 4 Step 5.
- Deploy provisioning (user, sudoers, wrapper, socket/FS model) → Task 6.
- Config + `.env.example` → Task 1.
- Tests cross-platform without root → Tasks 2–4 (mocked exec), Task 5 (rejections universal, happy-path root-gated).

**Placeholder scan:** the only non-literal is Task 4 Step 5's conditional test body — deliberately gated on "only if no existing coverage," with instructions to mirror existing fixtures; and Task 6's `%BALUHOST_USER%` vs `@@BALUHOST_USER@@` placeholder, flagged to verify against the sibling templates. rlimit values and exit codes are concrete.

**Type/name consistency:** `select_spawn_hook() -> SpawnHook | None`; `None` handled only in `_supervisor_factory` → `SandboxHardeningUnavailable` → caught in `_enable_external`. `_default_spawn`/`SpawnHook` imported from `supervisor`. `hardened_spawn(argv, cwd)` matches the `SpawnHook` signature (`Callable[[List[str], str], Awaitable[Process]]`). Wrapper exit codes (64/65/66/67) match the test assertions. Audit action string `plugin_sandbox_hardening_unavailable` identical in Task 3 code and test.
