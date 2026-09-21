"""HTTP routes of the steam_gaming plugin: list and launch installed games.

Design: docs/superpowers/specs/2026-09-14-steam-game-launch-design.md (PR B).
"""
# NB: no ``from __future__ import annotations`` here (cf. bluetooth, audio_control).
# Deferred annotations behind slowapi's ``@user_limiter.limit`` wrapper become
# ForwardRefs FastAPI can no longer resolve - every request would be a 422.
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.api.deps import require_power_launch_games
from app.core.database import get_db
from app.core.exceptions import (
    BadGatewayError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.network_utils import is_private_or_local_ip
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.installed.steam_gaming import detection, launch, library
from app.plugins.installed.steam_gaming.models import (
    GameListResponse,
    LaunchableGame,
    LaunchResponse,
    RunningGame,
    SessionStateResponse,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db
from app.services.power.session_lock import current_lock_state

logger = logging.getLogger(__name__)

router = APIRouter()

_READ_LIMIT = get_limit("steam_games_read")
_LAUNCH_LIMIT = get_limit("steam_launch")


def _client_host(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _audit(
    action: str, user: UserPublic, success: bool, details: dict, client_host: Optional[str]
) -> None:
    """Audit launches and refused attempts - never the game name, never a detail.

    The name comes from a manifest the desktop user can write; details carry
    subprocess and kscreen-doctor output.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action=action,
        user=user.username,
        resource="steam_gaming",
        success=success,
        details=details,
        ip_address=client_host,
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="launch_games",
            details={"action": action},
            success=success,
        )


def _running_game() -> Optional[RunningGame]:
    """The running game without the dev stand-in. Blocking - call via to_thread."""
    app_id = detection.current_app_id(dev_stand_in=False)
    if app_id is None:
        return None
    return RunningGame(app_id=app_id, name=detection.resolve_game_name(app_id))


@router.get("/games", response_model=GameListResponse)
@user_limiter.limit(_READ_LIMIT)
async def list_games(
    request: Request,
    response: Response,
    current_user=Depends(require_power_launch_games),
) -> GameListResponse:
    """Installed, launchable games and what is running right now.

    Behind the launch right although it only reads: the library and the
    running game are information about the box owner. No LAN gate - reading
    creates no trust.
    """
    try:
        games = await asyncio.to_thread(library.list_installed_games)
    except library.LibraryUnavailable as exc:
        raise ServiceUnavailableError("Game library unavailable") from exc
    running = await asyncio.to_thread(_running_game)
    return GameListResponse(
        games=[LaunchableGame(app_id=game.app_id, name=game.name) for game in games],
        running=running,
        can_launch_here=is_private_or_local_ip(_client_host(request)),
    )


@router.post(
    "/games/{app_id}/launch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=LaunchResponse,
)
@user_limiter.limit(_LAUNCH_LIMIT)
async def launch_installed_game(
    app_id: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_launch_games),
    db: Session = Depends(get_db),
) -> LaunchResponse:
    """Displays on, unlock (if permitted), Big Picture, then the game.

    Every check runs before the first side effect. No outer timeout: wait_for
    would cancel the await but not the thread behind it (#643).
    """
    client_host = _client_host(request)

    # For every role: a stolen account must not light up and drive the TV
    # from the internet. Refusals are exactly the pattern worth auditing.
    if not is_private_or_local_ip(client_host):
        _audit("steam_game_launch_denied", current_user, False, {"reason": "not_local"}, client_host)
        raise ForbiddenError("Launching is only allowed from the local network")

    if not library.is_valid_app_id(app_id):
        raise NotFoundError("Game not installed")
    try:
        game = await asyncio.to_thread(library.find_installed_game, app_id)
    except library.LibraryUnavailable as exc:
        raise ServiceUnavailableError("Game library unavailable") from exc
    if game is None:
        raise NotFoundError("Game not installed")

    # Nobody with the right takes a running game away from someone else.
    running = await asyncio.to_thread(detection.current_app_id, dev_stand_in=False)
    if running is not None:
        raise ConflictError("A game is already running")

    started = await launch.start_gaming_mode(user=current_user, client_host=client_host, db=db)
    if not started.ok:
        _audit(
            "steam_game_launch", current_user, False,
            {"app_id": game.app_id, "failed_step": started.failed_step}, client_host,
        )
        if started.failed_step == "displays":
            raise BadGatewayError("Displays could not be turned on")
        raise BadGatewayError("Steam could not be started")

    # The id from the library entry, not the request string.
    launched, detail = await asyncio.to_thread(launch.launch_game, game.app_id)
    if not launched:
        logger.warning("steam game launch: %s did not start: %s", game.app_id, detail)
        _audit(
            "steam_game_launch", current_user, False,
            {"app_id": game.app_id, "failed_step": "game"}, client_host,
        )
        raise BadGatewayError("Steam could not be started")

    _audit(
        "steam_game_launch", current_user, True,
        {"app_id": game.app_id, "failed_step": None}, client_host,
    )
    return LaunchResponse(status="requested", session_locked=await current_lock_state())


@router.get("/session-state", response_model=SessionStateResponse)
@user_limiter.limit(_READ_LIMIT)
async def session_state(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_user),
) -> SessionStateResponse:
    """Whether a gaming session is on screen - the tray gates popups on this.

    Not gaming_mode_on_screen(): its marker means "*we* started gaming mode"
    (see CLAUDE.md), so a game launched straight from Steam would not count -
    which is the common case. game_is_running() is the real source, the marker
    stays as a second path for Big Picture, and the lit-display requirement is
    what lets an abandoned session expire on its own.

    Behind get_current_user, not require_power_launch_games: this returns a
    single boolean the tray polls before every popup, and gating it on the
    launch right would hand the tray the ability to start games.

    Reads a marker file and sysfs, so it runs off the event loop. Any read
    error counts as "not gaming": rather one notification too many than a
    swallowed alarm.
    """
    from app.services.power import gaming_presence

    def _probe() -> bool:
        active = gaming_presence.game_is_running() or gaming_presence._marker_is_active()
        return bool(active and gaming_presence.displays_on())

    try:
        active = await asyncio.to_thread(_probe)
    except Exception:
        active = False
    return SessionStateResponse(gaming_active=active)
