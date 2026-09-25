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

import asyncio
import json
import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
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

# "close_user" is a command, not a broadcast: every process closes that user's
# sockets (#468). It carries no payload to any client.
VALID_KINDS = frozenset({"user", "admins", "all", "close_user"})

Deliver = Callable[["WsEnvelope"], Awaitable[None]]

# Matches the password segment of a `scheme://user:password@host` DSN, same
# shape core/database.py already redacts out of its startup log line.
_DSN_PASSWORD_RE = re.compile(r"(://[^:/@\s]*:)[^@\s]*(@)")


def _safe_reason(exc: BaseException) -> str:
    """A logging-safe rendering of an exception raised by this module.

    security-agent.md forbids logging secrets, "not even at DEBUG level", and
    two kinds of secret can otherwise reach these logs: a listener connect
    failure can echo the DSN verbatim, password included — psycopg2's
    `invalid dsn: missing "="...` (see _libpq_dsn's docstring) carries the
    whole attempted DSN — and a publish failure from SQLAlchemy appends
    `[SQL: ...]` / `[parameters: (...)]` on their own line(s), where the
    parameters are this module's own broadcast payload. Taking only the
    first line already drops the parameters clause; the regex then redacts
    a DSN password on that first line the same way core/database.py redacts
    it from its own startup log.
    """
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    return _DSN_PASSWORD_RE.sub(r"\1***\2", first_line)


@dataclass(frozen=True)
class WsEnvelope:
    """One broadcast, with the addressing the WebSocketManager needs.

    kind is the audience: a single user, every admin, or everyone — or
    "close_user", which closes one user's sockets instead of writing to them.
    msg_type is the type that reaches the wire unchanged — the client matches
    on it.
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
            # Not the raw exc: a SQLAlchemy DBAPIError's str() appends
            # "[parameters: (...)]" with this envelope's own payload —
            # logging it verbatim would put the broadcast's contents in the
            # log. type(exc).__name__ plus _safe_reason() is enough to act
            # on; the payload doesn't belong here.
            logger.warning(
                "ws bus: publish of %s failed: %s: %s",
                env.msg_type,
                type(exc).__name__,
                _safe_reason(exc),
            )

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

        # connect_timeout: an unreachable server would otherwise park this
        # to_thread call forever — no reconnect, no log line, indistinguishable
        # from a healthy listener. keepalives: a silently dropped TCP
        # connection (Postgres OOM-killed, a stateful firewall) never fires
        # add_reader either, so the bus goes quiet with no warning; keepalive
        # probes turn that into a detectable poll() failure instead.
        conn = psycopg2.connect(
            dsn, connect_timeout=10, keepalives=1, keepalives_idle=30
        )
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        return conn

    def _listen(self, conn: Any) -> None:
        """Issue LISTEN on a connection, whatever produced it.

        Deliberately not part of connect_fn: connect_fn's job is only to hand
        back a connection (real psycopg2, or a test double). LISTEN is the
        bus's own protocol setup and must run the same way for every
        connection, so it lives here instead of being duplicated into every
        connect_fn implementation.
        """
        with conn.cursor() as cur:
            # LISTEN takes an identifier, which cannot be parameterised. CHANNEL
            # is a module constant and never user input — see its definition.
            cur.execute(f"LISTEN {CHANNEL}")

    async def _open(self) -> None:
        try:
            conn = await asyncio.to_thread(self._connect_fn, self._dsn)
        except Exception as exc:
            # Not the raw exc: psycopg2's own "invalid dsn: ..." failure
            # echoes the full DSN, password included (see _libpq_dsn).
            logger.warning("ws bus: listener connect failed: %s", _safe_reason(exc))
            self._schedule_reconnect()
            return

        if self._stopping:
            # Reached only when this particular call to _open() was not
            # itself cancelled — the initial call from start(), or a race
            # where _open() resumed just before stop() got to cancel it.
            # When stop() instead cancels a live _reopen_after() task while
            # it is parked in the await above, CancelledError fires at that
            # await and this guard is never reached at all — the residual
            # risk is an abandoned connection that this code never closes.
            # psycopg2 closes it via its own destructor once nothing
            # references it anymore; deliberately not architected away with
            # a _pending_conn wrapper for what is only a shutdown path.
            self._close_conn(conn)
            return

        try:
            await asyncio.to_thread(self._listen, conn)
        except Exception as exc:
            logger.warning("ws bus: LISTEN %s failed: %s", CHANNEL, exc)
            self._close_conn(conn)
            self._schedule_reconnect()
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
        # min(self._attempt, 16): min() evaluates both its arguments before
        # comparing them, so it cannot protect against 2 ** self._attempt
        # itself overflowing. Once self._attempt reaches ~1024, converting
        # that int to a float for the multiplication raises OverflowError —
        # uncaught, since nothing calls this from inside a try block — and no
        # further reconnect is ever scheduled. Reachable after roughly 12.8
        # hours of continuous connection failure (1s base, doubling). Capping
        # the exponent at 16 keeps the value far past backoff_cap (which
        # clamps it to 60s anyway) without ever approaching float's range.
        delay = min(self._backoff_cap, self._backoff_base * (2 ** min(self._attempt, 16)))
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
        """Stop listening and shut down the publish executor.

        Cross-process publishing ends here, not just listening: the executor
        backing publish()'s pg_notify calls is shut down, so every publish()
        afterwards has run_in_executor raise "cannot schedule new futures
        after shutdown" and logs a warning instead of reaching Postgres.
        Local delivery keeps working — publish() calls self._deliver()
        directly whenever self._connected is False, which it is from here on
        — so this process's own clients still see its own broadcasts.
        """
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
