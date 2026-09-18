"""The one read path for stored plugin configuration (#522).

``PUT /api/plugins/{name}/config`` writes ``InstalledPlugin.config``. Nothing
pushes that value into a running plugin instance, and nothing should: a push
from the route reaches only the Uvicorn worker that answered the request, while
three more workers and the monitoring worker keep their own instances. The
database is the only state they share, so plugins read it when they need it -
through ``PluginBase.get_config()``, which delegates here.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.plugins.base import PluginBase

logger = logging.getLogger(__name__)


def resolve_plugin_config(plugin: "PluginBase", db: "Session") -> Dict[str, Any]:
    """Return the plugin's effective configuration.

    Stored row, validated against ``get_config_schema()`` so missing fields get
    their defaults. A missing, empty, unparsable or invalid row yields
    ``get_default_config()`` - stored data never makes this raise. Database
    errors do propagate.
    """
    from app.services import plugin_service

    name = plugin.metadata.name
    record = plugin_service.get_installed_plugin(db, name)
    stored = record.config if record is not None else None

    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except ValueError:
            stored = None
    if not isinstance(stored, dict) or not stored:
        # Validate the defaults too: a plugin with a schema but no
        # get_default_config() override would otherwise get {}.
        stored = plugin.get_default_config()

    try:
        return dict(plugin.validate_config(dict(stored)))
    except (ValueError, TypeError) as exc:
        # Type only: pydantic's message would echo the stored values.
        logger.warning(
            "Stored config for plugin %s is invalid (%s); using defaults",
            name, type(exc).__name__,
        )
        return dict(plugin.get_default_config())
