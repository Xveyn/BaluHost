"""Helper functions for emitting plugin hooks from services.

Provides convenient wrapper functions that handle the plugin manager
lookup and error handling.
"""
import logging
from typing import Any, Optional


logger = logging.getLogger(__name__)


def emit_hook(hook_name: str, **kwargs: Any) -> None:
    """Emit a plugin hook.

    This is a fire-and-forget operation. If the plugin system
    is not initialized or an error occurs, it will be logged
    but not raised.

    Args:
        hook_name: Name of the hook (e.g., "on_file_uploaded")
        **kwargs: Arguments to pass to hook implementations
    """
    try:
        from app.plugins.manager import PluginManager

        manager = PluginManager.get_instance()
        manager.emit_hook(hook_name, **kwargs)
    except Exception as e:
        logger.debug(f"Could not emit hook {hook_name}: {e}")


async def emit_event(
    event_name: str,
    data: dict,
    source: Optional[str] = None,
) -> None:
    """Emit an async plugin event.

    This is a fire-and-forget operation.

    Args:
        event_name: Name of the event
        data: Event data dictionary
        source: Optional source identifier
    """
    try:
        from app.plugins.events import get_event_manager

        manager = get_event_manager()
        await manager.emit(event_name, data, source)
    except Exception as e:
        logger.debug(f"Could not emit event {event_name}: {e}")


def emit_event_sync(
    event_name: str,
    data: dict,
    source: Optional[str] = None,
) -> None:
    """Emit an async plugin event from synchronous code.

    This is a fire-and-forget operation.

    Args:
        event_name: Name of the event
        data: Event data dictionary
        source: Optional source identifier
    """
    try:
        from app.plugins.events import get_event_manager

        manager = get_event_manager()
        manager.emit_sync(event_name, data, source)
    except Exception as e:
        logger.debug(f"Could not emit event {event_name}: {e}")
