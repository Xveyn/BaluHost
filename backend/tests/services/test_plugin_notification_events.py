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
