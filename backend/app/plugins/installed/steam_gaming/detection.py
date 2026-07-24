"""One source of truth for "is a game running" - pill, ledger and panel share it.

The dev-mode stand-in lives HERE and not in detector.py/names.py on purpose:
the test suite runs with NAS_MODE=dev (tests/conftest.py), so a dev branch
inside the pure /proc scan would make the detector tests assert the mock
instead of the real behaviour.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.plugins.installed.steam_gaming.detector import detect_running_app_id
from app.plugins.installed.steam_gaming.names import resolve_name

# There is no /proc on a Windows dev box, so nothing would ever be detected and
# neither the pill nor the panel would have anything to show locally.
DEV_APP_ID = "0"
DEV_GAME_NAME = "Dev Mode Game"


def current_app_id() -> Optional[str]:
    """AppID of the running game, or None. Blocking - call via asyncio.to_thread."""
    app_id = detect_running_app_id()
    if app_id is None and settings.is_dev_mode:
        return DEV_APP_ID
    return app_id


def resolve_game_name(app_id: str) -> Optional[str]:
    """Display name for *app_id*, or None. Blocking - call via asyncio.to_thread."""
    if settings.is_dev_mode and app_id == DEV_APP_ID:
        return DEV_GAME_NAME
    return resolve_name(app_id)
