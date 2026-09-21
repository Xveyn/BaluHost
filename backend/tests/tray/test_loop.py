"""Delivery, the gaming gate and its cadence."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from baluhost_tray import loop as loop_module
from baluhost_tray.loop import (
    GAMING_PROBE_SECONDS,
    REFRESH_COOLDOWN_SECONDS,
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


@pytest.mark.asyncio
async def test_a_failed_summary_also_keeps_the_newly_arrived_popups():
    """Der Zweig, in dem eine Meldung endgueltig verschwindet.

    Drei Dinge muessen zusammenkommen: genug Zurueckgehaltenes fuer die
    Sammelmeldung, ein D-Bus-Fehlschlag genau dann, und in derselben Runde
    eine *neue* kritische Meldung. Die alten wurden schon immer zurueckgelegt;
    die neue fiel durch, weil `pending` vor dem `return` niemandem mehr
    gehoerte — weder gezeigt noch gehalten.
    """
    notifier, queue = _notifier(), PopupQueue()
    for n in (1, 2, 3, 4):
        queue.hold(_popup(n))
    notifier.show_summary.side_effect = RuntimeError("bus gone")

    await deliver([_popup(99)], queue, notifier, hold=False)

    held, _summary = queue.release()
    assert sorted(popup.notification_id for popup in held) == [1, 2, 3, 4, 99]


def test_gaming_probe_404_counts_as_not_gaming(caplog):
    """Plugin abgeschaltet -> Route fehlt -> Popup wird gezeigt.

    Und zwar schweigend: das abgeschaltete Plugin ist ein Normalzustand, kein
    Vorfall. Eine Warnung pro Takt waere ein Dauerrauschen im Journal.
    """
    client = MagicMock()
    response = MagicMock()
    response.status_code = 404
    client.get.return_value = response
    with caplog.at_level(logging.WARNING, logger="baluhost_tray.loop"):
        assert is_gaming_active(client) is False
    assert caplog.records == [], caplog.text


@pytest.mark.parametrize("code", [401, 403, 429])
def test_a_refused_gaming_probe_is_logged_loudly(caplog, code):
    """Das Gate schaltet sich sonst lautlos ab.

    429, 401 und 403 heissen nicht "kein Spiel", sondern "ich darf nicht
    fragen". Die Folge ist genau das, was das Gate verhindern soll — Popups
    mitten im Vollbildspiel —, und ohne diese Zeile steht nirgends, warum.
    403 ist seit dem LAN-Gate der Route ein erreichbarer Fall.
    """
    client = MagicMock()
    response = MagicMock()
    response.status_code = code
    client.get.return_value = response

    with caplog.at_level(logging.WARNING, logger="baluhost_tray.loop"):
        assert is_gaming_active(client) is False

    assert any(str(code) in record.getMessage() for record in caplog.records), caplog.text


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
    """Liefert vorgegebene Frames, danach Timeouts — wie eine stille Leitung.

    Mit `clock` stellt jeder Leerlauf-Takt die Uhr um `step` weiter. Ohne das
    stuenden alle Runden eines Zyklus auf derselben Zeit, und jede Drosselung,
    die an `ctx.now` haengt, waere im Test nicht von einem Fehler zu
    unterscheiden.
    """

    def __init__(self, frames: list, then_idle: int = 0, clock=None,
                 step: float = TICK_SECONDS) -> None:
        # str kommt roh durch — so lassen sich kaputte Frames einspeisen.
        self._frames = [f if isinstance(f, str) else json.dumps(f) for f in frames]
        self._idle_left = then_idle
        self._clock, self._step = clock, step

    async def recv(self) -> str:
        if self._frames:
            return self._frames.pop(0)
        if self._idle_left > 0:
            self._idle_left -= 1
            if self._clock is not None:
                self._clock.advance(self._step)
            raise asyncio.TimeoutError
        raise ConnectionError("closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _ctx(frames, snapshot=None, gaming=False, then_idle=0, clock=None,
         step=TICK_SECONDS) -> LoopContext:
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

    ctx = LoopContext(
        session=session,
        watcher=Watcher(session, state),
        state=state,
        queue=PopupQueue(),
        notifier=_notifier(),
        sink=seen.append,
        hold_probe=lambda: gaming,
        connect=lambda url: FakeSocket(frames, then_idle=then_idle, clock=clock, step=step),
        sleep=AsyncMock(),
    )
    if clock is not None:
        ctx.now = clock
    return ctx


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

    Die Uhr laeuft mit: seit der Drosselung fragt der zweite Takt nur dann
    erneut, wenn seit der letzten Probe auch wirklich Zeit vergangen ist.
    """
    clock = FakeClock()
    ctx = _ctx(
        frames=[{"type": "notification",
                 "payload": {"id": 9, "notification_type": "critical",
                             "title": "SMART", "message": "Fehler"}}],
        then_idle=2,
        gaming=True,
        clock=clock,
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


_CRITICAL_FRAME = {
    "type": "notification",
    "payload": {"id": 5, "notification_type": "critical",
                "title": "RAID", "message": "degradiert"},
}


def _counting_probe(ctx: LoopContext, answer: bool) -> dict:
    calls = {"n": 0}

    def _probe() -> bool:
        calls["n"] += 1
        return answer

    ctx.hold_probe = _probe
    return calls


@pytest.mark.asyncio
async def test_the_gaming_probe_is_not_repeated_within_the_interval():
    """Nicht pro Frame fragen — pro halbe Minute.

    Solange waehrend einer Spielsitzung etwas in der Warteschlange liegt,
    kostete *jeder* eingehende Frame eine HTTP-Runde zu /session-state, auch
    die uninteressanten. Ein Schwall (30 im Web-UI einzeln weggeraeumte
    Meldungen, rund 60 Frames) reisst damit das Limit steam_games_read —
    60/min, nutzergebunden und geteilt mit GET /games, das die BaluApp
    benutzt.
    """
    clock = FakeClock()
    ctx = _ctx(frames=[_CRITICAL_FRAME], then_idle=1, gaming=True,
               clock=clock, step=5.0)
    calls = _counting_probe(ctx, answer=True)

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    assert calls["n"] == 1, "die zweite Runde lag innerhalb der 30 s"


@pytest.mark.asyncio
async def test_the_gaming_probe_runs_again_after_the_interval():
    """Die andere Richtung: gedrosselt ist nicht abgeschaltet.

    Ohne das Nachfragen bliebe das Zurueckgehaltene bis zum naechsten Frame
    liegen — die Spielsitzung endet aber, ohne dass ein Frame eintrifft.
    """
    clock = FakeClock()
    ctx = _ctx(frames=[_CRITICAL_FRAME], then_idle=1, gaming=True,
               clock=clock, step=GAMING_PROBE_SECONDS + 1.0)
    calls = _counting_probe(ctx, answer=True)

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_quiet_mode_holds_the_popup_and_skips_the_probe():
    """Die Verdrahtung, die die Doku zusagt und die nie geprueft war.

    QuietMode ist fuer sich getestet, aber dass `_should_hold` sie ueberhaupt
    ansieht, pruefte nichts. Die zweite Zusage steckt mit drin: stumm
    geschaltet, findet die HTTP-Runde zum Gaming-Plugin gar nicht erst statt.
    """
    clock = FakeClock()
    ctx = _ctx(frames=[_CRITICAL_FRAME], clock=clock)
    calls = _counting_probe(ctx, answer=False)
    ctx.quiet.mute_for(3600.0, clock())

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    ctx.notifier.show.assert_not_awaited()
    assert not ctx.queue.is_empty(), "zurueckgehalten heisst gehalten, nicht verworfen"
    assert calls["n"] == 0, "stumm schliesst den Gaming-Probe kurz"


@pytest.mark.asyncio
async def test_a_refused_snapshot_aborts_the_cycle():
    """Ein Zyklus ohne Snapshot darf nicht "verbunden" behaupten.

    Der Aufbau ist: Socket auf, Snapshot laden, *dann* gruen werden. Faellt
    der Snapshot durch und der Zyklus liefe trotzdem weiter, zeigte das Tray
    einen Zustand von vorhin als aktuellen an — und nichts sagte, dass er alt
    ist.
    """
    ctx = _ctx(frames=[])
    ctx.session.client.return_value.get.return_value.status_code = 503

    with pytest.raises(TemporaryFailure):
        await run_cycle(ctx)

    assert ctx.state.connected is False
    assert ctx.state.icon_state() is IconState.OFFLINE
    ctx.notifier.show_summary.assert_not_awaited()


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
        entry = script.pop(0)
        duration, exc = entry[0], entry[1]
        # Drittes Feld: stand in dieser Runde jemals eine Verbindung? Fehlt es,
        # heisst das nein — der Zyklus ist vor set_connected(True) gescheitert.
        connected = entry[2] if len(entry) > 2 else False
        calls.append({
            "forget_calls": ctx.session.forget.call_count,
            "refresh_calls": ctx.session.refresh_access.call_count,
            "sleeps": ctx.sleep.await_count,
        })
        if connected:
            ctx.connected_at = clock()
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
    # Die Meldung ist nach Sekunden weg, das graue Icon bleibt. Der Grund
    # muss deshalb im Zustand stehen, nicht nur im Popup.
    assert ctx.state.paired is False
    assert "gekoppelt" in ctx.state.tooltip()


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
        # gesunde Runde: Verbindung stand und hielt einen vollen Takt
        + [(TICK_SECONDS + 1.0, ConnectionError("drop"), True)]
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
        (TICK_SECONDS + 1.0, ConnectionError("drop"), True),   # gesunde Runde
        (0.0, AuthExpired("401")),                  # Refresh 2 ist wieder erlaubt
        (0.0, PairingLost("stop")),
    ]
    monkeypatch.setattr(loop_module, "run_cycle", _scripted_cycle(clock, script))

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert ctx.session.refresh_access.call_count == 2


@pytest.mark.asyncio
async def test_a_spent_refresh_comes_back_after_the_cooldown(monkeypatch):
    """Der Zustand ohne Ausweg: gelungener Refresh, weiter abgelehntes Token.

    `refreshed` wurde nur von einer gesunden Runde zurueckgegeben — und genau
    die kommt hier nie zustande, weil jeder Zyklus an der 401 scheitert. Die
    Schleife lief damit fuer immer im Sechzig-Sekunden-Backoff und fragte nie
    wieder nach einem frischen Token, obwohl ein frisches Token das einzige
    ist, was sie retten koennte.

    Das dritte Feld fehlt ueberall: keine Runde war je verbunden. Was die
    Bremse hier loest, ist die verstrichene Zeit, nicht der Gesundheitspfad.
    """
    clock = FakeClock()
    ctx, _ = _loop_ctx(clock)
    ctx.session.refresh_access.return_value = None
    script = [
        (0.0, AuthExpired("401")),                              # Refresh 1
        (0.0, AuthExpired("401")),                              # gebremst
        (REFRESH_COOLDOWN_SECONDS + 1.0, AuthExpired("401")),   # Bremse geht auf
        (0.0, PairingLost("stop")),
    ]
    cycle = _scripted_cycle(clock, script)
    monkeypatch.setattr(loop_module, "run_cycle", cycle)

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert ctx.session.refresh_access.call_count == 2
    # Und die Bremse bleibt eine Bremse: die zweite Runde lag innerhalb der
    # Frist und musste einen Backoff kosten statt eines Refreshs.
    assert [call["refresh_calls"] for call in cycle.calls] == [0, 1, 1, 2]


@pytest.mark.asyncio
async def test_unexpected_refresh_failure_backs_off_instead_of_dying(monkeypatch):
    """Ein Serverfehler beim Refresh ist keine verlorene Kopplung.

    Ohne den dritten except-Zweig laeuft der KeyError aus refresh_access() an
    beiden bekannten Klassen vorbei und aus run_loop heraus — der stille Tod
    des Threads, den die Docstring ausschliesst.
    """
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    ctx.session.refresh_access.side_effect = KeyError("access_token")
    script = [
        (0.0, AuthExpired("401")),
        (0.0, AuthExpired("401")),
        (0.0, PairingLost("stop")),     # beendet den Test
    ]
    cycle = _scripted_cycle(clock, script)
    monkeypatch.setattr(loop_module, "run_cycle", cycle)

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert len(cycle.calls) == 3, "die Schleife muss weitergelaufen sein"
    assert ctx.sleep.await_count == 2, "jeder Fehlschlag muss einen Backoff kosten"
    # Token wegwerfen waere hier die teure Fehlreaktion: forget() kommt erst
    # durch das abschliessende PairingLost, nie wegen des Refresh-Fehlers.
    assert all(c["forget_calls"] == 0 for c in cycle.calls)


@pytest.mark.asyncio
async def test_cancellation_still_gets_through(monkeypatch):
    """Der Auffang-Zweig darf CancelledError nicht schlucken."""
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    ctx.session.refresh_access.side_effect = asyncio.CancelledError()
    monkeypatch.setattr(
        loop_module, "run_cycle", _scripted_cycle(clock, [(0.0, AuthExpired("401"))])
    )

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(run_loop(ctx), timeout=5)

    ctx.session.forget.assert_not_called()


@pytest.mark.asyncio
async def test_failing_sink_does_not_kill_the_loop(monkeypatch):
    """Wenn die Anzeige klemmt, soll das Tray weiter beobachten und melden.

    ctx.sink kommt aus der Qt-Oberflaeche. Ein geloeschtes Qt-Objekt oder ein
    Aufruf aus dem falschen Thread wirft — ungeschuetzt verlaesst das die
    Schleife. Der Worker stirbt dann daran, dass die *Anzeige* kaputt ist.
    """
    clock = FakeClock()
    ctx, _ = _loop_ctx(clock)

    def _broken_sink(_state) -> None:
        raise RuntimeError("Qt object deleted")

    ctx.sink = _broken_sink
    script = [
        (0.0, ConnectionError("drop")),
        (0.0, ConnectionError("drop")),
        (0.0, PairingLost("stop")),
    ]
    cycle = _scripted_cycle(clock, script)
    monkeypatch.setattr(loop_module, "run_cycle", cycle)

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert len(cycle.calls) == 3, "die Schleife muss weitergelaufen sein"
    assert ctx.sleep.await_count == 2
    # Auch der Schlusspfad ueberlebt den kaputten Sink: eine Meldung fuer den
    # ersten Verbindungsverlust (die zweite Runde schweigt, siehe
    # ConnectionAnnouncer) und eine fuer die aufgehobene Kopplung am Ende.
    assert ctx.notifier.show_summary.await_count == 2


@pytest.mark.asyncio
async def test_failing_forget_still_reports_the_lost_pairing(monkeypatch):
    """Grau werden und sich melden, auch wenn die Token nicht zu loeschen sind.

    Im Stillen verschwinden hiesse: der Nutzer sieht ein Tray, das einfach
    aufgehoert hat, und erfaehrt nie, dass er neu koppeln muss.
    """
    clock = FakeClock()
    ctx, seen = _loop_ctx(clock)
    ctx.session.forget.side_effect = OSError("read-only file system")
    monkeypatch.setattr(
        loop_module, "run_cycle", _scripted_cycle(clock, [(0.0, PairingLost("revoked"))])
    )

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    assert seen[-1] is IconState.OFFLINE
    assert ctx.notifier.show_summary.await_count == 1


@pytest.mark.asyncio
async def test_slow_failure_before_the_connection_stands_does_not_reset(monkeypatch):
    """Das schweigende Backend: nimmt die TCP-Verbindung an und antwortet nie.

    ws_token() laeuft dann in BackendClients Timeout von 30 s -- exakt
    TICK_SECONDS -- und wirft TemporaryFailure. Wuerde die Zyklusdauer ab dem
    Start gemessen, saehe *jeder* dieser Versuche gesund aus und der Backoff
    wuchse nie, ausgerechnet in dem Szenario, fuer das es ihn gibt.
    """
    clock = FakeClock()
    ctx, _ = _loop_ctx(clock)
    script = (
        # Lang, aber nie verbunden (drittes Feld fehlt = False).
        [(TICK_SECONDS + 1.0, TemporaryFailure("read timeout"))] * 5
        + [(0.0, PairingLost("stop"))]
    )
    monkeypatch.setattr(loop_module, "run_cycle", _scripted_cycle(clock, script))

    await asyncio.wait_for(run_loop(ctx), timeout=5)

    delays = _delays(ctx)
    assert len(delays) == 5
    # Gewachsen statt bei jedem Versuch zurueckgesetzt: der fuenfte Backoff
    # liegt im Fenster von 2**4 = 16 s, nicht im Fenster des ersten Versuchs.
    assert delays[-1] > 1.0, delays


@pytest.mark.asyncio
async def test_recv_is_bounded_by_the_tick(monkeypatch):
    """Bewacht die erste Haelfte der Zusage: gewartet wird *mit Zeitlimit*.

    recv() kehrt hier nie von selbst zurueck. Ohne asyncio.wait_for haengt
    run_cycle, und der Takt -- und mit ihm die Zustellung -- faende nie statt.
    """
    monkeypatch.setattr(loop_module, "TICK_SECONDS", 0.01)

    class SilentSocket:
        """Eine Leitung, die offen ist und schweigt."""

        def __init__(self) -> None:
            self.attempts = 0

        async def recv(self) -> str:
            self.attempts += 1
            if self.attempts > 3:
                raise ConnectionError("closed")
            await asyncio.Event().wait()        # kehrt nie zurueck
            raise AssertionError("unreachable")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    ctx = _ctx(frames=[])
    socket = SilentSocket()
    ctx.connect = lambda url: socket
    ctx.queue.hold(_popup(3))                   # wartet auf einen Takt

    with pytest.raises(ConnectionError):
        await asyncio.wait_for(run_cycle(ctx), timeout=5)

    assert socket.attempts == 4, "jeder Takt muss recv() neu versucht haben"
    ctx.notifier.show.assert_awaited_once()


class TickingSocket:
    """Stille Leitung, die bei jedem Leerlauf-Takt die Uhr weiterstellt."""

    def __init__(self, clock: FakeClock, step: float, ticks: int) -> None:
        self._clock, self._step, self._left = clock, step, ticks

    async def recv(self) -> str:
        if self._left <= 0:
            raise ConnectionError("closed")
        self._left -= 1
        self._clock.advance(self._step)
        raise asyncio.TimeoutError

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _snapshot_calls(ctx: LoopContext) -> int:
    return ctx.session.client.return_value.get.call_count


@pytest.mark.asyncio
async def test_resnapshot_fires_after_the_interval():
    """Der Zehn-Minuten-Neuabgleich, der abgelaufene Snoozes einfaengt.

    Serverseitig gibt es dafuer keinen Job: die Meldung taucht einfach wieder
    in den Abfragen auf, und ohne diesen Takt saehe das Tray sie nie.
    """
    clock = FakeClock()
    ctx = _ctx(frames=[])
    ctx.now = clock
    ctx.connect = lambda url: TickingSocket(clock, step=300.0, ticks=3)

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    # 1x beim Verbinden + 1x nach 600 s. Der dritte Takt (900 s) liegt erst
    # 300 s nach dem Neuabgleich und zaehlt noch nicht.
    assert _snapshot_calls(ctx) == 2


@pytest.mark.asyncio
async def test_no_resnapshot_before_the_interval():
    """Kein Neuabgleich auf Verdacht — sonst waere der Takt eine Dauerabfrage."""
    clock = FakeClock()
    ctx = _ctx(frames=[])
    ctx.now = clock
    ctx.connect = lambda url: TickingSocket(clock, step=60.0, ticks=5)

    with pytest.raises(ConnectionError):
        await run_cycle(ctx)

    assert _snapshot_calls(ctx) == 1        # nur der beim Verbinden
