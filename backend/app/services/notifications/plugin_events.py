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
    _COOLDOWN_SECONDS,
    _check_cooldown,
    _set_cooldown,
    EventConfig,
    get_event_emitter,
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


async def emit_plugin_event(
    plugin_name: str, event_id: str, entity_id: str = "", **kwargs
) -> None:
    """Fire a plugin-declared notification event.

    Namespaces the id, resolves it against the registry, enforces the declared
    cooldown (the async emit() path carries none - only emit_sync does), and
    delivers to the declared target. Never raises: a plugin firing an event
    must not take down its caller.
    """
    public_id = f"{_PREFIX}{plugin_name}:{event_id}"
    entry = lookup_plugin_event(public_id)
    if entry is None:
        logger.warning("emit_plugin_event: unknown event %s", public_id)
        return

    # _check_cooldown/_set_cooldown read the window from _COOLDOWN_SECONDS -
    # a plugin id is never in that dict, so without seeding it here both calls
    # would be silent no-ops and the declared cooldown would be dead. Seeding
    # reuses the core machinery (cache, monotonic clock, entity keying) instead
    # of duplicating it.
    if entry.cooldown_seconds > 0:
        _COOLDOWN_SECONDS[public_id] = entry.cooldown_seconds
        if _check_cooldown(public_id, entity_id):
            return

    emitter = get_event_emitter()
    try:
        if entry.default_target == "all_users":
            # emit_for_all_users needs a session to enumerate users; the async
            # emit() each user triggers opens its own via the factory. Reaching
            # the factory here is fine - same package as EventEmitter.
            db = emitter._db_session_factory()
            try:
                await emitter.emit_for_all_users(public_id, db, **kwargs)
            finally:
                db.close()
        else:
            await emitter.emit_for_admins(public_id, **kwargs)
    except Exception:  # broad on purpose: an emit failure must not crash the poller
        logger.warning("emit_plugin_event %s failed", public_id, exc_info=True)
        return

    _set_cooldown(public_id, entity_id)
