"""Delivery, the gaming gate, and the reconnect loop.

Everything decidable lives here rather than in tray.py: reconnect, backoff,
snapshot ordering, the cadence of the gaming probe and when a pairing counts
as lost. tray.py only supplies a sink that takes an icon state.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from baluhost_tray.announce import ConnectionAnnouncer, QuietMode
from baluhost_tray.session import AuthExpired, PairingLost, TemporaryFailure
from baluhost_tray.state import IconState, PendingPopup, PopupQueue, TrayState
from baluhost_tray.watch import Watcher, backoff_delays

logger = logging.getLogger(__name__)

GAMING_PATH = "/api/plugins/steam_gaming/session-state"
TICK_SECONDS = 30.0
RESNAPSHOT_SECONDS = 600.0


def is_gaming_active(client) -> bool:
    """Ask the plugin whether a session is on screen.

    Anything other than a clear yes counts as "not gaming": the plugin can be
    disabled, in which case the route is simply absent. Rather one
    notification too many than a swallowed alarm.
    """
    try:
        response = client.get(GAMING_PATH)
        if response.status_code != 200:
            return False
        return bool(response.json().get("gaming_active", False))
    except Exception as exc:
        logger.debug("gaming probe failed, treating as not gaming: %s", exc)
        return False


async def deliver(
    popups: list[PendingPopup],
    queue: PopupQueue,
    notifier,
    hold: bool,
) -> None:
    """Show popups, or hold them back.

    `hold` has two possible reasons — a game on screen or quiet mode — and
    deliver does not care which: held is held, and held is never dropped.

    A failed delivery puts everything back. Losing an alarm because the bus
    hiccuped is worse than showing it a minute late.
    """
    if hold:
        for popup in popups:
            queue.hold(popup)
        return

    pending = list(popups)
    if not queue.is_empty():
        released, summary = queue.release()
        if summary:
            try:
                await notifier.show_summary(*summary)
            except Exception as exc:
                logger.warning("summary delivery failed: %s", exc)
                for popup in released:
                    queue.hold(popup)
                return
        else:
            pending = released + pending

    for popup in pending:
        try:
            await notifier.show(popup)
        except Exception as exc:
            logger.warning("delivery failed, keeping the popup: %s", exc)
            queue.hold(popup)


@dataclass
class LoopContext:
    session: Any
    watcher: Watcher
    state: TrayState
    queue: PopupQueue
    notifier: Any
    sink: Callable[[IconState], None]
    hold_probe: Callable[[], bool]
    connect: Callable[[str], Any]
    sleep: Callable[..., Any] = asyncio.sleep
    now: Callable[[], float] = time.monotonic
    announcer: ConnectionAnnouncer = field(default_factory=ConnectionAnnouncer)
    quiet: QuietMode = field(default_factory=QuietMode)

    # When the current cycle's connection actually stood, or None if it never
    # got that far. run_cycle writes it, run_loop clears it before each round
    # and uses it to decide whether the cycle counts as healthy. It is not an
    # input — callers leave it alone.
    connected_at: float | None = None


def _publish(ctx: LoopContext) -> None:
    """Hand the current icon state to the UI, and survive a UI that cannot take it.

    The sink comes from the Qt layer: a deleted object or a call from the wrong
    thread raises, and an unguarded call would end the worker. That is the wrong
    order of priorities — the tray can stop *showing* its state and still keep
    watching and notifying, but a dead worker shows nothing and notifies nobody.

    Exception, not BaseException: CancelledError has to keep propagating.
    """
    try:
        ctx.sink(ctx.state.icon_state())
    except Exception as exc:
        logger.warning("icon update failed, carrying on: %s", exc)


def _parse_frame(raw: str) -> dict | None:
    """Turn one raw frame into a dict, or None if it is unusable.

    None means "carry on as if nothing arrived". The caller must not skip the
    rest of the round over it: the resnapshot check, the queue drain and the
    icon update all still have to happen. A `continue` here would skip all
    three, and a stream of broken frames would starve the ten-minute cadence
    and strand a held popup indefinitely.
    """
    try:
        frame = json.loads(raw)
    except ValueError as exc:
        logger.warning("unparsable frame ignored: %s", exc)
        return None
    if not isinstance(frame, dict):
        # Valid JSON of the wrong shape — handle_frame() would raise on .get().
        logger.warning("frame is not an object, ignored: %s", type(frame).__name__)
        return None
    return frame


async def _should_hold(ctx: LoopContext) -> bool:
    """Two reasons, one answer: a game on screen or an active quiet hour.

    Quiet mode is checked first and short-circuits the probe: while muted,
    the HTTP round trip to the gaming plugin never happens.
    """
    if ctx.quiet.is_muted(ctx.now()):
        return True
    return await asyncio.to_thread(ctx.hold_probe)


async def run_cycle(ctx: LoopContext) -> None:
    """One connect-consume cycle. Returning or raising means: reconnect.

    Order: open the socket first, then load the snapshot, then read frames.
    The websockets library holds whatever arrived meanwhile, so those frames
    land on top of the snapshot. The other way round the snapshot undoes a
    "read" the socket already reported, and the icon jumps back to red.
    """
    token = await asyncio.to_thread(ctx.session.ws_token)
    url = f"{ctx.session.ws_url()}?token={token}"

    async with ctx.connect(url) as socket:
        ok = await asyncio.to_thread(ctx.watcher.load_snapshot)
        if not ok:
            raise TemporaryFailure("snapshot refused")

        ctx.state.set_connected(True)
        # From here on the connection demonstrably stands. Only time spent past
        # this point counts as healthy — see run_loop.
        ctx.connected_at = ctx.now()
        back = ctx.announcer.came_online(ctx.now())
        if back:
            try:
                await ctx.notifier.show_summary(*back)
            except Exception as exc:
                logger.debug("reconnect notice failed: %s", exc)
        _publish(ctx)

        last_snapshot = ctx.now()

        while True:
            try:
                raw = await asyncio.wait_for(socket.recv(), timeout=TICK_SECONDS)
            except asyncio.TimeoutError:
                raw = None

            reload_needed = False
            popups: list[PendingPopup] = []

            if raw is not None:
                frame = _parse_frame(raw)
                if frame is not None:
                    result = ctx.watcher.handle_frame(frame)
                    popups, reload_needed = result.popups, result.reload_needed

            due = ctx.now() - last_snapshot >= RESNAPSHOT_SECONDS
            if reload_needed or due:
                # Catches expired snoozes (the server has no job for them),
                # missed frames and counter drift.
                if await asyncio.to_thread(ctx.watcher.load_snapshot):
                    last_snapshot = ctx.now()

            if popups or not ctx.queue.is_empty():
                hold = await _should_hold(ctx)
                await deliver(popups, ctx.queue, ctx.notifier, hold)

            _publish(ctx)


async def _give_up_pairing(ctx: LoopContext) -> None:
    """Stop cleanly and say so.

    The credentials go too: a device that was revoked must not keep a token
    on disk. ws_token() can raise PairingLost without ever touching the
    store, so forgetting happens here rather than only in refresh_access().
    """
    logger.warning("pairing lost — tray goes idle until re-paired")
    try:
        await asyncio.to_thread(ctx.session.forget)
    except Exception:
        # A read-only store or a permission problem must not swallow the
        # notice: going grey and saying so is what tells the user to re-pair.
        # Disappearing silently at exactly this moment leaves them with a
        # tray that simply stopped.
        logger.exception("could not clear the stored tokens")
    ctx.state.set_connected(False)
    _publish(ctx)
    try:
        await ctx.notifier.show_summary(
            "BaluHost", "Kopplung aufgehoben — bitte neu koppeln"
        )
    except Exception as exc:
        logger.debug("pairing notice failed: %s", exc)


async def run_loop(ctx: LoopContext) -> None:
    """Reconnect forever, with the failure classes kept apart.

    A 401 is worth one refresh and another try — one, counted, not "every
    time round". A rate limit or a server error is worth a backoff. Only a
    lost pairing stops the loop — and even then it stops by going grey, not
    by killing the thread silently.
    """
    attempt = 0
    refreshed = False

    while True:
        # run_cycle never returns normally — its inner loop has no break and
        # no return, so every exit is an exception. The attempt counter
        # therefore cannot be reset "on success"; how long the connection held
        # is the only evidence of health we get.
        #
        # Measured from set_connected(True), not from the top of the cycle.
        # Everything before it — fetching the ws token, connecting, the
        # snapshot — runs against BackendClient's 30 s timeout, which is
        # exactly TICK_SECONDS. A backend that accepts the TCP connection and
        # then says nothing would burn a full tick in ws_token() and look
        # "healthy" on every single attempt, so the backoff would never grow —
        # in precisely the scenario it exists for.
        ctx.connected_at = None

        try:
            await run_cycle(ctx)
        except AuthExpired:
            if refreshed:
                # Already spent this round's refresh and the token is still
                # refused. Trying again would spin without ever sleeping and
                # burn the ws-token rate limit the pairing depends on.
                logger.info("access refused again after a refresh — backing off")
            else:
                try:
                    await asyncio.to_thread(ctx.session.refresh_access)
                    refreshed = True
                    continue
                except PairingLost:
                    await _give_up_pairing(ctx)
                    return
                except TemporaryFailure as exc:
                    logger.info("refresh temporarily unavailable: %s", exc)
                except Exception:
                    # Not one of the known classes: broken JSON, a response
                    # without access_token, anything the server was never
                    # supposed to send. Backing off is the right answer —
                    # a surprise here is not a revoked device, and throwing
                    # the tokens away would be the expensive wrong reaction.
                    # Logged loudly because this is not a normal operating
                    # state, it means the other side sent something nobody
                    # planned for.
                    #
                    # Exception, not BaseException: CancelledError has to keep
                    # propagating, otherwise the worker can no longer be shut
                    # down.
                    logger.exception("unexpected failure while refreshing the access token")
        except PairingLost:
            await _give_up_pairing(ctx)
            return
        except Exception as exc:
            logger.info("connection lost: %s", exc)

        held = ctx.connected_at is not None and ctx.now() - ctx.connected_at >= TICK_SECONDS
        if held:
            # The connection stood for a full idle tick: start the backoff
            # over, and hand back the refresh this round was allowed. Without
            # this a tray that runs for days ends up permanently at the cap
            # and waits a minute before every reconnect.
            attempt = 0
            refreshed = False

        ctx.state.set_connected(False)
        gone = ctx.announcer.went_offline(ctx.now())
        if gone:
            try:
                await ctx.notifier.show_summary(*gone)
            except Exception as exc:
                logger.debug("offline notice failed: %s", exc)
        _publish(ctx)
        delay = backoff_delays(attempt + 1)[-1]
        await ctx.sleep(delay)
        attempt = min(attempt + 1, 7)
