"""Base classes and interfaces for BaluHost plugins.

Provides the abstract base class that all plugins must extend,
along with supporting data structures.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field


class PluginMetadata(BaseModel):
    """Metadata describing a plugin.

    All plugins must provide this metadata in their manifest.
    """

    name: str = Field(..., description="Unique plugin identifier (snake_case)")
    version: str = Field(..., description="Semantic version (e.g., 1.0.0)")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Brief description of the plugin")
    author: str = Field(..., description="Plugin author name or organization")
    required_permissions: List[str] = Field(
        default_factory=list,
        description="List of required permission strings",
    )
    category: str = Field(
        default="general",
        description="Plugin category (general, monitoring, storage, network, security)",
    )
    homepage: Optional[str] = Field(
        default=None,
        description="URL to plugin homepage or documentation",
    )
    min_baluhost_version: Optional[str] = Field(
        default=None,
        description="Minimum required BaluHost version",
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="List of plugin dependencies (other plugin names)",
    )


class PluginNavItem(BaseModel):
    """Navigation item for plugin UI."""

    path: str = Field(..., description="Route path (relative to /plugins/{name}/)")
    label: str = Field(..., description="Navigation label")
    icon: str = Field(default="plug", description="Lucide icon name")
    admin_only: bool = Field(default=False, description="Require admin role")
    order: int = Field(default=100, description="Sort order in navigation")


class PluginUIManifest(BaseModel):
    """UI manifest for plugin frontend integration."""

    enabled: bool = Field(default=True, description="Whether UI is enabled")
    nav_items: List[PluginNavItem] = Field(
        default_factory=list,
        description="Navigation items to add to sidebar",
    )
    bundle_path: str = Field(
        default="ui/bundle.js",
        description="Path to the JavaScript bundle relative to plugin directory",
    )
    styles_path: Optional[str] = Field(
        default=None,
        description="Path to CSS file relative to plugin directory",
    )
    dashboard_widgets: List[str] = Field(
        default_factory=list,
        description="List of widget component names to add to dashboard",
    )


@dataclass
class BackgroundTaskSpec:
    """Specification for a plugin background task."""

    name: str
    func: Callable[[], Coroutine[Any, Any, None]]
    interval_seconds: float
    run_on_startup: bool = True


class PluginBase(ABC):
    """Abstract base class for all BaluHost plugins.

    Plugins must extend this class and implement the required methods.
    The plugin lifecycle is:
    1. Discovery: Plugin directory is scanned
    2. Registration: Plugin instance is created
    3. Permission check: Required permissions are validated
    4. Activation: on_startup() is called
    5. Running: Routes are mounted, tasks are scheduled
    6. Deactivation: on_shutdown() is called
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata.

        Returns:
            PluginMetadata instance describing this plugin
        """
        pass

    def get_router(self) -> Optional[APIRouter]:
        """Get the FastAPI router for this plugin.

        Override this method to provide API endpoints.
        Routes will be mounted at /api/plugins/{plugin_name}/

        Returns:
            APIRouter instance or None if no routes
        """
        return None

    async def on_startup(self) -> None:
        """Called when the plugin is activated.

        Override to perform initialization tasks like:
        - Database table creation
        - Cache warming
        - Resource allocation
        """
        pass

    async def on_shutdown(self) -> None:
        """Called when the plugin is deactivated.

        Override to perform cleanup tasks like:
        - Closing connections
        - Saving state
        - Releasing resources
        """
        pass

    def get_background_tasks(self) -> List[BackgroundTaskSpec]:
        """Get background tasks to register.

        Override to provide periodic tasks.

        Returns:
            List of BackgroundTaskSpec instances
        """
        return []

    def get_event_handlers(self) -> Dict[str, List[Callable]]:
        """Get event handlers to register.

        Override to subscribe to async events.

        Returns:
            Dict mapping event names to handler functions
        """
        return {}

    def get_ui_manifest(self) -> Optional[PluginUIManifest]:
        """Get the UI manifest for frontend integration.

        Override to provide navigation items and UI components.

        Returns:
            PluginUIManifest instance or None if no UI
        """
        return None

    def get_config_schema(self) -> Optional[type]:
        """Get the Pydantic model for plugin configuration.

        Override to provide a configuration schema.
        The model will be used to validate config from the database.

        Returns:
            Pydantic BaseModel subclass or None
        """
        return None

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values.

        Returns:
            Dictionary of default configuration
        """
        return {}

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and process configuration.

        Override to perform custom validation.

        Args:
            config: Configuration dictionary

        Returns:
            Validated configuration dictionary

        Raises:
            ValueError: If configuration is invalid
        """
        schema = self.get_config_schema()
        if schema:
            # Validate using Pydantic model
            validated = schema(**config)
            return validated.model_dump()
        return config

    def __repr__(self) -> str:
        meta = self.metadata
        return f"<Plugin({meta.name} v{meta.version})>"
