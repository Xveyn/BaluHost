"""Tests for the plugin system."""
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.plugins.base import (
    BackgroundTaskSpec,
    PluginBase,
    PluginMetadata,
    PluginNavItem,
    PluginUIManifest,
)
from app.plugins.permissions import (
    PermissionManager,
    PluginPermission,
    DANGEROUS_PERMISSIONS,
)
from app.plugins.events import EventManager, Event, get_event_manager
from app.plugins.hooks import BaluHostHookSpec, create_plugin_manager, hookimpl
from app.plugins.manager import PluginManager, PluginLoadError


# =============================================================================
# Test Fixtures
# =============================================================================

class MockPlugin(PluginBase):
    """A mock plugin for testing."""

    def __init__(self, name: str = "mock_plugin"):
        self._name = name
        self._started = False
        self._shutdown = False

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=self._name,
            version="1.0.0",
            display_name="Mock Plugin",
            description="A test plugin",
            author="Test",
            required_permissions=["file:read"],
            category="general",
        )

    def get_router(self) -> Optional[APIRouter]:
        router = APIRouter()

        @router.get("/test")
        async def test_endpoint():
            return {"message": "Hello from plugin"}

        return router

    async def on_startup(self) -> None:
        self._started = True

    async def on_shutdown(self) -> None:
        self._shutdown = True

    def get_ui_manifest(self) -> Optional[PluginUIManifest]:
        return PluginUIManifest(
            enabled=True,
            nav_items=[
                PluginNavItem(
                    path="dashboard",
                    label="Plugin Dashboard",
                    icon="plug",
                    admin_only=False,
                    order=100,
                )
            ],
        )

    @hookimpl
    def on_file_uploaded(self, path: str, user_id: int, size: int, content_type: Optional[str] = None):
        """Mock hook implementation."""
        pass


@pytest.fixture
def mock_plugin():
    """Create a mock plugin instance."""
    return MockPlugin()


@pytest.fixture
def event_manager():
    """Create an event manager for testing."""
    return EventManager()


@pytest.fixture
def permission_manager():
    """Create a permission manager for testing."""
    return PermissionManager()


# =============================================================================
# Permission Tests
# =============================================================================

class TestPermissions:
    """Tests for the permission system."""

    def test_dangerous_permissions_defined(self):
        """Dangerous permissions should be defined."""
        assert len(DANGEROUS_PERMISSIONS) > 0
        assert PluginPermission.SYSTEM_EXECUTE in DANGEROUS_PERMISSIONS
        assert PluginPermission.DB_WRITE in DANGEROUS_PERMISSIONS

    def test_is_dangerous(self):
        """Check if a permission is dangerous."""
        assert PermissionManager.is_dangerous(PluginPermission.SYSTEM_EXECUTE) is True
        assert PermissionManager.is_dangerous(PluginPermission.FILE_READ) is False

    def test_validate_permissions_success(self):
        """Validation should pass when all required permissions are granted."""
        required = ["file:read", "system:info"]
        granted = ["file:read", "system:info", "network:outbound"]
        assert PermissionManager.validate_permissions(required, granted) is True

    def test_validate_permissions_failure(self):
        """Validation should fail when required permissions are missing."""
        required = ["file:read", "system:execute"]
        granted = ["file:read"]
        assert PermissionManager.validate_permissions(required, granted) is False

    def test_get_dangerous_permissions(self):
        """Should filter out dangerous permissions from a list."""
        permissions = ["file:read", "system:execute", "db:write"]
        dangerous = PermissionManager.get_dangerous_permissions(permissions)
        assert "system:execute" in dangerous
        assert "db:write" in dangerous
        assert "file:read" not in dangerous

    def test_get_all_permissions(self):
        """Should return all permissions with metadata."""
        all_perms = PermissionManager.get_all_permissions()
        assert len(all_perms) > 0
        for perm in all_perms:
            assert "name" in perm
            assert "value" in perm
            assert "dangerous" in perm
            assert "description" in perm


# =============================================================================
# Event Manager Tests
# =============================================================================

class TestEventManager:
    """Tests for the async event manager."""

    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self, event_manager):
        """Test subscribing to events and emitting."""
        received_events = []

        async def handler(event: Event):
            received_events.append(event)

        event_manager.subscribe("test_event", handler)

        await event_manager.start()
        try:
            await event_manager.emit("test_event", {"key": "value"})
            # Give time for event processing
            await asyncio.sleep(0.1)
            assert len(received_events) == 1
            assert received_events[0].name == "test_event"
            assert received_events[0].data == {"key": "value"}
        finally:
            await event_manager.stop()

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self, event_manager):
        """Test subscribing to all events with wildcard."""
        received_events = []

        async def handler(event: Event):
            received_events.append(event)

        event_manager.subscribe("*", handler)

        await event_manager.start()
        try:
            await event_manager.emit("event1", {"a": 1})
            await event_manager.emit("event2", {"b": 2})
            await asyncio.sleep(0.1)
            assert len(received_events) == 2
        finally:
            await event_manager.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_manager):
        """Test unsubscribing from events."""
        received_events = []

        async def handler(event: Event):
            received_events.append(event)

        event_manager.subscribe("test", handler)
        event_manager.unsubscribe("test", handler)

        await event_manager.start()
        try:
            await event_manager.emit("test", {})
            await asyncio.sleep(0.1)
            assert len(received_events) == 0
        finally:
            await event_manager.stop()

    def test_get_subscribers_count(self, event_manager):
        """Test getting subscriber count."""
        async def h1(e): pass
        async def h2(e): pass

        assert event_manager.get_subscribers("test") == 0
        event_manager.subscribe("test", h1)
        assert event_manager.get_subscribers("test") == 1
        event_manager.subscribe("test", h2)
        assert event_manager.get_subscribers("test") == 2


# =============================================================================
# Hook System Tests
# =============================================================================

class TestHookSystem:
    """Tests for the Pluggy hook system."""

    def test_create_plugin_manager(self):
        """Test creating a pluggy plugin manager."""
        pm = create_plugin_manager()
        assert pm is not None
        assert hasattr(pm.hook, "on_file_uploaded")
        assert hasattr(pm.hook, "on_user_login")

    def test_register_plugin_with_hooks(self, mock_plugin):
        """Test registering a plugin with hook implementations."""
        pm = create_plugin_manager()
        pm.register(mock_plugin)

        # The hook should be callable
        result = pm.hook.on_file_uploaded(
            path="/test/file.txt",
            user_id=1,
            size=1024,
            content_type="text/plain",
        )
        # Result is a list of return values from all implementations
        assert isinstance(result, list)


# =============================================================================
# Plugin Base Tests
# =============================================================================

class TestPluginBase:
    """Tests for the PluginBase class."""

    def test_metadata(self, mock_plugin):
        """Test plugin metadata."""
        meta = mock_plugin.metadata
        assert meta.name == "mock_plugin"
        assert meta.version == "1.0.0"
        assert "file:read" in meta.required_permissions

    def test_get_router(self, mock_plugin):
        """Test getting plugin router."""
        router = mock_plugin.get_router()
        assert router is not None
        assert len(router.routes) > 0

    def test_ui_manifest(self, mock_plugin):
        """Test getting UI manifest."""
        manifest = mock_plugin.get_ui_manifest()
        assert manifest is not None
        assert manifest.enabled is True
        assert len(manifest.nav_items) == 1

    @pytest.mark.asyncio
    async def test_lifecycle(self, mock_plugin):
        """Test plugin startup and shutdown."""
        assert mock_plugin._started is False
        await mock_plugin.on_startup()
        assert mock_plugin._started is True

        assert mock_plugin._shutdown is False
        await mock_plugin.on_shutdown()
        assert mock_plugin._shutdown is True

    def test_default_config(self, mock_plugin):
        """Test default config."""
        config = mock_plugin.get_default_config()
        assert isinstance(config, dict)

    def test_validate_config(self, mock_plugin):
        """Test config validation."""
        config = {"key": "value"}
        validated = mock_plugin.validate_config(config)
        assert validated == config


# =============================================================================
# Plugin Manager Tests
# =============================================================================

class TestPluginManager:
    """Tests for the PluginManager."""

    def test_singleton(self):
        """Test singleton pattern."""
        PluginManager.reset_instance()
        pm1 = PluginManager.get_instance()
        pm2 = PluginManager.get_instance()
        assert pm1 is pm2
        PluginManager.reset_instance()

    def test_discover_plugins(self, tmp_path):
        """Test plugin discovery."""
        # Create a mock plugin directory
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# test")

        pm = PluginManager(plugins_dir=tmp_path)
        discovered = pm.discover_plugins()
        assert "test_plugin" in discovered

    def test_discover_empty_directory(self, tmp_path):
        """Test discovering plugins in empty directory."""
        pm = PluginManager(plugins_dir=tmp_path)
        discovered = pm.discover_plugins()
        assert discovered == []

    def test_load_plugin_not_found(self, tmp_path):
        """Test loading a plugin that doesn't exist."""
        pm = PluginManager(plugins_dir=tmp_path)
        with pytest.raises(PluginLoadError):
            pm.load_plugin("nonexistent")

    def test_get_ui_manifest_empty(self, tmp_path):
        """Test getting UI manifest with no enabled plugins."""
        pm = PluginManager(plugins_dir=tmp_path)
        manifest = pm.get_ui_manifest()
        assert manifest == {"plugins": []}

    def test_is_enabled(self, tmp_path):
        """Test checking if plugin is enabled."""
        pm = PluginManager(plugins_dir=tmp_path)
        assert pm.is_enabled("test") is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestPluginIntegration:
    """Integration tests for the plugin system."""

    @pytest.mark.asyncio
    async def test_full_plugin_lifecycle(self, mock_plugin, event_manager):
        """Test the full plugin lifecycle with events and hooks."""
        # Start event manager
        await event_manager.start()

        try:
            # Create plugin manager
            pm = create_plugin_manager()
            pm.register(mock_plugin)

            # Start plugin
            await mock_plugin.on_startup()
            assert mock_plugin._started

            # Register event handler
            events_received = []

            async def on_file_event(event):
                events_received.append(event)

            event_manager.subscribe("file:uploaded", on_file_event)

            # Emit hook
            pm.hook.on_file_uploaded(
                path="/test.txt",
                user_id=1,
                size=100,
            )

            # Shutdown
            await mock_plugin.on_shutdown()
            assert mock_plugin._shutdown

        finally:
            await event_manager.stop()
