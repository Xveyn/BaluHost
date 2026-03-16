"""Tests for services/plugin_service.py — DB CRUD for InstalledPlugin."""

import pytest
from sqlalchemy.orm import Session

from app.models.plugin import InstalledPlugin
from app.services.plugin_service import (
    disable_plugin_record,
    enable_plugin,
    get_enabled_plugin,
    get_installed_plugin,
    rollback_enable,
    uninstall_plugin,
    update_config,
)


def _enable_test_plugin(db: Session, name: str = "test-plugin") -> InstalledPlugin:
    """Helper to create and enable a plugin."""
    return enable_plugin(
        db,
        name=name,
        version="1.0.0",
        display_name="Test Plugin",
        permissions=["read", "write"],
        default_config={"key": "value"},
        installed_by="admin",
    )


class TestGetInstalledPlugin:
    def test_returns_none_when_not_found(self, db_session: Session):
        assert get_installed_plugin(db_session, "nonexistent") is None

    def test_returns_plugin_after_enable(self, db_session: Session):
        _enable_test_plugin(db_session)
        result = get_installed_plugin(db_session, "test-plugin")
        assert result is not None
        assert result.name == "test-plugin"


class TestGetEnabledPlugin:
    def test_returns_none_when_not_found(self, db_session: Session):
        assert get_enabled_plugin(db_session, "nonexistent") is None

    def test_returns_enabled_plugin(self, db_session: Session):
        _enable_test_plugin(db_session)
        result = get_enabled_plugin(db_session, "test-plugin")
        assert result is not None
        assert result.is_enabled is True

    def test_returns_none_when_disabled(self, db_session: Session):
        _enable_test_plugin(db_session)
        disable_plugin_record(db_session, "test-plugin")
        assert get_enabled_plugin(db_session, "test-plugin") is None


class TestEnablePlugin:
    def test_creates_new_record(self, db_session: Session):
        record = _enable_test_plugin(db_session)
        assert record.name == "test-plugin"
        assert record.version == "1.0.0"
        assert record.is_enabled is True
        assert record.granted_permissions == ["read", "write"]
        assert record.config == {"key": "value"}
        assert record.installed_by == "admin"
        assert record.enabled_at is not None

    def test_re_enables_existing_disabled_record(self, db_session: Session):
        _enable_test_plugin(db_session)
        disable_plugin_record(db_session, "test-plugin")

        record = enable_plugin(
            db_session,
            name="test-plugin",
            version="2.0.0",
            display_name="Test Plugin v2",
            permissions=["admin"],
            default_config={},
            installed_by="admin",
        )
        assert record.is_enabled is True
        assert record.granted_permissions == ["admin"]
        assert record.disabled_at is None


class TestDisablePluginRecord:
    def test_disables_existing_plugin(self, db_session: Session):
        _enable_test_plugin(db_session)
        disable_plugin_record(db_session, "test-plugin")

        record = get_installed_plugin(db_session, "test-plugin")
        assert record is not None
        assert record.is_enabled is False
        assert record.disabled_at is not None

    def test_noop_when_not_found(self, db_session: Session):
        # Should not raise
        disable_plugin_record(db_session, "nonexistent")


class TestRollbackEnable:
    def test_sets_enabled_to_false(self, db_session: Session):
        _enable_test_plugin(db_session)
        rollback_enable(db_session, "test-plugin")

        record = get_installed_plugin(db_session, "test-plugin")
        assert record is not None
        assert record.is_enabled is False

    def test_noop_when_not_found(self, db_session: Session):
        rollback_enable(db_session, "nonexistent")


class TestUpdateConfig:
    def test_updates_existing_config(self, db_session: Session):
        _enable_test_plugin(db_session)
        record = update_config(
            db_session,
            name="test-plugin",
            validated_config={"new_key": "new_value"},
        )
        assert record.config == {"new_key": "new_value"}

    def test_creates_new_record_if_not_found(self, db_session: Session):
        record = update_config(
            db_session,
            name="new-plugin",
            validated_config={"a": 1},
            version="0.1.0",
            display_name="New",
            installed_by="admin",
        )
        assert record.name == "new-plugin"
        assert record.is_enabled is False
        assert record.config == {"a": 1}


class TestUninstallPlugin:
    def test_deletes_existing_plugin(self, db_session: Session):
        _enable_test_plugin(db_session)
        assert uninstall_plugin(db_session, "test-plugin") is True
        assert get_installed_plugin(db_session, "test-plugin") is None

    def test_returns_false_when_not_found(self, db_session: Session):
        assert uninstall_plugin(db_session, "nonexistent") is False
