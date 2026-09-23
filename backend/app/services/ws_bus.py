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
