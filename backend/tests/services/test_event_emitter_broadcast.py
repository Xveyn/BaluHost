"""emit_sync must reach the websocket, not just Firebase.

The sync path is the one every critical hardware event uses (RAID, SMART,
temperature, disk space). Before this test existed it wrote a row, pushed to
Firebase and told no connected client anything.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notifications.events import EventEmitter


@pytest.mark.asyncio
async def test_broadcast_sync_reaches_admins_for_system_notifications():
    emitter = EventEmitter()
    emitter.set_event_loop(asyncio.get_running_loop())

    manager = MagicMock()
    manager.broadcast_to_admins = AsyncMock(return_value=1)
    manager.broadcast_to_user = AsyncMock(return_value=1)

    notification = MagicMock()
    notification.user_id = None
    notification.to_dict.return_value = {"id": 1, "notification_type": "critical"}

    with patch(
        "app.services.notifications.events.get_websocket_manager",
        return_value=manager,
    ):
        emitter._broadcast_sync(notification)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    manager.broadcast_to_admins.assert_awaited_once()
    # Roh, nicht eingewickelt: broadcast_to_admins baut den Rahmen selbst.
    assert manager.broadcast_to_admins.await_args[0][0] == {
        "id": 1, "notification_type": "critical",
    }
    manager.broadcast_to_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_scoped_notification_goes_to_that_user():
    emitter = EventEmitter()
    emitter.set_event_loop(asyncio.get_running_loop())

    manager = MagicMock()
    manager.broadcast_to_admins = AsyncMock(return_value=0)
    manager.broadcast_to_user = AsyncMock(return_value=1)

    notification = MagicMock()
    notification.user_id = 7
    notification.to_dict.return_value = {"id": 2, "notification_type": "warning"}

    with patch(
        "app.services.notifications.events.get_websocket_manager",
        return_value=manager,
    ):
        emitter._broadcast_sync(notification)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    manager.broadcast_to_user.assert_awaited_once()
    assert manager.broadcast_to_user.await_args[0][0] == 7
    assert manager.broadcast_to_user.await_args[0][1] == {
        "id": 2, "notification_type": "warning",
    }
    manager.broadcast_to_admins.assert_not_awaited()


def test_without_a_loop_it_stays_silent_instead_of_raising():
    """Worker ohne laufende App-Loop (Tests, Skripte) duerfen nicht platzen."""
    emitter = EventEmitter()  # set_event_loop nie gerufen
    notification = MagicMock()
    notification.user_id = None
    notification.to_dict.return_value = {"id": 3}

    emitter._broadcast_sync(notification)  # wirft nicht


@pytest.mark.asyncio
async def test_broadcast_failure_does_not_break_the_caller(caplog):
    """Ein kaputter Socket darf emit_sync nicht mitreissen — die Zeile steht
    zu diesem Zeitpunkt bereits in der Datenbank.

    Beweist den Fehlerpfad, statt nur "wirft nicht synchron" zu zeigen:
    _broadcast_sync fragt das Future von run_coroutine_threadsafe nie ab, ein
    fehlendes try/except um den await liesse den Test sonst genauso gruen
    durchlaufen. assert_awaited_once() belegt, dass der Aufruf ueberhaupt
    stattfand; die caplog-Pruefung belegt, dass die RuntimeError im except
    gefangen und geloggt wurde statt zu verschwinden.
    """
    emitter = EventEmitter()
    emitter.set_event_loop(asyncio.get_running_loop())

    manager = MagicMock()
    manager.broadcast_to_admins = AsyncMock(side_effect=RuntimeError("gone"))

    notification = MagicMock()
    notification.user_id = None
    notification.to_dict.return_value = {"id": 4}

    with patch(
        "app.services.notifications.events.get_websocket_manager",
        return_value=manager,
    ):
        with caplog.at_level(logging.WARNING, logger="app.services.notifications.events"):
            emitter._broadcast_sync(notification)
            await asyncio.sleep(0)
            await asyncio.sleep(0)

    manager.broadcast_to_admins.assert_awaited_once()
    assert any(
        "Websocket broadcast from emit_sync failed" in record.message
        for record in caplog.records
    ), "erwartete Warnung fehlt — wurde die Exception im except geloggt?"
