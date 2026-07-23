"""Plugin-contributed notification events (Teilprojekt 3/4).

Plugins declare events via ``PluginBase.get_notification_events()``. This
module turns a namespaced public id (``plugin:<name>:<suffix>``) back into a
core ``EventConfig`` so ``EventEmitter.emit()`` can deliver it exactly like a
built-in event, and provides ``emit_plugin_event()`` for a plugin to fire one.

The category is derived from the plugin name here, never taken from the plugin:
it is the delivery routing key (see services/notification_routing), so a
plugin-chosen category would be a reach-widening hole.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

from app.services.notifications.events import (
    EventConfig,
)

logger = logging.getLogger(__name__)

_PREFIX = "plugin:"


def _iter_enabled_plugins() -> Iterator[Tuple[str, object]]:
    """Indirection so tests can inject plugins without the manager singleton."""
    from app.plugins.manager import PluginManager

    return iter(PluginManager.get_instance().iter_enabled_plugins())


@dataclass
class PluginEventEntry:
    config: EventConfig
    cooldown_seconds: int
    default_target: str


def _parse(public_id: str) -> Optional[Tuple[str, str]]:
    """``plugin:<name>:<suffix>`` -> ``(name, suffix)``; None if not that shape."""
    if not public_id.startswith(_PREFIX):
        return None
    rest = public_id[len(_PREFIX) :]
    name, sep, suffix = rest.partition(":")
    if not sep or not name or not suffix:
        return None
    return name, suffix


def lookup_plugin_event(public_id: str) -> Optional[PluginEventEntry]:
    """Resolve a namespaced plugin event id to a deliverable entry, or None."""
    parsed = _parse(public_id)
    if parsed is None:
        return None
    plugin_name, suffix = parsed

    for name, plugin in _iter_enabled_plugins():
        if name != plugin_name:
            continue
        for spec in plugin.get_notification_events():
            if spec.id != suffix:
                continue
            config = EventConfig(
                priority=spec.priority,
                category=plugin_name,  # core-derived, never plugin-chosen
                notification_type=spec.notification_type,
                title_template=spec.title_template,
                message_template=spec.message_template,
                action_url=spec.action_url,
            )
            return PluginEventEntry(
                config=config,
                cooldown_seconds=spec.cooldown_seconds,
                default_target=spec.default_target,
            )
    return None
