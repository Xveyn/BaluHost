"""Tests for services/ws_bus.py — envelope, local bus, Postgres bus."""

import json
import logging

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

    def test_from_json_rejects_non_dict_top_level(self):
        """A JSON array or scalar parses fine but is not one of our envelopes."""
        raw = json.dumps(["kind", "all"])
        assert WsEnvelope.from_json(raw) is None

    def test_from_json_rejects_non_integer_user_id(self):
        """user_id addresses a single socket by its int primary key.

        A string here would fail every identity comparison downstream anyway,
        but silently — this stops it at the boundary instead.
        """
        raw = json.dumps(
            {"kind": "user", "msg_type": "notification", "payload": {}, "user_id": "3"}
        )
        assert WsEnvelope.from_json(raw) is None

    def test_from_json_rejects_missing_admins_only(self):
        """admins_only is the visibility boundary, not a convenience flag.

        deliver_local() decides from this field whether a payload may reach
        every connected socket or only admins'. An envelope that lost the
        field on the wire must not be treated as admins_only=False by
        default — that default is exactly the leak an admin-only dashboard
        panel must never suffer, so from_json() fails closed instead of
        falling back to `bool(data.get("admins_only", False))`.
        """
        raw = json.dumps({"kind": "all", "msg_type": "dashboard_panel_update", "payload": {}})
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
        # add_reader's callback fires from the loop's own I/O wait, which
        # needs an actual pass through it — sleep(0) is not enough, matching
        # the sleep(0.05) the sibling listener tests already use below.
        await asyncio.sleep(0.05)

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
