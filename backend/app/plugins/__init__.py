"""BaluHost Plugin System.

This module provides a plugin architecture for extending BaluHost with:
- Backend route injection
- Background task registration
- Event-driven hooks
- Frontend UI extensions

Usage:
    from app.plugins.manager import PluginManager

    plugin_manager = PluginManager.get_instance()
    await plugin_manager.load_enabled_plugins(db)
"""
from app.plugins.base import PluginBase, PluginMetadata, PluginUIManifest, BackgroundTaskSpec
from app.plugins.permissions import PluginPermission
from app.plugins.hooks import BaluHostHookSpec, hookimpl
from app.plugins.events import EventManager, get_event_manager
from app.plugins.emit import emit_hook, emit_event, emit_event_sync

__all__ = [
    "PluginBase",
    "PluginMetadata",
    "PluginUIManifest",
    "BackgroundTaskSpec",
    "PluginPermission",
    "BaluHostHookSpec",
    "hookimpl",
    "EventManager",
    "get_event_manager",
    "emit_hook",
    "emit_event",
    "emit_event_sync",
]
