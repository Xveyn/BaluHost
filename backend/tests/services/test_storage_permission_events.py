"""Tests for STORAGE_PERMISSION_ERROR event type and helpers."""

import time as _time
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User
from app.services.notifications.events import (
    EventType,
    EventConfig,
    EVENT_CONFIGS,
    EventEmitter,
    _cooldown_cache,
    _COOLDOWN_SECONDS,
    emit_storage_permission_error_sync,
)


class TestStoragePermissionEventType:
    """Verify the new event type is correctly defined."""

    def test_event_type_value(self):
        assert EventType.STORAGE_PERMISSION_ERROR == "system.storage_permission"

    def test_event_config_exists(self):
        config = EVENT_CONFIGS.get(EventType.STORAGE_PERMISSION_ERROR)
        assert config is not None

    def test_event_config_fields(self):
        config = EVENT_CONFIGS[EventType.STORAGE_PERMISSION_ERROR]
        assert config.priority == 2
        assert config.category == "system"
        assert config.notification_type == "warning"
        assert config.action_url == "/files"

    def test_title_template_formats(self):
        config = EVENT_CONFIGS[EventType.STORAGE_PERMISSION_ERROR]
        title = config.title_template.format(operation="upload")
        assert "upload" in title

    def test_message_template_formats(self):
        config = EVENT_CONFIGS[EventType.STORAGE_PERMISSION_ERROR]
        msg = config.message_template.format(
            operation="upload",
            path="Sven/test.txt",
            username="testuser",
        )
        assert "upload" in msg
        assert "Sven/test.txt" in msg
        assert "testuser" in msg

    def test_cooldown_configured(self):
        assert "system.storage_permission" in _COOLDOWN_SECONDS
        assert _COOLDOWN_SECONDS["system.storage_permission"] == 300


class TestConvenienceFunction:
    """Verify the sync convenience function."""

    @pytest.fixture(autouse=True)
    def _clear_cooldown(self):
        _cooldown_cache.clear()
        yield
        _cooldown_cache.clear()

    def test_emit_storage_permission_error_sync_calls_emitter(self):
        with patch("app.services.notifications.events.get_event_emitter") as mock_get:
            mock_emitter = MagicMock()
            mock_get.return_value = mock_emitter

            emit_storage_permission_error_sync(
                operation="delete",
                path="Sven/file.txt",
                username="testuser",
            )

            mock_emitter.emit_for_admins_sync.assert_called_once_with(
                EventType.STORAGE_PERMISSION_ERROR,
                cooldown_entity="Sven/file.txt",
                operation="delete",
                path="Sven/file.txt",
                username="testuser",
            )
