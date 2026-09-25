"""Core routes under /api/plugins/{name}/ silently shadow same-path plugin routes (#521).

The core plugins router is included at import time, the plugin router only at
startup, and FastAPI matches in registration order - so the core always wins.
That order is the safe one (a plugin must not hijack toggle or _storage), but
the loss was silent: Balu Code's GET/PUT /config landed on the core route and
the symptoms pointed at the plugin. Now it's reported at mount time.
"""
import logging

from fastapi import APIRouter, FastAPI

from app.plugins.route_shadowing import find_shadowed_plugin_routes, warn_shadowed_plugin_routes


def _core_app() -> FastAPI:
    core = APIRouter(prefix="/plugins")

    @core.get("/{name}/config")
    def core_get_config(name: str): ...

    @core.put("/{name}/config")
    def core_put_config(name: str): ...

    @core.get("/{name}/_storage/{key}")
    def core_storage(name: str, key: str): ...

    app = FastAPI()
    app.include_router(core, prefix="/api")
    return app


def _plugin_router(build) -> APIRouter:
    """Shaped like PluginManager.get_router(): /plugins + /{name} + tag plugin:{name}."""
    outer = APIRouter(prefix="/plugins")
    inner = APIRouter()
    build(inner)
    outer.include_router(inner, prefix="/demo", tags=["plugin:demo"])

    @outer.api_route("/{name}/{path:path}", methods=["GET", "POST"], include_in_schema=False)
    def _sandbox_proxy(name: str, path: str): ...

    return outer


def test_reports_a_plugin_route_the_core_shadows():
    def build(r):
        @r.get("/config")
        def cfg(): ...

        @r.get("/health")
        def health(): ...

    found = find_shadowed_plugin_routes(_core_app().routes, _plugin_router(build), "/api")

    assert [(s.plugin, s.path, s.methods, s.core_path) for s in found] == [
        ("demo", "/api/plugins/demo/config", ("GET",), "/api/plugins/{name}/config"),
    ]


def test_other_method_on_the_same_path_is_not_shadowed():
    def build(r):
        @r.post("/config")
        def cfg(): ...

    assert find_shadowed_plugin_routes(_core_app().routes, _plugin_router(build), "/api") == []


def test_path_parameters_in_the_plugin_route_are_matched():
    def build(r):
        @r.get("/_storage/{item}")
        def item(item: str): ...

    found = find_shadowed_plugin_routes(_core_app().routes, _plugin_router(build), "/api")

    assert [s.core_path for s in found] == ["/api/plugins/{name}/_storage/{key}"]


def test_the_sandbox_catch_all_is_not_reported():
    # It is meant to lose against every core route; reporting it would be noise.
    found = find_shadowed_plugin_routes(_core_app().routes, _plugin_router(lambda r: None), "/api")

    assert found == []


def test_lifespan_mount_warns_and_still_mounts(caplog):
    from app.core.lifespan import _mount_plugin_router

    def build(r):
        @r.get("/config")
        def cfg(): ...

        @r.get("/health")
        def health(): ...

    app = _core_app()
    caplog.set_level(logging.WARNING, logger="app.plugins.route_shadowing")
    _mount_plugin_router(app, _plugin_router(build))

    assert any("/api/plugins/demo/config" in r.getMessage() for r in caplog.records)
    assert "/api/plugins/demo/health" in {getattr(r, "path", None) for r in app.routes}


def test_real_core_routes_shadow_a_plugin_config_route(caplog):
    # Against the actual app: the Balu Code case from the issue.
    from app.main import app

    def build(r):
        @r.get("/config")
        def cfg(): ...

    caplog.set_level(logging.WARNING, logger="app.plugins.route_shadowing")
    warn_shadowed_plugin_routes(app.routes, _plugin_router(build), "/api")

    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "demo" in messages[0] and "/api/plugins/demo/config" in messages[0]
    assert "/api/plugins/{name}/config" in messages[0]
