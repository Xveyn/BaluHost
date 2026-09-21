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
    service = _service(3)
    p1, p2 = _patches(ws_manager, service)
    with p1, p2:
        await fanout_state(MagicMock(), 1, [7], "read", is_admin=False)

    ws_manager.send_notification_state.assert_awaited_once_with(1, [7], "read")
    ws_manager.send_unread_count.assert_awaited_once_with(1, 3)


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
async def test_unknown_action_rejected(ws_manager: MagicMock):
    with pytest.raises(ValueError):
        await fanout_state(MagicMock(), 1, [7], "exploded", is_admin=False)
