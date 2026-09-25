"""Closing a user's WebSockets after a role or status change (#468).

A connection's is_admin is a snapshot from connect time. Instead of re-reading
the role on every broadcast, the sockets of a changed user are closed; the
client reconnects on any code but 1000 and gets a fresh snapshot. The close
has to travel over the bus, because the socket may live in another process.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.websocket_manager import (
    WS_CLOSE_SESSION_CHANGED,
    WebSocketManager,
)
from app.services.ws_bus import WsEnvelope


def _make_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestCloseUserEnvelope:
    def test_close_user_is_a_valid_kind(self):
        env = WsEnvelope(kind="close_user", msg_type="session_changed", payload=None, user_id=7)
        assert env.kind == "close_user"

    def test_roundtrips_through_json(self):
        env = WsEnvelope(kind="close_user", msg_type="session_changed", payload=None, user_id=7)
        parsed = WsEnvelope.from_json(env.to_json())
        assert parsed == env


@pytest.mark.asyncio
class TestDeliverCloseUser:
    async def test_closes_only_that_users_sockets(self):
        manager = WebSocketManager()
        target_a, target_b, other = _make_ws(), _make_ws(), _make_ws()
        await manager.connect(target_a, user_id=1, is_admin=True)
        await manager.connect(target_b, user_id=1, is_admin=True)
        await manager.connect(other, user_id=2, is_admin=True)

        closed = await manager.deliver_local(
            WsEnvelope(kind="close_user", msg_type="session_changed", payload=None, user_id=1)
        )

        assert closed == 2
        target_a.close.assert_awaited_once_with(code=WS_CLOSE_SESSION_CHANGED)
        target_b.close.assert_awaited_once_with(code=WS_CLOSE_SESSION_CHANGED)
        other.close.assert_not_awaited()
        assert not manager.is_user_connected(1)
        assert manager.is_user_connected(2)

    async def test_demoted_admin_gets_no_admin_broadcast_afterwards(self):
        # The actual leak from #468: before the fix the stale is_admin=True
        # connection kept receiving admins_only payloads.
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws, user_id=1, is_admin=True)

        await manager.close_user_connections(1)
        await manager.broadcast_typed("dashboard_panel_update", {"x": 1}, admins_only=True)
        await manager.broadcast_to_admins({"title": "t"})

        ws.send_json.assert_not_awaited()
        assert 1 not in manager._admin_users

    async def test_close_failure_still_removes_the_connection(self):
        manager = WebSocketManager()
        ws = _make_ws()
        ws.close = AsyncMock(side_effect=RuntimeError("already closed"))
        await manager.connect(ws, user_id=1, is_admin=True)

        await manager.close_user_connections(1)

        assert not manager.is_user_connected(1)
        assert 1 not in manager._admin_users

    async def test_without_user_id_is_dropped(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws, user_id=1)

        closed = await manager.deliver_local(
            WsEnvelope(kind="close_user", msg_type="session_changed", payload=None)
        )

        assert closed == 0
        ws.close.assert_not_awaited()
        assert manager.is_user_connected(1)

    async def test_close_user_connections_publishes_over_the_bus(self):
        bus = MagicMock()
        bus.publish = AsyncMock()
        manager = WebSocketManager(bus=bus)

        await manager.close_user_connections(5)

        env = bus.publish.await_args.args[0]
        assert env.kind == "close_user"
        assert env.user_id == 5
