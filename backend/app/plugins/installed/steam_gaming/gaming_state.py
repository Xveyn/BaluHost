"""Remember that BaluHost put the box into gaming mode.

Big Picture's own state is not detectable from the outside (measured, see the
design doc from 2026-07-24), so the power menu cannot ask the box whether
gaming mode is running. What it CAN know is what we did ourselves: this module
records that the start action ran and has not been ended here since.

A marker FILE, not a module global and not a config row:

- all four Uvicorn workers answer manifest requests, so an in-process flag
  would make the menu flap depending on which worker replied
- it lives under the storage root's ``.system/``, which survives a deploy
  (``git reset --hard`` without ``git clean``); ``/tmp`` is ephemeral per
  service start under PrivateTmp
- its existence IS the state, so there is nothing to parse and no partial
  write to guard against

Nothing here raises. This is read while building the power menu, and a storage
hiccup must degrade to "offer the start action" - the harmless direction -
rather than break the menu.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

_STATE_DIR_NAME = "steam_gaming"
_MARKER_NAME = "gaming_mode_active"


def marker_path() -> Path:
    """``<storage>/.system/steam_gaming/gaming_mode_active``."""
    base = Path(str(settings.nas_storage_path)).expanduser()
    return base / ".system" / _STATE_DIR_NAME / _MARKER_NAME


def is_active() -> bool:
    """True while gaming mode was started here and not ended here."""
    try:
        return marker_path().exists()
    except OSError as exc:
        logger.debug("gaming mode marker unreadable: %s", exc)
        return False


def mark_started() -> None:
    """Record that gaming mode is on."""
    path = marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    except OSError as exc:
        logger.warning("could not record the start of gaming mode: %s", exc)


def mark_ended() -> None:
    """Record that gaming mode is off. Idempotent."""
    try:
        marker_path().unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("could not record the end of gaming mode: %s", exc)
