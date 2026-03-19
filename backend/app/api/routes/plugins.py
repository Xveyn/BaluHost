"""API routes for plugin management."""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.middleware.plugin_gate import invalidate_plugin_cache
from app.plugins.manager import PluginManager, PluginLoadError
from app.plugins.permissions import PermissionManager
from app.services import plugin_service
from app.schemas.plugin import (
    DashboardPanelToggleRequest,
    InstalledPluginSchema,
    PermissionInfo,
    PermissionListResponse,
    PluginConfigResponse,
    PluginConfigUpdateRequest,
    PluginDetailResponse,
    PluginInfo,
    PluginListResponse,
    PluginNavItemSchema,
    PluginToggleRequest,
    PluginToggleResponse,
    PluginUIManifestResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["plugins"])


def get_plugin_manager() -> PluginManager:
    """Get the plugin manager singleton."""
    return PluginManager.get_instance()


@router.get("", response_model=PluginListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_plugins(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> PluginListResponse:
    """List all available plugins.

    Returns discovered plugins with their status.
    """
    all_plugins = plugin_manager.get_all_plugins()

    plugins = []
    for name, info in all_plugins.items():
        # Get translations if plugin instance is available
        translations = None
        plugin_instance = plugin_manager.get_plugin(name)
        if plugin_instance:
            translations = plugin_instance.get_translations() or None

        plugins.append(
            PluginInfo(
                name=info.get("name", name),
                version=info.get("version", "0.0.0"),
                display_name=info.get("display_name", name),
                description=info.get("description", ""),
                author=info.get("author", "Unknown"),
                category=info.get("category", "general"),
                required_permissions=info.get("required_permissions", []),
                dangerous_permissions=info.get("dangerous_permissions", []),
                is_enabled=info.get("is_enabled", False),
                has_ui=info.get("has_ui", False),
                has_routes=info.get("has_routes", False),
                error=info.get("error"),
                translations=translations,
            )
        )

    return PluginListResponse(plugins=plugins, total=len(plugins))


@router.get("/permissions", response_model=PermissionListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_permissions(
    request: Request, response: Response,
    current_user: User = Depends(get_current_admin),
) -> PermissionListResponse:
    """List all available plugin permissions.

    Admin only.
    """
    perms = PermissionManager.get_all_permissions()
    return PermissionListResponse(
        permissions=[PermissionInfo(**p) for p in perms]
    )


@router.get("/ui/manifest", response_model=PluginUIManifestResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_ui_manifest(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> PluginUIManifestResponse:
    """Get UI manifest for frontend integration.

    Returns navigation items and bundle paths for all enabled plugins.
    """
    manifest = plugin_manager.get_ui_manifest()
    return PluginUIManifestResponse(**manifest)


@router.get("/{name}", response_model=PluginDetailResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_plugin_details(
    request: Request, response: Response,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> PluginDetailResponse:
    """Get detailed information about a specific plugin."""
    # Try to load plugin
    try:
        plugin = plugin_manager.get_plugin(name)
        if plugin is None:
            plugin = plugin_manager.load_plugin(name)
    except PluginLoadError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {e}",
        )

    meta = plugin.metadata
    ui_manifest = plugin.get_ui_manifest()

    # Get database record if exists
    db_record = plugin_service.get_installed_plugin(db, name)

    # Get config schema if available
    config_schema = None
    schema_class = plugin.get_config_schema()
    if schema_class:
        try:
            config_schema = schema_class.model_json_schema()
        except Exception:
            pass

    return PluginDetailResponse(
        name=meta.name,
        version=meta.version,
        display_name=meta.display_name,
        description=meta.description,
        author=meta.author,
        category=meta.category,
        homepage=meta.homepage,
        min_baluhost_version=meta.min_baluhost_version,
        dependencies=meta.dependencies,
        required_permissions=meta.required_permissions,
        granted_permissions=(db_record.granted_permissions or []) if db_record else [],
        dangerous_permissions=PermissionManager.get_dangerous_permissions(
            meta.required_permissions
        ),
        is_enabled=plugin_manager.is_enabled(name),
        is_installed=db_record is not None,
        has_ui=ui_manifest is not None and ui_manifest.enabled,
        has_routes=plugin.get_router() is not None,
        has_background_tasks=len(plugin.get_background_tasks()) > 0,
        has_dashboard_panel=plugin.get_dashboard_panel() is not None,
        dashboard_panel_enabled=db_record.dashboard_panel_enabled if db_record else False,
        nav_items=[
            PluginNavItemSchema(**item.model_dump())
            for item in (ui_manifest.nav_items if ui_manifest else [])
        ],
        dashboard_widgets=ui_manifest.dashboard_widgets if ui_manifest else [],
        installed_at=db_record.installed_at if db_record else None,
        enabled_at=db_record.enabled_at if db_record else None,
        config=(db_record.config or {}) if db_record else (plugin.get_default_config() or {}),
        config_schema=config_schema,
        translations=plugin.get_translations() or None,
    )


@router.post("/{name}/toggle", response_model=PluginToggleResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def toggle_plugin(
    request: Request, response: Response,
    name: str,
    body: PluginToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> PluginToggleResponse:
    """Enable or disable a plugin.

    Admin only. When enabling, required permissions must be granted.
    """
    # Try to load plugin first
    try:
        plugin = plugin_manager.get_plugin(name)
        if plugin is None:
            plugin = plugin_manager.load_plugin(name)
    except PluginLoadError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {e}",
        )

    meta = plugin.metadata

    if body.enabled:
        # Enabling plugin
        permissions_to_grant = body.grant_permissions

        # Validate all required permissions are granted
        if not PermissionManager.validate_permissions(
            meta.required_permissions, permissions_to_grant
        ):
            missing = set(meta.required_permissions) - set(permissions_to_grant)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required permissions: {list(missing)}",
            )

        plugin_service.enable_plugin(
            db,
            name=name,
            version=meta.version,
            display_name=meta.display_name,
            permissions=permissions_to_grant,
            default_config=plugin.get_default_config(),
            installed_by=current_user.username,
        )

        # Enable in plugin manager
        success = await plugin_manager.enable_plugin(
            name, permissions_to_grant, db
        )

        if not success:
            plugin_service.rollback_enable(db, name)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to enable plugin",
            )

        # If this is a SmartDevicePlugin, register with SmartDeviceManager
        from app.plugins.smart_device.base import SmartDevicePlugin
        if isinstance(plugin, SmartDevicePlugin):
            from app.plugins.smart_device.manager import SmartDeviceManager
            SmartDeviceManager.get_instance().register_plugin(plugin)

        invalidate_plugin_cache(name)
        logger.info("Plugin %s enabled by %s", name, current_user.username)
        return PluginToggleResponse(
            name=name,
            is_enabled=True,
            message=f"Plugin '{meta.display_name}' enabled successfully",
        )

    else:
        # Disabling plugin
        # If this is a SmartDevicePlugin, unregister from SmartDeviceManager
        from app.plugins.smart_device.base import SmartDevicePlugin
        if isinstance(plugin, SmartDevicePlugin):
            from app.plugins.smart_device.manager import SmartDeviceManager
            mgr = SmartDeviceManager.get_instance()
            mgr._plugins.pop(name, None)

        success = await plugin_manager.disable_plugin(name)

        plugin_service.disable_plugin_record(db, name)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to disable plugin",
            )

        invalidate_plugin_cache(name)
        logger.info("Plugin %s disabled by %s", name, current_user.username)
        return PluginToggleResponse(
            name=name,
            is_enabled=False,
            message=f"Plugin '{meta.display_name}' disabled successfully",
        )


@router.post("/{name}/dashboard-panel")
@user_limiter.limit(get_limit("admin_operations"))
async def toggle_dashboard_panel(
    request: Request,
    response: Response,
    name: str,
    body: DashboardPanelToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
):
    """Enable or disable a plugin's Dashboard panel.

    Admin only. When enabling, any other plugin's panel is deactivated
    (single-slot constraint).
    """
    plugin = plugin_manager.get_plugin(name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found or not enabled",
        )

    # Verify plugin supports dashboard panel
    if plugin.get_dashboard_panel() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plugin does not provide a Dashboard panel",
        )

    plugin_service.set_dashboard_panel_enabled(db, name, body.enabled)

    # Audit log
    from app.services.audit.logger_db import get_audit_logger_db
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="PLUGIN",
        user=current_user.username,
        action="toggle_dashboard_panel",
        resource=name,
        details={"enabled": body.enabled},
        ip_address=request.client.host if request.client else None,
    )

    logger.info(
        "Dashboard panel %s for plugin %s by %s",
        "enabled" if body.enabled else "disabled",
        name,
        current_user.username,
    )
    return {
        "name": name,
        "dashboard_panel_enabled": body.enabled,
        "message": f"Dashboard panel {'enabled' if body.enabled else 'disabled'}",
    }


@router.get("/{name}/config", response_model=PluginConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_plugin_config(
    request: Request, response: Response,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> PluginConfigResponse:
    """Get plugin configuration.

    Admin only.
    """
    plugin = plugin_manager.get_plugin(name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found",
        )

    db_record = plugin_service.get_installed_plugin(db, name)
    config = (db_record.config or {}) if db_record else (plugin.get_default_config() or {})

    # Get schema if available
    schema = None
    schema_class = plugin.get_config_schema()
    if schema_class:
        try:
            schema = schema_class.model_json_schema()
        except Exception:
            pass

    return PluginConfigResponse(
        name=name,
        config=config,
        schema=schema,
    )


@router.put("/{name}/config", response_model=PluginConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_plugin_config(
    request: Request, response: Response,
    name: str,
    body: PluginConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
) -> PluginConfigResponse:
    """Update plugin configuration.

    Admin only.
    """
    plugin = plugin_manager.get_plugin(name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found",
        )

    # Validate configuration
    try:
        validated_config = plugin.validate_config(body.config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid configuration: {e}",
        )

    meta = plugin.metadata
    plugin_service.update_config(
        db,
        name=name,
        validated_config=validated_config,
        version=meta.version,
        display_name=meta.display_name,
        installed_by=current_user.username,
    )

    logger.info("Plugin %s config updated by %s", name, current_user.username)

    return PluginConfigResponse(
        name=name,
        config=validated_config,
        schema=None,
    )


@router.get("/{name}/ui/{file_path:path}")
@user_limiter.limit(get_limit("admin_operations"))
async def serve_plugin_asset(
    request: Request, response: Response,
    name: str,
    file_path: str,
    db: Session = Depends(get_db),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
):
    """Serve plugin UI assets (JS/CSS bundles).

    Returns static files from the plugin's ui/ directory.
    No authentication required - assets are public code, not user data.
    Dynamic imports (ES modules) don't send auth headers.
    """
    # Check database for enabled status (works across workers)
    db_record = plugin_service.get_enabled_plugin(db, name)

    if not db_record and not plugin_manager.is_enabled(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found or not enabled",
        )

    # Construct file path
    plugin_path = plugin_manager.plugins_dir / name / "ui" / file_path

    # Security: ensure path doesn't escape plugin directory
    try:
        plugin_path = plugin_path.resolve()
        allowed_base = (plugin_manager.plugins_dir / name / "ui").resolve()
        if not str(plugin_path).startswith(str(allowed_base)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path",
        )

    if not plugin_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Determine content type
    content_type = "application/octet-stream"
    if file_path.endswith(".js"):
        content_type = "application/javascript"
    elif file_path.endswith(".css"):
        content_type = "text/css"
    elif file_path.endswith(".json"):
        content_type = "application/json"

    return FileResponse(
        plugin_path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.delete("/{name}")
@user_limiter.limit(get_limit("admin_operations"))
async def uninstall_plugin(
    request: Request, response: Response,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
):
    """Uninstall a plugin (remove from database, files remain).

    Admin only. Disables the plugin and removes its database record.
    Plugin files in the plugins directory are not removed.
    """
    # Disable first if enabled
    if plugin_manager.is_enabled(name):
        await plugin_manager.disable_plugin(name)

    deleted = plugin_service.uninstall_plugin(db, name)
    if deleted:
        logger.info("Plugin %s uninstalled by %s", name, current_user.username)
        return {"message": f"Plugin '{name}' uninstalled"}

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Plugin not installed",
    )
