# Plugin-Backend-Isolation — Phase 1: RPC-Fundament — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Baue die isolierte, voll-duplexe RPC-Transportschicht (msgpack-Framing über UDS/Socket + `RpcChannel` mit Correlation-IDs und reentranter Request-Dispatch), auf der alle weiteren Track-B-Phasen aufsetzen.

**Architecture:** Zwei kleine, FastAPI-/Subprozess-freie Module unter `backend/app/plugins/sandbox/`: `protocol.py` (Frame-Codec + Nachrichtentypen) und `channel.py` (`RpcChannel`: asynchroner Lese-Loop, Pending-Future-Map, reentrante Handler-Dispatch). Beide Seiten (Host und späterer Sandbox-Worker) nutzen denselben `RpcChannel` spiegelbildlich. Vollständig in-process über `socket.socketpair()` testbar — keine echten Subprozesse in dieser Phase.

**Tech Stack:** Python 3.11, asyncio, `msgpack` (neue Dependency), pytest + pytest-asyncio (`asyncio_mode=auto`).

## Global Constraints

- Python `>=3.11`; async/await für alle I/O; Type-Hints auf allen Funktionen (Backend-Coding-Style).
- Tests: pytest, `asyncio_mode="auto"` → async-Tests sind schlicht `async def test_...`, **kein** `@pytest.mark.asyncio`-Decorator.
- Test-DB-Fixture heißt `db_session` (für spätere Phasen; Phase 1 braucht keine DB).
- Keine `shell=True`, keine rohen SQL mit User-Input (Security-Invarianten) — in dieser Phase ohnehin nicht berührt.
- Repo läuft mit `core.autocrlf=true` auf Windows; neue Dateien werden als LF geschrieben (Git normalisiert).
- Branch: `feat/plugin-backend-isolation` (existiert bereits, enthält die Spec).
- Commit-Message-Stil: `feat(plugin-sandbox): …` / `test(plugin-sandbox): …`.
- Spec: `docs/superpowers/specs/2026-06-26-plugin-backend-isolation-design.md` (Abschnitt „RPC-Protokoll").

---

## Phasen-Roadmap (Kontext — nur Phase 1 ist in diesem Plan)

Track B ist eine sequenzielle Schichtung; jede Phase bekommt einen eigenen Plan:

1. **Phase 1 — RPC-Fundament** ← *dieser Plan*. Frame-Codec + `RpcChannel`. Deliverable: getestete Transportschicht, standalone.
2. Phase 2 — Sandbox-Worker + `SandboxSupervisor` (Low-Priv-Subprozess-Spawn, UDS, Health-Handshake, Restart-Budget, Primary-Worker-Ownership).
3. Phase 3 — Capability-Layer + Plugin-SDK (`CapabilityRouter` default-deny, `storage.*` via `plugin_storage_service`, `core.*`-Startkatalog, request-gebundener User-Kontext).
4. Phase 4 — Request-Proxy + `PluginManager`-Dual-Path (FastAPI-Catch-all, Auth/Gating, Header-Allowlist, Error-Scrubbing, Manifest/Scope-Wiring).
5. Phase 5 — Deploy-Härtung (OS-User-Provisioning, Netzwerk-Namespace) + Frontend-Doku-Update (`PluginDocumentation.tsx` + `plugins`-Locales).

---

## File Structure (Phase 1)

| Datei | Verantwortung |
|---|---|
| `backend/app/plugins/sandbox/__init__.py` (neu) | Package-Marker, kurzer Modul-Docstring. |
| `backend/app/plugins/sandbox/protocol.py` (neu) | `Message`-Dataclass, `MsgType`-Konstanten, `REQUEST_TYPES`/`RESPONSE_TYPES`, `FrameError`, `MAX_FRAME_BYTES`, `encode_frame`/`decode_payload`/`read_frame`/`write_frame`. |
| `backend/app/plugins/sandbox/channel.py` (neu) | `RpcChannel`: Lese-Loop, `call()`, reentrante Dispatch, Pending-Map, `close()`. |
| `backend/tests/plugins/sandbox/__init__.py` (neu) | Test-Package-Marker. |
| `backend/tests/plugins/sandbox/test_protocol.py` (neu) | Frame-Roundtrip, EOF, Oversize, Malformed-Envelope. |
| `backend/tests/plugins/sandbox/test_channel.py` (neu) | Happy-Path call/response, Timeout, Reentranz, Malformed-Drop, Close-fails-pending. |
| `backend/pyproject.toml` (modify) | `msgpack`-Dependency hinzufügen. |

---

## Task 1: Frame-Codec & Nachrichtentypen (`protocol.py`)

**Files:**
- Modify: `backend/pyproject.toml` (dependencies-Block, nach `"dbus-next>=0.2.3,<1.0.0"`)
- Create: `backend/app/plugins/sandbox/__init__.py`
- Create: `backend/app/plugins/sandbox/protocol.py`
- Create: `backend/tests/plugins/sandbox/__init__.py`
- Test: `backend/tests/plugins/sandbox/test_protocol.py`

**Interfaces:**
- Consumes: nichts (Fundament).
- Produces:
  - `Message(id: int, type: str, body: dict)` — Dataclass (Gleichheit per Value).
  - `class MsgType` mit `HTTP_REQUEST`, `HTTP_RESPONSE`, `CAP_CALL`, `CAP_RESULT`, `LIFECYCLE`, `ERROR` (alle `str`).
  - `REQUEST_TYPES: frozenset[str]`, `RESPONSE_TYPES: frozenset[str]`.
  - `MAX_FRAME_BYTES: int`, `FrameError(Exception)`.
  - `encode_frame(msg: Message) -> bytes`
  - `decode_payload(payload: bytes) -> Message`
  - `async read_frame(reader: asyncio.StreamReader) -> Message | None` (None bei sauberem EOF)
  - `async write_frame(writer: asyncio.StreamWriter, msg: Message) -> None`

- [ ] **Step 1: msgpack-Dependency hinzufügen**

In `backend/pyproject.toml` im `dependencies = [ ... ]`-Block die letzte Zeile
`"dbus-next>=0.2.3,<1.0.0"` um ein Komma ergänzen und eine Zeile anhängen:

```toml
  "dbus-next>=0.2.3,<1.0.0",
  "msgpack>=1.0.0,<2.0.0"
```

Dann installieren:

Run: `pip install -e ".[dev]"` (aus `backend/`)
Expected: Installation erfolgreich, `msgpack` vorhanden.

- [ ] **Step 2: Failing test schreiben**

Create `backend/tests/plugins/sandbox/__init__.py` mit einer einzigen Zeile:

```python
"""Tests for the plugin sandbox RPC layer."""
```

Create `backend/tests/plugins/sandbox/test_protocol.py`:

```python
"""Tests for the sandbox RPC frame codec and message types."""
import asyncio

import msgpack
import pytest

from app.plugins.sandbox.protocol import (
    FrameError,
    MAX_FRAME_BYTES,
    Message,
    MsgType,
    REQUEST_TYPES,
    RESPONSE_TYPES,
    _LENGTH_PREFIX,
    decode_payload,
    encode_frame,
    read_frame,
)


def _reader(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


async def test_frame_roundtrip():
    msg = Message(id=7, type=MsgType.HTTP_REQUEST, body={"method": "GET", "path": "x"})
    out = await read_frame(_reader(encode_frame(msg)))
    assert out == msg


async def test_read_frame_returns_none_on_clean_eof():
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await read_frame(reader) is None


async def test_read_frame_rejects_oversize_length():
    reader = _reader(_LENGTH_PREFIX.pack(MAX_FRAME_BYTES + 1))
    with pytest.raises(FrameError):
        await read_frame(reader)


async def test_decode_payload_rejects_non_envelope():
    with pytest.raises(FrameError):
        decode_payload(msgpack.packb([1, 2, 3], use_bin_type=True))


def test_request_response_type_partition():
    assert REQUEST_TYPES.isdisjoint(RESPONSE_TYPES)
    assert MsgType.HTTP_REQUEST in REQUEST_TYPES
    assert MsgType.HTTP_RESPONSE in RESPONSE_TYPES
```

- [ ] **Step 3: Test ausführen, Fehlschlag verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_protocol.py -v` (aus `backend/`)
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.plugins.sandbox'`.

- [ ] **Step 4: Minimal-Implementierung schreiben**

Create `backend/app/plugins/sandbox/__init__.py`:

```python
"""Plugin sandbox: isolated RPC runtime for external plugins (Track B)."""
```

Create `backend/app/plugins/sandbox/protocol.py`:

```python
"""Frame codec and message envelope for the plugin sandbox RPC layer.

A frame on the wire is a 4-byte big-endian length prefix followed by a
msgpack-encoded envelope ``{"id": int, "type": str, "body": dict}``. The same
codec is used by both ends of the channel (host and sandbox worker).
"""
import asyncio
import struct
from dataclasses import dataclass, field
from typing import Any, Optional

import msgpack

# Hard cap on a single frame's payload to bound memory and reject malformed
# length prefixes from an untrusted peer.
MAX_FRAME_BYTES: int = 16 * 1024 * 1024  # 16 MiB

_LENGTH_PREFIX = struct.Struct(">I")  # 4-byte big-endian unsigned length


class MsgType:
    """Envelope ``type`` values. Requests expect a correlated response."""

    HTTP_REQUEST = "http_request"
    HTTP_RESPONSE = "http_response"
    CAP_CALL = "cap_call"
    CAP_RESULT = "cap_result"
    LIFECYCLE = "lifecycle"
    ERROR = "error"


# A side routes inbound frames by category: request types go to the request
# handler, response types resolve a pending outbound call.
REQUEST_TYPES = frozenset({MsgType.HTTP_REQUEST, MsgType.CAP_CALL, MsgType.LIFECYCLE})
RESPONSE_TYPES = frozenset({MsgType.HTTP_RESPONSE, MsgType.CAP_RESULT, MsgType.ERROR})


class FrameError(Exception):
    """Raised when a frame is malformed, truncated, or exceeds MAX_FRAME_BYTES."""


@dataclass
class Message:
    """A single RPC envelope."""

    id: int
    type: str
    body: dict[str, Any] = field(default_factory=dict)


def encode_frame(msg: Message) -> bytes:
    """Serialize a Message to a length-prefixed msgpack frame."""
    payload = msgpack.packb(
        {"id": msg.id, "type": msg.type, "body": msg.body},
        use_bin_type=True,
    )
    if len(payload) > MAX_FRAME_BYTES:
        raise FrameError(f"frame too large: {len(payload)} > {MAX_FRAME_BYTES}")
    return _LENGTH_PREFIX.pack(len(payload)) + payload


def decode_payload(payload: bytes) -> Message:
    """Decode a msgpack payload (without length prefix) into a Message."""
    obj = msgpack.unpackb(payload, raw=False)
    if not isinstance(obj, dict) or "id" not in obj or "type" not in obj:
        raise FrameError("malformed envelope")
    body = obj.get("body") or {}
    if not isinstance(body, dict):
        raise FrameError("envelope body must be a map")
    return Message(id=int(obj["id"]), type=str(obj["type"]), body=body)


async def read_frame(reader: asyncio.StreamReader) -> Optional[Message]:
    """Read one frame. Returns None on a clean EOF (peer closed cleanly)."""
    try:
        prefix = await reader.readexactly(4)
    except asyncio.IncompleteReadError as exc:
        if not exc.partial:
            return None  # clean EOF at a frame boundary
        raise FrameError("truncated length prefix") from exc

    (length,) = _LENGTH_PREFIX.unpack(prefix)
    if length > MAX_FRAME_BYTES:
        raise FrameError(f"frame too large: {length} > {MAX_FRAME_BYTES}")

    try:
        payload = await reader.readexactly(length)
    except asyncio.IncompleteReadError as exc:
        raise FrameError("truncated frame body") from exc

    return decode_payload(payload)


async def write_frame(writer: asyncio.StreamWriter, msg: Message) -> None:
    """Serialize and write one frame, flushing the transport."""
    writer.write(encode_frame(msg))
    await writer.drain()
```

- [ ] **Step 5: Test ausführen, Erfolg verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_protocol.py -v` (aus `backend/`)
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/plugins/sandbox/__init__.py backend/app/plugins/sandbox/protocol.py backend/tests/plugins/sandbox/__init__.py backend/tests/plugins/sandbox/test_protocol.py
git commit -m "feat(plugin-sandbox): add RPC frame codec + message envelope (Track B Phase 1)"
```

---

## Task 2: Voll-duplexer `RpcChannel` (Happy-Path)

**Files:**
- Create: `backend/app/plugins/sandbox/channel.py`
- Test: `backend/tests/plugins/sandbox/test_channel.py`

**Interfaces:**
- Consumes: `Message`, `MsgType`, `REQUEST_TYPES`, `RESPONSE_TYPES`, `FrameError`, `read_frame`, `write_frame` aus `protocol.py`.
- Produces:
  - `RequestHandler = Callable[[Message], Awaitable[Message]]`
  - `class RpcChannel`:
    - `__init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, request_handler: RequestHandler | None = None)`
    - `start(self) -> None` — startet den Lese-Loop (idempotent).
    - `async call(self, type: str, body: dict, *, timeout: float | None = None) -> Message` — sendet eine neue Nachricht mit frischer ID, wartet auf die korrelierte Antwort. Wirft `asyncio.TimeoutError` bei Timeout, `ConnectionError` wenn Kanal geschlossen.
    - `async close(self) -> None` — Lese-Loop abbrechen, Writer schließen, alle Pending-Futures mit `ConnectionError` failen.

Dispatch-Semantik: Eingehende **Request-Typen** werden an `request_handler` übergeben (in eigener Task → erlaubt Reentranz); dessen zurückgegebene `Message` wird mit der **ID des Requests** zurückgeschickt. Eingehende **Response-Typen** lösen das Pending-Future mit der passenden ID.

- [ ] **Step 1: Failing test schreiben**

Create `backend/tests/plugins/sandbox/test_channel.py`:

```python
"""Tests for the duplex RpcChannel (happy path)."""
import asyncio

import pytest

from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType


async def _connect(handler_a=None, handler_b=None):
    # Loopback-TCP-Paar statt socket.socketpair()+open_connection(sock=…):
    # portabel über Linux UND Windows (ProactorEventLoop akzeptiert ein
    # vorab-connectetes `sock=` nicht zuverlässig); kein Subprozess nötig.
    accepted: dict[str, tuple] = {}
    ready = asyncio.Event()

    async def _on_client(reader, writer):
        accepted["pair"] = (reader, writer)
        ready.set()

    server = await asyncio.start_server(_on_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    a_reader, a_writer = await asyncio.open_connection(host, port)
    await ready.wait()
    b_reader, b_writer = accepted["pair"]
    server.close()

    ch_a = RpcChannel(a_reader, a_writer, request_handler=handler_a)
    ch_b = RpcChannel(b_reader, b_writer, request_handler=handler_b)
    ch_a.start()
    ch_b.start()
    return ch_a, ch_b


async def test_call_returns_handler_response():
    async def handler(msg: Message) -> Message:
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={"echo": msg.body["v"]})

    ch_a, ch_b = await _connect(handler_b=handler)
    try:
        resp = await ch_a.call(MsgType.HTTP_REQUEST, {"v": "hi"}, timeout=5)
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body == {"echo": "hi"}
    finally:
        await ch_a.close()
        await ch_b.close()


async def test_call_times_out_when_handler_is_slow():
    async def slow(msg: Message) -> Message:
        await asyncio.sleep(10)
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={})

    ch_a, ch_b = await _connect(handler_b=slow)
    try:
        with pytest.raises(asyncio.TimeoutError):
            await ch_a.call(MsgType.HTTP_REQUEST, {}, timeout=0.1)
    finally:
        await ch_a.close()
        await ch_b.close()
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_channel.py -v` (aus `backend/`)
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.plugins.sandbox.channel'`.

- [ ] **Step 3: Implementierung schreiben**

Create `backend/app/plugins/sandbox/channel.py`:

```python
"""Full-duplex RPC channel over a paired StreamReader/StreamWriter.

Both ends are symmetric: each can issue ``call()`` (outbound request → awaited
response) and each may serve inbound requests via a ``request_handler``. Inbound
requests are dispatched in their own task, so a handler may itself issue a
``call()`` back to the peer while the original request is still in flight
(reentrancy) — required for an http_request handler that needs a cap_call.
"""
import asyncio
import itertools
import logging
from typing import Awaitable, Callable, Optional

from app.plugins.sandbox.protocol import (
    FrameError,
    Message,
    MsgType,
    REQUEST_TYPES,
    RESPONSE_TYPES,
    read_frame,
    write_frame,
)

logger = logging.getLogger(__name__)

RequestHandler = Callable[[Message], Awaitable[Message]]


class RpcChannel:
    """A symmetric, reentrant RPC channel."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        request_handler: Optional[RequestHandler] = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._request_handler = request_handler
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._dispatch_tasks: set[asyncio.Task] = set()
        self._closed = False

    def start(self) -> None:
        """Start the read loop (idempotent)."""
        if self._read_task is None:
            self._read_task = asyncio.create_task(self._read_loop())

    async def call(
        self, type: str, body: dict, *, timeout: Optional[float] = None
    ) -> Message:
        """Send a request and await the correlated response."""
        if self._closed:
            raise ConnectionError("channel closed")
        msg_id = next(self._ids)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        try:
            await write_frame(self._writer, Message(id=msg_id, type=type, body=body))
            if timeout is not None:
                return await asyncio.wait_for(fut, timeout)
            return await fut
        finally:
            self._pending.pop(msg_id, None)

    async def _read_loop(self) -> None:
        try:
            while True:
                try:
                    msg = await read_frame(self._reader)
                except (FrameError, OSError) as exc:
                    logger.warning("rpc: dropping connection: %s", exc)
                    break
                if msg is None:
                    break  # clean EOF
                if msg.type in RESPONSE_TYPES:
                    self._resolve(msg)
                elif msg.type in REQUEST_TYPES:
                    task = asyncio.create_task(self._dispatch(msg))
                    self._dispatch_tasks.add(task)
                    task.add_done_callback(self._dispatch_tasks.discard)
                else:
                    logger.warning("rpc: unknown message type %r", msg.type)
        finally:
            self._closed = True
            self._fail_all(ConnectionError("channel closed"))

    def _resolve(self, msg: Message) -> None:
        fut = self._pending.get(msg.id)
        if fut is None or fut.done():
            logger.warning("rpc: response for unknown/settled id %s", msg.id)
            return
        fut.set_result(msg)

    async def _dispatch(self, msg: Message) -> None:
        if self._request_handler is None:
            await self._safe_write(
                Message(id=msg.id, type=MsgType.ERROR, body={"error": "no_handler"})
            )
            return
        try:
            response = await self._request_handler(msg)
        except Exception:
            logger.exception("rpc: request handler failed")
            await self._safe_write(
                Message(id=msg.id, type=MsgType.ERROR, body={"error": "handler_failed"})
            )
            return
        response.id = msg.id  # always correlate to the request id
        await self._safe_write(response)

    async def _safe_write(self, msg: Message) -> None:
        try:
            await write_frame(self._writer, msg)
        except Exception:
            logger.exception("rpc: failed to write frame")

    def _fail_all(self, exc: Exception) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()

    async def close(self) -> None:
        """Cancel the read loop, close the writer, fail pending calls."""
        self._closed = True
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass
        self._fail_all(ConnectionError("channel closed"))
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `python -m pytest tests/plugins/sandbox/test_channel.py -v` (aus `backend/`)
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/sandbox/channel.py backend/tests/plugins/sandbox/test_channel.py
git commit -m "feat(plugin-sandbox): add duplex RpcChannel with correlation IDs (Track B Phase 1)"
```

---

## Task 3: Reentranz & Robustheit (Adversarial-Tests)

**Files:**
- Test: `backend/tests/plugins/sandbox/test_channel.py` (erweitern)

**Interfaces:**
- Consumes: `RpcChannel`, `_connect`-Helper (aus Task 2), `Message`, `MsgType`.
- Produces: keine neuen Symbole — verifiziert das in Task 2 gebaute Verhalten unter Reentranz, Malformed-Input und Teardown.

Begründung: Reentranz, Malformed-Drop und Pending-Fail sind bereits in der `RpcChannel`-Implementierung (Task 2) angelegt (Dispatch in eigener Task, `FrameError`-Bruch, `_fail_all`). Diese Task verifiziert sie adversarial — ein Reviewer kann diese Garantien unabhängig vom Happy-Path freigeben.

- [ ] **Step 1: Failing tests schreiben**

An `backend/tests/plugins/sandbox/test_channel.py` anhängen (`import socket` und `import struct` oben im File ergänzen; `pytest` ist seit Task 2 bereits importiert):

```python
async def test_reentrant_cap_call_during_request():
    # Host answers cap_call; plugin issues a cap_call while serving http_request.
    async def host_handler(msg: Message) -> Message:
        assert msg.type == MsgType.CAP_CALL
        return Message(id=msg.id, type=MsgType.CAP_RESULT, body={"value": "42"})

    channels: dict[str, RpcChannel] = {}

    async def plugin_handler(msg: Message) -> Message:
        result = await channels["plugin"].call(
            MsgType.CAP_CALL, {"capability": "storage.get"}, timeout=5
        )
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={"got": result.body["value"]})

    ch_a, ch_b = await _connect(handler_a=host_handler, handler_b=plugin_handler)
    channels["plugin"] = ch_b
    try:
        resp = await ch_a.call(MsgType.HTTP_REQUEST, {}, timeout=5)
        assert resp.body == {"got": "42"}
    finally:
        await ch_a.close()
        await ch_b.close()


async def test_malformed_frame_drops_connection():
    # Ein roher Loopback-Client schickt ein bogus Oversize-Längenpräfix; der
    # RpcChannel auf der Server-Seite muss FrameError auslösen und abbauen
    # (statt 4 GiB zu allokieren). Loopback-TCP wie im _connect-Helper.
    accepted: dict[str, tuple] = {}
    ready = asyncio.Event()

    async def _on_client(reader, writer):
        accepted["pair"] = (reader, writer)
        ready.set()

    server = await asyncio.start_server(_on_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    raw = socket.create_connection((host, port))
    await ready.wait()
    s_reader, s_writer = accepted["pair"]
    server.close()

    ch = RpcChannel(s_reader, s_writer)
    ch.start()
    try:
        raw.sendall(struct.pack(">I", 0xFFFFFFFF))
        await asyncio.sleep(0.1)
        with pytest.raises(ConnectionError):
            await ch.call(MsgType.HTTP_REQUEST, {}, timeout=2)
    finally:
        await ch.close()
        raw.close()


async def test_close_fails_inflight_call():
    async def never(msg: Message) -> Message:
        await asyncio.sleep(100)
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={})

    ch_a, ch_b = await _connect(handler_b=never)
    task = asyncio.create_task(ch_a.call(MsgType.HTTP_REQUEST, {}))
    await asyncio.sleep(0.05)
    await ch_a.close()
    with pytest.raises(ConnectionError):
        await task
    await ch_b.close()
```

- [ ] **Step 2: Tests ausführen, Fehlschlag/Status prüfen**

Run: `python -m pytest tests/plugins/sandbox/test_channel.py -v` (aus `backend/`)
Expected: Die drei neuen Tests laufen durch (PASS), da `RpcChannel` aus Task 2 das Verhalten bereits implementiert. Falls einer fehlschlägt → Bug in Task 2, dort fixen (nicht den Test aufweichen).

> Hinweis: Diese Task ist test-getrieben gegen bereits existierenden Code (Reentranz/Robustheit waren Designziel von Task 2). Sollte ein Test rot sein, ist das ein echter Defekt in `channel.py` — beheben und erst dann fortfahren.

- [ ] **Step 3: Gesamte Sandbox-Suite grün verifizieren**

Run: `python -m pytest tests/plugins/sandbox/ -v` (aus `backend/`)
Expected: PASS (alle Protocol- + Channel-Tests, 10 passed).

- [ ] **Step 4: Lint**

Run: `ruff check app/plugins/sandbox/ tests/plugins/sandbox/` (aus `backend/`)
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add backend/tests/plugins/sandbox/test_channel.py
git commit -m "test(plugin-sandbox): reentrancy + malformed-frame + teardown robustness (Track B Phase 1)"
```

---

## Definition of Done (Phase 1)

- `backend/app/plugins/sandbox/{__init__,protocol,channel}.py` existieren und sind lint-clean.
- `python -m pytest tests/plugins/sandbox/ -v` ist grün (Protocol + Channel, inkl. Reentranz-, Malformed- und Teardown-Tests).
- `msgpack` ist in `backend/pyproject.toml` deklariert und installiert.
- Keine FastAPI-/Subprozess-/DB-Abhängigkeit in dieser Phase (reine Transportschicht).
- Phase 2 kann `RpcChannel` + `protocol`-Symbole konsumieren, ohne Phase-1-Interna zu kennen.

---

## Self-Review (gegen Spec-Abschnitt „RPC-Protokoll")

- **Längen-präfixierte msgpack-Frames** → Task 1 (`encode_frame`/`read_frame`, `_LENGTH_PREFIX` + msgpack). ✓
- **Voll-Duplex, reentrant, Correlation-IDs, Pending-Map** → Task 2 (`call`/`_pending`/`_dispatch` in eigener Task) + Task 3 (Reentranz-Test). ✓
- **Request-/Response-Typ-Partition** (Routing nach Kategorie) → Task 1 (`REQUEST_TYPES`/`RESPONSE_TYPES`) + Test. ✓
- **Malformed Frame → Connection-Drop** → Task 2 (`FrameError`-Bruch im Lese-Loop) + Task 3 (Oversize-Prefix-Test). ✓
- **Body-Size-Cap** → Task 1 (`MAX_FRAME_BYTES`, geprüft in `encode_frame` und `read_frame`) + Oversize-Test. ✓
- **Per-Request-Timeout** → Task 2 (`call(..., timeout=)` → `asyncio.TimeoutError`) + Timeout-Test. ✓
- Nicht in Phase 1 (bewusst, spätere Phasen): kuratierter Request-Contract/Header-Allowlist (Phase 4), `cap_call`-Dispatch-Gating (Phase 3), Subprozess-Spawn/Health/Restart (Phase 2). Diese Phase liefert nur den generischen Transport, auf dem sie aufsetzen.
