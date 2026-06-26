# Plugin-Backend-Isolation — Phase 2b: SandboxSupervisor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Baue den `SandboxSupervisor`, der den Worker-Prozess eines externen Plugins per echtem Subprozess-Spawn startet, über UDS/TCP verbindet, per Health-Handshake validiert, Requests hineinproxyt, seinen Exit überwacht (bounded Restart → auto-disable) und ihn graceful/hard wieder herunterfährt.

**Architecture:** Ein neues Modul `backend/app/plugins/sandbox/supervisor.py`. Der Supervisor nutzt `WorkerListener` (Phase 2a) für die Rückverbindung, spawnt `python -m app.plugins.sandbox.worker --connect <addr>` über einen injizierbaren **Spawn-Hook** (Default: plain `asyncio.create_subprocess_exec`; die Low-Priv-User/netns-Härtung ersetzt diesen Hook in Phase 5), wickelt die Verbindung in einen `RpcChannel` (Phase 1) und macht den Health-Handshake per `LIFECYCLE`→`LIFECYCLE_RESULT`. Eine Hintergrund-Supervise-Task awaitet `process.wait()` und restartet bei unerwartetem Exit innerhalb eines Budgets, sonst auto-disable.

**Tech Stack:** Python 3.11, asyncio (subprocess + Streams), pytest + pytest-asyncio (`asyncio_mode=auto`). Erste Phase mit **echten Subprozessen** in den Tests. Keine neuen Dependencies.

## Global Constraints

- Python `>=3.11`; async/await für alle I/O; Type-Hints auf allen Funktionen.
- Tests: pytest `asyncio_mode="auto"` → `async def test_...`, **kein** `@pytest.mark.asyncio`.
- **Echte Subprozesse in Tests:** der Kind-Prozess ist `sys.executable -m app.plugins.sandbox.worker --connect <addr>`. `app` ist im Kind importierbar, weil das Backend editable installiert ist (`pip install -e ".[dev]"`). Jeder Test MUSS den Worker in `finally` über `supervisor.stop()` beenden (kein Prozess-Leak).
- **Spawn-Hook ist die einzige Stelle, an der ein Prozess entsteht** — Phase 5 ersetzt den Default-Hook durch eine gehärtete Variante (Low-Priv-User + Netzwerk-Namespace). Der Supervisor selbst kennt keine OS-Härtung.
- Worker-Shutdown ist **cross-platform** über `asyncio.subprocess.Process.terminate()`/`.kill()` (nicht `os.kill`/Signale) — funktioniert auf Windows (TerminateProcess) und Unix (SIGTERM/SIGKILL).
- Konsumiert Phase 1/2a: `RpcChannel` (`channel.py`), `Message`/`MsgType` inkl. `LIFECYCLE`/`LIFECYCLE_RESULT`/`HTTP_REQUEST`/`HTTP_RESPONSE` (`protocol.py`), `WorkerListener` (`transport.py`). Der Worker (`worker.py`) antwortet auf `LIFECYCLE {action:"health"}` mit `LIFECYCLE_RESULT {status:"ok"}` und echo-t `HTTP_REQUEST`.
- Repo `core.autocrlf=true`; LF schreiben. Branch: `feat/plugin-backend-isolation`. Commit-Stil: `feat(plugin-sandbox): …` / `test(plugin-sandbox): …`.
- Spec: `docs/superpowers/specs/2026-06-26-plugin-backend-isolation-design.md` (Abschnitt „Prozess-Topologie & Lifecycle").

## Phasen-Roadmap (Kontext — nur Phase 2b ist in diesem Plan)
1. ✅ Phase 1 — RPC-Fundament. 2. ✅ Phase 2a — Transport + Worker-Runner. **3. Phase 2b — SandboxSupervisor ← dieser Plan.** 4. Phase 3 — Capability-Layer + SDK (ersetzt den Echo-Handler). 5. Phase 4 — Request-Proxy + `PluginManager`-Dual-Path (FastAPI). 6. Phase 5 — Deploy-Härtung (gehärteter Spawn-Hook) + Frontend-Doku.

---

## File Structure (Phase 2b)

| Datei | Verantwortung |
|---|---|
| `backend/app/plugins/sandbox/supervisor.py` (neu) | `SpawnHook`-Typ + `_default_spawn`, `SupervisorError`, `SandboxSupervisor` (start/dispatch/health/stop + interne Supervise-/Restart-/Kill-Logik). |
| `backend/tests/plugins/sandbox/test_supervisor.py` (neu) | Echte-Subprozess-Tests: Lifecycle-Happy-Path, Handshake-Timeout, Restart-Budget-Unit, Auto-Restart, Auto-Disable, Dispatch-nach-Disable. |

---

## Task 1: Supervisor-Kern — spawn + handshake + dispatch + stop

**Files:**
- Create: `backend/app/plugins/sandbox/supervisor.py`
- Test: `backend/tests/plugins/sandbox/test_supervisor.py`

**Interfaces:**
- Consumes: `RpcChannel`, `Message`, `MsgType`, `WorkerListener`.
- Produces:
  - `SpawnHook = Callable[[list[str], str], Awaitable[asyncio.subprocess.Process]]`
  - `async _default_spawn(argv: list[str], cwd: str) -> asyncio.subprocess.Process`
  - `class SupervisorError(Exception)`
  - `class SandboxSupervisor`:
    - `__init__(self, plugin_name: str, plugin_dir: str | Path, *, spawn_hook: SpawnHook = _default_spawn, handshake_timeout: float = 10.0, graceful_timeout: float = 5.0, max_restarts: int = 3, restart_window: float = 60.0)`
    - `async start(self) -> None`
    - `async dispatch(self, method: str, path: str, body: bytes, context: dict) -> Message`
    - `async health(self) -> bool`
    - `async stop(self) -> None`
    - Attribute fürs Testen: `disabled: bool` (Property über `self._disabled`).

- [ ] **Step 1: Failing test schreiben**

Create `backend/tests/plugins/sandbox/test_supervisor.py`:

```python
"""Real-subprocess tests for SandboxSupervisor."""
import asyncio

import pytest

from app.plugins.sandbox.protocol import MsgType
from app.plugins.sandbox.supervisor import SandboxSupervisor, SupervisorError


async def test_start_health_dispatch_stop(tmp_path):
    sup = SandboxSupervisor("echo_plugin", tmp_path)
    await sup.start()
    try:
        assert await sup.health() is True
        resp = await sup.dispatch("GET", "ping", b"", {"user_id": 5})
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body["status"] == 200
        assert resp.body["echo"]["method"] == "GET"
        assert resp.body["echo"]["context"] == {"user_id": 5}
    finally:
        await sup.stop()


async def test_stop_is_idempotent(tmp_path):
    sup = SandboxSupervisor("echo_plugin", tmp_path)
    await sup.start()
    await sup.stop()
    await sup.stop()  # must not raise


async def test_handshake_timeout_raises_and_kills(tmp_path):
    # A spawn hook that starts a process which never connects back.
    async def silent_spawn(argv, cwd):
        return await asyncio.create_subprocess_exec(
            __import__("sys").executable, "-c", "import time; time.sleep(30)"
        )

    sup = SandboxSupervisor(
        "bad_plugin", tmp_path, spawn_hook=silent_spawn, handshake_timeout=1.0
    )
    with pytest.raises(SupervisorError):
        await sup.start()
    # No lingering process / clean state:
    assert await sup.health() is False
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_supervisor.py -v` (aus `backend/`)
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.plugins.sandbox.supervisor'`.

- [ ] **Step 3: `supervisor.py` schreiben**

Create `backend/app/plugins/sandbox/supervisor.py`:

```python
"""SandboxSupervisor: spawn and supervise one external plugin's worker
subprocess, and proxy requests to it over an RpcChannel.

Phase 2b uses a plain subprocess spawn (the default spawn hook). The
low-privilege OS user + network-namespace isolation is a pluggable spawn hook
deferred to Phase 5 — it slots in at the same boundary without touching this
class. Real plugin loading + capability dispatch (replacing the worker's
echo/health handler) is Phase 3.
"""
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable, List, Optional

from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import WorkerListener

logger = logging.getLogger(__name__)

WORKER_MODULE = "app.plugins.sandbox.worker"

# Given argv + working dir, start and return a subprocess. Phase 5 replaces the
# default with a hardened (low-priv user + netns) implementation.
SpawnHook = Callable[[List[str], str], Awaitable[asyncio.subprocess.Process]]


async def _default_spawn(argv: List[str], cwd: str) -> asyncio.subprocess.Process:
    """Plain subprocess spawn (dev/baseline)."""
    return await asyncio.create_subprocess_exec(*argv, cwd=cwd)


class SupervisorError(Exception):
    """Raised when the worker cannot be started, handshaked, or reached."""


class SandboxSupervisor:
    """Owns one external plugin's worker process and the RPC channel to it."""

    def __init__(
        self,
        plugin_name: str,
        plugin_dir: "str | Path",
        *,
        spawn_hook: SpawnHook = _default_spawn,
        handshake_timeout: float = 10.0,
        graceful_timeout: float = 5.0,
        max_restarts: int = 3,
        restart_window: float = 60.0,
    ) -> None:
        self.plugin_name = plugin_name
        self._plugin_dir = Path(plugin_dir)
        self._spawn_hook = spawn_hook
        self._handshake_timeout = handshake_timeout
        self._graceful_timeout = graceful_timeout
        self._max_restarts = max_restarts
        self._restart_window = restart_window

        self._process: Optional[asyncio.subprocess.Process] = None
        self._channel: Optional[RpcChannel] = None
        self._supervise_task: Optional[asyncio.Task] = None
        self._restart_times: List[float] = []
        self._running = False
        self._stopping = False
        self._disabled = False

    @property
    def disabled(self) -> bool:
        return self._disabled

    async def start(self) -> None:
        """Spawn the worker, connect, health-handshake, begin supervision."""
        await self._spawn_and_connect()
        self._running = True
        self._stopping = False
        self._supervise_task = asyncio.create_task(self._supervise())

    async def dispatch(
        self, method: str, path: str, body: bytes, context: dict
    ) -> Message:
        """Proxy one HTTP request into the worker and return its response."""
        if self._disabled:
            raise SupervisorError(f"plugin {self.plugin_name} is disabled")
        channel = self._channel
        if channel is None:
            raise SupervisorError(f"plugin {self.plugin_name} is not running")
        return await channel.call(
            MsgType.HTTP_REQUEST,
            {"method": method, "path": path, "body": body, "context": context},
        )

    async def health(self) -> bool:
        """Return True iff the worker answers a health ping."""
        channel = self._channel
        if channel is None or self._disabled:
            return False
        try:
            resp = await channel.call(
                MsgType.LIFECYCLE, {"action": "health"}, timeout=self._handshake_timeout
            )
        except (asyncio.TimeoutError, ConnectionError):
            return False
        return resp.type == MsgType.LIFECYCLE_RESULT and resp.body.get("status") == "ok"

    async def stop(self) -> None:
        """Stop supervision, ask the worker to shut down, then ensure it exits."""
        self._stopping = True
        self._running = False
        if self._supervise_task is not None:
            self._supervise_task.cancel()
            try:
                await self._supervise_task
            except asyncio.CancelledError:
                pass
            self._supervise_task = None
        await self._graceful_channel_close()
        await self._await_exit_or_kill()
        self._process = None

    # --- internals -------------------------------------------------------

    async def _spawn_and_connect(self) -> None:
        listener = WorkerListener(self._plugin_dir)
        address = await listener.start()
        argv = [sys.executable, "-m", WORKER_MODULE, "--connect", address]
        self._process = await self._spawn_hook(argv, str(self._plugin_dir))
        try:
            reader, writer = await listener.accept(timeout=self._handshake_timeout)
        except asyncio.TimeoutError as exc:
            await self._hard_kill()
            raise SupervisorError(
                f"worker {self.plugin_name} did not connect back in time"
            ) from exc
        finally:
            await listener.close()

        self._channel = RpcChannel(reader, writer)
        self._channel.start()

        try:
            resp = await self._channel.call(
                MsgType.LIFECYCLE, {"action": "health"}, timeout=self._handshake_timeout
            )
        except (asyncio.TimeoutError, ConnectionError) as exc:
            await self._hard_kill()
            raise SupervisorError(
                f"worker {self.plugin_name} health handshake failed"
            ) from exc
        if resp.type != MsgType.LIFECYCLE_RESULT or resp.body.get("status") != "ok":
            await self._hard_kill()
            raise SupervisorError(
                f"worker {self.plugin_name} reported unhealthy: {resp.body}"
            )

    async def _supervise(self) -> None:
        while self._running:
            process = self._process
            if process is None:
                return
            await process.wait()
            if self._stopping or not self._running:
                return
            logger.warning(
                "plugin %s worker exited unexpectedly (code %s)",
                self.plugin_name,
                process.returncode,
            )
            await self._close_channel()
            if not self._register_restart():
                self._disable("exceeded restart budget")
                return
            try:
                await self._spawn_and_connect()
            except SupervisorError:
                self._disable("restart failed")
                return

    def _register_restart(self) -> bool:
        """Record a restart; return False if the budget is now exceeded."""
        now = time.monotonic()
        self._restart_times = [
            t for t in self._restart_times if now - t < self._restart_window
        ]
        self._restart_times.append(now)
        return len(self._restart_times) <= self._max_restarts

    def _disable(self, reason: str) -> None:
        self._disabled = True
        self._running = False
        logger.error("plugin %s auto-disabled: %s", self.plugin_name, reason)

    async def _graceful_channel_close(self) -> None:
        channel = self._channel
        if channel is None:
            return
        try:
            await channel.call(
                MsgType.LIFECYCLE, {"action": "shutdown"}, timeout=self._graceful_timeout
            )
        except (asyncio.TimeoutError, ConnectionError):
            pass
        await self._close_channel()

    async def _close_channel(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None

    async def _await_exit_or_kill(self) -> None:
        process = self._process
        if process is None:
            return
        if await self._wait_exit(self._graceful_timeout):
            return
        self._signal(process.terminate)
        if await self._wait_exit(self._graceful_timeout):
            return
        self._signal(process.kill)
        await process.wait()

    async def _wait_exit(self, timeout: float) -> bool:
        process = self._process
        if process is None:
            return True
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    @staticmethod
    def _signal(fn: Callable[[], None]) -> None:
        try:
            fn()
        except ProcessLookupError:
            pass

    async def _hard_kill(self) -> None:
        await self._close_channel()
        process = self._process
        if process is not None:
            self._signal(process.kill)
            await process.wait()
        self._process = None
```

- [ ] **Step 4: Tests ausführen, Erfolg verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_supervisor.py -v` (aus `backend/`)
Expected: PASS (3 passed). Diese Tests spawnen echte Subprozesse — sie dürfen einige Sekunden dauern.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/sandbox/supervisor.py backend/tests/plugins/sandbox/test_supervisor.py
git commit -m "feat(plugin-sandbox): SandboxSupervisor spawn/handshake/dispatch/stop (Track B Phase 2b)"
```

---

## Task 2: Supervision — Exit-Detection, bounded Restart, auto-disable

**Files:**
- Test: `backend/tests/plugins/sandbox/test_supervisor.py` (erweitern)

**Interfaces:**
- Consumes: `SandboxSupervisor`, `SupervisorError`, `MsgType` (aus Task 1). Keine neuen Produces — verifiziert das in Task 1 gebaute Supervise-/Restart-/Disable-Verhalten.

Begründung: Exit-Detection (`_supervise` awaitet `process.wait()`), bounded Restart (`_register_restart`) und auto-disable (`_disable`) sind bereits in Task 1 implementiert. Diese Task verifiziert sie adversarial — ein Reviewer kann sie unabhängig freigeben.

- [ ] **Step 1: Failing tests schreiben**

An `backend/tests/plugins/sandbox/test_supervisor.py` anhängen:

```python
def test_register_restart_budget_unit(tmp_path):
    # Unit-test the budget counter directly (no subprocess): max_restarts=2
    # allows 2 restarts, the 3rd registration trips the budget.
    sup = SandboxSupervisor("p", tmp_path, max_restarts=2)
    assert sup._register_restart() is True   # 1
    assert sup._register_restart() is True   # 2
    assert sup._register_restart() is False  # 3 -> over budget


async def test_auto_restart_after_unexpected_exit(tmp_path):
    sup = SandboxSupervisor("echo_plugin", tmp_path)
    await sup.start()
    try:
        assert await sup.health() is True
        # Kill the worker out from under the supervisor.
        sup._process.kill()
        # The supervise loop should detect the exit and respawn a healthy worker.
        async def _healthy_again() -> bool:
            for _ in range(50):
                if not sup.disabled and await sup.health():
                    return True
                await asyncio.sleep(0.1)
            return False
        assert await _healthy_again() is True
        # And it serves requests again.
        resp = await sup.dispatch("GET", "again", b"", {})
        assert resp.body["echo"]["path"] == "again"
    finally:
        await sup.stop()


async def test_auto_disable_when_restart_fails(tmp_path):
    # First spawn succeeds (real worker); subsequent spawns produce a process
    # that exits immediately, so the restart's handshake fails -> auto-disable.
    state = {"calls": 0}

    async def flaky_spawn(argv, cwd):
        state["calls"] += 1
        if state["calls"] == 1:
            return await _default_spawn_passthrough(argv, cwd)
        return await asyncio.create_subprocess_exec(
            sys.executable, "-c", "raise SystemExit(1)"
        )

    sup = SandboxSupervisor(
        "flaky_plugin", tmp_path, spawn_hook=flaky_spawn, handshake_timeout=2.0
    )
    await sup.start()
    try:
        sup._process.kill()  # force the unexpected exit -> restart attempt (fails)
        async def _disabled() -> bool:
            for _ in range(50):
                if sup.disabled:
                    return True
                await asyncio.sleep(0.1)
            return False
        assert await _disabled() is True
        with pytest.raises(SupervisorError):
            await sup.dispatch("GET", "x", b"", {})
    finally:
        await sup.stop()
```

Außerdem oben in der Datei die Imports ergänzen: `import sys` und `from app.plugins.sandbox.supervisor import SandboxSupervisor, SupervisorError, _default_spawn as _default_spawn_passthrough` (der Passthrough-Alias macht den Reuse des echten Spawns im `flaky_spawn`-Hook deutlich).

- [ ] **Step 2: Tests ausführen, Erfolg verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_supervisor.py -v` (aus `backend/`)
Expected: PASS (alle 6 — die 3 aus Task 1 + 3 neue). Echte Subprozesse → kann ein paar Sekunden dauern. Falls ein neuer Test rot ist, ist das ein echter Defekt in der Supervise-/Restart-Logik aus Task 1 — dort fixen, nicht den Test aufweichen.

- [ ] **Step 3: Gesamte Sandbox-Suite + Lint**

Run: `python -m pytest tests/plugins/sandbox/ -v` (aus `backend/`)
Expected: PASS (Phase 1 + 2a + 2b zusammen). Bestätige den Pass-Count und dass keine neuen `Task was destroyed`/`Task exception was never retrieved`-Warnings auftauchen und **kein** Worker-Subprozess geleakt ist (alle Tests beenden via `stop()`).

Run: `ruff check app/plugins/sandbox/ tests/plugins/sandbox/` (aus `backend/`)
Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add backend/tests/plugins/sandbox/test_supervisor.py
git commit -m "test(plugin-sandbox): supervisor exit-detection, bounded restart, auto-disable (Track B Phase 2b)"
```

---

## Definition of Done (Phase 2b)

- `backend/app/plugins/sandbox/supervisor.py` existiert, lint-clean.
- `python -m pytest tests/plugins/sandbox/ -v` grün (Phase 1 + 2a + 2b), keine geleakten Subprozesse.
- Supervisor spawnt einen echten Worker, handshaket, dispatcht Echo-Requests, restartet bei unerwartetem Exit (bis Budget) und auto-disabled danach; stop() ist idempotent und killt hart, falls graceful scheitert.
- Der Spawn-Hook ist die einzige Prozess-Erzeugungsstelle (Phase-5-Härtung steckt dort ein).
- Keine neue Dependency. FastAPI/Manager-Wiring bleibt Phase 4; echtes Plugin-Loading bleibt Phase 3.

---

## Self-Review (gegen Spec „Prozess-Topologie & Lifecycle")

- **Subprozess-Spawn als eigener Prozess** → Task 1 (`_spawn_and_connect`, `_default_spawn`). ✓ (Low-Priv-User/netns = Phase 5 via Spawn-Hook, bewusst Stub.)
- **Health-Handshake** (`LIFECYCLE`→`LIFECYCLE_RESULT {status:ok}`) → Task 1 (`_spawn_and_connect`, `health`). ✓
- **Request-Proxy in den Worker** → Task 1 (`dispatch` → `HTTP_REQUEST`). ✓ (Voller kuratierter Contract + Auth/Gating = Phase 4.)
- **Crash-Supervision: bounded Restart, sonst auto-disable + Log** → Task 1 (`_supervise`, `_register_restart`, `_disable`) + Task 2 (Tests). ✓ (Audit-Log statt nur logger.error = Phase 4, wenn der Manager den Audit-Logger einspeist.)
- **Graceful → hard shutdown (SIGTERM→SIGKILL)** → Task 1 (`_graceful_channel_close`, `_await_exit_or_kill`, cross-platform `terminate()`/`kill()`). ✓
- **Primary-Worker-only Ownership** (nur der Primary-Uvicorn-Worker spawnt) → bewusst Phase 4 (Manager-Integration entscheidet, wer den Supervisor instanziiert); der Supervisor selbst ist worker-agnostisch.
- **Keine Platzhalter**; vollständiger Code; Typen/Namen konsistent mit Phase 1/2a (`RpcChannel.call/close`, `WorkerListener.accept(timeout=)`, `MsgType.LIFECYCLE_RESULT`).

## Bekannter Follow-up (nicht in 2b zu fixen)
- **Worker-Import-Footprint:** `python -m app.plugins.sandbox.worker` triggert `app/plugins/__init__.py`, das `fastapi`/`pluggy`/EventManager mitzieht (verifiziert: Import läuft in ~0,4s, kein DB/env-Bedarf — funktioniert). Der *isolierte* Worker sollte das Host-Plugin-Framework idealerweise NICHT importieren. Vor Phase 5 (Prod-Härtung) prüfen, ob der Sandbox-Worker auf einen schlanken Import-Pfad gelegt werden kann (z. B. Sandbox-Submodule ohne schwere Parent-`__init__`-Seiteneffekte). Für 2b/3 bewusst belassen.
