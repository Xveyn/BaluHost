"""SHM-to-WebSocket bridge for Dashboard plugin panel updates.

Runs as a background task in the web worker (primary only). Detects
changes in the smart device SHM file, calls the active dashboard
plugin's get_dashboard_data(), and broadcasts via WebSocket.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.plugins.manager import PluginManager
from app.services.plugin_service import get_dashboard_panel_plugin

logger = logging.getLogger(__name__)


async def _build_panel_update(db: Session) -> Optional[Dict[str, Any]]:
    """Build a dashboard_panel_update payload for the active plugin.

    Args:
        db: SQLAlchemy session.

    Returns:
        Payload dict or None if no plugin panel is active.
    """
    record = get_dashboard_panel_plugin(db)
    if record is None:
        return None

    pm = PluginManager.get_instance()
    plugin = pm.get_plugin(record.name)
    if plugin is None:
        return None

    spec = plugin.get_dashboard_panel()
    if spec is None:
        return None

    data = None
    try:
        data = await plugin.get_dashboard_data(db)
    except Exception as exc:
        logger.debug("Dashboard panel data error: %s", exc)

    if data is None:
        return None

    return {
        "panel_type": spec.panel_type,
        "plugin_name": record.name,
        "data": data,
    }


async def dashboard_panel_ws_bridge() -> None:
    """Background task: SHM change detection -> get_dashboard_data -> WS broadcast.

    Runs every 3 seconds. When the SHM changes file is newer than the last
    check, calls get_dashboard_data(db) for full state and broadcasts
    a dashboard_panel_update message.
    """
    import asyncio

    from app.core.database import SessionLocal
    from app.services.monitoring.shm import read_shm, SMART_DEVICES_CHANGES_FILE
    from app.services.websocket_manager import get_websocket_manager

    _last_broadcast_ts: float = 0.0

    while True:
        await asyncio.sleep(3.0)
        try:
            # Check if there are any new changes
            data = read_shm(SMART_DEVICES_CHANGES_FILE, max_age_seconds=10.0)
            if data is None:
                continue

            ts = data.get("timestamp", 0.0)
            if ts <= _last_broadcast_ts:
                continue

            _last_broadcast_ts = ts

            # Build panel update from the active plugin
            db = SessionLocal()
            try:
                payload = await _build_panel_update(db)
            finally:
                db.close()

            if payload is None:
                continue

            ws = get_websocket_manager()
            if ws:
                await ws.broadcast_typed("dashboard_panel_update", payload)

        except Exception as exc:
            logger.debug("Dashboard panel WS bridge error: %s", exc)
