"""Icon lookup for the tray."""

from __future__ import annotations

from pathlib import Path

from baluhost_tray.state import IconState

_DIR = Path(__file__).parent
SIZES = (22, 24, 32, 48)
_DEFAULT_SIZE = 22


def icon_path(state: IconState, size: int = _DEFAULT_SIZE) -> Path:
    """Path to the icon file for this state, falling back to 22 px."""
    if size not in SIZES:
        size = _DEFAULT_SIZE
    return _DIR / f"baluhost-tray-{state.value}-{size}.png"
