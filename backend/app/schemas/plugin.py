"""Pydantic schemas for plugin API."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PluginNavItemSchema(BaseModel):
    """Navigation item in plugin UI."""

    path: str
    label: str
    icon: str = "plug"
    admin_only: bool = False
    order: int = 100


class PluginUIInfo(BaseModel):
    """UI information for a plugin."""

    name: str
    display_name: str
    nav_items: List[PluginNavItemSchema] = []
    bundle_path: str = "ui/bundle.js"
    styles_path: Optional[str] = None
    dashboard_widgets: List[str] = []


class PluginUIManifestResponse(BaseModel):
    """Combined UI manifest for all enabled plugins."""

    plugins: List[PluginUIInfo] = []


class PluginInfo(BaseModel):
    """Basic plugin information."""

    name: str
    version: str
    display_name: str
    description: str
    author: str
    category: str = "general"
    required_permissions: List[str] = []
    dangerous_permissions: List[str] = []
    is_enabled: bool = False
    has_ui: bool = False
    has_routes: bool = False
    error: Optional[str] = None


class PluginListResponse(BaseModel):
    """Response for listing all plugins."""

    plugins: List[PluginInfo]
    total: int


class InstalledPluginSchema(BaseModel):
    """Schema for installed plugin database record."""

    id: int
    name: str
    version: str
    display_name: str
    is_enabled: bool
    granted_permissions: List[str] = []
    config: Dict[str, Any] = {}
    installed_at: datetime
    enabled_at: Optional[datetime] = None
    disabled_at: Optional[datetime] = None
    installed_by: Optional[str] = None

    class Config:
        from_attributes = True


class PluginDetailResponse(BaseModel):
    """Detailed plugin information."""

    # From metadata
    name: str
    version: str
    display_name: str
    description: str
    author: str
    category: str = "general"
    homepage: Optional[str] = None
    min_baluhost_version: Optional[str] = None
    dependencies: List[str] = []

    # Permissions
    required_permissions: List[str] = []
    granted_permissions: List[str] = []
    dangerous_permissions: List[str] = []

    # Status
    is_enabled: bool = False
    is_installed: bool = False
    has_ui: bool = False
    has_routes: bool = False
    has_background_tasks: bool = False

    # UI info
    nav_items: List[PluginNavItemSchema] = []
    dashboard_widgets: List[str] = []

    # Database record (if installed)
    installed_at: Optional[datetime] = None
    enabled_at: Optional[datetime] = None
    config: Dict[str, Any] = {}

    # Config schema (if available)
    config_schema: Optional[Dict[str, Any]] = None


class PluginToggleRequest(BaseModel):
    """Request to enable/disable a plugin."""

    enabled: bool
    grant_permissions: List[str] = Field(
        default_factory=list,
        description="Permissions to grant (only for enabling)",
    )


class PluginToggleResponse(BaseModel):
    """Response after toggling plugin state."""

    name: str
    is_enabled: bool
    message: str


class PluginConfigUpdateRequest(BaseModel):
    """Request to update plugin configuration."""

    config: Dict[str, Any]


class PluginConfigResponse(BaseModel):
    """Response for plugin configuration."""

    name: str
    config: Dict[str, Any]
    schema_: Optional[Dict[str, Any]] = Field(None, alias="schema")


class PermissionInfo(BaseModel):
    """Information about a plugin permission."""

    name: str
    value: str
    dangerous: bool
    description: str


class PermissionListResponse(BaseModel):
    """Response listing all available permissions."""

    permissions: List[PermissionInfo]
