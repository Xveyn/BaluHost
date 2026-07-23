"""Plugin notification events: the extension point (subproject 3 of 4)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.plugins.base import (
    PluginBase,
    PluginEventSpec,
    PluginMetadata,
)


@pytest.fixture(autouse=True)
def _clear_cooldown():
    """Cooldown state is module state and would leak across tests.

    Clears the emit-timestamp cache AND the plugin: keys that
    emit_plugin_event seeds into _COOLDOWN_SECONDS (mutation, not rebinding -
    plugin_events imported the same dict object).
    """
    from app.services.notifications import events as ev

    def _reset():
        ev._cooldown_cache.clear()
        for key in [k for k in ev._COOLDOWN_SECONDS if k.startswith("plugin:")]:
            del ev._COOLDOWN_SECONDS[key]

    _reset()
    yield
    _reset()


class TestPluginEventSpec:
    def test_minimal_spec(self):
        spec = PluginEventSpec(
            id="session_started",
            title_template="Started: {game}",
            message_template="Game {game} started.",
        )
        assert spec.notification_type == "info"
        assert spec.priority == 0
        assert spec.cooldown_seconds == 0
        assert spec.default_target == "admins"

    @pytest.mark.parametrize("bad_id", ["Session", "session-started", "session.started", "../x", "", "a b"])
    def test_rejects_ids_outside_the_namespace(self, bad_id):
        with pytest.raises(ValidationError):
            PluginEventSpec(id=bad_id, title_template="t", message_template="m")

    def test_priority_is_bounded(self):
        with pytest.raises(ValidationError):
            PluginEventSpec(id="x", title_template="t", message_template="m", priority=4)

    def test_has_no_category_field(self):
        """The category is the routing key - the core sets it to the plugin
        name, a plugin must not choose it (a plugin declaring category='backup'
        would reach every backup-routed user)."""
        assert "category" not in PluginEventSpec.model_fields


class _BarePlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bare", display_name="Bare", version="1.0.0",
            description="", author="test",
        )


class TestPluginBaseDefault:
    def test_no_events_by_default(self):
        assert _BarePlugin().get_notification_events() == []


from unittest.mock import MagicMock, patch


def _plugin_with_events(*specs):
    plugin = MagicMock()
    plugin.get_notification_events.return_value = list(specs)
    return plugin


class TestRegistryLookup:
    def _spec(self, suffix="session_started"):
        return PluginEventSpec(
            id=suffix,
            notification_type="info",
            priority=1,
            title_template="Started: {game}",
            message_template="Game {game} started.",
            action_url="/plugins",
            cooldown_seconds=60,
            default_target="admins",
        )

    def test_resolves_a_namespaced_id_to_an_entry(self):
        from app.services.notifications.plugin_events import lookup_plugin_event

        plugin = _plugin_with_events(self._spec())
        with patch(
            "app.services.notifications.plugin_events._iter_enabled_plugins",
            return_value=[("steam_gaming", plugin)],
        ):
            entry = lookup_plugin_event("plugin:steam_gaming:session_started")

        assert entry is not None
        assert entry.config.category == "steam_gaming"       # core-derived
        assert entry.config.priority == 1
        assert entry.config.notification_type == "info"
        assert entry.config.title_template == "Started: {game}"
        assert entry.cooldown_seconds == 60
        assert entry.default_target == "admins"

    def test_unknown_plugin_is_none(self):
        from app.services.notifications.plugin_events import lookup_plugin_event

        with patch(
            "app.services.notifications.plugin_events._iter_enabled_plugins",
            return_value=[],
        ):
            assert lookup_plugin_event("plugin:nope:session_started") is None

    def test_unknown_suffix_is_none(self):
        from app.services.notifications.plugin_events import lookup_plugin_event

        plugin = _plugin_with_events(self._spec("session_started"))
        with patch(
            "app.services.notifications.plugin_events._iter_enabled_plugins",
            return_value=[("steam_gaming", plugin)],
        ):
            assert lookup_plugin_event("plugin:steam_gaming:other") is None

    def test_non_plugin_id_is_none(self):
        """A core id like 'raid.degraded' must not be looked up here."""
        from app.services.notifications.plugin_events import lookup_plugin_event

        assert lookup_plugin_event("raid.degraded") is None
        assert lookup_plugin_event("plugin:only_two") is None


from unittest.mock import AsyncMock


class TestEmitFallback:
    async def test_emit_uses_the_registry_when_the_id_is_not_a_core_event(self):
        """emit() already does EVENT_CONFIGS.get(); the plugin path is the
        registry fallback. Persisted notification carries the derived category."""
        from app.services.notifications.events import EventEmitter
        from app.plugins.base import PluginEventSpec
        from app.services.notifications import plugin_events

        spec = PluginEventSpec(
            id="session_started", priority=1,
            title_template="Started: {game}",
            message_template="Game {game} started.",
        )
        plugin = _plugin_with_events(spec)

        emitter = EventEmitter()
        created = {}

        class _Svc:
            async def create(self, **kw):
                created.update(kw)

        emitter.set_db_session_factory(lambda: MagicMock(close=lambda: None))

        with patch.object(plugin_events, "_iter_enabled_plugins",
                          return_value=[("steam_gaming", plugin)]), \
             patch("app.services.notifications.service.get_notification_service",
                   return_value=_Svc()):
            await emitter.emit("plugin:steam_gaming:session_started", game="Metro")

        assert created["category"] == "steam_gaming"
        assert created["title"] == "Started: Metro"
        assert created["priority"] == 1

    async def test_core_event_still_uses_event_configs(self):
        """Regression: the open path must not change built-in delivery."""
        from app.services.notifications.events import EventEmitter, EVENT_CONFIGS

        emitter = EventEmitter()
        created = {}

        class _Svc:
            async def create(self, **kw):
                created.update(kw)

        emitter.set_db_session_factory(lambda: MagicMock(close=lambda: None))
        with patch("app.services.notifications.service.get_notification_service",
                   return_value=_Svc()):
            await emitter.emit("raid.degraded", array_name="md0", details="")

        assert created["category"] == "raid"   # from EVENT_CONFIGS, not the registry


class TestEmitPluginEvent:
    def _entry(self, target="admins", cooldown=60):
        from app.services.notifications.plugin_events import PluginEventEntry
        from app.services.notifications.events import EventConfig
        return PluginEventEntry(
            config=EventConfig(priority=0, category="steam_gaming",
                               notification_type="info",
                               title_template="Started: {game}",
                               message_template="m", action_url=None),
            cooldown_seconds=cooldown, default_target=target,
        )

    async def test_admins_target_calls_emit_for_admins_with_namespaced_id(self):
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=self._entry()), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", game="Metro")

        emitter.emit_for_admins.assert_awaited_once()
        args, kwargs = emitter.emit_for_admins.await_args
        assert args[0] == "plugin:steam_gaming:session_started"
        assert kwargs["game"] == "Metro"

    async def test_unknown_event_is_a_warning_not_a_crash(self):
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=None), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "nope")

        emitter.emit_for_admins.assert_not_awaited()

    async def test_the_helper_enforces_the_cooldown(self):
        """The async emit path has no cooldown machinery (only emit_sync does);
        the helper must enforce it itself, or a declared cooldown is dead."""
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=self._entry(cooldown=60)), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="1449560", game="Metro")
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="1449560", game="Metro")

        assert emitter.emit_for_admins.await_count == 1

    async def test_different_entities_are_not_cooled_down_together(self):
        from app.services.notifications import plugin_events

        emitter = MagicMock()
        emitter.emit_for_admins = AsyncMock()
        with patch.object(plugin_events, "lookup_plugin_event", return_value=self._entry(cooldown=60)), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="1", game="A")
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", entity_id="2", game="B")

        assert emitter.emit_for_admins.await_count == 2

    async def test_all_users_target_uses_the_session_factory_and_emit_for_all_users(self):
        """The all_users branch (opens a session, calls emit_for_all_users,
        closes in finally) has no consumer today - the only shipped plugin
        uses admins. Unexercised, a broken factory call here would only
        surface the first time a plugin declares all_users."""
        from app.services.notifications import plugin_events

        session = MagicMock()
        emitter = MagicMock()
        emitter.emit_for_all_users = AsyncMock()
        emitter._db_session_factory = MagicMock(return_value=session)

        with patch.object(plugin_events, "lookup_plugin_event",
                           return_value=self._entry(target="all_users", cooldown=0)), \
             patch.object(plugin_events, "get_event_emitter", return_value=emitter):
            await plugin_events.emit_plugin_event("steam_gaming", "session_started", game="Metro")

        emitter._db_session_factory.assert_called_once()
        emitter.emit_for_all_users.assert_awaited_once()
        args, kwargs = emitter.emit_for_all_users.await_args
        assert args[0] == "plugin:steam_gaming:session_started"
        assert args[1] is session
        assert kwargs["game"] == "Metro"
        session.close.assert_called_once()


class TestEmitPluginEventIntegration:
    """Drives the FULL compose: emit_plugin_event -> namespacing ->
    lookup_plugin_event -> a REAL EventEmitter.emit() -> a captured
    notification service. The other tests in this file exercise the two
    halves separately (registry+real-emitter-vs-mocked-service, and
    emit_plugin_event+cooldown-vs-mocked-emitter); neither would catch a
    namespacing mismatch between what emit_plugin_event builds
    (``plugin:<name>:<suffix>``) and what lookup_plugin_event parses - that
    would pass CI while the feature is silently dead in production."""

    async def test_emit_plugin_event_through_the_real_emitter_to_a_captured_service(self):
        from app.services.notifications.events import EventEmitter
        from app.services.notifications import plugin_events
        from app.plugins.base import PluginEventSpec

        spec = PluginEventSpec(
            id="session_started",
            notification_type="info",
            priority=1,
            title_template="Started: {game}",
            message_template="Game {game} started.",
            cooldown_seconds=60,
            default_target="admins",
        )
        plugin = _plugin_with_events(spec)

        real_emitter = EventEmitter()
        real_emitter.set_db_session_factory(lambda: MagicMock(close=lambda: None))

        created = {}

        class _Svc:
            async def create(self, **kw):
                created.update(kw)

        with patch.object(plugin_events, "get_event_emitter", return_value=real_emitter), \
             patch.object(plugin_events, "_iter_enabled_plugins",
                          return_value=[("steam_gaming", plugin)]), \
             patch("app.services.notifications.service.get_notification_service",
                   return_value=_Svc()):
            await plugin_events.emit_plugin_event(
                "steam_gaming", "session_started", entity_id="1449560", game="Metro"
            )

        assert created["category"] == "steam_gaming"       # core-derived
        assert created["title"] == "Started: Metro"
        assert created["user_id"] is None                  # admins path
        assert created["priority"] == 1
