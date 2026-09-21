"""Delivery, the gaming gate and its cadence."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from baluhost_tray.loop import LoopContext, deliver, is_gaming_active, run_cycle
from baluhost_tray.state import IconState, PendingPopup, PopupQueue, TrayState
from baluhost_tray.watch import Watcher


def _popup(n: int) -> PendingPopup:
    return PendingPopup(notification_id=n, title=f"T{n}", message=f"M{n}")


def _notifier() -> MagicMock:
    notifier = MagicMock()
    notifier.show = AsyncMock()
    notifier.show_summary = AsyncMock()
    return notifier


@pytest.mark.asyncio
async def test_delivers_when_not_holding():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(1)], queue, notifier, hold=False)
    notifier.show.assert_awaited_once()
    assert queue.is_empty()


@pytest.mark.asyncio
async def test_holds_while_holding():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(1)], queue, notifier, hold=True)
    notifier.show.assert_not_awaited()
    assert not queue.is_empty()


@pytest.mark.asyncio
async def test_release_collapses_above_threshold():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(n) for n in (1, 2, 3, 4)], queue, notifier, hold=True)
    await deliver([], queue, notifier, hold=False)
    notifier.show_summary.assert_awaited_once()
    notifier.show.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_shows_each_below_threshold():
    notifier, queue = _notifier(), PopupQueue()
    await deliver([_popup(1), _popup(2)], queue, notifier, hold=True)
    await deliver([], queue, notifier, hold=False)
    assert notifier.show.await_count == 2
    notifier.show_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_delivery_keeps_the_popups():
    """Ein D-Bus-Fehler darf die Warteschlange nicht leeren."""
    notifier, queue = _notifier(), PopupQueue()
    notifier.show.side_effect = RuntimeError("bus gone")
    await deliver([_popup(1)], queue, notifier, hold=False)
    assert not queue.is_empty()


def test_gaming_probe_404_counts_as_not_gaming():
    """Plugin abgeschaltet -> Route fehlt -> Popup wird gezeigt."""
    client = MagicMock()
    response = MagicMock()
    response.status_code = 404
    client.get.return_value = response
    assert is_gaming_active(client) is False


def test_gaming_probe_error_counts_as_not_gaming():
    client = MagicMock()
    client.get.side_effect = OSError("network down")
    assert is_gaming_active(client) is False


def test_gaming_probe_true():
    client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"gaming_active": True}
    client.get.return_value = response
    assert is_gaming_active(client) is True


class FakeSocket:
    """Liefert vorgegebene Frames, danach Timeouts — wie eine stille Leitung."""

    def __init__(self, frames: list[dict], then_idle: int = 0) -> None:
        self._frames = [json.dumps(f) for f in frames]
        self._idle_left = then_idle

    async def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        if self._idle_left > 0:
            self._idle_left -= 1
            raise asyncio.TimeoutError
        raise ConnectionError("closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _ctx(frames, snapshot=None, gaming=False, then_idle=0) -> LoopContext:
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "notifications": snapshot or [],
        "unread_count": len(snapshot or []),
    }
    session.client.return_value.get.return_value = response
    session.ws_token.return_value = "wt"
    session.ws_url.return_value = "ws://x/api/notifications/ws"

    state = TrayState()
    seen: list[IconState] = []

    return LoopContext(
        session=session,
        watcher=Watcher(session, state),
        state=state,
        queue=PopupQueue(),
        notifier=_notifier(),
        sink=seen.append,
        hold_probe=lambda: gaming,
        connect=lambda url: FakeSocket(frames, then_idle=then_idle),
        sleep=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_cycle_loads_snapshot_before_reading_frames():
    ctx = _ctx(
        frames=[{"type": "notification_state",
                 "payload": {"ids": [1], "action": "read"}}],
        snapshot=[{"id": 1, "notification_type": "critical", "is_read": False,
                   "title": "RAID", "message": "degradiert"}],
    )
    with pytest.raises(ConnectionError):
        await run_cycle(ctx)
    assert ctx.state.icon_state() == IconState.OK


@pytest.mark.asyncio
async def test_idle_tick_drains_the_queue_without_any_frame():
    """Der Fall, der ohne Takt ewig haengt: nichts kommt mehr rein, das Spiel
    ist vorbei, die zurueckgehaltene Meldung muss trotzdem raus.

    Das Flag kippt ueber hold_probe, nicht ueber sleep: run_cycle ruft sleep
    nie -- das tut nur run_loop vor dem Backoff.
    """
    ctx = _ctx(
        frames=[{"type": "notification",
                 "payload": {"id": 9, "notification_type": "critical",
                             "title": "SMART", "message": "Fehler"}}],
        then_idle=2,
        gaming=True,
    )
    calls = {"n": 0}

    def _probe() -> bool:
        calls["n"] += 1
        return calls["n"] <= 1      # erster Aufruf: Spiel laeuft noch

    ctx.hold_probe = _probe

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    # Ohne den Idle-Tick waere hier nie zugestellt worden.
    ctx.notifier.show.assert_awaited()
    assert calls["n"] >= 2, "der Tick muss erneut gefragt haben"
