"""Vertrag: jeder API-Pfad des Trays ist im Backend gebunden (#859).

Zweimal lag das Tray daneben, und jedes Mal waren die Tests gruen, weil sie die
Konstante gegen einen abgeschriebenen String prueften: `/api/desktop/...` statt
`/api/desktop-pairing/...` (pairing.py) und `/api/sleep/config` statt
`/api/system/sleep/config` (awake.py, #861 — jeder Aufruf 404).

Geprueft wird mit Starlettes eigenem Routing (`BaseRoute.matches`), also genau
der Entscheidung, die der Server bei einer Anfrage trifft — fuer HTTP-Methoden
und WebSocket gleichermassen. `app.openapi()` kennt keine WebSocket-Routen,
`route_shadowing.flatten_routes()` auch nicht.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from starlette.routing import Match

import baluhost_tray

WEBSOCKET = "WEBSOCKET"

# Modul.Konstante -> Methoden, mit denen das Tray den Pfad aufruft. Eine neue
# *_PATH-Konstante unter /api/ ohne Eintrag hier laesst
# test_every_tray_api_path_is_declared fehlschlagen — Absicht.
EXPECTED: dict[str, set[str]] = {
    "awake.SLEEP_CONFIG_PATH": {"PUT"},
    "awake.SLEEP_STATUS_PATH": {"GET"},
    "handoff.HANDOFF_PATH": {"POST"},
    "loop.GAMING_PATH": {"GET"},
    "pairing.DEVICE_CODE_PATH": {"POST"},
    "pairing.POLL_PATH": {"POST"},
    "restart.HEALTH_PATH": {"GET"},
    "restart.ME_PATH": {"GET"},
    "restart.TOTP_STATUS_PATH": {"GET"},
    "restart.PIN_STATUS_PATH": {"GET"},
    "restart.RESTART_ALL_PATH": {"POST"},
    "session.WS_TOKEN_PATH": {"POST"},
    "session.REFRESH_PATH": {"POST"},
    "session.WS_PATH": {WEBSOCKET},
    "watch.SNAPSHOT_PATH": {"GET"},
}

# Bundled Plugins, deren Routen das Tray anspricht. Plugin-Router haengt erst
# die Lifespan ein (PluginManager.get_router), beim Import von app.main fehlen sie.
PLUGINS = ("steam_gaming",)


def _tray_api_paths() -> dict[str, str]:
    """Modulweite `*_PATH = "/api/..."` aus den Quelltexten, ohne Import.

    Per ast statt importlib: tray.py braucht PyQt6 (fehlt im Dev-venv), und
    __main__.py wuerde beim Import das Tray starten.
    """
    found: dict[str, str] = {}
    for source in sorted(Path(baluhost_tray.__file__).parent.glob("*.py")):
        for node in ast.parse(source.read_text(encoding="utf-8")).body:
            if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)):
                continue
            value = node.value.value
            if not (isinstance(value, str) and value.startswith("/api/")):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("_PATH"):
                    found[f"{source.stem}.{target.id}"] = value
    return found


TRAY_PATHS = _tray_api_paths()


@pytest.fixture(scope="module")
def routes() -> list:
    from fastapi import APIRouter

    from app.core.config import settings
    from app.main import app
    from app.plugins.manager import PluginManager

    # Derselbe Prefix wie PluginManager.get_router() + lifespan:
    # {api_prefix}/plugins/{name}. Nicht get_router() selbst — dessen
    # Catch-all fuer Sandbox-Plugins passt auf jeden Pfad darunter.
    plugin_routes = APIRouter()
    manager = PluginManager()
    for name in PLUGINS:
        router = manager.load_plugin(name).get_router()
        assert router is not None, f"Plugin {name} liefert keinen Router"
        plugin_routes.include_router(router, prefix=f"{settings.api_prefix}/plugins/{name}")
    return [*app.routes, *plugin_routes.routes]


def _is_bound(routes: list, path: str, method: str) -> bool:
    if method == WEBSOCKET:
        scope = {"type": "websocket", "path": path, "root_path": "", "headers": [], "query_string": b""}
    else:
        scope = {"type": "http", "path": path, "root_path": "", "method": method, "headers": [], "query_string": b""}
    return any(route.matches(scope)[0] == Match.FULL for route in routes)


def test_every_tray_api_path_is_declared():
    assert set(TRAY_PATHS) == set(EXPECTED)


@pytest.mark.parametrize(
    ("constant", "method"),
    sorted((constant, method) for constant, methods in EXPECTED.items() for method in methods),
)
def test_tray_api_path_is_bound(routes, constant, method):
    path = TRAY_PATHS[constant]
    assert _is_bound(routes, path, method), f"{constant} = {path!r}: {method} nicht gebunden"


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/sleep/config", "GET"),               # vor #861 in awake.py
        ("/api/desktop/device-code", "POST"),       # frueher in pairing.py
        ("/api/notifications/ws-token", "GET"),     # gebunden, aber nur POST
        ("/api/notifications/nope", WEBSOCKET),
    ],
)
def test_matcher_rejects_unbound(routes, path, method):
    """Gegenprobe: der Abgleich kann auch nein sagen."""
    assert not _is_bound(routes, path, method)
