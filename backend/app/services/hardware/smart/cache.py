"""SMART cache and dev-mode toggle.

Leaf module — no internal package dependencies.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.system import SmartStatusResponse


class SmartUnavailableError(RuntimeError):
    """Raised when SMART diagnostics cannot be accessed."""


# Cache-Konfiguration (vereinfacht, klare Typen)
_SMART_CACHE_TTL_SECONDS = 120  # Wie lange SMART Daten gültig bleiben
_SMART_CACHE_TIMESTAMP: datetime | None = None
_SMART_CACHE_DATA: SmartStatusResponse | None = None

# Dev-Mode: Toggle zwischen Mock und Real SMART Daten
_DEV_USE_MOCK_DATA = True  # Default: Mock-Daten im Dev-Mode


def _smart_cache_valid() -> bool:
    if _SMART_CACHE_TIMESTAMP is None:
        return False
    return (datetime.now(timezone.utc) - _SMART_CACHE_TIMESTAMP).total_seconds() < _SMART_CACHE_TTL_SECONDS


def _set_smart_cache(payload: SmartStatusResponse) -> None:
    global _SMART_CACHE_TIMESTAMP, _SMART_CACHE_DATA
    _SMART_CACHE_TIMESTAMP = datetime.now(timezone.utc)
    _SMART_CACHE_DATA = payload


def get_cached_smart_status() -> SmartStatusResponse | None:
    if _smart_cache_valid():
        return _SMART_CACHE_DATA
    return None


def invalidate_smart_cache() -> None:
    global _SMART_CACHE_TIMESTAMP, _SMART_CACHE_DATA
    _SMART_CACHE_TIMESTAMP = None
    _SMART_CACHE_DATA = None


def get_dev_mode_state() -> str:
    """Gibt den aktuellen Dev-Mode Status zurück: 'mock' oder 'real'."""
    return "mock" if _DEV_USE_MOCK_DATA else "real"


def toggle_dev_mode() -> str:
    """Wechselt zwischen Mock und Real SMART-Daten im Dev-Mode.

    Returns:
        str: Neuer Modus ('mock' oder 'real')
    """
    global _DEV_USE_MOCK_DATA
    _DEV_USE_MOCK_DATA = not _DEV_USE_MOCK_DATA
    invalidate_smart_cache()  # Cache invalidieren beim Toggle
    import logging
    logger = logging.getLogger(__name__)
    new_mode = get_dev_mode_state()
    logger.info(f"Dev-Mode SMART data toggled to: {new_mode}")
    return new_mode
