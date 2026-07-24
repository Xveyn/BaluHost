"""One source of truth for "is a game running" - pill, ledger and panel share it.

The dev-mode stand-in lives HERE and not in detector.py/names.py on purpose:
the test suite runs with NAS_MODE=dev (tests/conftest.py), so a dev branch
inside the pure /proc scan would make the detector tests assert the mock
instead of the real behaviour.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.config import settings
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name

logger = logging.getLogger(__name__)

# There is no /proc on a Windows dev box, so nothing would ever be detected and
# neither the pill nor the panel would have anything to show locally.
DEV_APP_ID = "0"
DEV_GAME_NAME = "Dev Mode Game"

# Matches SteamSession.app_id: String(32) in app/models/steam_session.py.
# Real Steam AppIDs are at most 10 digits today; anything longer than the
# column width is not a game, it is a process that merely looks like one -
# passing it through would make every booking tick fail with a PostgreSQL
# DataError (SQLite does not enforce VARCHAR length, so this only bites in
# production).
_MAX_APP_ID_LENGTH = 32

# Matches SteamSession.game_name: String(200) in app/models/steam_session.py.
# A truncated name is a cosmetic issue in the panel; an unbounded one is a
# permanently failing booking on PostgreSQL.
_MAX_GAME_NAME_LENGTH = 200


def current_app_id() -> Optional[str]:
    """AppID of the running game, or None. Blocking - call via asyncio.to_thread."""
    app_id = detect_running_app_id()
    if app_id is not None and len(app_id) > _MAX_APP_ID_LENGTH:
        logger.warning(
            "Ignoring detected app_id longer than %d chars (got %d): %r",
            _MAX_APP_ID_LENGTH,
            len(app_id),
            app_id,
        )
        app_id = None
    if app_id is None and settings.is_dev_mode:
        return DEV_APP_ID
    return app_id


def resolve_game_name(app_id: str) -> Optional[str]:
    """Display name for *app_id*, or None. Blocking - call via asyncio.to_thread."""
    if settings.is_dev_mode and app_id == DEV_APP_ID:
        return DEV_GAME_NAME
    name = resolve_name(app_id)
    if name is not None and len(name) > _MAX_GAME_NAME_LENGTH:
        name = name[:_MAX_GAME_NAME_LENGTH]
    return name
