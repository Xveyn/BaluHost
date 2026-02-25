"""
SMART disk health monitoring sub-package.

Re-exports all public symbols for backward compatibility.
All existing imports (``from app.services.hardware.smart import X``) continue
to work unchanged.
"""
from __future__ import annotations

# --- Leaf modules ---
from app.services.hardware.smart.cache import (
    SmartUnavailableError,
    get_cached_smart_status,
    get_dev_mode_state,
    invalidate_smart_cache,
    toggle_dev_mode,
)

# --- Public API ---
from app.services.hardware.smart.api import (
    get_smart_device_models,
    get_smart_device_order,
    get_smart_status,
)

# --- Scheduler ---
from app.services.hardware.smart.scheduler import (
    get_smart_scheduler_status,
    run_smart_self_test,
    start_smart_scheduler,
    stop_smart_scheduler,
)

# Keep references to canonical modules for monkey-patching support
from app.services.hardware.smart import cache as _cache_module
from app.services.hardware.smart import scheduler as _scheduler_module


def __getattr__(name: str):
    """Support reading internal state from the package level.

    Tests that do ``smart._DEV_USE_MOCK_DATA`` or ``smart._SMART_CACHE_DATA``
    or ``smart._smart_scheduler`` after monkey-patching will be redirected to
    the canonical location in the appropriate sub-module.
    """
    if name == "_DEV_USE_MOCK_DATA":
        return _cache_module._DEV_USE_MOCK_DATA
    if name == "_SMART_CACHE_DATA":
        return _cache_module._SMART_CACHE_DATA
    if name == "_SMART_CACHE_TIMESTAMP":
        return _cache_module._SMART_CACHE_TIMESTAMP
    if name == "_SMART_CACHE_TTL_SECONDS":
        return _cache_module._SMART_CACHE_TTL_SECONDS
    if name == "_smart_scheduler":
        return _scheduler_module._smart_scheduler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __setattr__(name: str, value: object) -> None:
    """Forward writes of internal state to the canonical sub-module."""
    if name == "_DEV_USE_MOCK_DATA":
        _cache_module._DEV_USE_MOCK_DATA = value  # type: ignore[assignment]
        return
    if name == "_smart_scheduler":
        _scheduler_module._smart_scheduler = value  # type: ignore[assignment]
        return
    if name == "_SMART_CACHE_DATA":
        _cache_module._SMART_CACHE_DATA = value  # type: ignore[assignment]
        return
    if name == "_SMART_CACHE_TIMESTAMP":
        _cache_module._SMART_CACHE_TIMESTAMP = value  # type: ignore[assignment]
        return
    raise AttributeError(f"module {__name__!r} has no settable attribute {name!r}")


__all__ = [
    "SmartUnavailableError",
    "get_smart_status",
    "get_cached_smart_status",
    "invalidate_smart_cache",
    "run_smart_self_test",
    "start_smart_scheduler",
    "stop_smart_scheduler",
    "get_smart_scheduler_status",
    "get_dev_mode_state",
    "toggle_dev_mode",
    "get_smart_device_models",
    "get_smart_device_order",
]
