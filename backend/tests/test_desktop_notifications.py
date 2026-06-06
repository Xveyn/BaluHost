"""Tests for desktop disable/enable notifications."""
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

import app.services.notifications.service as _notification_service_mod
from app.services.notifications.events import (
    EventEmitter,
    EVENT_CONFIGS,
    EventType,
    _COOLDOWN_SECONDS,
)


def test_desktop_event_configs_present():
    assert EventType.DESKTOP_DISABLED.value == "lifecycle.desktop_disabled"
    assert EventType.DESKTOP_ENABLED.value == "lifecycle.desktop_enabled"
    for et in (EventType.DESKTOP_DISABLED, EventType.DESKTOP_ENABLED):
        cfg = EVENT_CONFIGS[et]
        assert cfg.category == "lifecycle"
        assert cfg.priority == 1
        assert cfg.notification_type == "info"
        assert "{username}" in cfg.message_template
        assert cfg.action_url == "/admin/system-control?tab=sleep"


def test_desktop_event_cooldowns_present():
    assert _COOLDOWN_SECONDS["lifecycle.desktop_disabled"] == 30
    assert _COOLDOWN_SECONDS["lifecycle.desktop_enabled"] == 30
