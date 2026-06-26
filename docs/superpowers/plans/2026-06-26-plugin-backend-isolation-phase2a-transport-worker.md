# Plugin-Backend-Isolation — Phase 2a: Transport + Worker-Runner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Baue die cross-plattform Host↔Worker-Socket-Transportschicht und den Sandbox-Worker-Entry-Point (mit einem minimalen Echo/Health-Handler), sodass ein Worker-Prozess sich an den Host zurückverbinden, einen `RpcChannel` aufspannen und Requests beantworten kann — alles in-process deterministisch testbar, noch ohne echten Subprozess-Spawn (der kommt in Phase 2b: Supervisor).

**Architecture:** Zwei neue Module unter `backend/app/plugins/sandbox/`: `transport.py` (Host-seitiger `WorkerListener` der genau eine Worker-Verbindung akzeptiert + Worker-seitiges `connect_to_host`; UDS auf Linux/prod, Loopback-TCP auf Windows/dev) und `worker.py` (Entry-Point: verbindet, baut `RpcChannel` mit einem Phase-2-Echo/Health-Handler, läuft bis Verbindungsschluss). Eine kleine Ergänzung an `channel.py` (`wait_closed()`). Der `RpcChannel` aus Phase 1 bleibt transport-agnostisch — Transport liefert nur ein `(StreamReader, StreamWriter)`-Paar.

**Tech Stack:** Python 3.11, asyncio (Streams + UDS/TCP), argparse, pytest + pytest-asyncio (`asyncio_mode=auto`). Keine neuen Dependencies.

## Global Constraints

- Python `>=3.11`; async/await für alle I/O; Type-Hints auf allen Funktionen.
- Tests: pytest `asyncio_mode="auto"` → async-Tests sind `async def test_...`, **kein** `@pytest.mark.asyncio`.
- **Transport-Wahl ist plattformbasiert, NICHT konfigurierbar durch Plugin-Daten:** UDS gdw. `hasattr(asyncio, "start_unix_server") and sys.platform != "win32"`, sonst Loopback-TCP `127.0.0.1`. UDS ist der Prod-Pfad (funktioniert über eine Netzwerk-Namespace-Grenze via Socket-Datei im Arbeitsverzeichnis); Loopback-TCP ist der Dev-Fallback (asyncio hat `open_unix_connection` auf Windows nicht).
- Connect-Adress-Format (Host→Worker, ein String): `unix:<path>` ODER `tcp:<host>:<port>`.
- `RpcChannel` (Phase 1, `app/plugins/sandbox/channel.py`) ist transport-agnostisch und wird **nicht** in seinem Kern verändert — nur eine additive `wait_closed()`-Methode kommt hinzu.
- Phase-2-Worker-Handler ist ein **Platzhalter** (Health + Echo) — echtes Plugin-Loading + Capability-SDK kommen in Phase 3 und ersetzen `build_worker_handler()`. NICHT mehr bauen als Health + Echo (YAGNI).
- Repo `core.autocrlf=true` auf Windows; LF schreiben.
- Branch: `feat/plugin-backend-isolation` (enthält Phase 1, merge-reif). Commit-Stil: `feat(plugin-sandbox): …` / `test(plugin-sandbox): …`.
- Spec: `docs/superpowers/specs/2026-06-26-plugin-backend-isolation-design.md` (Abschnitte „Prozess-Topologie & Lifecycle", „RPC-Protokoll").

## Konsumiert aus Phase 1 (bereits auf dem Branch, getestet)

`app/plugins/sandbox/protocol.py`: `Message(id:int, type:str, body:dict)`, `MsgType` (HTTP_REQUEST/HTTP_RESPONSE/CAP_CALL/CAP_RESULT/LIFECYCLE/ERROR), `read_frame`/`write_frame`.
`app/plugins/sandbox/channel.py`: `RpcChannel(reader, writer, *, request_handler=None)` mit `start()`, `async call(type, body, *, timeout=None)`, `async close()`, internem `self._read_task`.

## Phasen-Roadmap (Kontext — nur Phase 2a ist in diesem Plan)

1. ✅ Phase 1 — RPC-Fundament (protocol.py + RpcChannel), merge-reif auf dem Branch.
2. **Phase 2a — Transport + Worker-Runner** ← *dieser Plan*. In-process testbar, kein Subprozess.
3. Phase 2b — `SandboxSupervisor`: echter Subprozess-Spawn (`asyncio.create_subprocess_exec`), Health-Handshake, Exit-Detection, bounded Restart→auto-disable, graceful+hard shutdown. Spawn-Hook für Low-Priv-User/netns ist Stub (echte OS-Härtung = Phase 5).
4. Phase 3 — Capability-Layer + Plugin-SDK; ersetzt den Phase-2-Echo-Handler durch echtes Plugin-Loading + `core.*`/`storage.*`-Dispatch.
5. Phase 4 — Request-Proxy + `PluginManager`-Dual-Path (FastAPI-Wiring, Auth/Gating).
6. Phase 5 — Deploy-Härtung (OS-User/netns Spawn-Hook) + Frontend-Doku.

---

## File Structure (Phase 2a)

| Datei | Verantwortung |
|---|---|
| `backend/app/plugins/sandbox/transport.py` (neu) | `_use_unix_socket()`, Host-seitiger `WorkerListener` (listen+accept-one), Worker-seitiges `connect_to_host(address)`. Plattform-Wahl UDS/TCP. |
| `backend/app/plugins/sandbox/worker.py` (neu) | `build_worker_handler()` (Phase-2 Health+Echo), `async run_worker(address)`, `main(argv)` (argparse), `__main__`-Guard. |
| `backend/app/plugins/sandbox/channel.py` (modify) | Additive `async wait_closed()`-Methode. |
| `backend/tests/plugins/sandbox/test_transport.py` (neu) | Adress-Schema + Accept-Roundtrip (Frame über den Transport). |
| `backend/tests/plugins/sandbox/test_worker.py` (neu) | In-process: Health, Echo, argparse. |

---

## Task 1: Cross-platform Transport (`transport.py`)

**Files:**
- Create: `backend/app/plugins/sandbox/transport.py`
- Test: `backend/tests/plugins/sandbox/test_transport.py`

**Interfaces:**
- Consumes: `Message`, `MsgType`, `read_frame`, `write_frame` aus `protocol.py` (nur in den Tests, zum Roundtrip-Beweis).
- Produces:
  - `_use_unix_socket() -> bool`
  - `class WorkerListener`:
    - `__init__(self, socket_dir: str | os.PathLike)` — `socket_dir` ist das Verzeichnis für die UDS-Datei (im Prod das Arbeitsverzeichnis des Workers); im TCP-Fall ungenutzt.
    - `async start(self) -> str` — beginnt zu lauschen, gibt die `connect_address` zurück (`unix:<path>` oder `tcp:<host>:<port>`).
    - `async accept(self, *, timeout: float) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]` — wartet auf die EINE Worker-Verbindung; `asyncio.TimeoutError` bei Ablauf.
    - `async close(self) -> None` — schließt den Listener (nicht die akzeptierte Verbindung).
    - Attribut `connect_address: str`.
  - `async connect_to_host(address: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]` — Worker-Seite; parst `unix:`/`tcp:`.

- [ ] **Step 1: Failing test schreiben**

Create `backend/tests/plugins/sandbox/test_transport.py`:

```python
"""Tests for the cross-platform host<->worker transport."""
import asyncio

import pytest

from app.plugins.sandbox.protocol import Message, MsgType, read_frame, write_frame
from app.plugins.sandbox.transport import (
    WorkerListener,
    _use_unix_socket,
    connect_to_host,
)


async def test_connect_address_scheme_matches_platform(tmp_path):
    listener = WorkerListener(tmp_path)
    address = await listener.start()
    try:
        expected = "unix:" if _use_unix_socket() else "tcp:"
        assert address.startswith(expected)
    finally:
        await listener.close()


async def test_accept_roundtrip_carries_a_frame(tmp_path):
    listener = WorkerListener(tmp_path)
    address = await listener.start()
    try:
        # Worker side connects back; host accepts the one connection.
        w_reader, w_writer = await connect_to_host(address)
        h_reader, h_writer = await listener.accept(timeout=5)

        # Worker -> host
        await write_frame(w_writer, Message(id=1, type=MsgType.LIFECYCLE, body={"ping": True}))
        got = await read_frame(h_reader)
        assert got == Message(id=1, type=MsgType.LIFECYCLE, body={"ping": True})

        # Host -> worker
        await write_frame(h_writer, Message(id=2, type=MsgType.HTTP_RESPONSE, body={"ok": 1}))
        back = await read_frame(w_reader)
        assert back == Message(id=2, type=MsgType.HTTP_RESPONSE, body={"ok": 1})

        w_writer.close()
        h_writer.close()
    finally:
        await listener.close()


async def test_connect_to_host_rejects_unknown_scheme():
    with pytest.raises(ValueError):
        await connect_to_host("carrierpigeon:/nope")
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_transport.py -v` (aus `backend/`)
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.plugins.sandbox.transport'`.

- [ ] **Step 3: Implementierung schreiben**

Create `backend/app/plugins/sandbox/transport.py`:

```python
"""Cross-platform host<->worker socket transport for the plugin sandbox.

Prod (Linux): a Unix-domain socket whose path lives in the worker's working
directory, so it works across a network-namespace boundary (the worker needs
no host-loopback access — only the bind-mounted socket file). Dev (Windows, or
any platform without AF_UNIX in asyncio): a loopback-TCP socket on 127.0.0.1.

Either way the result is an (asyncio.StreamReader, asyncio.StreamWriter) pair
that an RpcChannel wraps; the channel itself is transport-agnostic.
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, Tuple


def _use_unix_socket() -> bool:
    """True iff asyncio AF_UNIX servers are available (Linux/macOS, not Windows)."""
    return hasattr(asyncio, "start_unix_server") and sys.platform != "win32"


class WorkerListener:
    """Host side: listen for the worker's callback connection and accept one.

    The worker is spawned with the string returned by ``start()`` and connects
    back exactly once. ``accept()`` resolves with that single connection.
    """

    def __init__(self, socket_dir: "str | os.PathLike[str]") -> None:
        self._socket_dir = Path(socket_dir)
        self._server: Optional[asyncio.AbstractServer] = None
        self._accepted: Optional[asyncio.Future] = None
        self.connect_address: str = ""

    async def start(self) -> str:
        loop = asyncio.get_running_loop()
        self._accepted = loop.create_future()

        def _on_conn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            # Accept only the first connection; ignore any extras defensively.
            if self._accepted is not None and not self._accepted.done():
                self._accepted.set_result((reader, writer))
            else:
                writer.close()

        if _use_unix_socket():
            path = str(self._socket_dir / "plugin.sock")
            # Stale socket file from a crashed prior worker would block bind.
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            self._server = await asyncio.start_unix_server(_on_conn, path=path)
            self.connect_address = f"unix:{path}"
        else:
            self._server = await asyncio.start_server(_on_conn, "127.0.0.1", 0)
            host, port = self._server.sockets[0].getsockname()[:2]
            self.connect_address = f"tcp:{host}:{port}"

        return self.connect_address

    async def accept(
        self, *, timeout: float
    ) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self._accepted is None:
            raise RuntimeError("WorkerListener.accept() called before start()")
        return await asyncio.wait_for(asyncio.shield(self._accepted), timeout)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None


async def connect_to_host(
    address: str,
) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Worker side: connect back to the host using a ``start()`` address."""
    scheme, _, rest = address.partition(":")
    if scheme == "unix":
        return await asyncio.open_unix_connection(path=rest)
    if scheme == "tcp":
        host, _, port = rest.rpartition(":")
        return await asyncio.open_connection(host, int(port))
    raise ValueError(f"unknown connect address scheme: {address!r}")
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_transport.py -v` (aus `backend/`)
Expected: PASS (3 passed).

> Hinweis für den Implementierer: `asyncio.wait_for(asyncio.shield(...))` schützt das geteilte `_accepted`-Future davor, bei einem Accept-Timeout gecancelt zu werden (sonst wäre der Listener nach einem Timeout unbrauchbar). Das ist beabsichtigt.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/sandbox/transport.py backend/tests/plugins/sandbox/test_transport.py
git commit -m "feat(plugin-sandbox): cross-platform host<->worker transport (UDS prod / TCP dev) (Track B Phase 2a)"
```

---

## Task 2: Worker-Entry-Point + `RpcChannel.wait_closed()` (`worker.py`)

**Files:**
- Modify: `backend/app/plugins/sandbox/channel.py` (additive `wait_closed()`)
- Create: `backend/app/plugins/sandbox/worker.py`
- Test: `backend/tests/plugins/sandbox/test_worker.py`

**Interfaces:**
- Consumes: `RpcChannel` (+ neue `wait_closed`), `Message`, `MsgType` aus Phase 1; `WorkerListener`, `connect_to_host` aus Task 1.
- Produces:
  - `RpcChannel.wait_closed(self) -> None` (async) — blockt bis der Read-Loop endet.
  - `build_worker_handler() -> RequestHandler` — der Phase-2 Health/Echo-Handler.
  - `async run_worker(address: str) -> None` — verbindet, fährt den Channel, läuft bis Verbindungsschluss, räumt auf.
  - `main(argv: list[str] | None = None) -> None` — argparse `--connect`, ruft `asyncio.run(run_worker(...))`.

- [ ] **Step 1: `wait_closed()` an `RpcChannel` — Failing test schreiben**

Create `backend/tests/plugins/sandbox/test_worker.py`:

```python
"""In-process tests for the sandbox worker entry point (no real subprocess)."""
import asyncio

import pytest

from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import WorkerListener
from app.plugins.sandbox.worker import build_worker_handler, main, run_worker


async def _host_and_worker(tmp_path):
    """Start a host listener + an in-process run_worker; return (host_channel,
    worker_task, listener) wired and ready."""
    listener = WorkerListener(tmp_path)
    address = await listener.start()
    worker_task = asyncio.create_task(run_worker(address))
    reader, writer = await listener.accept(timeout=5)
    host = RpcChannel(reader, writer)
    host.start()
    return host, worker_task, listener


async def test_worker_answers_health(tmp_path):
    host, worker_task, listener = await _host_and_worker(tmp_path)
    try:
        resp = await host.call(MsgType.LIFECYCLE, {"action": "health"}, timeout=5)
        assert resp.type == MsgType.LIFECYCLE
        assert resp.body == {"status": "ok"}
    finally:
        await host.close()
        await asyncio.wait_for(worker_task, timeout=5)
        await listener.close()


async def test_worker_echoes_http_request(tmp_path):
    host, worker_task, listener = await _host_and_worker(tmp_path)
    try:
        resp = await host.call(
            MsgType.HTTP_REQUEST,
            {"method": "GET", "path": "ping", "body": b"", "context": {"user_id": 7}},
            timeout=5,
        )
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body["status"] == 200
        assert resp.body["echo"]["method"] == "GET"
        assert resp.body["echo"]["path"] == "ping"
        assert resp.body["echo"]["context"] == {"user_id": 7}
    finally:
        await host.close()
        await asyncio.wait_for(worker_task, timeout=5)
        await listener.close()


async def test_worker_run_returns_when_host_closes(tmp_path):
    host, worker_task, listener = await _host_and_worker(tmp_path)
    await host.close()
    # run_worker must observe the closed connection and return on its own.
    await asyncio.wait_for(worker_task, timeout=5)
    assert worker_task.done() and worker_task.exception() is None
    await listener.close()


def test_main_requires_connect_arg():
    with pytest.raises(SystemExit):
        main([])


def test_build_worker_handler_is_async_callable():
    handler = build_worker_handler()
    assert asyncio.iscoroutinefunction(handler)
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_worker.py -v` (aus `backend/`)
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.plugins.sandbox.worker'` (und/oder `ImportError` für `wait_closed` sobald worker.py existiert).

- [ ] **Step 3: `wait_closed()` an `RpcChannel` ergänzen**

In `backend/app/plugins/sandbox/channel.py`, direkt **vor** der `close`-Methode, diese Methode einfügen:

```python
    async def wait_closed(self) -> None:
        """Block until the read loop ends (peer closed the connection or a
        frame error tore it down). Returns immediately if never started."""
        if self._read_task is not None:
            try:
                await self._read_task
            except (asyncio.CancelledError, Exception):
                pass
```

- [ ] **Step 4: `worker.py` schreiben**

Create `backend/app/plugins/sandbox/worker.py`:

```python
"""Plugin sandbox worker entry point — runs inside the isolated child process.

Phase 2 ships a minimal built-in request handler (health + echo) so the
host<->worker round-trip can be exercised end-to-end. Real plugin loading and
the capability SDK arrive in Phase 3, which replaces build_worker_handler().
"""
import argparse
import asyncio
from typing import List, Optional

from app.plugins.sandbox.channel import RequestHandler, RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import connect_to_host


def build_worker_handler() -> RequestHandler:
    """Return the Phase-2 placeholder handler: health pings + request echo."""

    async def handler(msg: Message) -> Message:
        if msg.type == MsgType.LIFECYCLE:
            action = msg.body.get("action")
            if action == "health":
                return Message(id=msg.id, type=MsgType.LIFECYCLE, body={"status": "ok"})
            if action == "shutdown":
                return Message(
                    id=msg.id, type=MsgType.LIFECYCLE, body={"status": "stopping"}
                )
            return Message(
                id=msg.id, type=MsgType.LIFECYCLE, body={"status": "unknown_action"}
            )
        if msg.type == MsgType.HTTP_REQUEST:
            # Phase-2 echo: prove the request contract round-trips intact.
            return Message(
                id=msg.id,
                type=MsgType.HTTP_RESPONSE,
                body={
                    "status": 200,
                    "headers": {},
                    "echo": {
                        "method": msg.body.get("method"),
                        "path": msg.body.get("path"),
                        "body": msg.body.get("body"),
                        "context": msg.body.get("context"),
                    },
                },
            )
        return Message(id=msg.id, type=MsgType.ERROR, body={"error": "unsupported"})

    return handler


async def run_worker(address: str) -> None:
    """Connect back to the host, serve requests until the connection closes."""
    reader, writer = await connect_to_host(address)
    channel = RpcChannel(reader, writer, request_handler=build_worker_handler())
    channel.start()
    try:
        await channel.wait_closed()
    finally:
        await channel.close()


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="plugin-sandbox-worker")
    parser.add_argument(
        "--connect",
        required=True,
        help="host callback address: 'unix:<path>' or 'tcp:<host>:<port>'",
    )
    args = parser.parse_args(argv)
    asyncio.run(run_worker(args.connect))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Tests ausführen, Erfolg verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_worker.py -v` (aus `backend/`)
Expected: PASS (5 passed).

- [ ] **Step 6: Gesamte Sandbox-Suite + Lint**

Run: `python -m pytest tests/plugins/sandbox/ -v` (aus `backend/`)
Expected: PASS (alle Phase-1 + Phase-2a Tests; bestätige den Pass-Count und dass keine neuen `Task was destroyed`/`Task exception was never retrieved`-Warnings auftauchen).

Run: `ruff check app/plugins/sandbox/ tests/plugins/sandbox/` (aus `backend/`)
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add backend/app/plugins/sandbox/channel.py backend/app/plugins/sandbox/worker.py backend/tests/plugins/sandbox/test_worker.py
git commit -m "feat(plugin-sandbox): worker entry point with health/echo handler + RpcChannel.wait_closed (Track B Phase 2a)"
```

---

## Definition of Done (Phase 2a)

- `backend/app/plugins/sandbox/{transport,worker}.py` existieren, lint-clean.
- `RpcChannel.wait_closed()` ergänzt (additiv, kein Verhalten der bestehenden Methoden geändert).
- `python -m pytest tests/plugins/sandbox/ -v` grün (Phase 1 + 2a).
- Transport wählt UDS auf Linux, Loopback-TCP auf Windows — beide Pfade durch denselben Roundtrip-Test abgedeckt (der jeweils plattformaktive Pfad läuft in CI/lokal).
- Kein echter Subprozess in dieser Phase; Phase 2b (Supervisor) kann `WorkerListener` + `python -m app.plugins.sandbox.worker --connect <addr>` konsumieren.
- Keine neue Dependency.

---

## Self-Review (gegen Spec)

- **UDS prod / TCP dev, plattformgewählt, nicht plugin-konfigurierbar** → Task 1 (`_use_unix_socket`, `WorkerListener`) + Global Constraints. ✓ (Deckt Spec „Windows-Dev-Fallback" + „UDS ist der einzige Außen-Kanal" in prod.)
- **Worker verbindet zurück, spannt RpcChannel auf, beantwortet Requests** → Task 2 (`run_worker` + `build_worker_handler`). ✓
- **Worker-Entry per `python -m … --connect <addr>`** (für Phase-2b-Spawn) → Task 2 (`main`/argparse/`__main__`). ✓
- **Request-Contract round-trip** (method/path/body/context) → Echo-Handler + `test_worker_echoes_http_request`. ✓ (Voller kuratierter Contract + Header-Allowlist = Phase 4.)
- **Lifecycle health-ping** (vom Supervisor-Handshake in 2b gebraucht) → Health-Handler + Test. ✓
- Bewusst NICHT in 2a (spätere Phasen): echter Subprozess-Spawn/Supervision/Restart (2b), echtes Plugin-Loading + Capability-Dispatch (3, ersetzt den Echo-Handler), Low-Priv-User/netns (5), Auth/Gating/Header-Allowlist/Scrubbing (4). Der Echo-Handler ist ein bewusster Platzhalter, kein Überbau.
- **Keine Platzhalter** im Plan; vollständiger Code in jedem Code-Step; `wait_closed()` additiv und konsistent mit dem `_read_task`-Attribut aus Phase 1.
