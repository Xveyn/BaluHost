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
from dataclasses import dataclass
from typing import Any, Callable

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


def _publish(ctx: LoopContext) -> None:
    ctx.sink(ctx.state.icon_state())


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
                try:
                    frame = json.loads(raw)
                except ValueError:
                    continue
                result = ctx.watcher.handle_frame(frame)
                popups, reload_needed = result.popups, result.reload_needed

            due = ctx.now() - last_snapshot >= RESNAPSHOT_SECONDS
            if reload_needed or due:
                # Catches expired snoozes (the server has no job for them),
                # missed frames and counter drift.
                if await asyncio.to_thread(ctx.watcher.load_snapshot):
                    last_snapshot = ctx.now()

            if popups or not ctx.queue.is_empty():
                hold = await asyncio.to_thread(ctx.hold_probe)
                await deliver(popups, ctx.queue, ctx.notifier, hold)

            _publish(ctx)


async def _give_up_pairing(ctx: LoopContext) -> None:
    """Stop cleanly and say so.

    The credentials go too: a device that was revoked must not keep a token
    on disk. ws_token() can raise PairingLost without ever touching the
    store, so forgetting happens here rather than only in refresh_access().
    """
    logger.warning("pairing lost — tray goes idle until re-paired")
    await asyncio.to_thread(ctx.session.forget)
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

    A 401 is worth one refresh and another try. A rate limit or a server
    error is worth a backoff. Only a lost pairing stops the loop — and even
    then it stops by going grey, not by killing the thread silently.
    """
    attempt = 0
    while True:
        try:
            await run_cycle(ctx)
            attempt = 0
        except AuthExpired:
            try:
                await asyncio.to_thread(ctx.session.refresh_access)
                continue
            except PairingLost:
                await _give_up_pairing(ctx)
                return
            except TemporaryFailure as exc:
                logger.info("refresh temporarily unavailable: %s", exc)
        except PairingLost:
            await _give_up_pairing(ctx)
            return
        except Exception as exc:
            logger.info("connection lost: %s", exc)

        ctx.state.set_connected(False)
        _publish(ctx)
        delay = backoff_delays(attempt + 1)[-1]
        await ctx.sleep(delay)
        attempt = min(attempt + 1, 7)
