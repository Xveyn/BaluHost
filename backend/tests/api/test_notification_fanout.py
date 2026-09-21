"""Tests for the notification state fan-out helper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.routes._notification_fanout import fanout_state


@pytest.fixture
def ws_manager() -> MagicMock:
    manager = MagicMock()
    manager.is_user_connected = MagicMock(return_value=True)
    manager.send_notification_state = AsyncMock(return_value=1)
    manager.send_unread_count = AsyncMock(return_value=1)
    return manager


def _service(unread: int = 3) -> MagicMock:
    service = MagicMock()
    service.get_unread_count.return_value = unread
    return service


def _patches(ws_manager: MagicMock, service: MagicMock):
    return (
        patch(
            "app.api.routes._notification_fanout.get_websocket_manager",
            return_value=ws_manager,
        ),
        patch(
            "app.api.routes._notification_fanout.get_notification_service",
            return_value=service,
        ),
    )


@pytest.mark.asyncio
async def test_sends_state_then_count(ws_manager: MagicMock):
    """The name promises an order, so prove the order.

    `send_notification_state` and `send_unread_count` are assigned directly
    onto `ws_manager`, which makes `ws_manager` itself the common parent mock:
    Mock's attribute-set logic auto-attaches child mocks so their calls are
    recorded on the parent's `mock_calls`, in call order. Two
    `assert_awaited_once_with` checks alone would stay green if the two
    `await`s inside `fanout_state` were swapped; comparing `mock_calls`
    catches that.
    """
    service = _service(3)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [7], "read")
    ws_manager.send_unread_count.assert_awaited_once_with(1, 3)
    relevant = {"send_notification_state", "send_unread_count"}
    assert [c[0] for c in ws_manager.mock_calls if c[0] in relevant] == [
        "send_notification_state",
        "send_unread_count",
    ]


@pytest.mark.asyncio
async def test_bulk_action_sends_despite_empty_ids(ws_manager: MagicMock):
    service = _service(0)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [], "read_all", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [], "read_all")


@pytest.mark.asyncio
async def test_empty_ids_on_single_action_sends_nothing(ws_manager: MagicMock):
    service = _service(0)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [], "read", is_admin=False)

    ws_manager.send_notification_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_nothing_happens_without_a_connection(ws_manager: MagicMock):
    """Kein offener Client -> keine COUNT-Query. Der Zaehler kostet sonst
    eine Datenbankabfrage pro Klick, auch wenn niemand zuhoert."""
    ws_manager.is_user_connected.return_value = False
    service = _service(3)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)

    service.get_unread_count.assert_not_called()
    ws_manager.send_notification_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_failure_does_not_propagate(ws_manager: MagicMock):
    """Ein toter Socket darf aus einem erfolgreichen POST kein 500 machen."""
    ws_manager.send_notification_state.side_effect = RuntimeError("socket gone")
    service = _service(0)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)


@pytest.mark.asyncio
async def test_unread_count_failure_does_not_propagate(ws_manager: MagicMock):
    """The DB-gone case: both awaits share one try/except, so a raising
    `get_unread_count` must be swallowed exactly like a dead socket is.
    `send_unread_count` must then never even be attempted."""
    service = _service(0)
    service.get_unread_count.side_effect = RuntimeError("db gone")
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [7], "read")
    ws_manager.send_unread_count.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_action_rejected():
    with pytest.raises(ValueError):
        await fanout_state(MagicMock(), 1, [7], "exploded", is_admin=False)


@pytest.mark.asyncio
async def test_socket_mark_read_reaches_the_other_connections():
    """Der Socket-Zweig darf nicht nur dem Aufrufer antworten."""
    from app.services.websocket_manager import WebSocketManager

    manager = WebSocketManager()
    caller, other = MagicMock(), MagicMock()
    caller.send_json = AsyncMock()
    other.send_json = AsyncMock()
    await manager.connect(caller, user_id=1)
    await manager.connect(other, user_id=1)

    service = _service(2)
    with patch(
        "app.api.routes._notification_fanout.get_websocket_manager",
        return_value=manager,
    ), patch(
        "app.api.routes._notification_fanout.get_notification_service",
        return_value=service,
    ):
        await fanout_state(MagicMock(), 1, [5], "read", is_admin=False)

    types_seen = [c[0][0]["type"] for c in other.send_json.call_args_list]
    assert "notification_state" in types_seen
    assert "unread_count" in types_seen
