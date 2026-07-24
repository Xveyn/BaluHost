"""Base classes and interfaces for BaluHost plugins.

Provides the abstract base class that all plugins must extend,
along with supporting data structures.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, List, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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


class PluginMenuItem(BaseModel):
    """An action a plugin contributes to the system (power) menu.

    Declaration only: the plugin says what it offers, the core decides who may
    run it. There is deliberately no ``admin_only`` field (unlike
    PluginNavItem) - a menu action executes something, so widening its
    audience must not be the plugin's call.
    """

    id: str = Field(
        pattern=r"^[a-z0-9_]+$",
        description="Plugin-local action id, e.g. 'gaming_mode'",
    )
    icon: str = Field(description="lucide icon name, e.g. 'Gamepad2'")
    label_key: str = Field(description="Key into get_translations() for the label")
    label_text: str = Field(description="Literal fallback for the label")
    description_key: Optional[str] = Field(
        default=None, description="Key into get_translations() for the sub-label"
    )
    description_text: Optional[str] = Field(
        default=None, description="Literal fallback for the sub-label"
    )
    tone: Literal["neutral", "info", "success", "warning", "danger"] = "neutral"
    order: int = Field(default=100, description="Sort order within the plugin block")


class MenuActionResult(BaseModel):
    """Outcome of a menu action, rendered as a toast by the frontend.

    ``message_key`` is resolved client-side against the plugin's translations
    (same mechanic as pill labels) - the backend never picks a language.
    """

    ok: bool
    message_key: Optional[str] = None
    message_text: str = Field(description="Literal fallback, always set")


class PluginUIManifest(BaseModel):
    """UI manifest for plugin frontend integration."""

    enabled: bool = Field(default=True, description="Whether UI is enabled")
    nav_items: List[PluginNavItem] = Field(
        default_factory=list,
        description="Navigation items to add to sidebar",
    )
    menu_items: List["PluginMenuItem"] = Field(
        default_factory=list,
        description="Actions to add to the system menu",
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


PanelType = Literal["gauge", "stat", "status", "chart"]


class DashboardPanelSpec(BaseModel):
    """Specification for a plugin's Dashboard panel.

    ``admin_only`` is enforced by the core - in the REST route and in the
    WebSocket bridge - not by the plugin, so no plugin can get its own gate
    wrong. Same pattern as PluginNavItem.admin_only. (PluginMenuItem
    deliberately has no such field: an action executes something, a panel
    displays something.)
    """

    panel_type: PanelType = Field(
        ...,
        description="Panel renderer type",
    )
    title: str = Field(..., description="Panel title, e.g. 'Power Monitoring'")
    icon: str = Field(default="plug", description="Lucide icon name")
    accent: str = Field(
        default="from-sky-500 to-indigo-500",
        description="Tailwind gradient classes for icon background",
    )
    admin_only: bool = Field(
        default=False,
        description="Only serve this panel to privileged users",
    )


class StatusPillSpec(BaseModel):
    """A status-strip pill contributed by a plugin.

    The public pill id is namespaced by the core as
    ``plugin:<plugin_name>:<id>`` — the plugin only picks the suffix.
    """

    id: str = Field(
        pattern=r"^[a-z0-9_]+$",
        description="Plugin-local suffix, e.g. 'session'",
    )
    icon: str = Field(description="lucide icon name, e.g. 'Gamepad2'")
    href: str = Field(description="Click-through target")
    name_key: str = Field(description="Key into get_translations() for the catalog name")
    name_text: str = Field(description="Literal fallback for the catalog name")
    default_visibility: Literal["admin", "all"] = "admin"
    visibility_locked: bool = False
    silent_when_ok: bool = True


class PluginEventSpec(BaseModel):
    """A notification event a plugin contributes.

    The public event id is namespaced by the core as
    ``plugin:<plugin_name>:<id>`` - the plugin only picks the suffix. The
    category is deliberately NOT here: it is the delivery routing key, so the
    core derives it from the plugin name. A plugin free to set category="backup"
    would reach every user an admin routed for backups.
    """

    id: str = Field(
        pattern=r"^[a-z0-9_]+$",
        description="Plugin-local suffix, e.g. 'session_started'",
    )
    notification_type: Literal["info", "warning", "critical"] = "info"
    priority: int = Field(default=0, ge=0, le=3)
    title_template: str = Field(description="Server-rendered, one language")
    message_template: str = Field(description="Server-rendered, one language")
    action_url: Optional[str] = None
    cooldown_seconds: int = Field(
        default=0, ge=0,
        description="Suppress a repeat of the same event+entity within this window",
    )
    default_target: Literal["admins", "all_users"] = "admins"


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

    def get_dashboard_panel(self) -> Optional["DashboardPanelSpec"]:
        """Override to claim the Dashboard plugin slot.

        Returns:
            DashboardPanelSpec or None if this plugin has no Dashboard panel.
        """
        return None

    def get_status_pills(self) -> List["StatusPillSpec"]:
        """Status-strip pills this plugin contributes. Default: none."""
        return []

    async def collect_status_pill(self, pill_id: str, db: "Session") -> Optional[dict]:
        """Current state of one pill, or None to stay silent.

        *pill_id* is the plugin-local suffix from the spec, not the namespaced
        public id. The returned dict is passed to PillState — supply at least
        ``kind``, ``tone`` and ``label_key``/``label_text``.
        """
        return None

    def get_notification_events(self) -> List["PluginEventSpec"]:
        """Notification events this plugin contributes. Default: none.

        The core namespaces each id to ``plugin:<name>:<suffix>``, derives the
        category from the plugin name, and owns delivery. The plugin emits an
        event via ``services.notifications.plugin_events.emit_plugin_event``.
        """
        return []

    def get_menu_items(self) -> List["PluginMenuItem"]:
        """System-menu actions this plugin contributes. Default: none.

        Derived from get_ui_manifest() so a plugin declares its items once: the
        manifest is what reaches the frontend, and this is what the core
        validates an incoming action_id against. Two declaration sites would
        drift, and the drift is invisible - the entry renders and the click 404s.

        Respects manifest.enabled the same way PluginManager.get_ui_manifest()
        does: a manifest with enabled=False must not advertise a dispatchable
        action just because it still lists menu_items - that would be the same
        two-sites drift in the opposite direction (nothing shown, something
        runnable).
        """
        manifest = self.get_ui_manifest()
        if manifest is None or not manifest.enabled:
            return []
        return list(manifest.menu_items)

    async def run_menu_action(
        self,
        action_id: str,
        db: "Session",
        *,
        user: Optional[Any] = None,
        client_host: Optional[str] = None,
    ) -> Optional["MenuActionResult"]:
        """Execute one menu action, or None if this plugin does not know it.

        *action_id* is the plugin-local id from the declared menu item. The
        core validates it against get_menu_items() before calling, enforces the
        admin gate, and applies a timeout - implementations only do the work.
        Blocking work belongs in ``asyncio.to_thread`` so the timeout can
        actually take effect.

        ``db`` is the route's request-scoped SQLAlchemy Session - it is not
        thread-safe. Do not hand it into ``asyncio.to_thread`` (or any other
        thread): a slow action that outlives the request's timeout continues
        running in its own thread with a Session that may already be torn
        down, which is a use-after-close bug waiting to happen, not a
        performance question. If a menu action needs blocking work AND
        database access, open a fresh Session inside the thread instead of
        reusing this one.

        ``user`` and ``client_host`` describe the CALLER, so an action can ask
        the core for a privileged side effect under the core's own rules (see
        services/power/session_lock.unlock_if_permitted). Both are keyword-only
        with defaults: an older implementation keeps working, it just cannot
        request anything caller-dependent.
        """
        return None

    async def get_dashboard_data(self, db: "Session") -> Optional[dict]:
        """Return current data for the Dashboard panel.

        Called by the dashboard endpoint and the SHM-to-WS bridge.
        The returned dict must conform to the schema matching the
        plugin's DashboardPanelSpec.panel_type.

        Args:
            db: SQLAlchemy session.

        Returns:
            Panel data dict or None if no data available.
        """
        return None

    def get_translations(self) -> Optional[Dict[str, Dict[str, str]]]:
        """Return translations keyed by language code.

        Override to provide multi-language support for plugin strings.
        The plugin decides which keys and languages to include.

        Example::

            {
                "en": {"display_name": "Smart Plug", "description": "..."},
                "de": {"display_name": "Smarte Steckdose", "description": "..."},
            }

        Returns:
            Dict mapping language codes to key-value translation dicts,
            or None if the plugin does not provide translations.
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
