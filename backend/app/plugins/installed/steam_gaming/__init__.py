"""Steam gaming plugin: shows a status-strip pill while a game is running.

Detection is a /proc scan (see detector.py); the result is cached for a few
seconds so the status strip's poll — once per logged-in user every 10s across
four production workers — does not re-scan for every request. A per-worker
cache is enough: the pill is an activity indicator, not a ledger, and this
avoids sharing state between workers entirely.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone, tzinfo
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.plugins.base import (
    BackgroundTaskSpec,
    DashboardPanelSpec,
    MenuActionResult,
    PluginBase,
    PluginEventSpec,
    PluginMenuItem,
    PluginMetadata,
    PluginUIManifest,
    StatusPillSpec,
)
from app.core.config import settings
from app.models.steam_session import SteamSession
from app.plugins.dashboard_panel import StatusItem, StatusPanelData
from app.plugins.installed.steam_gaming import gaming_state, ledger
from app.plugins.installed.steam_gaming.detection import (
    current_app_id,
    resolve_game_name,
    steam_is_running,
)
from app.plugins.installed.steam_gaming.launch import start_gaming_mode
from app.plugins.installed.steam_gaming.launcher import close_big_picture
from app.plugins.installed.steam_gaming.poller import SteamSessionPoller
from app.services.power.desktop_windows import show_desktop

logger = logging.getLogger(__name__)

_PILL_ID = "session"
_MENU_ACTION_ID = "gaming_mode"
_MENU_END_ACTION_ID = "gaming_mode_end"
# Steam needs a moment to put its windowed UI back on screen after leaving Big
# Picture. Minimizing before that would clear a desktop the window then pops
# back onto. Measured on BaluNode with 2s; kept well inside the 20s budget of a
# plugin menu action.
_WINDOW_SETTLE_SECONDS = 2.0
_EVENT_STARTED = ledger.EVENT_STARTED
_EVENT_ENDED = ledger.EVENT_ENDED
_POLL_INTERVAL_SECONDS = 30.0
_CACHE_TTL_SECONDS = 3.0
_CACHE: Dict[str, object] = {}
_PANEL_ROWS = 5


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def _utc_now() -> datetime:
    """Indirection so tests can control the clock, like the poller's."""
    return datetime.now(timezone.utc)


def _current_game() -> Optional[tuple[str, Optional[str]]]:
    """``(app_id, name)`` of the running game, or None. Cached for a few seconds."""
    now = _monotonic()
    checked_at = _CACHE.get("checked_at")
    if isinstance(checked_at, float) and now - checked_at < _CACHE_TTL_SECONDS:
        return _CACHE.get("game")  # type: ignore[return-value]

    app_id = current_app_id()
    game = (app_id, resolve_game_name(app_id)) if app_id else None
    _CACHE["checked_at"] = now
    _CACHE["game"] = game
    return game


def _format_duration(seconds: float) -> str:
    """``3h 04m`` / ``12m`` - digits only, so no string needs translating."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _display_tz() -> Optional[tzinfo]:
    """Time zone the panel's dates are shown in: the server's (None = local).

    A seam so tests can pin it; the box's zone is the owner's, which is the
    right reference for "when did I play this".
    """
    return None


def _panel_value(row: SteamSession, now: datetime) -> str:
    """Running sessions show the bare duration; finished ones prepend the date."""
    duration = _format_duration(ledger.duration_seconds(row, now))
    if row.ended_at is None:
        return duration
    # Explicit conversion, not the value's own offset: SQLite returns naive
    # UTC, psycopg2 an aware value in the DB session's zone, so without it the
    # date depended on the driver (#470).
    started_local = ledger.as_utc(row.started_at).astimezone(_display_tz())
    return f"{started_local:%d.%m.} · {duration}"


def _start_menu_item() -> PluginMenuItem:
    return PluginMenuItem(
        id=_MENU_ACTION_ID,
        icon="Gamepad2",
        tone="info",
        order=10,
        label_key="menu_gaming_mode",
        label_text="Gaming Mode",
        description_key="menu_gaming_mode_desc",
        description_text="Turn displays on and open Big Picture",
    )


def _end_menu_item() -> PluginMenuItem:
    # "Monitor", not something more expressive: the frontend icon map is a
    # closed set (#451), and anything outside it silently degrades to the
    # generic plug icon.
    return PluginMenuItem(
        id=_MENU_END_ACTION_ID,
        icon="Monitor",
        tone="neutral",
        order=10,
        label_key="menu_gaming_mode_end",
        label_text="End Gaming Mode",
        description_key="menu_gaming_mode_end_desc",
        description_text="Close Big Picture and clear the desktop",
    )


def _displays_on() -> bool:
    """True while at least one display is lit.

    Read synchronously because the UI manifest is built synchronously - a few
    small sysfs reads, the async sibling only wraps the same helper in a
    thread. Unreadable sysfs counts as "off": that steers the menu to the
    start action, which is the harmless one to offer wrongly.

    The implementation lives in services/power/gaming_presence.py because the
    sleep service asks the identical question when deciding whether Big
    Picture should suppress a suspend - two copies of this policy would drift.

    Imported inside the function on purpose: gaming_presence imports this
    package's detector at module level, so a top-level import here would be a
    cycle - and the loser of that cycle is the detector, which silently
    degrades to "no game is ever running".
    """
    from app.services.power.gaming_presence import displays_on  # noqa: PLC0415

    return displays_on()


def _end_action_is_current() -> bool:
    """Whether the menu should offer to END gaming mode rather than start it.

    Two signals, because the obvious one does not exist: whether Big Picture
    runs is not detectable (design doc 2026-07-24).

    - the marker says BaluHost started gaming mode and has not ended it
    - the displays are on, so there is something on screen to end

    The display check is what rescues a stale marker: if Big Picture was left
    at the box and the screens went dark, the menu offers "start" again
    instead of stranding on "end".
    """
    return gaming_state.is_active() and _displays_on()


class SteamGamingPlugin(PluginBase):
    """Surfaces a running Steam session in the topbar status strip."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="steam_gaming",
            display_name="Steam Gaming",
            version="1.0.0",
            description="Shows a status-strip pill while a Steam game is running",
            author="BaluHost",
        )

    async def on_startup(self) -> None:
        """Forget a gaming mode that the previous process started.

        A deploy or a crash restarts the backend while Big Picture may well
        keep running, and the marker would then outlive everything we know
        about it. Clearing means the menu offers "start" again - wrong at
        worst by one harmless click, whereas a stale "end" minimizes the
        windows of someone who never asked for it.
        """
        await asyncio.to_thread(gaming_state.mark_ended)

    def get_status_pills(self) -> List[StatusPillSpec]:
        return [StatusPillSpec(
            id=_PILL_ID,
            icon="Gamepad2",
            href="/plugins",
            name_key="pill_name",
            name_text="Gaming Session",
            default_visibility="admin",
            silent_when_ok=True,
        )]

    async def collect_status_pill(self, pill_id: str, db: Session) -> Optional[dict]:
        if pill_id != _PILL_ID:
            return None

        # _current_game() does synchronous filesystem I/O (/proc scan, manifest
        # reads); asyncio.wait_for() can only cancel awaits, not blocking sync
        # code, so a slow/spun-down Steam library mount would otherwise stall
        # the whole worker's event loop instead of being cut off by the
        # PLUGIN_COLLECTOR_TIMEOUT_SECONDS timeout in the status bar service.
        # The dev-mode stand-in now lives in detection.py, so pill, ledger and
        # panel agree on what is running.
        game = await asyncio.to_thread(_current_game)
        if game is None:
            return None

        _app_id, name = game
        return {
            "kind": "state",
            "tone": "info",
            "label_key": "pill_label",
            "label_text": "Gaming Session",
            "value": name,
            "icon": "Gamepad2",
        }

    def get_ui_manifest(self) -> PluginUIManifest:
        """Advertise the direction that makes sense right now - only one."""
        item = _end_menu_item() if _end_action_is_current() else _start_menu_item()
        return PluginUIManifest(enabled=True, menu_items=[item])

    def get_menu_items(self) -> List[PluginMenuItem]:
        """Both directions stay dispatchable, whatever the manifest shows.

        The core validates a clicked action_id against THIS list. Deriving it
        from the manifest (the base class default) would 404 any click that
        races a state change - the menu in the browser was rendered when the
        other direction was current. Advertising a subset of what is declared
        is the safe direction; the reverse is the drift base.py warns about.
        """
        return [_start_menu_item(), _end_menu_item()]

    def get_router(self):
        """The launch routes (routes.py).

        Imported here, not at module level: routes imports detection, launch
        and library from this package, and the package __init__ must finish
        before those resolve. Routers are mounted once at startup, so enabling
        the plugin later needs a backend restart before these routes exist
        (restart_required reports that) - pill, menu and panel still work
        immediately.
        """
        from app.plugins.installed.steam_gaming.routes import router  # noqa: PLC0415

        return router

    async def run_menu_action(
        self,
        action_id: str,
        db: Session,
        *,
        user=None,
        client_host: Optional[str] = None,
    ) -> Optional[MenuActionResult]:
        if action_id == _MENU_END_ACTION_ID:
            return await self._end_gaming_mode()
        if action_id != _MENU_ACTION_ID:
            return None

        # The sequence lives in launch.py so the launch route runs the very
        # same steps. The user only ever sees the translated key; the detail
        # goes into the literal fallback like before.
        started = await start_gaming_mode(user=user, client_host=client_host, db=db)
        if started.failed_step == "displays":
            return MenuActionResult(
                ok=False,
                message_key="menu_displays_failed",
                message_text=f"Displays could not be turned on: {started.detail}",
            )
        if started.failed_step == "steam":
            return MenuActionResult(
                ok=False,
                message_key="menu_steam_failed",
                message_text=f"Displays are on, but Steam did not start: {started.detail}",
            )
        # "started", not "Big Picture is running": nothing past the spawn is
        # observable from here.
        return MenuActionResult(
            ok=True,
            message_key="menu_gaming_mode_started",
            message_text="Gaming mode started",
        )

    async def _end_gaming_mode(self) -> MenuActionResult:
        """Leave Big Picture and clear the desktop again.

        Deliberately does NOT turn the displays off - that already exists as
        its own entry in the power menu, and combining both would make one
        click do two things the user may not want together.
        """
        # A running game is the one state that IS detectable, so it is the one
        # precondition worth enforcing: nobody wants a remote click pulling the
        # UI out from under someone playing at the box.
        game = await asyncio.to_thread(_current_game)
        if game is not None:
            app_id, name = game
            return MenuActionResult(
                ok=False,
                message_key="menu_end_game_running",
                message_text=f"A game is still running: {name or app_id}",
            )

        # Without this guard the close URL would START Steam - see launcher.py.
        if not await asyncio.to_thread(steam_is_running):
            # Steam is down, so gaming mode is over no matter what the marker
            # claims - clearing it here is how a stale one heals.
            await asyncio.to_thread(gaming_state.mark_ended)
            return MenuActionResult(
                ok=True,
                message_key="menu_end_steam_not_running",
                message_text="Steam is not running - nothing to end",
            )

        closed, detail = await asyncio.to_thread(close_big_picture)
        if not closed:
            logger.warning("end gaming mode: Big Picture was not closed: %s", detail)
            return MenuActionResult(
                ok=False,
                message_key="menu_end_close_failed",
                message_text=f"Big Picture could not be closed: {detail}",
            )

        # Big Picture is gone, so gaming mode has ended - independently of
        # whether the windows go down below. Leaving the marker set on that
        # failure would strand the menu on "end".
        await asyncio.to_thread(gaming_state.mark_ended)

        await asyncio.sleep(_WINDOW_SETTLE_SECONDS)

        minimized, detail = await asyncio.to_thread(show_desktop)
        if not minimized:
            logger.warning("end gaming mode: windows stayed up: %s", detail)
            return MenuActionResult(
                ok=False,
                message_key="menu_end_windows_failed",
                message_text=f"Big Picture was closed, but the windows stayed up: {detail}",
            )

        # "ended", not "Big Picture is gone": ok means the systemd unit was
        # started, not that Big Picture actually closed - that stays
        # unobservable from here either.
        return MenuActionResult(
            ok=True,
            message_key="menu_gaming_mode_ended",
            message_text="Gaming mode ended",
        )

    def get_dashboard_panel(self) -> Optional[DashboardPanelSpec]:
        return DashboardPanelSpec(
            panel_type="status",
            title="Steam Gaming",
            icon="gamepad-2",
            accent="from-indigo-500 to-purple-500",
            # The game name is information about the box owner - same call as
            # the pill's default visibility in Teilprojekt 1.
            admin_only=True,
        )

    async def get_dashboard_data(self, db: Session) -> Optional[dict]:
        """The five newest sessions; the running one sorts to the top.

        Returns None when nothing was ever recorded - a placeholder line would
        be a translatable string, and StatusItem has no key fields.
        """
        rows = (
            db.query(SteamSession)
            .order_by(SteamSession.started_at.desc())
            .limit(_PANEL_ROWS)
            .all()
        )
        if not rows:
            return None

        now = _utc_now()
        items = [
            StatusItem(
                label=row.game_name or f"AppID {row.app_id}",
                value=_panel_value(row, now),
                tone="ok" if row.ended_at is None else "neutral",
            )
            for row in rows
        ]
        return StatusPanelData(items=items).model_dump()

    def get_notification_events(self) -> List[PluginEventSpec]:
        return [
            PluginEventSpec(
                id=_EVENT_STARTED,
                notification_type="info",
                priority=0,
                title_template="Gaming-Session gestartet: {game}",
                message_template="Auf BaluNode läuft jetzt {game}.",
                action_url="/plugins",
                cooldown_seconds=60,
                default_target="admins",
            ),
            PluginEventSpec(
                id=_EVENT_ENDED,
                notification_type="info",
                priority=0,
                title_template="Gaming-Session beendet",
                message_template="{game} wurde beendet.",
                action_url="/plugins",
                cooldown_seconds=60,
                default_target="admins",
            ),
        ]

    def get_background_tasks(self) -> List[BackgroundTaskSpec]:
        poller = SteamSessionPoller()
        return [BackgroundTaskSpec(
            name="session_poller",
            func=poller.tick,
            interval_seconds=_POLL_INTERVAL_SECONDS,
        )]

    def get_translations(self) -> Optional[Dict[str, Dict[str, str]]]:
        return {
            "en": {
                "pill_name": "Gaming Session",
                "pill_label": "Gaming Session",
                "menu_gaming_mode": "Gaming Mode",
                "menu_gaming_mode_desc": "Displays on + Big Picture",
                "menu_gaming_mode_started": "Gaming mode started",
                "menu_displays_failed": "Displays could not be turned on",
                "menu_steam_failed": "Displays are on, but Steam did not start",
                "menu_gaming_mode_end": "End Gaming Mode",
                "menu_gaming_mode_end_desc": "Close Big Picture + clear the desktop",
                "menu_gaming_mode_ended": "Gaming mode ended",
                "menu_end_game_running": "A game is still running",
                "menu_end_steam_not_running": "Steam is not running - nothing to end",
                "menu_end_close_failed": "Big Picture could not be closed",
                "menu_end_windows_failed": "Big Picture was closed, but the windows stayed up",
            },
            "de": {
                "pill_name": "Gaming-Session",
                "pill_label": "Gaming-Session",
                "menu_gaming_mode": "Gaming-Modus",
                "menu_gaming_mode_desc": "Displays an + Big Picture",
                "menu_gaming_mode_started": "Gaming-Modus gestartet",
                "menu_displays_failed": "Displays konnten nicht eingeschaltet werden",
                "menu_steam_failed": "Displays sind an, aber Steam startete nicht",
                "menu_gaming_mode_end": "Gaming-Modus beenden",
                "menu_gaming_mode_end_desc": "Big Picture schließen + Fenster minimieren",
                "menu_gaming_mode_ended": "Gaming-Modus beendet",
                "menu_end_game_running": "Es läuft noch ein Spiel",
                "menu_end_steam_not_running": "Steam läuft nicht - nichts zu beenden",
                "menu_end_close_failed": "Big Picture konnte nicht geschlossen werden",
                "menu_end_windows_failed": "Big Picture ist zu, aber die Fenster blieben offen",
            },
        }
