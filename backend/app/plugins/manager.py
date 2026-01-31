"""Plugin Manager for BaluHost.

Handles plugin discovery, loading, lifecycle management,
and hook dispatching.
"""
import asyncio
import importlib
import importlib.util
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.plugins.base import BackgroundTaskSpec, PluginBase, PluginMetadata, PluginUIManifest
from app.plugins.hooks import create_plugin_manager
from app.plugins.events import EventManager, get_event_manager, start_event_manager, stop_event_manager
from app.plugins.permissions import PermissionManager, DANGEROUS_PERMISSIONS


logger = logging.getLogger(__name__)

# Default plugins directory
PLUGINS_DIR = Path(__file__).parent / "installed"


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""

    pass


class PluginPermissionError(Exception):
    """Raised when a plugin lacks required permissions."""

    pass


class PluginManager:
    """Central manager for all plugins.

    Provides:
    - Plugin discovery and loading
    - Lifecycle management (startup/shutdown)
    - Route mounting
    - Background task scheduling
    - Hook dispatching via Pluggy
    - Event management
    """

    _instance: Optional["PluginManager"] = None

    def __init__(self, plugins_dir: Optional[Path] = None):
        self._plugins_dir = plugins_dir or PLUGINS_DIR
        self._plugins: Dict[str, PluginBase] = {}
        self._enabled: Set[str] = set()
        self._hook_manager = create_plugin_manager()
        self._event_manager: Optional[EventManager] = None
        self._background_tasks: Dict[str, List[asyncio.Task]] = {}
        self._routers_mounted = False

    @classmethod
    def get_instance(cls, plugins_dir: Optional[Path] = None) -> "PluginManager":
        """Get the singleton PluginManager instance.

        Args:
            plugins_dir: Optional custom plugins directory

        Returns:
            The PluginManager singleton
        """
        if cls._instance is None:
            cls._instance = cls(plugins_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    @property
    def plugins_dir(self) -> Path:
        """Get the plugins directory."""
        return self._plugins_dir

    def discover_plugins(self) -> List[str]:
        """Discover available plugins in the plugins directory.

        Scans for directories containing __init__.py files.

        Returns:
            List of discovered plugin names
        """
        discovered = []

        if not self._plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {self._plugins_dir}")
            return discovered

        for path in self._plugins_dir.iterdir():
            if path.is_dir() and (path / "__init__.py").exists():
                discovered.append(path.name)
                logger.debug(f"Discovered plugin: {path.name}")

        logger.info(f"Discovered {len(discovered)} plugins")
        return discovered

    def load_plugin(self, name: str) -> PluginBase:
        """Load a plugin by name.

        Args:
            name: Plugin directory name

        Returns:
            Loaded PluginBase instance

        Raises:
            PluginLoadError: If plugin cannot be loaded
        """
        if name in self._plugins:
            return self._plugins[name]

        plugin_path = self._plugins_dir / name
        if not plugin_path.exists():
            raise PluginLoadError(f"Plugin directory not found: {plugin_path}")

        init_file = plugin_path / "__init__.py"
        if not init_file.exists():
            raise PluginLoadError(f"Plugin __init__.py not found: {init_file}")

        try:
            # Load the plugin module
            # Use full module path to enable relative imports within the plugin
            import sys
            module_name = f"app.plugins.installed.{name}"

            # Ensure parent packages are in sys.modules for relative imports
            if "app.plugins.installed" not in sys.modules:
                import types
                # Create parent package entries if they don't exist
                if "app" not in sys.modules:
                    sys.modules["app"] = types.ModuleType("app")
                if "app.plugins" not in sys.modules:
                    sys.modules["app.plugins"] = types.ModuleType("app.plugins")
                installed_module = types.ModuleType("app.plugins.installed")
                installed_module.__path__ = [str(self._plugins_dir)]
                sys.modules["app.plugins.installed"] = installed_module

            spec = importlib.util.spec_from_file_location(
                module_name,
                init_file,
                submodule_search_locations=[str(plugin_path)],
            )
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Cannot create module spec for {name}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module  # Register before exec for relative imports
            spec.loader.exec_module(module)

            # Find the plugin class
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase
                ):
                    plugin_class = attr
                    break

            if plugin_class is None:
                raise PluginLoadError(
                    f"No PluginBase subclass found in {name}"
                )

            # Create plugin instance
            plugin = plugin_class()

            # Validate metadata
            meta = plugin.metadata
            if meta.name != name:
                logger.warning(
                    f"Plugin name mismatch: directory={name}, metadata={meta.name}"
                )

            self._plugins[name] = plugin
            logger.info(f"Loaded plugin: {meta.display_name} v{meta.version}")

            return plugin

        except Exception as e:
            raise PluginLoadError(f"Failed to load plugin {name}: {e}") from e

    async def enable_plugin(
        self,
        name: str,
        granted_permissions: List[str],
        db: Session,
    ) -> bool:
        """Enable a plugin.

        Args:
            name: Plugin name
            granted_permissions: List of granted permission strings
            db: Database session

        Returns:
            True if plugin was enabled successfully
        """
        if name not in self._plugins:
            try:
                self.load_plugin(name)
            except PluginLoadError as e:
                logger.error(f"Cannot enable plugin {name}: {e}")
                return False

        plugin = self._plugins[name]
        meta = plugin.metadata

        # Check permissions
        if not PermissionManager.validate_permissions(
            meta.required_permissions, granted_permissions
        ):
            missing = set(meta.required_permissions) - set(granted_permissions)
            logger.warning(
                f"Plugin {name} missing permissions: {missing}"
            )
            return False

        try:
            # Call startup hook
            await plugin.on_startup()

            # Register with Pluggy hook manager
            self._hook_manager.register(plugin)

            # Register event handlers
            event_handlers = plugin.get_event_handlers()
            event_manager = get_event_manager()
            for event_name, handlers in event_handlers.items():
                for handler in handlers:
                    event_manager.subscribe(event_name, handler, source=name)

            # Start background tasks
            await self._start_background_tasks(name, plugin)

            self._enabled.add(name)
            logger.info(f"Enabled plugin: {name}")
            return True

        except Exception as e:
            logger.exception(f"Failed to enable plugin {name}: {e}")
            return False

    async def disable_plugin(self, name: str) -> bool:
        """Disable a plugin.

        Args:
            name: Plugin name

        Returns:
            True if plugin was disabled successfully
        """
        if name not in self._enabled:
            return True

        plugin = self._plugins.get(name)
        if not plugin:
            self._enabled.discard(name)
            return True

        try:
            # Stop background tasks
            await self._stop_background_tasks(name)

            # Unregister event handlers
            event_manager = get_event_manager()
            event_manager.unsubscribe_all(name)

            # Unregister from Pluggy
            try:
                self._hook_manager.unregister(plugin)
            except ValueError:
                pass  # Already unregistered

            # Call shutdown hook
            await plugin.on_shutdown()

            self._enabled.discard(name)
            logger.info(f"Disabled plugin: {name}")
            return True

        except Exception as e:
            logger.exception(f"Failed to disable plugin {name}: {e}")
            return False

    async def _start_background_tasks(
        self, name: str, plugin: PluginBase
    ) -> None:
        """Start background tasks for a plugin."""
        task_specs = plugin.get_background_tasks()
        if not task_specs:
            return

        tasks = []
        for spec in task_specs:
            task = asyncio.create_task(
                self._run_periodic_task(name, spec),
                name=f"plugin_{name}_{spec.name}",
            )
            tasks.append(task)
            logger.debug(f"Started background task: {name}/{spec.name}")

        self._background_tasks[name] = tasks

    async def _run_periodic_task(
        self, plugin_name: str, spec: BackgroundTaskSpec
    ) -> None:
        """Run a periodic background task."""
        if spec.run_on_startup:
            try:
                await spec.func()
            except Exception as e:
                logger.exception(
                    f"Error in plugin task {plugin_name}/{spec.name}: {e}"
                )

        while plugin_name in self._enabled:
            await asyncio.sleep(spec.interval_seconds)
            try:
                await spec.func()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(
                    f"Error in plugin task {plugin_name}/{spec.name}: {e}"
                )

    async def _stop_background_tasks(self, name: str) -> None:
        """Stop background tasks for a plugin."""
        tasks = self._background_tasks.pop(name, [])
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if tasks:
            logger.debug(f"Stopped {len(tasks)} background tasks for {name}")

    async def load_enabled_plugins(self, db: Session) -> None:
        """Load all enabled plugins from database.

        Args:
            db: Database session
        """
        from app.models.plugin import InstalledPlugin

        # Start event manager
        self._event_manager = get_event_manager()
        await start_event_manager()

        # Discover available plugins
        available = self.discover_plugins()

        # Load enabled plugins from database
        try:
            enabled_records = (
                db.query(InstalledPlugin)
                .filter(InstalledPlugin.is_enabled == True)
                .all()
            )
        except Exception as e:
            logger.warning(f"Could not load plugins from database: {e}")
            return

        for record in enabled_records:
            if record.name not in available:
                logger.warning(
                    f"Enabled plugin {record.name} not found in plugins directory"
                )
                continue

            await self.enable_plugin(
                record.name,
                record.granted_permissions or [],
                db,
            )

        logger.info(f"Loaded {len(self._enabled)} enabled plugins")

    async def shutdown_all(self) -> None:
        """Shutdown all enabled plugins."""
        for name in list(self._enabled):
            await self.disable_plugin(name)

        # Stop event manager
        await stop_event_manager()

        logger.info("All plugins shut down")

    def emit_hook(self, hook_name: str, **kwargs: Any) -> List[Any]:
        """Emit a Pluggy hook to all registered plugins.

        Args:
            hook_name: Name of the hook method (e.g., "on_file_uploaded")
            **kwargs: Arguments to pass to the hook

        Returns:
            List of results from all hook implementations
        """
        hook = getattr(self._hook_manager.hook, hook_name, None)
        if hook is None:
            logger.warning(f"Unknown hook: {hook_name}")
            return []

        try:
            return hook(**kwargs)
        except Exception as e:
            logger.exception(f"Error emitting hook {hook_name}: {e}")
            return []

    def get_router(self) -> APIRouter:
        """Get a combined router for all enabled plugins.

        Returns:
            APIRouter with all plugin routes mounted
        """
        router = APIRouter(prefix="/plugins", tags=["plugins"])

        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin:
                plugin_router = plugin.get_router()
                if plugin_router:
                    router.include_router(
                        plugin_router,
                        prefix=f"/{name}",
                        tags=[f"plugin:{name}"],
                    )

        return router

    def get_ui_manifest(self) -> Dict[str, Any]:
        """Get combined UI manifest for all enabled plugins.

        Returns:
            Dictionary with plugin UI information
        """
        manifest = {
            "plugins": [],
        }

        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin:
                ui_manifest = plugin.get_ui_manifest()
                if ui_manifest and ui_manifest.enabled:
                    manifest["plugins"].append({
                        "name": name,
                        "display_name": plugin.metadata.display_name,
                        "nav_items": [
                            item.model_dump() for item in ui_manifest.nav_items
                        ],
                        "bundle_path": ui_manifest.bundle_path,
                        "styles_path": ui_manifest.styles_path,
                        "dashboard_widgets": ui_manifest.dashboard_widgets,
                    })

        return manifest

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """Get a loaded plugin by name.

        Args:
            name: Plugin name

        Returns:
            PluginBase instance or None
        """
        return self._plugins.get(name)

    def is_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled.

        Args:
            name: Plugin name

        Returns:
            True if plugin is enabled
        """
        return name in self._enabled

    def get_all_plugins(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all discovered plugins.

        Returns:
            Dictionary mapping plugin names to their info
        """
        discovered = self.discover_plugins()
        result = {}

        for name in discovered:
            try:
                if name not in self._plugins:
                    self.load_plugin(name)

                plugin = self._plugins[name]
                meta = plugin.metadata

                result[name] = {
                    "name": meta.name,
                    "version": meta.version,
                    "display_name": meta.display_name,
                    "description": meta.description,
                    "author": meta.author,
                    "category": meta.category,
                    "required_permissions": meta.required_permissions,
                    "is_enabled": name in self._enabled,
                    "has_ui": plugin.get_ui_manifest() is not None,
                    "has_routes": plugin.get_router() is not None,
                    "dangerous_permissions": PermissionManager.get_dangerous_permissions(
                        meta.required_permissions
                    ),
                }
            except PluginLoadError as e:
                result[name] = {
                    "name": name,
                    "error": str(e),
                    "is_enabled": False,
                }

        return result
