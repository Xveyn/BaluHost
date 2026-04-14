"""Plugin Manager for BaluHost.

Handles plugin discovery, loading, lifecycle management,
and hook dispatching.

Supports two plugin sources:
- **Bundled** plugins shipped in the BaluHost release at
  ``backend/app/plugins/installed/`` — loaded under the
  ``app.plugins.installed.{name}`` module namespace.
- **External** plugins installed via the marketplace into a
  separate directory (``settings.plugins_external_dir``,
  e.g. ``/var/lib/baluhost/plugins/``) — loaded under the
  ``baluhost_plugins.{name}`` namespace and may have their own
  isolated ``site-packages/`` directory that is prepended to
  ``sys.path`` at load time.
"""
import asyncio
import importlib
import importlib.util
import logging
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Set

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.plugins.base import BackgroundTaskSpec, PluginBase, PluginMetadata, PluginUIManifest
from app.plugins.events import EventManager, get_event_manager, start_event_manager, stop_event_manager
from app.plugins.hooks import create_plugin_manager
from app.plugins.manifest import ManifestError, PluginManifest, load_manifest
from app.plugins.permissions import DANGEROUS_PERMISSIONS, PermissionManager


logger = logging.getLogger(__name__)

# Canonical bundled plugins directory — plugins shipped with BaluHost.
BUNDLED_PLUGINS_DIR = Path(__file__).parent / "installed"

# Backward-compat alias for code that still imports PLUGINS_DIR.
PLUGINS_DIR = BUNDLED_PLUGINS_DIR


PluginSource = Literal["bundled", "external"]


@dataclass
class DiscoveredPlugin:
    """A plugin found on disk, with everything we know about it before loading."""

    name: str
    path: Path
    source: PluginSource
    manifest: Optional[PluginManifest]  # None if the plugin has no plugin.json (legacy)


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

    def __init__(
        self,
        plugins_dir: Optional[Path] = None,
        plugins_dirs: Optional[Sequence[Path]] = None,
    ):
        """Construct a PluginManager.

        Args:
            plugins_dir: Legacy single-directory mode. When set (and
                ``plugins_dirs`` is not), only this directory is scanned —
                used by existing tests and by callers that want explicit
                isolation.
            plugins_dirs: New multi-directory mode. Pass an explicit list
                of directories to scan, in order. Plugins discovered in a
                directory whose resolved path equals
                ``BUNDLED_PLUGINS_DIR`` are treated as ``"bundled"``;
                everything else is ``"external"``.

        If neither argument is given, the default is
        ``[BUNDLED_PLUGINS_DIR, settings.plugins_external_dir]``.
        """
        if plugins_dirs is not None:
            dirs = [Path(p) for p in plugins_dirs]
        elif plugins_dir is not None:
            dirs = [Path(plugins_dir)]
        else:
            # Lazy import to avoid pulling settings during early bootstrap.
            from app.core.config import settings
            dirs = [BUNDLED_PLUGINS_DIR]
            ext = settings.plugins_external_dir
            if ext:
                dirs.append(Path(ext))

        self._plugins_dirs: List[Path] = dirs
        self._plugins: Dict[str, PluginBase] = {}
        self._enabled: Set[str] = set()
        self._hook_manager = create_plugin_manager()
        self._event_manager: Optional[EventManager] = None
        self._background_tasks: Dict[str, List[asyncio.Task]] = {}
        self._routers_mounted = False
        self._discovered: Optional[Dict[str, DiscoveredPlugin]] = None

    @classmethod
    def get_instance(
        cls,
        plugins_dir: Optional[Path] = None,
        plugins_dirs: Optional[Sequence[Path]] = None,
    ) -> "PluginManager":
        """Get the singleton PluginManager instance.

        Args mirror ``__init__`` and only take effect on first construction.
        """
        if cls._instance is None:
            cls._instance = cls(plugins_dir=plugins_dir, plugins_dirs=plugins_dirs)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    @property
    def plugins_dir(self) -> Path:
        """Get the *first* configured plugins directory.

        Backward-compat property: pre-multi-dir callers and tests assume
        a single dir. Returns the first entry of ``plugins_dirs``.
        """
        return self._plugins_dirs[0]

    @property
    def plugins_dirs(self) -> List[Path]:
        """Get all configured plugin directories, in scan order."""
        return list(self._plugins_dirs)

    def _classify_source(self, parent_dir: Path) -> PluginSource:
        """Decide if a plugin discovered in ``parent_dir`` is bundled or external."""
        try:
            return "bundled" if parent_dir.resolve() == BUNDLED_PLUGINS_DIR.resolve() else "external"
        except OSError:
            return "external"

    def _scan_directory(self, scan_dir: Path) -> List[DiscoveredPlugin]:
        """Scan a single directory for plugin candidates.

        A directory is considered a plugin if it contains either
        ``plugin.json`` (manifest-first, preferred) or, as a legacy fallback,
        an ``__init__.py``.
        """
        results: List[DiscoveredPlugin] = []
        if not scan_dir.exists():
            logger.debug("Plugins directory does not exist: %s", scan_dir)
            return results

        source = self._classify_source(scan_dir)

        for path in scan_dir.iterdir():
            if not path.is_dir():
                continue
            has_manifest = (path / "plugin.json").exists()
            has_init = (path / "__init__.py").exists()
            if not (has_manifest or has_init):
                continue

            manifest: Optional[PluginManifest] = None
            if has_manifest:
                try:
                    manifest = load_manifest(path)
                except ManifestError as exc:
                    logger.warning(
                        "Skipping plugin %s — invalid plugin.json: %s",
                        path.name,
                        exc,
                    )
                    continue

            results.append(
                DiscoveredPlugin(
                    name=path.name,
                    path=path,
                    source=source,
                    manifest=manifest,
                )
            )
            logger.debug("Discovered plugin: %s (%s)", path.name, source)

        return results

    def discover_plugins(self, force: bool = False) -> List[str]:
        """Discover available plugins across all configured directories.

        Results are cached after the first scan.  Pass ``force=True``
        to rescan (e.g. after installing a new plugin).

        Returns:
            List of discovered plugin names. If a name appears in multiple
            directories, the first one wins (so bundled plugins shadow
            external plugins of the same name).
        """
        if self._discovered is not None and not force:
            return list(self._discovered.keys())

        discovered: Dict[str, DiscoveredPlugin] = {}

        for scan_dir in self._plugins_dirs:
            for found in self._scan_directory(scan_dir):
                if found.name in discovered:
                    logger.warning(
                        "Plugin %s already discovered in %s — ignoring duplicate at %s",
                        found.name,
                        discovered[found.name].path,
                        found.path,
                    )
                    continue
                discovered[found.name] = found

        self._discovered = discovered
        logger.info("Discovered %d plugins", len(discovered))
        return list(discovered.keys())

    def get_discovered(self, name: str) -> Optional[DiscoveredPlugin]:
        """Return discovery info for ``name`` (or None if not discovered)."""
        if self._discovered is None:
            self.discover_plugins()
        return (self._discovered or {}).get(name)

    def _ensure_external_namespace(self) -> None:
        """Make sure ``baluhost_plugins`` is registered as a parent package.

        External plugins live under the ``baluhost_plugins.{name}`` namespace,
        which doesn't physically exist anywhere on disk — we synthesize a
        package entry in ``sys.modules`` once so relative imports inside the
        plugin work.
        """
        if "baluhost_plugins" not in sys.modules:
            pkg = types.ModuleType("baluhost_plugins")
            pkg.__path__ = []  # marks it as a namespace package
            sys.modules["baluhost_plugins"] = pkg

    def _ensure_bundled_namespace(self, scan_dir: Path) -> None:
        """Synthesize ``app.plugins.installed`` for legacy/test scan dirs.

        When a single non-canonical directory is used (e.g. tests passing a
        tmp_path), we still want plugins to load under
        ``app.plugins.installed.{name}`` for relative-import compatibility.
        """
        if "app.plugins.installed" not in sys.modules:
            if "app" not in sys.modules:
                sys.modules["app"] = types.ModuleType("app")
            if "app.plugins" not in sys.modules:
                sys.modules["app.plugins"] = types.ModuleType("app.plugins")
            installed_module = types.ModuleType("app.plugins.installed")
            installed_module.__path__ = [str(scan_dir)]
            sys.modules["app.plugins.installed"] = installed_module

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

        # Resolve which directory this plugin lives in.
        discovered = self.get_discovered(name)
        if discovered is None:
            # Fall back to scanning the first dir directly — this preserves
            # the legacy contract "load_plugin works even if discover_plugins
            # was never called explicitly with a fresh single-dir manager".
            plugin_path = self._plugins_dirs[0] / name
            if not plugin_path.exists():
                raise PluginLoadError(f"Plugin directory not found: {plugin_path}")
            scan_dir = self._plugins_dirs[0]
            source: PluginSource = self._classify_source(scan_dir)
        else:
            plugin_path = discovered.path
            scan_dir = plugin_path.parent
            source = discovered.source

        init_file = plugin_path / "__init__.py"
        if not init_file.exists():
            raise PluginLoadError(f"Plugin __init__.py not found: {init_file}")

        # External plugins may ship isolated Python deps in site-packages/.
        # Prepend it to sys.path *before* importing the plugin module so the
        # plugin's imports resolve against its private deps first.
        site_packages = plugin_path / "site-packages"
        if site_packages.exists() and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
            logger.debug("Added %s to sys.path for plugin %s", site_packages, name)

        try:
            if source == "external":
                self._ensure_external_namespace()
                module_name = f"baluhost_plugins.{name}"
            else:
                self._ensure_bundled_namespace(scan_dir)
                module_name = f"app.plugins.installed.{name}"

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

            # Find the plugin class (skip abstract base classes)
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase
                    and not getattr(attr, "__abstractmethods__", None)
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

            # Validate capability contracts for smart device plugins
            from app.plugins.smart_device.base import SmartDevicePlugin
            if isinstance(plugin, SmartDevicePlugin):
                from app.plugins.smart_device.capabilities import validate_capability_contracts
                contract_errors = validate_capability_contracts(plugin)
                if contract_errors:
                    del self._plugins[name]
                    errors_str = "; ".join(contract_errors)
                    raise PluginLoadError(
                        f"Plugin '{name}' failed capability contract validation: {errors_str}"
                    )

            logger.info(f"Loaded plugin: {meta.display_name} v{meta.version}")

            return plugin

        except Exception as e:
            raise PluginLoadError(f"Failed to load plugin {name}: {e}") from e

    async def enable_plugin(
        self,
        name: str,
        granted_permissions: List[str],
        db: Session,
        start_background_tasks: bool = True,
    ) -> bool:
        """Enable a plugin.

        Args:
            name: Plugin name
            granted_permissions: List of granted permission strings
            db: Database session
            start_background_tasks: Whether to start background tasks (False on secondary workers)

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

            # Register with Pluggy hook manager (skip if already registered)
            try:
                self._hook_manager.register(plugin)
            except ValueError:
                pass  # Already registered from a previous enable cycle

            # Register event handlers
            event_handlers = plugin.get_event_handlers()
            event_manager = get_event_manager()
            for event_name, handlers in event_handlers.items():
                for handler in handlers:
                    event_manager.subscribe(event_name, handler, source=name)

            # Start background tasks
            if start_background_tasks:
                await self._start_background_tasks(name, plugin)
            else:
                logger.debug(f"Skipping background tasks for {name} (secondary worker)")

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

    async def load_enabled_plugins(
        self, db: Session, start_background_tasks: bool = True,
    ) -> None:
        """Load all enabled plugins from database.

        Args:
            db: Database session
            start_background_tasks: Whether to start background tasks (False on secondary workers)
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
                start_background_tasks=start_background_tasks,
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
                        "translations": plugin.get_translations() or None,
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

    def get_required_permissions(self, name: str) -> List[str]:
        """Get required permissions for a loaded plugin.

        Args:
            name: Plugin name

        Returns:
            List of required permission strings, or empty list if unknown
        """
        plugin = self._plugins.get(name)
        if plugin:
            return plugin.metadata.required_permissions
        return []

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
