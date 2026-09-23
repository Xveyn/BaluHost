"""Tests for services/websocket_manager.py — WebSocketManager with mock WebSockets."""

import asyncio
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
        assert manager.get_connection_count() == 0

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


# ---------------------------------------------------------------------------
# Task 2: per-user WebSocket connection cap (Posten 5 #2)
# ---------------------------------------------------------------------------

import pytest
from app.services.websocket_manager import (
    ConnectionLimitExceeded,
    MAX_CONNECTIONS_PER_USER,
)


class _FakeWS:
    async def send_json(self, _):  # pragma: no cover - not exercised here
        pass


@pytest.mark.asyncio
async def test_connect_caps_connections_per_user():
    mgr = WebSocketManager()
    # Fill up to the cap for one user.
    for _ in range(MAX_CONNECTIONS_PER_USER):
        await mgr.connect(_FakeWS(), user_id=7)
    # The next one is rejected.
    with pytest.raises(ConnectionLimitExceeded):
        await mgr.connect(_FakeWS(), user_id=7)
    # A different user is unaffected.
    await mgr.connect(_FakeWS(), user_id=8)
    assert mgr.get_connection_count(7) == MAX_CONNECTIONS_PER_USER
    assert mgr.get_connection_count(8) == 1


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
        assert manager.get_connection_count() == 0

    async def test_drops_broken_connection(self, manager: WebSocketManager):
        ws = _make_ws(send_json_side_effect=RuntimeError("gone"))
        await manager.connect(ws, user_id=1)

        await manager.send_notification_state(1, [1], "read")

        assert manager.get_connection_count(1) == 0


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

    async def test_send_timeout_counts_as_dead(self, manager: WebSocketManager, monkeypatch):
        """A stuck client must not freeze the bus consumer forever (#685)."""
        import app.services.websocket_manager as websocket_manager_module
        from app.services.ws_bus import WsEnvelope

        monkeypatch.setattr(websocket_manager_module, "SEND_TIMEOUT_SECONDS", 0.01)

        async def _hang(_frame):
            await asyncio.sleep(1)

        ws = _make_ws()
        ws.send_json = AsyncMock(side_effect=_hang)
        await manager.connect(ws, user_id=1)

        sent = await manager.deliver_local(
            WsEnvelope(kind="user", msg_type="notification", payload={"a": 1}, user_id=1)
        )

        assert sent == 0
        assert manager.get_connection_count(1) == 0
