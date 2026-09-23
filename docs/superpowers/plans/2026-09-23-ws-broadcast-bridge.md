# Prozessübergreifende WebSocket-Brücke — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Broadcast, der in irgendeinem BaluHost-Prozess entsteht, erreicht jede WebSocket-Verbindung, für die er bestimmt ist — heute erreicht er nur die Sockets seines eigenen Prozesses.

**Architecture:** Ein Bus über Postgres `LISTEN`/`NOTIFY` mit der Nachricht in der `pg_notify`-Nutzlast. Jeder API-Prozess hält eine eigene Listener-Verbindung außerhalb des SQLAlchemy-Pools, am Event-Loop über `loop.add_reader`. Der `WebSocketManager` wird in „Umschlag bauen und publizieren" (die fünf bestehenden öffentlichen Methoden) und „lokal zustellen" (`deliver_local`) getrennt; zugestellt wird ausschließlich aus dem Listener.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, psycopg2-binary (bereits vorhanden — keine neue Abhängigkeit), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-23-ws-broadcast-bridge-design.md`

## Global Constraints

- **Keine neue Abhängigkeit, keine Alembic-Migration, keine Änderung an Unit-Templates.** `ci-deploy.sh` muss zum Ausrollen reichen (#689: Unit-Templates erreichen eine installierte Box nicht von selbst).
- **Kanalname:** `baluhost_ws`. **Nutzlastdeckel:** 7500 Byte (`pg_notify` erlaubt 8000). **Queue-Größe:** 1000.
- **Kein Aufrufer bekommt je eine Ausnahme aus dem Broadcast-Pfad.** Wenn wir dort ankommen, ist die DB-Zeile längst geschrieben; ein toter Socket darf einen erfolgreichen Vorgang nicht in einen Fehler verwandeln.
- **Zustellung nur aus dem Listener.** `publish()` stellt nie selbst zu — außer wenn die Listener-Verbindung getrennt ist (dann zusätzlich lokal, weil in der Lücke nichts nachgespielt wird).
- **Type Hints auf allen Funktionen, Docstrings auf allen Services** (`.claude/rules/backend/coding-style.md`).
- **Alle `subprocess`-Aufrufe mit Argumentlisten, kein `shell=True`** — in diesem Plan kommt kein Subprozess vor, die Regel gilt trotzdem.
- **`LISTEN` lässt sich nicht parametrisieren.** Der Kanalname ist eine Modulkonstante, nie Nutzereingabe. Das gehört als Kommentar an die Stelle, sonst liest es sich beim Security-Review wie ein SQL-Injection-Fund.
- **Testumgebung:** `python -m pytest` aus `backend/`. Auf dieser Maschine scheitert `tests/plugins/sandbox/test_phase3_e2e.py::test_e2e_storage_and_metrics_granted` vorbestehend (Issue #706, `AF_UNIX path too long` — Pfadlänge des Checkouts). **Kein `-x` verwenden**, sonst bricht der Lauf dort ab; stattdessen `--deselect tests/plugins/sandbox/test_phase3_e2e.py::test_e2e_storage_and_metrics_granted`.

---

## Dateien im Überblick

| Datei | Verantwortung |
|---|---|
| `backend/app/services/ws_bus.py` (neu) | Umschlag, Bus-Protocol, `LocalWsBus`, `PostgresWsBus`, `build_bus()` |
| `backend/app/services/websocket_manager.py` | Umschlag bauen + publizieren; `deliver_local()` als einzige Stelle, die Sockets anfasst; Gesamtobergrenze |
| `backend/app/core/lifespan.py` | Bus je Worker starten/stoppen; Primary-Wahl am Kanal |
| `backend/app/api/routes/_notification_fanout.py` | lokale Vorprüfung entfernen |
| `backend/scripts/monitoring_worker.py`, `backend/scripts/scheduler_worker.py` | Loop binden, Bus im Publish-Modus |
| `backend/scripts/debug/verify_ws_bus.py` (neu) | Verifikation gegen echtes Postgres |
| `backend/tests/services/test_ws_bus.py` (neu) | Bus-Verhalten |
| `backend/app/services/ws_bus_publisher.py` (neu) | Publish-Modus für die zwei emittierenden Worker-Skripte |
| `backend/tests/services/test_ws_bus_publisher.py` (neu) | dito, inkl. Loop-im-Thread |
| `backend/tests/core/test_lifespan_ws_bus.py` (neu) | Bus-Start je Worker |
| `backend/tests/services/test_websocket_manager.py` | angepasst auf Publish/Deliver-Trennung + Gesamtobergrenze |
| `backend/tests/plugins/test_dashboard_panel.py` | drei Zähler-Zusicherungen auf den Frame umgestellt (leicht zu übersehen) |
| `backend/tests/core/test_primary_worker_channel.py` (neu) | Primary-Wahl am Kanal |
| `backend/app/core/database.py` | Docstring: die gemessene Pool-Auslastung, damit niemand sie erneut rät |
| `backend/app/services/CLAUDE.md`, `backend/app/core/CLAUDE.md`, `.claude/rules/architecture.md`, `.claude/rules/security-agent.md`, `CLAUDE.md` | Dokumentation und Sicherheitsregel nachziehen |

Reihenfolge der Tasks: 1–2 bauen das Fundament (Umschlag, Manager-Trennung) und sind ohne Postgres testbar; 3–4 hängen den echten Transport an; 5–9 sind je ein eigenständiger Fix; 10 schließt ab.

---

### Task 1: Umschlag und lokaler Bus

**Files:**
- Create: `backend/app/services/ws_bus.py`
- Test: `backend/tests/services/test_ws_bus.py`

**Interfaces:**
- Consumes: nichts
- Produces: `WsEnvelope` (frozen dataclass, Felder `kind: str`, `msg_type: str`, `payload: Any`, `user_id: int | None = None`, `admins_only: bool = False`; Methoden `to_json() -> str`, statisch `from_json(raw: str) -> WsEnvelope | None`), `Deliver = Callable[[WsEnvelope], Awaitable[None]]`, `WsBus` (Protocol mit `publish`, `start`, `stop`), `LocalWsBus`, Konstanten `CHANNEL`, `MAX_PAYLOAD_BYTES`, `QUEUE_MAXSIZE`, `VALID_KINDS`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_ws_bus.py`:

```python
"""Tests for services/ws_bus.py — envelope, local bus, Postgres bus."""

import json

import pytest

from app.services.ws_bus import (
    CHANNEL,
    MAX_PAYLOAD_BYTES,
    LocalWsBus,
    WsEnvelope,
)


class TestEnvelope:
    def test_round_trip_user(self):
        env = WsEnvelope(kind="user", msg_type="notification", payload={"id": 7}, user_id=3)
        assert WsEnvelope.from_json(env.to_json()) == env

    def test_round_trip_all_with_admins_only(self):
        env = WsEnvelope(
            kind="all",
            msg_type="dashboard_panel_update",
            payload={"panel_type": "gauge"},
            admins_only=True,
        )
        assert WsEnvelope.from_json(env.to_json()) == env

    def test_round_trip_admins_keeps_user_id_none(self):
        env = WsEnvelope(kind="admins", msg_type="notification", payload={"id": 1})
        restored = WsEnvelope.from_json(env.to_json())
        assert restored is not None
        assert restored.user_id is None

    def test_payload_may_be_a_list(self):
        """smart_device_update sends a list, not a dict."""
        env = WsEnvelope(kind="all", msg_type="smart_device_update", payload=[{"device_id": 9}])
        assert WsEnvelope.from_json(env.to_json()) == env

    def test_from_json_rejects_broken_json(self):
        assert WsEnvelope.from_json("{not json") is None

    def test_from_json_rejects_unknown_kind(self):
        raw = json.dumps({"kind": "everyone", "msg_type": "notification", "payload": {}})
        assert WsEnvelope.from_json(raw) is None

    def test_from_json_rejects_missing_msg_type(self):
        raw = json.dumps({"kind": "all", "payload": {}})
        assert WsEnvelope.from_json(raw) is None

    def test_channel_is_a_bare_identifier(self):
        """It goes into LISTEN unquoted, so it must not need quoting."""
        assert CHANNEL.replace("_", "").isalnum()

    def test_payload_cap_leaves_headroom_below_pg_notify_limit(self):
        assert MAX_PAYLOAD_BYTES < 8000


@pytest.mark.asyncio
class TestLocalWsBus:
    async def test_publish_delivers_immediately(self):
        seen: list[WsEnvelope] = []

        async def deliver(env: WsEnvelope) -> None:
            seen.append(env)

        bus = LocalWsBus(deliver)
        env = WsEnvelope(kind="admins", msg_type="notification", payload={"id": 1})
        await bus.publish(env)
        assert seen == [env]

    async def test_publish_without_deliver_is_a_noop(self):
        bus = LocalWsBus()
        await bus.publish(WsEnvelope(kind="admins", msg_type="notification", payload={}))

    async def test_start_sets_the_deliver_callback(self):
        seen: list[WsEnvelope] = []
        bus = LocalWsBus()
        await bus.start(lambda env: _collect(seen, env))
        await bus.publish(WsEnvelope(kind="all", msg_type="unread_count", payload={"count": 2}))
        await bus.stop()
        assert len(seen) == 1


async def _collect(sink: list, env) -> None:
    sink.append(env)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_ws_bus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ws_bus'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/ws_bus.py`:

```python
"""Cross-process bus for WebSocket broadcasts.

A broadcast used to reach only the sockets of the process that produced it:
the WebSocketManager keeps its connections in a process-local dict, and
production runs six API processes across two systemd units. Roughly three out
of four notifications never reached the client that was waiting for them
(#685).

Everything on this bus is ephemeral live state that refreshes within seconds.
It is deliberately not durable: a client that is not listening when a message
is published does not get it later. For critical notifications the tray's REST
resync is the safety net.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Protocol

logger = logging.getLogger(__name__)

# The NOTIFY channel. Goes into `LISTEN <name>` unquoted — LISTEN cannot be
# parameterised — so this must stay a bare identifier and a module constant.
# It is never derived from user input.
CHANNEL = "baluhost_ws"

# The invariant belongs next to the constant, not only in a test: LISTEN takes
# an identifier and cannot be parameterised, so this name is interpolated into
# SQL. Asserting the shape here makes a future rename that breaks it fail at
# import instead of at runtime.
assert re.fullmatch(r"[a-z_][a-z0-9_]*", CHANNEL), "CHANNEL must be a bare identifier"

# pg_notify caps its payload at 8000 bytes. We watch below that and drop
# anything larger with a warning rather than letting psycopg2 raise.
MAX_PAYLOAD_BYTES = 7500

# Bounded so a burst cannot grow without limit. Oldest goes first.
QUEUE_MAXSIZE = 1000

VALID_KINDS = frozenset({"user", "admins", "all"})

Deliver = Callable[["WsEnvelope"], Awaitable[None]]


@dataclass(frozen=True)
class WsEnvelope:
    """One broadcast, with the addressing the WebSocketManager needs.

    kind is the audience: a single user, every admin, or everyone. msg_type is
    the type that reaches the wire unchanged — the client matches on it.
    """

    kind: str
    msg_type: str
    payload: Any
    user_id: Optional[int] = None
    admins_only: bool = False

    def __post_init__(self) -> None:
        """Reject an unknown kind at construction, not at delivery.

        deliver_local() dispatches on kind and its final branch is the
        permissive one ("all"). A typo like kind="admin" would therefore reach
        every socket. from_json() already validates, but envelopes are also
        built directly in-process, and those paths deserve the same guard.
        """
        if self.kind not in VALID_KINDS:
            raise ValueError(f"unknown envelope kind: {self.kind!r}")

    def to_json(self) -> str:
        """Serialise for the NOTIFY payload. Raises on unserialisable payloads."""
        return json.dumps(
            {
                "kind": self.kind,
                "msg_type": self.msg_type,
                "payload": self.payload,
                "user_id": self.user_id,
                "admins_only": self.admins_only,
            },
            separators=(",", ":"),
        )

    @staticmethod
    def from_json(raw: str) -> Optional["WsEnvelope"]:
        """Parse a NOTIFY payload, or None when it is not one of ours.

        Never raises: anything on the channel that we cannot read is dropped
        with a warning. A foreign notification must not kill the consumer.
        """
        try:
            data = json.loads(raw)
        except ValueError as exc:
            logger.warning("ws bus: unreadable payload dropped: %s", exc)
            return None

        if not isinstance(data, dict):
            logger.warning("ws bus: payload is not an object, dropped")
            return None

        kind = data.get("kind")
        msg_type = data.get("msg_type")
        if kind not in VALID_KINDS:
            logger.warning("ws bus: unknown kind %r dropped", kind)
            return None
        if not isinstance(msg_type, str) or not msg_type:
            logger.warning("ws bus: missing msg_type dropped")
            return None

        user_id = data.get("user_id")
        if user_id is not None and not isinstance(user_id, int):
            logger.warning("ws bus: non-integer user_id %r dropped", user_id)
            return None

        # admins_only must be an explicit bool, not a default. Every other check
        # here fails closed; a `bool(data.get("admins_only", False))` would be
        # the single field that fails OPEN — an envelope that parses but lost
        # the flag would deliver an admin_only dashboard panel to every socket,
        # which is exactly the leak the REST is_privileged() gate exists to
        # prevent (plugins/CLAUDE.md: "Beides ist nötig").
        admins_only = data.get("admins_only")
        if not isinstance(admins_only, bool):
            logger.warning(
                "ws bus: %s envelope without a boolean admins_only dropped", msg_type
            )
            return None

        return WsEnvelope(
            kind=kind,
            msg_type=msg_type,
            payload=data.get("payload"),
            user_id=user_id,
            admins_only=admins_only,
        )


class WsBus(Protocol):
    """Transport for envelopes between processes."""

    async def publish(self, env: WsEnvelope) -> None:
        ...

    async def start(self, deliver: Optional[Deliver]) -> None:
        ...

    async def stop(self) -> None:
        ...


class LocalWsBus:
    """Single-process bus: publish delivers straight away.

    This is the dev/SQLite path and what the tests run against. It is also the
    shape the Postgres bus falls back to while its listener is reconnecting.
    """

    def __init__(self, deliver: Optional[Deliver] = None) -> None:
        self._deliver = deliver

    async def publish(self, env: WsEnvelope) -> None:
        if self._deliver is None:
            return
        await self._deliver(env)

    async def start(self, deliver: Optional[Deliver]) -> None:
        self._deliver = deliver

    async def stop(self) -> None:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_ws_bus.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ws_bus.py backend/tests/services/test_ws_bus.py
git commit -m "feat(ws): Umschlag und lokaler Bus für prozessübergreifende Broadcasts (#685)"
```

---

### Task 2: WebSocketManager — publizieren und zustellen trennen

**Files:**
- Modify: `backend/app/services/websocket_manager.py` (die fünf Sendemethoden, `__init__`)
- Test: `backend/tests/services/test_websocket_manager.py` (bestehende Zusicherungen auf Rückgabewerte umstellen)

**Interfaces:**
- Consumes: `WsEnvelope`, `LocalWsBus`, `Deliver` aus Task 1
- Produces: `WebSocketManager.__init__(self, bus: WsBus | None = None)`, `WebSocketManager.deliver_local(env: WsEnvelope) -> int`, `WebSocketManager.set_bus(bus: WsBus) -> None`; die fünf Methoden `broadcast_to_user(user_id: int, message: dict) -> None`, `broadcast_to_admins(message: dict) -> None`, `broadcast_typed(msg_type: str, payload: Any, admins_only: bool = False) -> None`, `send_unread_count(user_id: int, count: int) -> None`, `send_notification_state(user_id: int, ids: list[int], action: str) -> None`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_ws_bus.py`:

```python
@pytest.mark.asyncio
class TestManagerPublishesEnvelopes:
    """The five public methods build envelopes; they no longer touch sockets."""

    async def test_each_method_builds_its_envelope(self):
        from app.services.websocket_manager import WebSocketManager

        sent: list[WsEnvelope] = []

        class FakeBus:
            async def publish(self, env):
                sent.append(env)

            async def start(self, deliver):
                pass

            async def stop(self):
                pass

        manager = WebSocketManager(bus=FakeBus())

        await manager.broadcast_to_user(3, {"id": 7})
        await manager.broadcast_to_admins({"id": 8})
        await manager.broadcast_typed("smart_device_update", [{"device_id": 1}])
        await manager.broadcast_typed("dashboard_panel_update", {"a": 1}, admins_only=True)
        await manager.send_unread_count(3, 5)
        await manager.send_notification_state(3, [7, 8], "read")

        assert sent[0] == WsEnvelope(kind="user", msg_type="notification", payload={"id": 7}, user_id=3)
        assert sent[1] == WsEnvelope(kind="admins", msg_type="notification", payload={"id": 8})
        assert sent[2] == WsEnvelope(
            kind="all", msg_type="smart_device_update", payload=[{"device_id": 1}]
        )
        assert sent[3] == WsEnvelope(
            kind="all", msg_type="dashboard_panel_update", payload={"a": 1}, admins_only=True
        )
        assert sent[4] == WsEnvelope(
            kind="user", msg_type="unread_count", payload={"count": 5}, user_id=3
        )
        assert sent[5] == WsEnvelope(
            kind="user",
            msg_type="notification_state",
            payload={"ids": [7, 8], "action": "read"},
            user_id=3,
        )

    async def test_publish_methods_return_none(self):
        """The publisher cannot know how many sockets were reached."""
        from app.services.websocket_manager import WebSocketManager

        manager = WebSocketManager()
        assert await manager.broadcast_to_user(1, {"id": 1}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_ws_bus.py::TestManagerPublishesEnvelopes -v`
Expected: FAIL — `TypeError: WebSocketManager.__init__() got an unexpected keyword argument 'bus'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/websocket_manager.py`, extend the constructor:

```python
    def __init__(self, bus: "WsBus | None" = None) -> None:
        """Initialize the WebSocket manager.

        Args:
            bus: Transport for broadcasts. Defaults to a LocalWsBus wired to
                this manager — the single-process behaviour, which is what dev
                mode and the tests want. Production replaces it via set_bus()
                with the Postgres bus, so a broadcast reaches the other five
                API processes too (#685).
        """
        # Map of user_id -> list of connections
        self._user_connections: dict[int, list[Connection]] = {}
        # Set of admin user_ids for admin broadcasts
        self._admin_users: set[int] = set()
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
        self._bus: "WsBus" = bus or LocalWsBus(self.deliver_local)

    def set_bus(self, bus: "WsBus") -> None:
        """Replace the transport. Called once at startup, before any publish."""
        self._bus = bus
```

Add the import at the top of the module (no `Deliver` — it is unused here, and ruff would flag it):

```python
from app.services.ws_bus import LocalWsBus, WsBus, WsEnvelope
```

And one new constant next to `MAX_CONNECTIONS_PER_USER`:

```python
# How long one socket may take a frame before it counts as dead. Delivery now
# runs through a single bus consumer task, so an unbounded send would let one
# client with a full TCP window freeze delivery for every user in this process.
SEND_TIMEOUT_SECONDS = 5.0
```

Replace the five send methods' bodies with envelope construction. `broadcast_to_user`:

```python
    async def broadcast_to_user(self, user_id: int, message: dict[str, Any]) -> None:
        """Publish a notification for one user's connections.

        Returns nothing on purpose: delivery happens in every process that
        holds a connection, so the publisher cannot count sockets. Use
        deliver_local()'s return value when you need the local number.
        """
        await self._bus.publish(
            WsEnvelope(kind="user", msg_type="notification", payload=message, user_id=user_id)
        )

    async def broadcast_to_admins(self, message: dict[str, Any]) -> None:
        """Publish a notification for every admin connection."""
        await self._bus.publish(
            WsEnvelope(kind="admins", msg_type="notification", payload=message)
        )

    async def broadcast_typed(
        self, msg_type: str, payload: Any, admins_only: bool = False
    ) -> None:
        """Publish a typed message to connected users.

        Sends {"type": msg_type, "payload": payload} — the caller names the
        type and it reaches the wire unchanged. This is the only all-users
        broadcast. There used to be a broadcast_to_all() next to it that
        force-set "type": "notification" and nested the caller's dict under
        it; a caller that had already typed its message got wrapped twice and
        no client could match on it (#511). Pass "notification" as msg_type if
        that is genuinely what you are sending.

        Args:
            msg_type: Message type string (e.g. "dashboard_panel_update").
            payload: Message payload — a dict for most message types, a list
                for the batch-shaped ones like "smart_device_update".
            admins_only: Skip non-admin connections. Needed for payloads that a
                REST route would gate behind is_privileged() - without it the
                gate would be decorative. "Admin" here means conn.is_admin,
                set at connect time from `role == "admin"` in
                api/routes/notifications.py - NOT is_privileged(). A
                PRIVILEGED_ROLES config extended beyond "admin" (e.g. adding
                "operator") widens REST visibility for admin_only panels
                without widening this broadcast, so the two enforcement
                points drift apart. That's fail-closed (no leak), just a trap
                for the next reader.
        """
        await self._bus.publish(
            WsEnvelope(
                kind="all", msg_type=msg_type, payload=payload, admins_only=admins_only
            )
        )

    async def send_unread_count(self, user_id: int, count: int) -> None:
        """Publish an updated unread count for one user's connections."""
        await self._bus.publish(
            WsEnvelope(
                kind="user",
                msg_type="unread_count",
                payload={"count": count},
                user_id=user_id,
            )
        )

    async def send_notification_state(
        self, user_id: int, ids: list[int], action: str
    ) -> None:
        """Tell a user's connections that notification state changed elsewhere.

        Counterpart to send_unread_count: that one carries the number, this
        one carries which notifications changed and how, so an open client can
        update its list.

        Args:
            user_id: Target user ID
            ids: Affected notification IDs; empty for the bulk actions, where
                "all" is exactly what the empty list means
            action: read | dismissed | snoozed | deleted | restored |
                read_all | dismissed_all | deleted_all
        """
        await self._bus.publish(
            WsEnvelope(
                kind="user",
                msg_type="notification_state",
                payload={"ids": ids, "action": action},
                user_id=user_id,
            )
        )
```

Add `deliver_local()` as the single place that touches `_user_connections`:

```python
    async def deliver_local(self, env: WsEnvelope) -> int:
        """Write an envelope to this process's matching sockets.

        The only method that touches _user_connections for sending. Called
        from the bus consumer, never from publish() — see ws_bus for why there
        is exactly one delivery path.

        Returns:
            Number of connections in *this* process that got the frame.
        """
        frame = {"type": env.msg_type, "payload": env.payload}
        sent_count = 0

        async with self._lock:
            if env.kind == "user":
                if env.user_id is None:
                    logger.warning("deliver_local: kind=user without user_id, dropped")
                    return 0
                targets = [(env.user_id, self._user_connections.get(env.user_id, []))]
            elif env.kind == "admins":
                targets = [
                    (uid, self._user_connections.get(uid, []))
                    for uid in list(self._admin_users)
                ]
            elif env.kind == "all":
                targets = list(self._user_connections.items())
            else:
                # Never the permissive branch by accident: "all" is named
                # explicitly, and anything unrecognised is dropped rather than
                # broadcast to every socket.
                logger.warning("deliver_local: unknown kind %r, dropped", env.kind)
                return 0

            for user_id, connections in targets:
                disconnected = []
                for conn in connections:
                    if env.kind == "admins" and not conn.is_admin:
                        continue
                    if env.kind == "all" and env.admins_only and not conn.is_admin:
                        continue
                    try:
                        # Bounded on purpose. A client that stops reading (full
                        # TCP window) used to stall only its own caller; now it
                        # would stall the single bus consumer while holding
                        # self._lock, freezing delivery for every user in this
                        # process and silently overflowing the queue.
                        await asyncio.wait_for(
                            conn.websocket.send_json(frame), timeout=SEND_TIMEOUT_SECONDS
                        )
                        sent_count += 1
                    except (Exception, asyncio.TimeoutError) as e:
                        logger.warning(f"Failed to send to user {user_id}: {e}")
                        disconnected.append(conn)

                for conn in disconnected:
                    if conn in connections:
                        connections.remove(conn)

                if not connections and user_id in self._user_connections:
                    del self._user_connections[user_id]
                    self._admin_users.discard(user_id)

        return sent_count
```

One neighbouring comment becomes untrue with this change. `backend/app/services/notifications/events.py:639-641` says "There is no cycle to avoid — **websocket_manager imports nothing from app**". The conclusion still holds (verified: `ws_bus` loads only stdlib at module level and defers `app.core.database` into `build_bus()`), the premise does not. Amend it to "…imports only `app.services.ws_bus`, which loads nothing from `app` at module level".

Mark the three local-only accessors in their docstrings — add this line to each of `is_user_connected`, `get_connection_count`, `get_connected_user_ids`:

```python
        Local only: knows the connections of *this* process. Six API processes
        hold connections, so a False here does not mean "nobody is listening".
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_ws_bus.py -v`
Expected: PASS

- [ ] **Step 5: Adapt the existing manager tests**

The existing tests assert on the return counts, which are gone. In `backend/tests/services/test_websocket_manager.py`, replace each count assertion with an assertion on the frame or on state. The six affected classes:

```python
@pytest.mark.asyncio
class TestBroadcastToUser:
    async def test_sends_to_user(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1)
        await manager.broadcast_to_user(1, {"msg": "hello"})
        ws.send_json.assert_called_once()
        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "notification"
        assert payload["payload"] == {"msg": "hello"}

    async def test_disconnected_user_gets_nothing(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1)
        await manager.broadcast_to_user(999, {"msg": "hello"})
        ws.send_json.assert_not_called()

    async def test_cleans_up_failed_connection(self, manager: WebSocketManager):
        ws = _make_ws(send_json_side_effect=Exception("connection lost"))
        await manager.connect(ws, user_id=1)
        await manager.broadcast_to_user(1, {"msg": "hello"})
        assert not manager.is_user_connected(1)


@pytest.mark.asyncio
class TestBroadcastToAdmins:
    async def test_sends_only_to_admins(self, manager: WebSocketManager):
        ws_admin = _make_ws()
        ws_user = _make_ws()
        await manager.connect(ws_admin, user_id=1, is_admin=True)
        await manager.connect(ws_user, user_id=2, is_admin=False)

        await manager.broadcast_to_admins({"alert": "disk full"})
        ws_admin.send_json.assert_called_once()
        ws_user.send_json.assert_not_called()


@pytest.mark.asyncio
class TestBroadcastToAll:
    """All-users reach, now via broadcast_typed() — broadcast_to_all() is gone (#511)."""

    async def test_sends_to_all_users(self, manager: WebSocketManager):
        ws1, ws2 = _make_ws(), _make_ws()
        await manager.connect(ws1, user_id=1)
        await manager.connect(ws2, user_id=2)

        await manager.broadcast_typed("some_event", {"event": "update"})
        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    async def test_no_connections_is_a_noop(self, manager: WebSocketManager):
        await manager.broadcast_typed("some_event", {"event": "update"})

    async def test_caller_type_is_not_overwritten(self, manager: WebSocketManager):
        """The regression that made #511 possible: an envelope forced onto the caller."""
        ws = _make_ws()
        await manager.connect(ws, user_id=1)

        await manager.broadcast_typed("smart_device_update", [{"device_id": 9}])

        frame = ws.send_json.await_args[0][0]
        assert frame == {"type": "smart_device_update", "payload": [{"device_id": 9}]}

    async def test_broadcast_to_all_is_removed(self, manager: WebSocketManager):
        """Keep it gone: re-adding it re-opens the double-wrap trap."""
        assert not hasattr(manager, "broadcast_to_all")


@pytest.mark.asyncio
class TestSendUnreadCount:
    async def test_sends_unread_count(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1)
        await manager.send_unread_count(1, 5)
        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "unread_count"
        assert payload["payload"]["count"] == 5
```

`TestSendNotificationState` at the end of the file has four tests that assert on counts. Replace the whole class with:

```python
@pytest.mark.asyncio
class TestSendNotificationState:
    async def test_sends_to_all_connections_of_user(self, manager: WebSocketManager):
        ws1, ws2 = _make_ws(), _make_ws()
        await manager.connect(ws1, user_id=1)
        await manager.connect(ws2, user_id=1)

        await manager.send_notification_state(1, [7, 8], "read")

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()
        frame = ws1.send_json.call_args[0][0]
        assert frame == {
            "type": "notification_state",
            "payload": {"ids": [7, 8], "action": "read"},
        }

    async def test_other_users_untouched(self, manager: WebSocketManager):
        mine, theirs = _make_ws(), _make_ws()
        await manager.connect(mine, user_id=1)
        await manager.connect(theirs, user_id=2)

        await manager.send_notification_state(1, [7], "dismissed")

        assert theirs.send_json.call_count == 0

    async def test_no_connections_is_a_noop(self, manager: WebSocketManager):
        await manager.send_notification_state(99, [1], "read")

    async def test_drops_broken_connection(self, manager: WebSocketManager):
        ws = _make_ws(send_json_side_effect=RuntimeError("gone"))
        await manager.connect(ws, user_id=1)

        await manager.send_notification_state(1, [1], "read")

        assert manager.get_connection_count(1) == 0
```

There is no existing `admins_only` test in this file — `broadcast_typed`'s admins-only path was never covered. Add it together with the tests for the new method:

```python
@pytest.mark.asyncio
class TestDeliverLocal:
    async def test_returns_the_local_count(self, manager: WebSocketManager):
        from app.services.ws_bus import WsEnvelope

        ws1, ws2 = _make_ws(), _make_ws()
        await manager.connect(ws1, user_id=1)
        await manager.connect(ws2, user_id=1)

        sent = await manager.deliver_local(
            WsEnvelope(kind="user", msg_type="notification", payload={"a": 1}, user_id=1)
        )
        assert sent == 2

    async def test_kind_user_without_user_id_is_dropped(self, manager: WebSocketManager):
        from app.services.ws_bus import WsEnvelope

        ws = _make_ws()
        await manager.connect(ws, user_id=1)
        sent = await manager.deliver_local(
            WsEnvelope(kind="user", msg_type="notification", payload={})
        )
        assert sent == 0
        ws.send_json.assert_not_called()

    async def test_admins_only_skips_non_admin_connections(self, manager: WebSocketManager):
        """Without this the REST gate on admin_only panels would be decorative."""
        from app.services.ws_bus import WsEnvelope

        ws_admin, ws_user = _make_ws(), _make_ws()
        await manager.connect(ws_admin, user_id=1, is_admin=True)
        await manager.connect(ws_user, user_id=2, is_admin=False)

        sent = await manager.deliver_local(
            WsEnvelope(
                kind="all",
                msg_type="dashboard_panel_update",
                payload={"admin_only": True},
                admins_only=True,
            )
        )

        assert sent == 1
        ws_admin.send_json.assert_called_once()
        ws_user.send_json.assert_not_called()

    async def test_kind_admins_skips_non_admin_connection_of_an_admin_user(
        self, manager: WebSocketManager
    ):
        """_admin_users is keyed by user; a user's non-admin socket must stay out."""
        from app.services.ws_bus import WsEnvelope

        ws_admin = _make_ws()
        ws_plain = _make_ws()
        await manager.connect(ws_admin, user_id=1, is_admin=True)
        await manager.connect(ws_plain, user_id=1, is_admin=False)

        sent = await manager.deliver_local(
            WsEnvelope(kind="admins", msg_type="notification", payload={"id": 1})
        )

        assert sent == 1
        ws_plain.send_json.assert_not_called()
```

- [ ] **Step 6: Adapt the three count assertions in the dashboard panel tests**

These are the easiest ones to miss — they live under `tests/plugins/`, not `tests/services/`, and they call `broadcast_typed` on a real `WebSocketManager`. In `backend/tests/plugins/test_dashboard_panel.py`:

- `:187` — delete `assert count == 1` and change line 176's `count = await manager.broadcast_typed(` to `await manager.broadcast_typed(`. The `mock_ws.send_json.assert_called_once_with({...})` right below it stays exactly as it is: `deliver_local` builds the same frame.
- `:203` — delete `assert count == 0` and drop the `count = ` on line 195. The `assert manager.get_connection_count() == 0` below it is the real assertion and still holds.
- `:627` — delete `assert count == 1` and drop the `count = ` on line 618. Keep `admin_ws.send_json.assert_called_once()` and `user_ws.send_json.assert_not_called()`.

- [ ] **Step 7: Run the full manager + bus + panel tests**

Run: `cd backend && python -m pytest tests/services/test_websocket_manager.py tests/services/test_ws_bus.py tests/plugins/test_dashboard_panel.py -v`
Expected: PASS, no failures

- [ ] **Step 8: Run everything that touches notifications**

Run: `cd backend && python -m pytest tests/services/test_event_emitter_broadcast.py tests/api/test_notification_fanout.py tests/services/test_notification_service.py -v`

Expected: PASS. No `-k` filter here on purpose: `-k "notification or websocket"` matches module names too, and `test_event_emitter_broadcast` contains neither word — the filter would silently deselect the two tests that matter most (`test_without_a_loop_it_stays_silent_instead_of_raising`, `test_broadcast_failure_does_not_break_the_caller`). These files assert on `await_args` of mocked manager methods, so they should be unaffected by the return-type change — confirm that rather than assume it.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/websocket_manager.py backend/tests/services/test_websocket_manager.py backend/tests/services/test_ws_bus.py
git commit -m "refactor(ws): Publizieren und lokales Zustellen im WebSocketManager trennen (#685)"
```

---

### Task 3: PostgresWsBus

**Files:**
- Modify: `backend/app/services/ws_bus.py`
- Test: `backend/tests/services/test_ws_bus.py`

**Interfaces:**
- Consumes: `WsEnvelope`, `Deliver`, `CHANNEL`, `MAX_PAYLOAD_BYTES`, `QUEUE_MAXSIZE` aus Task 1
- Produces: `PostgresWsBus(dsn: str, engine: Any, connect_fn: Callable[[str], Any] | None = None)` mit `publish`, `start`, `stop`; `build_bus(dsn: str | None = None, engine: Any = None) -> WsBus`

Der Test benutzt eine gefälschte Verbindung mit einem echten Dateideskriptor aus `os.pipe()` — so löst ein Schreiben auf das andere Ende den `add_reader`-Callback wirklich aus, statt ihn nachzuspielen.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_ws_bus.py`:

```python
import asyncio
import os

from app.services.ws_bus import PostgresWsBus, QUEUE_MAXSIZE, build_bus


class _Notify:
    def __init__(self, payload: str) -> None:
        self.payload = payload


class FakeConn:
    """A psycopg2-shaped connection whose readable fd is a real pipe.

    fileno() mimics the behaviour that matters most: psycopg2 raises
    InterfaceError once the connection is broken or closed. A fake that keeps
    returning the fd would hide the worst failure this class can have — a
    listener that never wakes again after one reconnect.
    """

    def __init__(self) -> None:
        self._r, self._w = os.pipe()
        self.notifies: list = []
        self.closed = False
        self.listened: list[str] = []
        self.poll_raises: Exception | None = None
        self.fileno_raises = False

    def fileno(self) -> int:
        if self.fileno_raises or self.closed:
            raise RuntimeError("connection already closed")
        return self._r

    def set_isolation_level(self, level) -> None:
        self.isolation_level = level

    def cursor(self):
        conn = self

        class _Cur:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def execute(self_inner, sql):
                conn.listened.append(sql)

        return _Cur()

    def close(self) -> None:
        self.closed = True
        for fd in (self._r, self._w):
            try:
                os.close(fd)
            except OSError:
                pass

    def deliver(self, payload: str) -> None:
        """Queue a notification and make the fd readable, like Postgres would."""
        self.notifies.append(_Notify(payload))
        os.write(self._w, b"x")

    def poll(self) -> None:
        if self.poll_raises is not None:
            # psycopg2 marks the connection closed when poll() fails, and
            # fileno() raises from then on.
            self.fileno_raises = True
            raise self.poll_raises
        try:
            os.read(self._r, 1)
        except BlockingIOError:
            pass


class FakeEngine:
    """Captures what publish() would send to Postgres."""

    def __init__(self) -> None:
        self.statements: list[tuple] = []
        self.commits = 0

    def connect(self):
        engine = self

        class _Conn:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def exec_driver_sql(self_inner, sql, params):
                engine.statements.append((sql, params))

            def commit(self_inner):
                engine.commits += 1

        return _Conn()


@pytest.mark.asyncio
class TestPostgresWsBusPublish:
    async def test_publish_sends_pg_notify_with_the_envelope(self):
        engine = FakeEngine()
        bus = PostgresWsBus("postgresql://x", engine)
        env = WsEnvelope(kind="admins", msg_type="notification", payload={"id": 1})

        await bus.publish(env)

        sql, params = engine.statements[0]
        assert "pg_notify" in sql
        assert isinstance(params, tuple), "a list raises ArgumentError in SQLAlchemy"
        assert params[0] == CHANNEL
        assert WsEnvelope.from_json(params[1]) == env

    async def test_publish_commits(self):
        """NOTIFY is delivered on commit. Without this, nothing ever arrives."""
        engine = FakeEngine()
        bus = PostgresWsBus("postgresql://x", engine)

        await bus.publish(WsEnvelope(kind="all", msg_type="notification", payload={}))

        assert engine.commits == 1

    async def test_oversized_payload_is_dropped_not_sent(self, caplog):
        engine = FakeEngine()
        bus = PostgresWsBus("postgresql://x", engine)
        huge = WsEnvelope(kind="all", msg_type="dashboard_panel_update", payload="x" * 9000)

        with caplog.at_level(logging.WARNING):
            await bus.publish(huge)

        assert engine.statements == []
        assert "dashboard_panel_update" in caplog.text

    async def test_unserialisable_payload_is_dropped(self, caplog):
        engine = FakeEngine()
        bus = PostgresWsBus("postgresql://x", engine)

        with caplog.at_level(logging.WARNING):
            await bus.publish(
                WsEnvelope(kind="all", msg_type="notification", payload={"when": object()})
            )

        assert engine.statements == []

    async def test_publish_never_raises_when_the_database_is_gone(self):
        class DeadEngine:
            def connect(self):
                raise RuntimeError("no database")

        bus = PostgresWsBus("postgresql://x", DeadEngine())
        await bus.publish(WsEnvelope(kind="all", msg_type="notification", payload={}))

    async def test_publish_delivers_locally_while_the_listener_is_down(self):
        """Without this, a process with a broken listener goes silent for its own clients."""
        engine = FakeEngine()
        seen: list[WsEnvelope] = []
        bus = PostgresWsBus("postgresql://x", engine)
        bus._deliver = lambda env: _collect(seen, env)  # listener never started

        env = WsEnvelope(kind="all", msg_type="notification", payload={})
        await bus.publish(env)

        assert seen == [env]
        assert len(engine.statements) == 1


@pytest.mark.asyncio
class TestPostgresWsBusListener:
    async def test_listens_and_delivers_a_notification(self):
        conn = FakeConn()
        seen: list[WsEnvelope] = []
        bus = PostgresWsBus("postgresql://x", FakeEngine(), connect_fn=lambda dsn: conn)

        await bus.start(lambda env: _collect(seen, env))
        assert any("LISTEN" in stmt for stmt in conn.listened)

        env = WsEnvelope(kind="user", msg_type="unread_count", payload={"count": 1}, user_id=4)
        conn.deliver(env.to_json())
        await asyncio.sleep(0.05)

        await bus.stop()
        assert seen == [env]

    async def test_garbage_on_the_channel_does_not_kill_the_consumer(self):
        conn = FakeConn()
        seen: list[WsEnvelope] = []
        bus = PostgresWsBus("postgresql://x", FakeEngine(), connect_fn=lambda dsn: conn)
        await bus.start(lambda env: _collect(seen, env))

        conn.deliver("{not json")
        good = WsEnvelope(kind="admins", msg_type="notification", payload={"id": 2})
        conn.deliver(good.to_json())
        await asyncio.sleep(0.05)

        await bus.stop()
        assert seen == [good]

    async def test_publish_only_mode_opens_no_listener(self):
        """deliver=None means there is nowhere to deliver, so there is no reason to listen."""
        opened = []
        bus = PostgresWsBus(
            "postgresql://x", FakeEngine(), connect_fn=lambda dsn: opened.append(dsn)
        )
        await bus.start(None)
        await bus.stop()
        assert opened == []

    async def test_lost_connection_schedules_a_reconnect(self):
        first, second = FakeConn(), FakeConn()
        conns = iter([first, second])
        seen: list[WsEnvelope] = []
        bus = PostgresWsBus(
            "postgresql://x", FakeEngine(), connect_fn=lambda dsn: next(conns)
        )
        bus._backoff_base = 0.01  # keep the test fast

        await bus.start(lambda env: _collect(seen, env))
        first.poll_raises = RuntimeError("server closed the connection")
        first.deliver("{}")
        await asyncio.sleep(0.2)

        env = WsEnvelope(kind="all", msg_type="notification", payload={"after": "reconnect"})
        second.deliver(env.to_json())
        await asyncio.sleep(0.05)

        await bus.stop()
        assert seen == [env]

    async def test_lost_connection_unregisters_the_reader(self):
        """The regression that would have silenced a worker permanently.

        Reading conn.fileno() inside _close_conn() raises once the connection
        is broken, remove_reader() is skipped, the next connection gets the
        same fd back, and add_reader() then only swaps the callback without
        arming the fd. The listener never wakes again — and _open() logs
        "reconnected" while it happens.
        """
        conn = FakeConn()
        bus = PostgresWsBus("postgresql://x", FakeEngine(), connect_fn=lambda dsn: conn)
        bus._backoff_base = 0.01

        await bus.start(lambda env: _collect([], env))
        registered_fd = bus._fd
        assert registered_fd is not None

        loop = asyncio.get_running_loop()
        conn.poll_raises = RuntimeError("server closed the connection")
        conn.deliver("{}")

        assert bus._fd is None, "the cached fd must be cleared on loss"
        assert not loop.remove_reader(registered_fd), (
            "the reader was still registered — _close_conn did not unregister it"
        )
        await bus.stop()

    async def test_stop_during_a_pending_connect_closes_the_connection(self):
        """to_thread cannot be cancelled: a late connection must not leak."""
        conn = FakeConn()
        bus = PostgresWsBus("postgresql://x", FakeEngine(), connect_fn=lambda dsn: conn)

        bus._stopping = True
        await bus._open()

        assert conn.closed is True
        assert bus._conn is None


@pytest.mark.asyncio
class TestQueueOverflow:
    """Tested directly on _enqueue: driving it through the pipe would let one
    reader callback drain everything in a single pass, which proves nothing
    about what happens when the consumer falls behind."""

    async def test_drops_the_oldest_not_the_newest(self, caplog):
        bus = PostgresWsBus("postgresql://x", FakeEngine())
        bus._queue = asyncio.Queue(maxsize=3)

        first = WsEnvelope(kind="all", msg_type="oldest", payload={})
        for msg_type in ("oldest", "b", "c"):
            bus._enqueue(WsEnvelope(kind="all", msg_type=msg_type, payload={}))

        with caplog.at_level(logging.WARNING):
            bus._enqueue(WsEnvelope(kind="all", msg_type="newest", payload={}))

        assert "queue full" in caplog.text
        assert bus._queue.qsize() == 3
        remaining = [bus._queue.get_nowait().msg_type for _ in range(3)]
        assert remaining == ["b", "c", "newest"], "the oldest must be the one dropped"
        assert first.msg_type not in remaining

    async def test_enqueue_without_a_queue_is_a_noop(self):
        """Publish-only processes never create one."""
        bus = PostgresWsBus("postgresql://x", FakeEngine())
        bus._enqueue(WsEnvelope(kind="all", msg_type="m", payload={}))


class TestBuildBus:
    def test_sqlite_dsn_gets_the_local_bus(self):
        assert isinstance(build_bus("sqlite:///x.db", engine=None), LocalWsBus)

    def test_postgres_dsn_gets_the_postgres_bus(self):
        assert isinstance(
            build_bus("postgresql://u:p@h/db", engine=FakeEngine()), PostgresWsBus
        )

    def test_sqlalchemy_driver_suffix_is_stripped_for_psycopg2(self):
        """psycopg2.connect() cannot parse postgresql+psycopg2:// and the
        failure is silent — the listener never opens while publish keeps
        working."""
        from sqlalchemy import create_engine

        engine = create_engine("postgresql+psycopg2://u:p@h/db")
        bus = build_bus("postgresql+psycopg2://u:p@h/db", engine=engine)

        assert isinstance(bus, PostgresWsBus)
        assert "+psycopg2" not in bus._dsn
        assert bus._dsn.startswith("postgresql://")
        assert "p@h" in bus._dsn or ":p@" in bus._dsn, "the password must survive"
```

`create_engine` on a Postgres URL does not connect, so this test needs no database.

Add `import logging` to the test module's imports.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_ws_bus.py -k "Postgres or BuildBus" -v`
Expected: FAIL — `ImportError: cannot import name 'PostgresWsBus'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/services/ws_bus.py`:

```python
class PostgresWsBus:
    """Cross-process bus over Postgres LISTEN/NOTIFY.

    Publishing goes through the SQLAlchemy pool in a worker thread (psycopg2 is
    synchronous and must not stall the event loop). Listening uses a dedicated
    connection *outside* the pool — a pooled connection would have to stay
    checked out forever, which would lie to the pool — registered on the event
    loop via loop.add_reader.

    Delivery happens only here, never in publish(): NOTIFY reaches every
    session that ran LISTEN, including this process's own, so there is exactly
    one path to a socket and no double delivery. The one exception is a
    disconnected listener, where publish() also delivers locally — nothing is
    replayed across that gap, so it cannot duplicate.
    """

    def __init__(
        self,
        dsn: str,
        engine: Any,
        connect_fn: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._dsn = dsn
        self._engine = engine
        self._connect_fn = connect_fn or self._default_connect
        self._deliver: Optional[Deliver] = None
        self._conn: Any = None
        # The listener's file descriptor, cached at add_reader() time. It must
        # NOT be re-read with conn.fileno() later: by the time we unregister,
        # the connection is usually already dead and fileno() raises
        # InterfaceError. See _close_conn for what that costs.
        self._fd: Optional[int] = None
        self._queue: "Optional[asyncio.Queue[WsEnvelope]]" = None
        self._consumer: "Optional[asyncio.Task[None]]" = None
        self._reconnect: "Optional[asyncio.Task[None]]" = None
        self._connected = False
        self._stopping = False
        self._attempt = 0
        self._dropped = 0
        self._backoff_base = 1.0
        self._backoff_cap = 60.0
        # One thread, on purpose — see publish(). Bounds this process's pooled
        # connections for publishing to one, and keeps NOTIFY order.
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ws_bus_publish"
        )

    # ---------------- publishing ----------------

    async def publish(self, env: WsEnvelope) -> None:
        """Send an envelope to every process. Never raises."""
        try:
            raw = env.to_json()
        except (TypeError, ValueError) as exc:
            logger.warning(
                "ws bus: payload for %s is not serialisable, dropped: %s", env.msg_type, exc
            )
            return

        size = len(raw.encode("utf-8"))
        if size > MAX_PAYLOAD_BYTES:
            logger.warning(
                "ws bus: dropping %s — %d bytes exceed the %d byte pg_notify budget",
                env.msg_type,
                size,
                MAX_PAYLOAD_BYTES,
            )
            return

        # Read once: the listener can reconnect while this publish is in flight.
        # A residual race remains and is accepted — if the reconnect completes
        # between here and the NOTIFY landing, this envelope is delivered twice
        # and a desktop popup appears twice. The window is the backoff delay
        # (>=0.5s) against one executor round-trip, so it is narrow, and it only
        # opens right after a reconnect. Closing it properly needs a generation
        # counter compared after the publish; that is not worth the machinery
        # for a duplicate popup that follows a visible reconnect in the log.
        connected = self._connected
        if not connected and self._deliver is not None:
            # Listener down: at least our own clients keep seeing our own work.
            try:
                await self._deliver(env)
            except Exception as exc:
                logger.warning("ws bus: local fallback delivery failed: %s", exc)

        try:
            # NOT asyncio.to_thread: that uses the loop's default executor,
            # which is min(32, cpu+4) = 16 threads on this box. Sixteen
            # concurrent publishes would each check out a pooled connection —
            # on top of request handling — and pg_notify is the one thing here
            # that must not fan out. A single-worker executor bounds pool use
            # to one connection per process and serialises publishes, which is
            # also the only way the order of two publishes survives: _notify_sync
            # commits, and NOTIFY is delivered on commit. Without it,
            # fanout_state's "state then count" pair can arrive reversed.
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, self._notify_sync, raw)
        except Exception as exc:
            logger.warning("ws bus: publish of %s failed: %s", env.msg_type, exc)

    def _notify_sync(self, raw: str) -> None:
        """Run pg_notify on a pooled connection. Called in a worker thread.

        Three things here are load-bearing and were each verified against
        PostgreSQL 17.11 with psycopg2 2.9.11:

        - The params must be a TUPLE. A list raises `ArgumentError: List
          argument must consist only of tuples or dictionaries`.
        - `conn.commit()` is mandatory. SQLAlchemy's connect() opens a
          transaction, the `with` exit rolls it back, and NOTIFY is delivered
          on commit — without it nothing arrives at all.
        - Every publish gets its own transaction, which matters more than it
          looks: Postgres collapses identical (channel, payload) notifies
          raised within ONE transaction into a single delivery. Batching
          publishes into a shared transaction would silently drop duplicates.
        """
        with self._engine.connect() as conn:
            conn.exec_driver_sql("SELECT pg_notify(%s, %s)", (CHANNEL, raw))
            conn.commit()

    # ---------------- listening ----------------

    async def start(self, deliver: Optional[Deliver]) -> None:
        """Begin listening, or stay publish-only when there is nowhere to deliver."""
        self._deliver = deliver
        if deliver is None:
            logger.info("ws bus: publish-only, no listener in this process")
            return
        self._queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._consumer = asyncio.create_task(self._consume(), name="ws_bus_consumer")
        await self._open()

    def _default_connect(self, dsn: str) -> Any:
        import psycopg2
        import psycopg2.extensions

        conn = psycopg2.connect(dsn)
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            # LISTEN takes an identifier, which cannot be parameterised. CHANNEL
            # is a module constant and never user input — see its definition.
            cur.execute(f"LISTEN {CHANNEL}")
        return conn

    async def _open(self) -> None:
        try:
            conn = await asyncio.to_thread(self._connect_fn, self._dsn)
        except Exception as exc:
            logger.warning("ws bus: listener connect failed: %s", exc)
            self._schedule_reconnect()
            return

        if self._stopping:
            # stop() cannot cancel a connect already running in a worker
            # thread, so the connection can land after shutdown. Close it here
            # or it leaks a Postgres session for the rest of the process.
            self._close_conn(conn)
            return

        try:
            fd = conn.fileno()
            asyncio.get_running_loop().add_reader(fd, self._on_readable)
            self._fd = fd
        except NotImplementedError:
            # Windows' Proactor loop has no add_reader. Unreachable in practice
            # (dev runs SQLite and so gets LocalWsBus), but a Windows dev box
            # pointed at Postgres would otherwise retry forever, one warning per
            # attempt. Stay publish-only instead.
            logger.warning("ws bus: this event loop cannot watch sockets, publish-only")
            self._close_conn(conn)
            return
        except Exception as exc:
            logger.warning("ws bus: cannot watch listener socket: %s", exc)
            self._close_conn(conn)
            self._schedule_reconnect()
            return

        self._conn = conn
        self._connected = True
        if self._attempt:
            logger.info("ws bus: listener reconnected after %d attempt(s)", self._attempt)
        else:
            logger.info("ws bus: listening on %s", CHANNEL)
        self._attempt = 0

    def _on_readable(self) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            conn.poll()
        except Exception as exc:
            logger.warning("ws bus: listener connection lost: %s", exc)
            self._drop()
            self._schedule_reconnect()
            return

        # One poll() can surface a whole burst — measured: five pg_notify in one
        # transaction arrive in a single poll(). After a long event-loop stall
        # (this process has seen 128s of loop lag) the backlog lands here at
        # once, so count the drops instead of logging one line per envelope.
        burst = 0
        while conn.notifies:
            note = conn.notifies.pop(0)
            env = WsEnvelope.from_json(note.payload)
            if env is not None:
                self._enqueue(env)
                burst += 1
        if burst > 50:
            logger.info("ws bus: drained a burst of %d envelopes", burst)

    def _enqueue(self, env: WsEnvelope) -> None:
        queue = self._queue
        if queue is None:
            return
        try:
            queue.put_nowait(env)
            return
        except asyncio.QueueFull:
            pass
        try:
            dropped = queue.get_nowait()
            self._dropped += 1
            # Not one line per envelope: a backlog drains in a single poll(), so
            # per-drop logging would bury the journal in exactly the situation
            # where it needs to stay readable.
            if self._dropped == 1 or self._dropped % 100 == 0:
                logger.warning(
                    "ws bus: queue full, dropped oldest (%s); %d dropped so far",
                    dropped.msg_type,
                    self._dropped,
                )
        except asyncio.QueueEmpty:
            pass
        try:
            queue.put_nowait(env)
        except asyncio.QueueFull:
            logger.warning("ws bus: queue full, dropped %s", env.msg_type)

    async def _consume(self) -> None:
        assert self._queue is not None
        while True:
            env = await self._queue.get()
            if self._deliver is None:
                continue
            try:
                await self._deliver(env)
            except Exception as exc:
                logger.warning("ws bus: delivery of %s failed: %s", env.msg_type, exc)

    def _schedule_reconnect(self) -> None:
        if self._stopping:
            return
        delay = min(self._backoff_cap, self._backoff_base * (2 ** self._attempt))
        delay *= random.uniform(0.5, 1.0)  # jitter: don't stampede after a restart
        self._attempt += 1
        self._reconnect = asyncio.create_task(
            self._reopen_after(delay), name="ws_bus_reconnect"
        )

    async def _reopen_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if not self._stopping:
            await self._open()

    def _drop(self) -> None:
        conn, self._conn = self._conn, None
        self._connected = False
        if conn is not None:
            self._close_conn(conn)

    def _close_conn(self, conn: Any) -> None:
        """Unregister the cached fd, then close.

        The fd comes from self._fd, never from conn.fileno(): this runs after
        poll() has already failed, and psycopg2 then raises InterfaceError from
        fileno(). Skipping remove_reader() is not a cosmetic leak — it is a
        silent, permanent outage. The stale selector entry survives close(),
        the next connection gets the same fd back (the kernel hands out the
        lowest free one), and add_reader() on an existing key with the same
        event mask only swaps the callback without ever calling epoll_ctl. The
        listener would then never wake again while the data sat in the socket,
        and _open() would have logged "reconnected" — measured on both the
        selector loop and uvloop.
        """
        if self._fd is not None:
            try:
                asyncio.get_running_loop().remove_reader(self._fd)
            except Exception:
                pass
            self._fd = None
        try:
            conn.close()
        except Exception:
            pass

    async def stop(self) -> None:
        """Stop listening. Publishing after this still works."""
        self._stopping = True
        self._drop()
        tasks = [t for t in (self._consumer, self._reconnect) if t is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._consumer = None
        self._reconnect = None
        # wait=False: a publish already inside _notify_sync may be waiting on
        # pool_timeout, and shutdown must not block behind it.
        self._executor.shutdown(wait=False)


def build_bus(dsn: Optional[str] = None, engine: Any = None) -> WsBus:
    """Pick the bus for this database.

    Postgres gets the real cross-process bus; anything else (SQLite in dev and
    in tests) gets the local one, where a single process holds every socket
    anyway. The engine is only looked up for the Postgres path, so a SQLite
    caller never drags the app engine into an import.
    """
    if dsn is None:
        from app.core.database import DATABASE_URL

        dsn = DATABASE_URL

    if not dsn.startswith("postgresql"):
        return LocalWsBus()

    if engine is None:
        from app.core.database import engine as default_engine

        engine = default_engine

    return PostgresWsBus(_libpq_dsn(dsn, engine), engine)


def _libpq_dsn(dsn: str, engine: Any) -> str:
    """Strip the SQLAlchemy driver suffix so psycopg2.connect() can read it.

    SQLAlchemy accepts `postgresql+psycopg2://…`; psycopg2 does not, and fails
    with `invalid dsn: missing "=" after "postgresql+psycopg2://..."`. That
    failure mode is the bad kind: the listener never opens, reconnects forever
    in the 60s backoff, while publishing keeps working — a silently one-way bus
    with no alarm. This box currently uses the plain `postgresql://` form, so
    the guard is for the day someone writes the canonical one into .env.
    """
    if "+" not in dsn.split("://", 1)[0]:
        return dsn
    try:
        return engine.url.set(drivername="postgresql").render_as_string(
            hide_password=False
        )
    except Exception:  # pragma: no cover - engine without a parsed URL
        scheme, rest = dsn.split("://", 1)
        return f"{scheme.split('+', 1)[0]}://{rest}"
```

Add to the module's imports: `import asyncio`, `import random`, and `from concurrent.futures import ThreadPoolExecutor`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_ws_bus.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ws_bus.py backend/tests/services/test_ws_bus.py
git commit -m "feat(ws): Postgres-Bus über LISTEN/NOTIFY mit Reconnect (#685)"
```

---

### Task 4: Bus in jedem Worker starten

**Files:**
- Modify: `backend/app/core/lifespan.py` (Startup bei `:671`, Shutdown bei `:789`)
- Test: `backend/tests/core/test_lifespan_ws_bus.py` (neu)

**Interfaces:**
- Consumes: `build_bus()` aus Task 3, `WebSocketManager.set_bus`/`deliver_local` aus Task 2
- Produces: Modulfunktionen `_start_ws_bus(manager) -> None` und `_stop_ws_bus() -> None` in `lifespan`, Modulvariable `_ws_bus`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/core/test_lifespan_ws_bus.py`:

```python
"""The ws bus must start in EVERY worker — that is the whole point of #685."""

import pytest

from app.core import lifespan as lifespan_module
from app.services.websocket_manager import WebSocketManager


class RecordingBus:
    def __init__(self) -> None:
        self.started_with = "not started"
        self.stopped = False

    async def publish(self, env):
        pass

    async def start(self, deliver):
        self.started_with = deliver

    async def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_bus_starts_bound_to_deliver_local(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    manager = WebSocketManager()

    await lifespan_module._start_ws_bus(manager)

    assert bus.started_with == manager.deliver_local
    assert manager._bus is bus


@pytest.mark.asyncio
async def test_bus_start_is_not_gated_on_primary_worker(monkeypatch):
    """A secondary worker holds connections too; gating this would keep #685 open."""
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", False)

    await lifespan_module._start_ws_bus(WebSocketManager())

    assert bus.started_with != "not started"


@pytest.mark.asyncio
async def test_stop_stops_the_bus(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    await lifespan_module._start_ws_bus(WebSocketManager())

    await lifespan_module._stop_ws_bus()

    assert bus.stopped is True


@pytest.mark.asyncio
async def test_start_failure_does_not_break_startup(monkeypatch):
    class ExplodingBus(RecordingBus):
        async def start(self, deliver):
            raise RuntimeError("no database")

    monkeypatch.setattr(lifespan_module, "build_bus", lambda: ExplodingBus())
    await lifespan_module._start_ws_bus(WebSocketManager())  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/core/test_lifespan_ws_bus.py -v`
Expected: FAIL — `AttributeError: module 'app.core.lifespan' has no attribute 'build_bus'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/core/lifespan.py`, add to the module imports:

```python
from app.services.ws_bus import build_bus
```

Next to the other module-level service references (near `_websocket_manager`):

```python
_ws_bus = None  # cross-process broadcast bus, one per worker process
```

Add the two helpers next to the other private lifespan helpers:

```python
async def _start_ws_bus(manager) -> None:
    """Start the cross-process broadcast bus for this worker.

    Deliberately NOT behind IS_PRIMARY_WORKER: every worker holds its own
    WebSocket connections, and a bus that only ran on the primary would leave
    #685 open for the other five API processes.

    Never fatal: without the bus this process falls back to local-only
    broadcasts, which is what it did before the bus existed.
    """
    global _ws_bus
    try:
        bus = build_bus()
        await bus.start(manager.deliver_local)
        manager.set_bus(bus)
        _ws_bus = bus
        logger.info("WebSocket bus started (PID %d)", os.getpid())
    except Exception as exc:
        logger.warning("WebSocket bus could not start, local-only broadcasts: %s", exc)


async def _stop_ws_bus() -> None:
    """Stop the bus and release its listener connection."""
    global _ws_bus
    if _ws_bus is None:
        return
    try:
        await _ws_bus.stop()
    except Exception as exc:
        logger.warning("WebSocket bus shutdown failed: %s", exc)
    _ws_bus = None
```

In `_startup()`, extend the notification block (currently at `:670-675`):

```python
    # Initialize notification system services
    try:
        _websocket_manager = init_websocket_manager()
        init_event_emitter(SessionLocal)
        logger.info("Notification system initialized")
    except Exception as e:
        logger.warning(f"Notification system could not initialize: {e}")

    # Cross-process broadcast bus — every worker, primary or not (#685).
    if _websocket_manager is not None:
        await _start_ws_bus(_websocket_manager)
```

In `_shutdown()`, stop the bus right after the background tasks are cancelled and before the services are torn down:

```python
    # Stop our own loops before the services they touch (DB, WebSocket manager,
    # plugins) are torn down below.
    await _cancel_background_tasks()
    await _stop_ws_bus()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/core/test_lifespan_ws_bus.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/lifespan.py backend/tests/core/test_lifespan_ws_bus.py
git commit -m "feat(ws): Broadcast-Bus in jedem Worker starten und stoppen (#685)"
```

---

### Task 5: Lokale Vorprüfung im Fan-out entfernen

**Files:**
- Modify: `backend/app/api/routes/_notification_fanout.py:45-48`
- Test: `backend/tests/api/test_notification_fanout.py`

**Interfaces:**
- Consumes: der publizierende `WebSocketManager` aus Task 2
- Produces: nichts Neues

- [ ] **Step 1: Write the failing test**

In `backend/tests/api/test_notification_fanout.py`, the existing test at line 88 sets `ws_manager.is_user_connected.return_value = False` and asserts nothing is sent. That expectation is now wrong. Replace that test with the following — note the `_patches(...)` context managers from `:25-35`: without them `fanout_state` reaches for the real singleton and the real notification service, and the assertions on the mock fail no matter how correct the implementation is.

```python
@pytest.mark.asyncio
async def test_publishes_even_without_a_local_connection(ws_manager: MagicMock):
    """The user's client may hang in another process — six of them hold sockets.

    Before #685 this returned early, so the worker that handled the "read"
    never published and the tray in the neighbouring process kept its old
    count forever.
    """
    ws_manager.is_user_connected.return_value = False
    p1, p2 = _patches(ws_manager, _service(3))

    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [7], "read")
    ws_manager.send_unread_count.assert_awaited_once_with(1, 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_notification_fanout.py -v`
Expected: FAIL — `send_notification_state` was not awaited (the early return still fires)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/routes/_notification_fanout.py`, delete the early return and explain the absence:

```python
    # No is_user_connected() check here, deliberately. It only knows this
    # process's connections, and production runs six API processes: the worker
    # that handles a "mark as read" usually does not hold the tray's socket, so
    # the check used to skip the publish for exactly the client that needed it
    # (#685). Publishing unconditionally costs one COUNT query on a user
    # action, which is affordable.
    manager = get_websocket_manager()

    try:
        await manager.send_notification_state(user_id, ids, action)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_notification_fanout.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/_notification_fanout.py backend/tests/api/test_notification_fanout.py
git commit -m "fix(ws): Fan-out publiziert auch ohne Verbindung im eigenen Prozess (#685)"
```

---

### Task 6: Worker-Skripte an den Bus hängen

**Files:**
- Modify: `backend/scripts/monitoring_worker.py` (nach `init_event_emitter`, `:42`)
- Modify: `backend/scripts/scheduler_worker.py` (nach `init_event_emitter`, `:47`)
- Create: `backend/app/services/ws_bus_publisher.py`
- Test: `backend/tests/services/test_ws_bus_publisher.py`

Ein eigenes kleines Modul, weil beide Skripte dasselbe brauchen und ein Skript nichts enthalten soll, was sich testen lässt, aber nicht getestet wird.

**Die beiden Skripte sind unterschiedlich gebaut — das ist der Kern dieser Task:**

| Skript | Einstieg | Event-Loop | Weg |
|---|---|---|---|
| `monitoring_worker.py` | `async_main()` (`:22`), über `asyncio.run` (`:97`) | ja, im Hauptthread | `await start_publish_only_bus()` |
| `scheduler_worker.py` | `main()` (`:27`), vollständig synchron, `worker.run_loop()` blockiert | **keiner** | `start_publish_only_bus_threaded()` |

Der Scheduler-Worker hat überhaupt keinen Loop. `EventEmitter._broadcast_sync()` braucht aber einen laufenden Loop, in den es mit `run_coroutine_threadsafe` hineinplant — das ist genau seine Bauart („emit_sync runs on worker threads"). Also bekommt dieser Prozess einen Loop in einem Daemon-Thread. Der Vorteil gegenüber einem synchronen Publish-Pfad: `events.py` bleibt unangetastet.

**Interfaces:**
- Consumes: `build_bus()` aus Task 3, `get_websocket_manager()`, `get_event_emitter()`
- Produces: `async def start_publish_only_bus() -> WsBus | None`, `def start_publish_only_bus_threaded() -> ThreadedBus | None` (mit `ThreadedBus.stop() -> None`)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_ws_bus_publisher.py`:

```python
"""The standalone workers emit notifications; without this they reach no client."""

import asyncio

import pytest

from app.services import ws_bus_publisher
from app.services.ws_bus import WsEnvelope


@pytest.fixture(autouse=True)
def _restore_process_singletons():
    """These helpers mutate two process-wide singletons on purpose.

    Without restoring them, the manager keeps a RecordingBus and the event
    emitter keeps a loop that this test already closed — harmless today, a
    cross-test failure as soon as the suite runs under xdist or someone adds a
    test that relies on either.
    """
    from app.services.notifications.events import get_event_emitter
    from app.services.websocket_manager import get_websocket_manager

    manager = get_websocket_manager()
    emitter = get_event_emitter()
    saved_bus, saved_loop = manager._bus, emitter._loop
    yield
    manager._bus = saved_bus
    emitter._loop = saved_loop


class RecordingBus:
    def __init__(self) -> None:
        self.started = False
        self.deliver = "unset"
        self.published: list[WsEnvelope] = []

    async def publish(self, env):
        self.published.append(env)

    async def start(self, deliver):
        self.started = True
        self.deliver = deliver

    async def stop(self):
        pass


@pytest.mark.asyncio
async def test_starts_the_bus_publish_only(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)

    result = await ws_bus_publisher.start_publish_only_bus()

    assert result is bus
    assert bus.started is True
    assert bus.deliver is None  # nothing to deliver to in this process


@pytest.mark.asyncio
async def test_binds_the_event_loop_so_emit_sync_can_broadcast(monkeypatch):
    """emit_sync runs on worker threads and needs the loop to schedule the send."""
    from app.services.notifications.events import get_event_emitter

    bus = RecordingBus()
    monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
    get_event_emitter()._loop = None

    await ws_bus_publisher.start_publish_only_bus()

    assert get_event_emitter()._loop is asyncio.get_running_loop()


@pytest.mark.asyncio
async def test_manager_publishes_through_the_new_bus(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
    await ws_bus_publisher.start_publish_only_bus()

    from app.services.websocket_manager import get_websocket_manager

    await get_websocket_manager().broadcast_to_admins({"id": 1})

    assert bus.published[0].kind == "admins"


@pytest.mark.asyncio
async def test_failure_returns_none_and_does_not_raise(monkeypatch):
    def boom():
        raise RuntimeError("no database")

    monkeypatch.setattr(ws_bus_publisher, "build_bus", boom)

    assert await ws_bus_publisher.start_publish_only_bus() is None


class TestThreadedVariant:
    """scheduler_worker.main() is fully synchronous — it has no event loop at all."""

    def test_provides_a_running_loop_for_emit_sync(self, monkeypatch):
        from app.services.notifications.events import get_event_emitter

        bus = RecordingBus()
        monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
        get_event_emitter()._loop = None

        handle = ws_bus_publisher.start_publish_only_bus_threaded()
        try:
            assert handle is not None
            loop = get_event_emitter()._loop
            assert loop is not None
            assert loop.is_running()
            assert bus.started is True
            assert bus.deliver is None
        finally:
            handle.stop()

    def test_stop_shuts_the_loop_thread_down(self, monkeypatch):
        bus = RecordingBus()
        monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)

        handle = ws_bus_publisher.start_publish_only_bus_threaded()
        assert handle is not None
        handle.stop()

        assert not handle.thread.is_alive()

    def test_a_broadcast_from_the_sync_thread_reaches_the_bus(self, monkeypatch):
        """The whole point: emit_sync runs here, with no loop of its own."""
        import time

        bus = RecordingBus()
        monkeypatch.setattr(ws_bus_publisher, "build_bus", lambda: bus)
        handle = ws_bus_publisher.start_publish_only_bus_threaded()
        try:
            from app.services.websocket_manager import get_websocket_manager

            manager = get_websocket_manager()
            future = asyncio.run_coroutine_threadsafe(
                manager.broadcast_to_admins({"id": 42}), handle.loop
            )
            future.result(timeout=5)
        finally:
            handle.stop()

        assert bus.published[-1].payload == {"id": 42}

    def test_failure_returns_none(self, monkeypatch):
        def boom():
            raise RuntimeError("no database")

        monkeypatch.setattr(ws_bus_publisher, "build_bus", boom)

        assert ws_bus_publisher.start_publish_only_bus_threaded() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_ws_bus_publisher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ws_bus_publisher'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/ws_bus_publisher.py`:

```python
"""Bus wiring for the standalone worker processes.

monitoring_worker and scheduler_worker emit notifications (temperature and
disk-space thresholds, scheduler failures) but hold no WebSocket connections.
Two things were missing for those to reach a client at all:

- Nobody called EventEmitter.set_event_loop() outside lifespan, so
  _broadcast_sync() returned early with "No app loop bound" and the whole
  synchronous path was invisible.
- Even with the loop bound, a broadcast would only have reached this process's
  own sockets, of which there are none.

So these processes get the bus in publish-only mode: no listener, no extra
connection, just a way out (#685).

Two limits worth knowing before debugging this:

- In dev (SQLite) build_bus() returns a LocalWsBus, and start(None) leaves it
  without a deliver callback — publish() is a no-op there. Unavoidable: these
  processes hold no sockets, and in dev there is only one process anyway.
- NotificationService._websocket_manager stays None here, so its async
  _send_in_app/_broadcast_to_recipients paths do nothing. That does not matter:
  both workers only ever use emit_*_sync, and EventEmitter._broadcast_sync
  reaches for get_websocket_manager() directly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.services.ws_bus import WsBus, build_bus

logger = logging.getLogger(__name__)


async def start_publish_only_bus() -> Optional[WsBus]:
    """Wire this process so emit_sync() broadcasts reach the other processes.

    Returns:
        The bus, or None when it could not be started — in which case the
        process keeps working exactly as it did before, minus the broadcasts.
    """
    try:
        from app.services.notifications.events import get_event_emitter
        from app.services.websocket_manager import get_websocket_manager

        bus = build_bus()
        # deliver=None: there is nowhere to deliver in this process, so there is
        # no reason to hold a listener connection either.
        await bus.start(None)
        get_websocket_manager().set_bus(bus)
        get_event_emitter().set_event_loop(asyncio.get_running_loop())
        logger.info("WebSocket bus started (publish-only)")
        return bus
    except Exception as exc:
        logger.warning("WebSocket bus could not start (publish-only): %s", exc)
        return None


@dataclass
class ThreadedBus:
    """A bus plus the background loop it lives on, for processes without one."""

    bus: WsBus
    loop: asyncio.AbstractEventLoop
    thread: threading.Thread

    def stop(self) -> None:
        """Stop the bus, then the loop, then join and close. Safe to call twice.

        Order matters: stopping the loop first would cancel an in-flight publish
        — including the worker's own shutdown notification — and would leave a
        listener connection open if this ever runs with one.
        """
        if not self.thread.is_alive():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.bus.stop(), self.loop).result(timeout=5)
        except Exception as exc:
            logger.warning("WebSocket bus shutdown failed: %s", exc)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        try:
            self.loop.close()
        except Exception:
            pass


def start_publish_only_bus_threaded() -> Optional[ThreadedBus]:
    """Same as start_publish_only_bus(), for a process with no event loop.

    scheduler_worker.main() is synchronous from top to bottom — worker.run_loop()
    blocks the main thread — so there is no loop for
    EventEmitter._broadcast_sync() to schedule into, and it returned early with
    "No app loop bound". Rather than build a second, synchronous broadcast path
    through events.py, this gives the process the one thing it lacks: a loop,
    running in a daemon thread. run_coroutine_threadsafe() then works exactly as
    it does in the web workers.

    Returns:
        A handle to stop the loop with, or None when the bus could not start.
    """
    try:
        from app.services.notifications.events import get_event_emitter
        from app.services.websocket_manager import get_websocket_manager

        bus = build_bus()
        loop = asyncio.new_event_loop()
        started = threading.Event()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.call_soon(started.set)
            loop.run_forever()

        thread = threading.Thread(target=_run, name="ws_bus_loop", daemon=True)
        thread.start()
        if not started.wait(timeout=5):
            raise RuntimeError("bus loop thread did not start")

        asyncio.run_coroutine_threadsafe(bus.start(None), loop).result(timeout=5)
        get_websocket_manager().set_bus(bus)
        get_event_emitter().set_event_loop(loop)
        logger.info("WebSocket bus started (publish-only, background loop)")
        return ThreadedBus(bus=bus, loop=loop, thread=thread)
    except Exception as exc:
        logger.warning("WebSocket bus could not start (threaded): %s", exc)
        return None
```

Add to that module's imports: `import threading` and `from dataclasses import dataclass`.

In `backend/scripts/monitoring_worker.py`, inside `async_main()` right after `init_event_emitter(SessionLocal)` (`:42`):

```python
    # Let emit_sync() broadcasts leave this process: bind the loop and publish
    # onto the cross-process bus. Without this, temperature and disk-space
    # notifications reached the database and Firebase but no WebSocket (#685).
    from app.services.ws_bus_publisher import start_publish_only_bus
    await start_publish_only_bus()
```

In `backend/scripts/scheduler_worker.py`, inside the synchronous `main()` right after `init_event_emitter(SessionLocal)` (`:47`) — **the threaded variant**, because this function has no event loop:

```python
    # Let emit_sync() broadcasts leave this process. main() is synchronous, so
    # the bus brings its own loop in a daemon thread — _broadcast_sync() needs
    # one to schedule into. Without this, scheduler failure notifications
    # reached the database and Firebase but no WebSocket (#685).
    from app.services.ws_bus_publisher import start_publish_only_bus_threaded
    _ws_bus_handle = start_publish_only_bus_threaded()
```

And in the same function's existing `finally:` block, after the `worker.shutdown()` line:

```python
    finally:
        if worker.running:
            worker.shutdown()
        if _ws_bus_handle is not None:
            _ws_bus_handle.stop()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_ws_bus_publisher.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Verify both workers still import and start**

Run: `cd backend && python -c "import scripts.monitoring_worker, scripts.scheduler_worker; print('imports clean')"`
Expected: `imports clean`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ws_bus_publisher.py backend/tests/services/test_ws_bus_publisher.py backend/scripts/monitoring_worker.py backend/scripts/scheduler_worker.py
git commit -m "fix(ws): Meldungen der eigenständigen Worker erreichen erstmals Clients (#685)"
```

---

### Task 7: Ein Primary Worker statt zwei

**Files:**
- Modify: `backend/app/core/lifespan.py:96-135` (`_try_become_primary`)
- Test: `backend/tests/core/test_primary_worker_channel.py` (neu)

**Interfaces:**
- Consumes: `settings.channel` aus `app.core.config`
- Produces: unveränderte Signatur `_try_become_primary() -> bool`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/core/test_primary_worker_channel.py`:

```python
"""The local-channel unit must never own the hardware loops.

Production runs two systemd units of the same app. baluhost-backend sets
PrivateTmp=true, baluhost-backend-local does not, so each unit sees a different
/tmp/baluhost-primary.lock and BOTH elected a primary worker — confirmed live
on 2026-09-23 (PID 1339281 and PID 1338770 both logged "Primary worker: True").
Fan control, the power manager, the SMART collector and mDNS all ran twice, and
so did the scheduled-reboot tick, which means two processes could independently
fire `systemctl reboot`.

Note for anyone reading a failure here: tests/conftest.py:31 sets
BALUHOST_CHANNEL=local for the whole suite, so after this change
_try_become_primary() returns False by default everywhere. The tests below that
need the production behaviour set settings.channel explicitly.
"""

from pathlib import Path

import pytest

from app.core import lifespan as lifespan_module


@pytest.fixture(autouse=True)
def _release_lock():
    yield
    fd = getattr(lifespan_module, "_primary_lock_fd", None)
    if fd is not None:
        fd.close()
        lifespan_module._primary_lock_fd = None


def test_local_channel_never_becomes_primary(monkeypatch, tmp_path):
    monkeypatch.setattr(lifespan_module.settings, "channel", "local")
    touched = tmp_path / "should-not-exist.lock"
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", touched)

    assert lifespan_module._try_become_primary() is False
    assert not touched.exists(), "the local channel must not even open the lock"


def test_remote_channel_still_wins_the_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(lifespan_module.settings, "channel", "remote")
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", tmp_path / "primary.lock")

    assert lifespan_module._try_become_primary() is True


def test_explicit_env_override_still_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(lifespan_module.settings, "channel", "remote")
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", tmp_path / "primary.lock")
    monkeypatch.setenv("BALUHOST_PRIMARY_WORKER", "0")

    assert lifespan_module._try_become_primary() is False


def test_second_remote_process_does_not_also_win(monkeypatch, tmp_path):
    """The flock behaviour that keeps one owner within a unit must survive."""
    import fcntl

    lock = tmp_path / "primary.lock"
    monkeypatch.setattr(lifespan_module.settings, "channel", "remote")
    monkeypatch.setattr(lifespan_module, "PRIMARY_LOCK_PATH", lock)

    holder = open(lock, "a")
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert lifespan_module._try_become_primary() is False
    finally:
        holder.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/core/test_primary_worker_channel.py -v`
Expected: FAIL — `AttributeError: module 'app.core.lifespan' has no attribute 'PRIMARY_LOCK_PATH'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/core/lifespan.py`, lift the lock path to a module constant so it can be pointed at a tmpdir in tests. Next to `_primary_lock_fd`:

```python
# Kept as a module attribute so tests can redirect it; production never changes it.
PRIMARY_LOCK_PATH = Path("/tmp/baluhost-primary.lock")
```

Extend the detection comment block to name the channel rule, then add the gate at the top of `_try_become_primary()`:

```python
def _try_become_primary() -> bool:
    """Try to acquire the primary-worker file lock (non-blocking).

    Returns True if this process is now the primary worker.
    """
    # The local channel never owns the hardware loops. Both units run the same
    # app, but only baluhost-backend.service sets PrivateTmp=true — so each unit
    # sees its own lock file and both used to elect a primary, running fan
    # control, the power manager, the SMART collector and mDNS twice over.
    #
    # Gating on the channel rather than sharing one lock path under /run is
    # deliberate: a shared lock would hand the role to whoever starts first, and
    # that is the socket-activated local unit — precisely the process that
    # should not have it. BALUHOST_CHANNEL=local is already set in that unit, so
    # this needs no unit-template change (#689) and no operator step.
    if settings.channel == "local":
        return False

    # Explicit opt-out via env var
    env_val = os.environ.get("BALUHOST_PRIMARY_WORKER")
    if env_val == "0":
        return False

    # On non-Linux (Windows dev-mode), skip file locking
    try:
        import fcntl as _fcntl  # type: ignore[import-not-found]
    except ImportError:
        return True

    global _primary_lock_fd
    lock_path = PRIMARY_LOCK_PATH
```

Leave the rest of the function unchanged.

**What this costs, stated plainly — it is more than the design first claimed.**
`baluhost-backend.service` has `Restart=always`/`RestartSec=10s`, so a normal
restart leaves the box without a primary for about ten seconds. But a
crash-looping or deliberately stopped TCP unit leaves it without one
**indefinitely**, because the socket-activated local unit stays up and no longer
volunteers. During that window nothing runs the fan loop, the power manager's
enforcement and `command_queue.run_poll_loop`, the sleep manager, the scheduled
reboot tick, the SMART and panel bridges, the heartbeat writer, or plugin
background tasks.

Concretely for the Companion: `POST /api/power/boost-now` and
`PUT /api/power/authority` sit behind `require_local_admin`, i.e. they are
reachable **only** through the local unit. On a follower they go through the
command queue with a 3-second timeout, which the TCP primary's poll loop serves.
That works in normal operation and fails with a timeout while the TCP unit is
down — where today it works, because the local unit happens to be primary.

That trade is still right, and the reason is bigger than the duplicate
notifications: `_schedule_check_loop` runs in *both* primaries today, so **two
processes can independently arm and fire `systemctl reboot`** — the widest
sudoers grant in this project (`ci-cd-security.md`, Known Gap 11). Task 7 closes
a double-reboot hazard, and that alone justifies it.

**No new health signal is built for this, deliberately.** The condition "no
primary" is identical to "the TCP unit is down", and that is already loud: the
web UI is unreachable, and the tray points at `http://localhost:8000`
(`baluhost_tray/main.py:18`) so it reports connection failures. An extra
"no primary elected" indicator would restate what two other surfaces already
show. If the operator later wants it explicitly, the mechanism is already
there — `service_heartbeats.updated_at` is written only by the primary every 15
seconds, so "newest row older than 45 seconds" is the whole detector. That is a
follow-up, not part of this work.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/core/test_primary_worker_channel.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Check nothing else depended on the old behaviour**

Run: `cd backend && python -m pytest tests -k "primary or lifespan" -v`
Expected: PASS. If a test asserted that a `local`-channel process becomes primary, that assertion encoded the bug — update it and note the reason in the commit body.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/lifespan.py backend/tests/core/test_primary_worker_channel.py
git commit -m "fix(power): Nur der Fernkanal wird Primary Worker, nicht beide Units"
```

---

### Task 8: Gesamtobergrenze für Verbindungen

**Files:**
- Modify: `backend/app/services/websocket_manager.py:15-17` (Konstanten) und `connect()`
- Test: `backend/tests/services/test_websocket_manager.py`

**Interfaces:**
- Consumes: `ConnectionLimitExceeded` (existiert)
- Produces: Konstante `MAX_CONNECTIONS_TOTAL = 100`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_websocket_manager.py`:

```python
@pytest.mark.asyncio
class TestTotalConnectionCap:
    """The per-user cap bounded nothing in aggregate: N users meant N*5 sockets."""

    async def test_rejects_beyond_the_total_cap(self, manager: WebSocketManager):
        from app.services.websocket_manager import (
            MAX_CONNECTIONS_TOTAL,
            ConnectionLimitExceeded,
        )

        # Fill the process with connections from many different users, so the
        # per-user cap is never the thing that trips.
        for user_id in range(MAX_CONNECTIONS_TOTAL):
            await manager.connect(_make_ws(), user_id=user_id)

        with pytest.raises(ConnectionLimitExceeded):
            await manager.connect(_make_ws(), user_id=9999)

    async def test_per_user_cap_still_applies_below_the_total(
        self, manager: WebSocketManager
    ):
        from app.services.websocket_manager import (
            MAX_CONNECTIONS_PER_USER,
            ConnectionLimitExceeded,
        )

        for _ in range(MAX_CONNECTIONS_PER_USER):
            await manager.connect(_make_ws(), user_id=1)

        with pytest.raises(ConnectionLimitExceeded):
            await manager.connect(_make_ws(), user_id=1)

    async def test_total_cap_is_higher_than_the_per_user_cap(self):
        from app.services.websocket_manager import (
            MAX_CONNECTIONS_PER_USER,
            MAX_CONNECTIONS_TOTAL,
        )

        assert MAX_CONNECTIONS_TOTAL > MAX_CONNECTIONS_PER_USER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_websocket_manager.py::TestTotalConnectionCap -v`
Expected: FAIL — `ImportError: cannot import name 'MAX_CONNECTIONS_TOTAL'`

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/websocket_manager.py`, replace the constant block:

```python
# Max simultaneous WebSocket connections per user, per PROCESS (DoS guard,
# Posten 5 #2). Six API processes hold connections — four workers of
# baluhost-backend plus two of baluhost-backend-local — so one user can reach
# up to 6x this number in total. Enforcing it across processes would need
# shared state (a presence table, or advisory locks on the bus connection);
# that is deliberately not built, because the binding limit is the one below.
MAX_CONNECTIONS_PER_USER = 5

# Max simultaneous connections in this process, across all users. Without this
# the per-user cap bounded nothing in aggregate: N accounts meant N*5 sockets
# and the number that costs memory was unlimited.
MAX_CONNECTIONS_TOTAL = 100
```

In `connect()`, check the total before the per-user cap:

```python
        async with self._lock:
            if self._count_connections() >= MAX_CONNECTIONS_TOTAL:
                raise ConnectionLimitExceeded(
                    f"process reached {MAX_CONNECTIONS_TOTAL} connections"
                )
            if len(self._user_connections.get(user_id, [])) >= MAX_CONNECTIONS_PER_USER:
                raise ConnectionLimitExceeded(
                    f"user {user_id} exceeded {MAX_CONNECTIONS_PER_USER} connections"
                )
```

The route already maps `ConnectionLimitExceeded` to `WS_1008_POLICY_VIOLATION` (`api/routes/notifications.py`), so no route change is needed — confirm that by reading the handler rather than assuming it.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_websocket_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/websocket_manager.py backend/tests/services/test_websocket_manager.py
git commit -m "fix(ws): Gesamtobergrenze für Verbindungen je Prozess einführen"
```

---

### Task 9: Pool-Dimensionierung belegen statt verkleinern

**Files:**
- Modify: `backend/app/core/database.py:_get_pg_pool_config` (nur der Docstring)
- Test: keiner — es gibt keine Verhaltensänderung zu testen

Dieser Task hat sich im Review umgedreht. Der ursprüngliche Plan wollte die
Defaults von `10 + 20` auf `5 + 5` senken. Die Messung sagt, dass das eine
Regression wäre:

| Kennzahl (65.734 Concurrency-Fenster seit 2026-08-20) | Wert |
|---|---|
| `pool_in_use_max`, Spitze | **11** |
| `pool_open_max`, Spitze | 10 |
| `pool_saturation_events` | 0 |
| Fenster mit ≥6 belegten Verbindungen | 84 |

Eine Decke von 10 (= `5 + 5`) liegt **unter** der gemessenen Spitze von 11: die
elfte Anforderung wartet `pool_timeout=30`, bekommt `TimeoutError` und wird zu
HTTP 500 auf einer Nutzeranfrage. Nach der Datenlage etwa monatlich, gehäuft in
genau den Bursts, in denen die Box ohnehin lädt. Die „2–3 je Prozess" aus dem
ersten Entwurf waren ein Schnappschuss aus einer ruhigen Minute, kein Maximum.

Dazu kommt, dass das Ziel gar nicht erreichbar war: die drei Worker-Skripte
haben je eine eigene Engine, der theoretische Verbrauch ist also
`6×Decke + 6 Listener + 3×Decke` gegen 97 nutzbare Verbindungen (100 minus 3
für Superuser reserviert). Das trägt nur bei einer Decke von 10 — also unter der
gemessenen Spitze. Die theoretische Schranke ist über Pool-Größen nicht zu
halten; dafür bräuchte es ein höheres `max_connections` oder pgbouncer, und das
ist ein Operator-Schritt mit DB-Neustart und damit ein eigenes Vorhaben.

Und es wäre ohnehin der schlechteste Zeitpunkt zum Verkleinern: Task 3 führt mit
`_notify_sync()` einen **neuen** Pool-Verbraucher ein. Er ist durch den
Single-Thread-Executor auf eine Verbindung je Prozess begrenzt, aber er ist neu.

- [ ] **Step 1: Die Messung dorthin schreiben, wo beim nächsten Mal gesucht wird**

In `backend/app/core/database.py`, **nur** der Docstring — die Werte bleiben:

```python
def _get_pg_pool_config() -> dict:
    """Get PostgreSQL connection pool configuration from environment.

    Sizing note, measured 2026-09-23 over 65,734 concurrency windows of
    baluhost-backend: peak pool_in_use_max was 11, peak pool_open_max 10, and
    pool_saturation_events stayed at 0 against the ceiling of 30 these values
    give. Do not lower them without re-measuring — a ceiling of 10 would sit
    *under* the observed peak and turn a burst into HTTP 500 after pool_timeout.

    The theoretical worst case does exceed the server: nine processes (six API
    workers plus three standalone workers, each with its own engine) times 30,
    against max_connections=100. It has never been approached, and shrinking the
    pool cannot fix it — the only real remedies are a higher max_connections or
    pgbouncer. Publishing on the ws bus adds one pooled connection per process;
    its single-worker executor is what bounds it to one.
    """
```

- [ ] **Step 2: Nichts kaputtgemacht?**

Run: `cd backend && python -m pytest tests/core -q`
Expected: PASS. Der Docstring ändert kein Verhalten; der Lauf belegt nur, dass die Datei heil ist.

- [ ] **Step 3: Commit**

```
commit -m "docs(db): Pool-Dimensionierung mit Messwerten belegen statt raten"
```

### Task 10: Verifikationsskript, Doku, Gesamtlauf

**Files:**
- Create: `backend/scripts/debug/verify_ws_bus.py`
- Modify: `backend/app/services/CLAUDE.md`, `.claude/rules/architecture.md`, `CLAUDE.md`
- Test: der vollständige Suite-Lauf

- [ ] **Step 1: Write the verification script**

Create `backend/scripts/debug/verify_ws_bus.py`:

```python
"""Prove the cross-process bus works against the real database.

CI runs SQLite only, so no test touches the LISTEN path. This script is that
gap's counterweight, in two phases:

1. A listener in a child process receives an envelope published by the parent.
2. The parent kills the listener's Postgres session and publishes again. This
   is the phase worth having: the reconnect path is where this class fails, and
   a unit test cannot see it, because a fake connection's fileno() does not
   raise the way psycopg2's does once the connection is gone.

Run on the box:

    cd <worktree>/backend
    /opt/baluhost/backend/.venv/bin/python scripts/debug/verify_ws_bus.py

It only ever kills the session it created itself, by pid. Exit code 0 means
both phases delivered.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

MARKER = "verify-ws-bus"
TIMEOUT_SECONDS = 10.0
PROD_ENV_FILE = Path("/opt/baluhost/.env.production")


def _ensure_dsn() -> None:
    """Put DATABASE_URL into the environment before anything imports settings.

    Settings read `.env`, not `.env.production` (config.py:282), so running this
    by hand against the production database needs the value supplied. Read from
    the file rather than passed on the command line — a DSN carries a password,
    and a command line is readable in ps.
    """
    if os.environ.get("DATABASE_URL"):
        return
    if not PROD_ENV_FILE.exists():
        return
    for line in PROD_ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("DATABASE_URL="):
            os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip("\"'")
            return


def _listener(
    ready: multiprocessing.Event,
    got: multiprocessing.Queue,
    pids: multiprocessing.Queue,
) -> None:
    """Child process: listen, report its backend pid and every matching envelope."""

    async def main() -> None:
        from app.services.ws_bus import build_bus

        async def deliver(env) -> None:
            if env.msg_type == MARKER:
                got.put(env.payload)

        bus = build_bus()
        await bus.start(deliver)
        # The listener connection's server-side pid, so the parent can kill
        # exactly this session and nothing else.
        with bus._conn.cursor() as cur:
            cur.execute("SELECT pg_backend_pid()")
            pids.put(cur.fetchone()[0])
        ready.set()
        await asyncio.sleep(TIMEOUT_SECONDS * 3)
        await bus.stop()

    asyncio.run(main())


def _terminate(pid: int) -> None:
    """Kill one Postgres session — the listener's, by pid."""
    from app.core.database import engine

    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT pg_terminate_backend(%s)", (pid,))
        conn.commit()


async def _publish(phase: str) -> None:
    from app.services.ws_bus import WsEnvelope, build_bus

    bus = build_bus()
    await bus.publish(
        WsEnvelope(
            kind="all",
            msg_type=MARKER,
            payload={"phase": phase, "sent_at": time.time()},
        )
    )


def main() -> int:
    _ensure_dsn()

    import app.services.ws_bus as ws_bus_module
    from app.core.database import DATABASE_URL

    # Say which copy of the code is under test — running this from the
    # production working directory against a worktree checkout is exactly the
    # situation where a PASS could mean nothing.
    print(f"using {ws_bus_module.__file__}")
    # Also name the database: /opt/baluhost/backend/.env holds a DIFFERENT DSN
    # than .env.production, so a PASS against the wrong database would be
    # indistinguishable otherwise.
    print(f"database {DATABASE_URL.rsplit('@', 1)[-1]}")

    if not DATABASE_URL.startswith("postgresql"):
        print(f"FAIL: needs PostgreSQL, got {DATABASE_URL.split(':')[0]}")
        return 1

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    got: multiprocessing.Queue = ctx.Queue()
    pids: multiprocessing.Queue = ctx.Queue()
    child = ctx.Process(target=_listener, args=(ready, got, pids), daemon=True)
    child.start()

    try:
        if not ready.wait(timeout=TIMEOUT_SECONDS):
            print("FAIL: listener process never became ready")
            return 1

        # ---- phase 1: does it work at all? ----
        started = time.perf_counter()
        asyncio.run(_publish("phase1"))
        try:
            payload = got.get(timeout=TIMEOUT_SECONDS)
        except Exception:
            print("FAIL phase 1: envelope never arrived in the other process")
            return 1
        print(
            f"PASS phase 1: delivered cross-process in "
            f"{(time.perf_counter() - started) * 1000:.1f} ms (payload={payload})"
        )

        # ---- phase 2: does it survive losing the connection? ----
        # This is the phase that matters. A listener whose reader was not
        # unregistered on loss reconnects, logs success, and never delivers
        # again — and no unit test can see it, because a fake connection's
        # fileno() does not raise the way psycopg2's does.
        listener_pid = pids.get(timeout=TIMEOUT_SECONDS)
        print(f"terminating the listener's backend pid {listener_pid} ...")
        _terminate(listener_pid)

        deadline = time.monotonic() + TIMEOUT_SECONDS * 2
        while time.monotonic() < deadline:
            asyncio.run(_publish("phase2"))
            try:
                payload = got.get(timeout=2.0)
            except Exception:
                continue
            print(f"PASS phase 2: delivered again after reconnect (payload={payload})")
            return 0

        print("FAIL phase 2: nothing arrived after the connection was killed")
        print("  -> the listener reconnected but its fd is not being watched")
        return 1
    finally:
        child.terminate()
        child.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it on the box against the real database**

Run it from the worktree with the production virtualenv (which has psycopg2), letting `_ensure_dsn()` pull the DSN out of `/opt/baluhost/.env.production`:

```bash
cd /home/sven/projects/BaluHost/.claude/worktrees/ws-broadcast-bridge/backend
/opt/baluhost/backend/.venv/bin/python scripts/debug/verify_ws_bus.py
```

The first output line names the `ws_bus.py` that was imported. It must be the worktree's path — if it says `/opt/baluhost/backend/app/services/ws_bus.py`, the run verified the deployed code and a PASS means nothing.

This publishes one envelope with `msg_type="verify-ws-bus"` onto the production channel. Harmless: the deployed code has no listener yet, and every client ignores message types it does not know.

Expected: `PASS: delivered cross-process in <N> ms`. Paste the actual output into the PR description — this is the only evidence that the Postgres path works, since CI cannot produce it.

If it reports FAIL, do not proceed: check `journalctl` for `ws bus:` lines, confirm `DATABASE_URL` resolves, and confirm the database accepts two more connections.

- [ ] **Step 3: Update the documentation**

`backend/app/services/CLAUDE.md:8-9` is a **table** (`| File | Purpose |`), not a bullet list. Add two rows, and amend the existing `websocket_manager.py` row at `:19`:

```markdown
| `websocket_manager.py` | WebSocket connections; publish methods build envelopes for `ws_bus`, `deliver_local()` is the only code that writes to sockets (#685) |
| `ws_bus.py` | Cross-process broadcast bus over Postgres LISTEN/NOTIFY; one listener connection per API process, outside the pool. Not durable by design |
| `ws_bus_publisher.py` | Publish-only bus wiring for `monitoring_worker` / `scheduler_worker` (no sockets there), plus the `set_event_loop()` call those processes never made |
```

In `backend/app/core/CLAUDE.md:26`, the multi-worker line is now wrong — the channel decides before the lock does. Replace it with:

```markdown
- **Multi-worker**: Production runs 4 Uvicorn workers in `baluhost-backend` plus 2 in `baluhost-backend-local`. Only one process becomes primary: the local channel never volunteers (`settings.channel == "local"` → False), the rest race for the file lock in `/tmp/baluhost-primary.lock`. Hardware services (fans, power, mDNS, monitoring) only run on primary. Before #685 each unit had its own `PrivateTmp` view of that lock and **both** elected one, running every hardware loop twice
```

Also in `backend/app/core/CLAUDE.md:14`, the `lifespan.py` row gains `_start_ws_bus`/`_stop_ws_bus` (started in **every** worker, not just the primary) and `PRIMARY_LOCK_PATH`.

In `.claude/rules/architecture.md`, add to the top-level services list:

```markdown
- `ws_bus.py` - Prozessübergreifender Broadcast-Bus (Postgres LISTEN/NOTIFY);
  ein Listener je API-Prozess, Zustellung nur aus dem Listener (#685)
```

In the root `CLAUDE.md`, add to "Quick Reference: Finding Things":

```markdown
**WebSocket-Broadcasts über Prozessgrenzen**: `backend/app/services/ws_bus.py`
(Bus), `websocket_manager.py:deliver_local()` (Zustellung), Design:
`docs/superpowers/specs/2026-09-23-ws-broadcast-bridge-design.md`
```

In `.claude/rules/security-agent.md`, extend the raw-SQL exception. The NEVER
reads "Execute raw SQL with user-controlled input — ORM-only; sole exception:
static query strings in `services/audit/admin_db.py`". That list is exhaustive,
and `ws_bus.py` now interpolates an identifier into `LISTEN`, so leaving the rule
untouched guarantees a future security review re-litigates it (and CodeQL's
`py/sql-injection` flags f-strings in `execute`). Change it to:

```markdown
- Execute raw SQL with user-controlled input — ORM-only; sole exceptions: static
  query strings in `services/audit/admin_db.py`, and `LISTEN`/`pg_notify` in
  `services/ws_bus.py` (the channel name is a module constant asserted to be a
  bare identifier at import; `LISTEN` cannot take a bind parameter, the payload
  always does)
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && python -m pytest -q --deselect tests/plugins/sandbox/test_phase3_e2e.py::test_e2e_storage_and_metrics_granted`

Expected: no failures. The deselected test fails on this machine for a path-length reason unrelated to this work (#706).

**On comparing against a baseline:** the suite collects ~5941 tests. The figure "1211 passed" recorded before this work came from a `-x` run that stopped at the sandbox failure and is therefore **not** comparable to this command's output — do not treat a number near 5900 as an anomaly. If a baseline comparison is wanted, re-run this exact command on `origin/main` first and use that number. Either way: report the actual output, and do not claim the suite is green without it in front of you.

- [ ] **Step 5: Confirm the client ignores the verification message type**

No frontend change is needed — the frame on the wire is unchanged
(`{"type": ..., "payload": ...}`). `npm run build` is **not** the way to confirm
that: this worktree has no `client/node_modules`, so the build would fail for
reasons unrelated to the change, and no frontend file is touched anyway.

Instead read the message switch in `client/src/hooks/useNotificationSocket.ts`
and confirm an unknown `type` (specifically `verify-ws-bus` from the
verification script) falls through without throwing. That is the one frontend
assumption this work actually makes.

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/debug/verify_ws_bus.py backend/app/services/CLAUDE.md .claude/rules/architecture.md CLAUDE.md
git commit -m "docs(ws): Bus dokumentieren und Verifikationsskript für den echten Pfad (#685)"
```

---

## Nach dem Plan: Abnahme am lebenden System

Diese drei Prüfungen gehören in die PR-Beschreibung, mit echter Ausgabe:

1. **Der eigentliche Fehler ist weg.** Einen Scheduler-Job über
   `/api/schedulers/<name>/run-now` auslösen, der eine Meldung erzeugt, und das
   Tray-Popup beobachten — **viermal hintereinander, viermal ein Popup**. Vorher
   war die Trefferquote etwa eins von vier.
2. **Ein Primary Worker.** `journalctl -u baluhost-backend-local --since "<Start>" | grep "Primary worker"`
   zeigt für alle Worker `False`; dieselbe Abfrage auf `baluhost-backend` zeigt
   genau ein `True`.
3. **Der neue Pool-Verbraucher tut nicht weh.** `pool_saturation_events` bleibt
   über eine Woche bei 0 (`journalctl -u baluhost-backend | grep pool_saturation`).
   Das ist das Kriterium, nicht ein einmaliges `select count(*) from
   pg_stat_activity` — das zeigt nur einen Augenblick, und die Spitzen sind
   genau das, was hier interessiert. Zum Vergleich: über 65.734 Fenster seit
   dem 20.08. lag die Spitze bei 11 belegten Verbindungen je Prozess, bei 0
   Sättigungen.
4. **Der Reconnect hält.** `scripts/debug/verify_ws_bus.py` ein zweites Mal
   fahren, diesmal gegen die deployte Version. Phase 2 tötet die
   Listener-Sitzung und publiziert erneut — das ist der Pfad, den kein Unit-Test
   sehen kann.

## Offene Punkte, die dieser Plan bewusst nicht schließt

- **Prozessübergreifende Obergrenze je Nutzer** — begründet nicht gebaut, siehe
  Spec („Nicht-Ziele") und Task 8.
- **Haltbarkeit über Verbindungsabrisse** — bewusst nicht, siehe Spec.
- **Issue #706** (`AF_UNIX path too long` in der Plugin-Sandbox) — eigener
  Befund, eigener Fix; hier nur als Grund, `-x` nicht zu benutzen.
