"""Report plugin routes that a core route under /api/plugins/{name}/ shadows (#521).

The core plugins router (``api/routes/plugins.py``) is included when the app is
built; the plugin router only at startup, after the enabled plugins are loaded
(``core/lifespan.py``). FastAPI matches in registration order, so a core route
always wins over a plugin route with the same method and path.

That order is deliberate and stays: a plugin must not be able to take over
``toggle``, ``config`` or ``_storage``. What this module fixes is that the loss
used to be silent - the plugin route even showed up in the OpenAPI schema, and
the symptoms (a core response shape, a 422) pointed at the plugin.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from fastapi import APIRouter
from starlette.routing import BaseRoute

logger = logging.getLogger(__name__)

_PLUGIN_TAG = "plugin:"
_PARAM_RE = re.compile(r"\{[^}]+\}")


@dataclass(frozen=True)
class ShadowedRoute:
    plugin: str
    path: str
    methods: tuple[str, ...]
    core_path: str


def _plugin_name(route: BaseRoute) -> str | None:
    """Bundled plugin routes carry the tag ``plugin:<name>`` (PluginManager.get_router)."""
    for tag in getattr(route, "tags", None) or []:
        if isinstance(tag, str) and tag.startswith(_PLUGIN_TAG):
            return tag[len(_PLUGIN_TAG):]
    return None


def find_shadowed_plugin_routes(
    existing_routes: Iterable[BaseRoute], plugin_router: APIRouter, api_prefix: str
) -> list[ShadowedRoute]:
    """Plugin routes that an already registered route would answer instead.

    Only bundled plugin routes are checked; the catch-all for sandboxed plugins
    carries no plugin tag and is meant to lose against every core route.
    """
    existing = [r for r in existing_routes if getattr(r, "path_regex", None) is not None]
    found: list[ShadowedRoute] = []

    for route in plugin_router.routes:
        plugin = _plugin_name(route)
        if plugin is None:
            continue
        path = f"{api_prefix}{route.path}"
        # Any value satisfies a str/path parameter, which is all the core uses.
        concrete = _PARAM_RE.sub("x", path)
        methods = set(getattr(route, "methods", None) or ())

        for core in existing:
            core_methods = set(getattr(core, "methods", None) or ())
            overlap = methods & core_methods
            if overlap and core.path_regex.match(concrete):
                found.append(ShadowedRoute(plugin, path, tuple(sorted(overlap)), core.path))
                break

    return found


def warn_shadowed_plugin_routes(
    existing_routes: Iterable[BaseRoute], plugin_router: APIRouter, api_prefix: str
) -> list[ShadowedRoute]:
    """Log one warning per shadowed plugin route. Call before mounting the router."""
    found = find_shadowed_plugin_routes(existing_routes, plugin_router, api_prefix)
    for s in found:
        logger.warning(
            "Plugin %s registers %s %s, which is shadowed by the core route %s "
            "and will never be reached - pick another sub-path",
            s.plugin, "/".join(s.methods), s.path, s.core_path,
        )
    return found
