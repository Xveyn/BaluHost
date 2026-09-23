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
