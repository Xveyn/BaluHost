"""Plugin notification events: the extension point (Teilprojekt 3/4)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.plugins.base import (
    PluginBase,
    PluginEventSpec,
    PluginMetadata,
)


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
