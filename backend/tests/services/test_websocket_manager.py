"""Tests for services/websocket_manager.py — WebSocketManager with mock WebSockets."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.websocket_manager import Connection, WebSocketManager, get_websocket_manager


def _make_ws(send_json_side_effect=None) -> MagicMock:
    """Create a mock WebSocket object."""
    ws = MagicMock()
    ws.send_json = AsyncMock(side_effect=send_json_side_effect)
    return ws


@pytest.fixture
def manager() -> WebSocketManager:
    return WebSocketManager()


@pytest.mark.asyncio
class TestConnect:
    async def test_registers_connection(self, manager: WebSocketManager):
        ws = _make_ws()
        conn = await manager.connect(ws, user_id=1)
        assert isinstance(conn, Connection)
        assert conn.user_id == 1
        assert manager.is_user_connected(1)
        assert manager.get_connection_count(1) == 1

    async def test_multiple_connections_same_user(self, manager: WebSocketManager):
        ws1, ws2 = _make_ws(), _make_ws()
        await manager.connect(ws1, user_id=1)
        await manager.connect(ws2, user_id=1)
        assert manager.get_connection_count(1) == 2

    async def test_admin_tracked(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1, is_admin=True)
        assert 1 in manager._admin_users


@pytest.mark.asyncio
class TestDisconnect:
    async def test_removes_connection(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1)
        await manager.disconnect(ws)
        assert not manager.is_user_connected(1)

    async def test_disconnect_one_of_many(self, manager: WebSocketManager):
        ws1, ws2 = _make_ws(), _make_ws()
        await manager.connect(ws1, user_id=1)
        await manager.connect(ws2, user_id=1)
        await manager.disconnect(ws1)
        assert manager.get_connection_count(1) == 1

    async def test_disconnect_unknown_ws_is_noop(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.disconnect(ws)  # Should not raise

    async def test_admin_removed_when_last_connection_drops(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1, is_admin=True)
        await manager.disconnect(ws)
        assert 1 not in manager._admin_users


@pytest.mark.asyncio
class TestBroadcastToUser:
    async def test_sends_to_user(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1)
        count = await manager.broadcast_to_user(1, {"msg": "hello"})
        assert count == 1
        ws.send_json.assert_called_once()
        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "notification"
        assert payload["payload"] == {"msg": "hello"}

    async def test_returns_zero_for_disconnected_user(self, manager: WebSocketManager):
        count = await manager.broadcast_to_user(999, {"msg": "hello"})
        assert count == 0

    async def test_cleans_up_failed_connection(self, manager: WebSocketManager):
        ws = _make_ws(send_json_side_effect=Exception("connection lost"))
        await manager.connect(ws, user_id=1)
        count = await manager.broadcast_to_user(1, {"msg": "hello"})
        assert count == 0
        assert not manager.is_user_connected(1)


@pytest.mark.asyncio
class TestBroadcastToAdmins:
    async def test_sends_only_to_admins(self, manager: WebSocketManager):
        ws_admin = _make_ws()
        ws_user = _make_ws()
        await manager.connect(ws_admin, user_id=1, is_admin=True)
        await manager.connect(ws_user, user_id=2, is_admin=False)

        count = await manager.broadcast_to_admins({"alert": "disk full"})
        assert count == 1
        ws_admin.send_json.assert_called_once()
        ws_user.send_json.assert_not_called()


@pytest.mark.asyncio
class TestBroadcastToAll:
    async def test_sends_to_all_users(self, manager: WebSocketManager):
        ws1, ws2 = _make_ws(), _make_ws()
        await manager.connect(ws1, user_id=1)
        await manager.connect(ws2, user_id=2)

        count = await manager.broadcast_to_all({"event": "update"})
        assert count == 2

    async def test_empty_when_no_connections(self, manager: WebSocketManager):
        count = await manager.broadcast_to_all({"event": "update"})
        assert count == 0


@pytest.mark.asyncio
class TestSendUnreadCount:
    async def test_sends_unread_count(self, manager: WebSocketManager):
        ws = _make_ws()
        await manager.connect(ws, user_id=1)
        count = await manager.send_unread_count(1, 5)
        assert count == 1
        payload = ws.send_json.call_args[0][0]
        assert payload["type"] == "unread_count"
        assert payload["payload"]["count"] == 5


class TestGetConnectedUserIds:
    @pytest.mark.asyncio
    async def test_returns_connected_ids(self, manager: WebSocketManager):
        await manager.connect(_make_ws(), user_id=10)
        await manager.connect(_make_ws(), user_id=20)
        ids = manager.get_connected_user_ids()
        assert set(ids) == {10, 20}


class TestGetConnectionCount:
    @pytest.mark.asyncio
    async def test_total_count(self, manager: WebSocketManager):
        await manager.connect(_make_ws(), user_id=1)
        await manager.connect(_make_ws(), user_id=1)
        await manager.connect(_make_ws(), user_id=2)
        assert manager.get_connection_count() == 3

    @pytest.mark.asyncio
    async def test_per_user_count(self, manager: WebSocketManager):
        await manager.connect(_make_ws(), user_id=1)
        await manager.connect(_make_ws(), user_id=1)
        assert manager.get_connection_count(user_id=1) == 2
        assert manager.get_connection_count(user_id=99) == 0


class TestIsUserConnected:
    @pytest.mark.asyncio
    async def test_connected(self, manager: WebSocketManager):
        await manager.connect(_make_ws(), user_id=1)
        assert manager.is_user_connected(1) is True

    def test_not_connected(self, manager: WebSocketManager):
        assert manager.is_user_connected(999) is False


class TestGetWebSocketManagerSingleton:
    def test_returns_same_instance(self):
        a = get_websocket_manager()
        b = get_websocket_manager()
        assert a is b
