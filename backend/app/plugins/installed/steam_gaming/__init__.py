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
from datetime import datetime, timezone
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
from app.models.steam_session import SteamSession
from app.plugins.dashboard_panel import StatusItem, StatusPanelData
from app.plugins.installed.steam_gaming import ledger
from app.plugins.installed.steam_gaming.detection import current_app_id, resolve_game_name
from app.plugins.installed.steam_gaming.launcher import open_big_picture
from app.plugins.installed.steam_gaming.poller import SteamSessionPoller
from app.services.power.desktop import get_desktop_service
from app.services.power.session_lock import unlock_if_permitted

logger = logging.getLogger(__name__)

_PILL_ID = "session"
_MENU_ACTION_ID = "gaming_mode"
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


def _panel_value(row: SteamSession, now: datetime) -> str:
    """Running sessions show the bare duration; finished ones prepend the date."""
    duration = _format_duration(ledger.duration_seconds(row, now))
    if row.ended_at is None:
        return duration
    return f"{ledger.as_utc(row.started_at):%d.%m.} · {duration}"


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
        return PluginUIManifest(
            enabled=True,
            menu_items=[PluginMenuItem(
                id=_MENU_ACTION_ID,
                icon="Gamepad2",
                tone="info",
                order=10,
                label_key="menu_gaming_mode",
                label_text="Gaming Mode",
                description_key="menu_gaming_mode_desc",
                description_text="Turn displays on and open Big Picture",
            )],
        )

    async def run_menu_action(
        self,
        action_id: str,
        db: Session,
        *,
        user=None,
        client_host: Optional[str] = None,
    ) -> Optional[MenuActionResult]:
        if action_id != _MENU_ACTION_ID:
            return None

        # Displays first: opening Big Picture onto dark screens helps nobody.
        # LinuxDesktopBackend.enable() runs kscreen-doctor in a thread, so the
        # core's wait_for stays effective.
        ok, detail = await get_desktop_service().enable()
        if not ok:
            # The user only ever sees the translated key, so without this line
            # the reason kscreen-doctor refused is lost for good.
            logger.warning("gaming mode: turning the displays on failed: %s", detail)
            return MenuActionResult(
                ok=False,
                message_key="menu_displays_failed",
                message_text=f"Displays could not be turned on: {detail}",
            )

        # Then the lock screen - Big Picture behind it would be just as useless
        # as behind a dark monitor. Same gates as the enable route; a refusal
        # is not a failure of the action.
        if user is not None:
            unlocked, unlock_detail = await unlock_if_permitted(
                user=user, client_host=client_host, db=db
            )
            if not unlocked:
                logger.info("gaming mode: session not unlocked: %s", unlock_detail)

        launched, detail = await asyncio.to_thread(open_big_picture)
        if not launched:
            logger.warning("gaming mode: Big Picture did not start: %s", detail)
            return MenuActionResult(
                ok=False,
                message_key="menu_steam_failed",
                message_text=f"Displays are on, but Steam did not start: {detail}",
            )

        # "started", not "Big Picture is running": the process is detached, so
        # anything past the spawn is not observable from here.
        return MenuActionResult(
            ok=True,
            message_key="menu_gaming_mode_started",
            message_text="Gaming mode started",
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
            },
            "de": {
                "pill_name": "Gaming-Session",
                "pill_label": "Gaming-Session",
                "menu_gaming_mode": "Gaming-Modus",
                "menu_gaming_mode_desc": "Displays an + Big Picture",
                "menu_gaming_mode_started": "Gaming-Modus gestartet",
                "menu_displays_failed": "Displays konnten nicht eingeschaltet werden",
                "menu_steam_failed": "Displays sind an, aber Steam startete nicht",
            },
        }
