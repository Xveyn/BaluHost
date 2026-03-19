"""API routes for Dashboard plugin panel."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.plugins.manager import PluginManager
from app.schemas.plugin import DashboardPanelResponse
from app.services.plugin_service import get_dashboard_panel_plugin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/plugin-panel", response_model=Optional[DashboardPanelResponse])
@user_limiter.limit(get_limit("default"))
async def get_plugin_panel(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Optional[DashboardPanelResponse]:
    """Get the active Dashboard plugin panel with current data.

    Returns the panel spec + data for the plugin that has
    dashboard_panel_enabled=True, or null if no plugin is active.
    """
    record = get_dashboard_panel_plugin(db)
    if record is None:
        return None

    # Get the loaded plugin instance
    pm = PluginManager.get_instance()
    plugin = pm.get_plugin(record.name)
    if plugin is None:
        return None

    spec = plugin.get_dashboard_panel()
    if spec is None:
        return None

    # Get current data
    data = None
    try:
        data = await plugin.get_dashboard_data(db)
    except Exception as exc:
        logger.warning(
            "Dashboard panel data error for plugin %s: %s",
            record.name, exc,
        )

    return DashboardPanelResponse(
        plugin_name=record.name,
        panel_type=spec.panel_type,
        title=spec.title,
        icon=spec.icon,
        accent=spec.accent,
        data=data,
        translations=plugin.get_translations() or None,
    )
