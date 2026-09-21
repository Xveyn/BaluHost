"""Delivery, the gaming gate and its cadence."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from baluhost_tray import loop as loop_module
from baluhost_tray.loop import (
    TICK_SECONDS,
    LoopContext,
    deliver,
    is_gaming_active,
    run_cycle,
    run_loop,
)
from baluhost_tray.session import AuthExpired, PairingLost, TemporaryFailure
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

    def __init__(self, frames: list, then_idle: int = 0) -> None:
        # str kommt roh durch — so lassen sich kaputte Frames einspeisen.
        self._frames = [f if isinstance(f, str) else json.dumps(f) for f in frames]
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


@pytest.mark.asyncio
async def test_broken_frame_does_not_skip_the_round():
    """Ein kaputter Frame darf die Runde nicht ueberspringen.

    Mit `continue` fielen Resnapshot-Pruefung, Queue-Draining und Icon-Update
    dieser Runde aus — eine zurueckgehaltene Meldung bliebe liegen.
    """
    ctx = _ctx(frames=["{kaputt"])
    ctx.queue.hold(_popup(7))               # wartet auf Zustellung

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    ctx.notifier.show.assert_awaited_once()


@pytest.mark.asyncio
async def test_frame_that_is_not_an_object_is_ignored():
    """Gueltiges JSON, falsche Form: handle_frame() wuerde auf .get() fliegen."""
    ctx = _ctx(frames=["[1, 2, 3]"])
    ctx.queue.hold(_popup(7))

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    ctx.notifier.show.assert_awaited_once()


# --- run_loop: drei Fehlerklassen, drei Reaktionen -------------------------


class FakeClock:
    """Eine Uhr, die nur der Test weiterdreht — run_loop misst mit ihr."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _loop_ctx(clock: FakeClock) -> tuple[LoopContext, list[IconState]]:
    seen: list[IconState] = []
    ctx = LoopContext(
        session=MagicMock(),
        watcher=MagicMock(),
        state=TrayState(),
        queue=PopupQueue(),
        notifier=_notifier(),
        sink=seen.append,
        hold_probe=lambda: False,
        connect=MagicMock(),
        sleep=AsyncMock(),
        now=clock,
    )
    return ctx, seen


def _scripted_cycle(clock: FakeClock, script: list[tuple[float, Exception]]):
    """Ersetzt run_cycle: haelt `duration` durch und wirft dann `exc`.

    Jeder Aufruf notiert, wie die Welt beim Betreten der Runde aussah — daran
    laesst sich ablesen, was *zwischen* den Runden passiert ist.
    """
    calls: list[dict] = []

    async def _cycle(ctx: LoopContext) -> None:
        if not script:
            # Notbremse: ein Test darf nie endlos laufen.
            raise PairingLost("script exhausted")
        duration, exc = script.pop(0)
        calls.append({
            "forget_calls": ctx.session.forget.call_count,
            "refresh_calls": ctx.session.refresh_access.call_count,
            "sleeps": ctx.sleep.await_count,
        })
        clock.advance(duration)
        raise exc

    _cycle.calls = calls
    return _cycle


def _delays(ctx: LoopContext) -> list[float]:
    return [call.args[0] for call in ctx.sleep.await_args_list]


@pytest.mark.asyncio
async def test_pairing_lost_stops_the_loop_visibly(monkeypatch):
    """Sichtbar aufhoeren: Token weg, Icon grau, genau eine Meldung."""
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    monkeypatch.setattr(
        loop_module, "run_cycle", _scripted_cycle(clock, [(0.0, PairingLost("revoked"))])
    )

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    ctx.session.forget.assert_called_once()
    assert seen[-1] is IconState.OFFLINE
    assert ctx.notifier.show_summary.await_count == 1
    ctx.sleep.assert_not_awaited()          # kein Backoff mehr noetig


@pytest.mark.asyncio
async def test_temporary_failure_backs_off_and_keeps_going(monkeypatch):
    """Ratelimit kostet einen Backoff — und *nur* das."""
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    script = [(0.0, TemporaryFailure("429"))] * 3 + [(0.0, PairingLost("stop"))]
    cycle = _scripted_cycle(clock, script)
    monkeypatch.setattr(loop_module, "run_cycle", cycle)

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert len(cycle.calls) == 4, "die Schleife muss weitergelaufen sein"
    # Vor jeder Folge-Runde genau ein Backoff, und nie ein forget() unterwegs.
    assert [c["sleeps"] for c in cycle.calls] == [0, 1, 2, 3]
    assert all(c["forget_calls"] == 0 for c in cycle.calls)
    ctx.session.refresh_access.assert_not_called()


@pytest.mark.asyncio
async def test_auth_expired_refreshes_once_then_backs_off(monkeypatch):
    """Regressionswaechter: ohne die Bremse waeren es 4 Refreshs und 0 Sleeps.

    Der Refresh gelingt jedes Mal, das Token wird trotzdem weiter abgelehnt —
    genau der Fall, in dem die alte Fassung ohne ein einziges sleep() im Kreis
    lief.
    """
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    ctx.session.refresh_access.return_value = None
    script = [(0.0, AuthExpired("401"))] * 4 + [(0.0, PairingLost("stop"))]
    cycle = _scripted_cycle(clock, script)
    monkeypatch.setattr(loop_module, "run_cycle", cycle)

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert ctx.session.refresh_access.call_count == 1
    assert ctx.sleep.await_count == 3, "jede weitere 401 muss einen Backoff kosten"
    # Nur die erste Runde darf ohne Backoff auf die naechste folgen.
    assert [c["sleeps"] for c in cycle.calls] == [0, 0, 1, 2, 3]


@pytest.mark.asyncio
async def test_healthy_cycle_resets_the_backoff(monkeypatch):
    """Ein Zyklus, der einen vollen Leerlauf-Takt haelt, gilt als gesund."""
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    script = (
        [(0.0, ConnectionError("drop"))] * 5           # Backoff hochtreiben
        + [(TICK_SECONDS + 1.0, ConnectionError("drop"))]   # gesunde Runde
        + [(0.0, PairingLost("stop"))]
    )
    monkeypatch.setattr(loop_module, "run_cycle", _scripted_cycle(clock, script))

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    delays = _delays(ctx)
    assert len(delays) == 6
    # Der fuenfte Fehlschlag liegt im Fenster von 2**4 = 16 s.
    assert delays[4] > 1.0, delays
    # Nach der gesunden Runde wieder im Fenster des ersten Versuchs (<= 1 s).
    assert delays[5] <= 1.0, delays


@pytest.mark.asyncio
async def test_healthy_cycle_hands_back_the_refresh(monkeypatch):
    """Nach einer gesunden Runde darf wieder genau einmal refresht werden."""
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    ctx.session.refresh_access.return_value = None
    script = [
        (0.0, AuthExpired("401")),                  # Refresh 1, dann continue
        (0.0, AuthExpired("401")),                  # gebremst -> Backoff
        (TICK_SECONDS + 1.0, ConnectionError("drop")),   # gesunde Runde
        (0.0, AuthExpired("401")),                  # Refresh 2 ist wieder erlaubt
        (0.0, PairingLost("stop")),
    ]
    monkeypatch.setattr(loop_module, "run_cycle", _scripted_cycle(clock, script))

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert ctx.session.refresh_access.call_count == 2
