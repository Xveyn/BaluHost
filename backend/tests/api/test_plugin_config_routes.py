"""GET /api/plugins/{name}/config serves the config the plugin actually uses (#522)."""
from typing import Any, Dict

import pytest
from pydantic import BaseModel, Field

from app.api.routes.plugins import get_plugin_manager
from app.main import app
from app.plugins.base import PluginBase, PluginMetadata
from app.services import plugin_service


class _Cfg(BaseModel):
    interval: int = Field(default=10, ge=1)
    label: str = "default"


class _SchemaPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="cfg_plugin", version="1.0.0", display_name="Cfg",
            description="test", author="test",
        )

    def get_config_schema(self) -> type:
        return _Cfg

    def get_default_config(self) -> Dict[str, Any]:
        return _Cfg().model_dump()


class _FakeManager:
    def __init__(self, plugin: PluginBase) -> None:
        self._plugin = plugin

    def get_plugin(self, name: str):
        return self._plugin if name == self._plugin.metadata.name else None

    def get_discovered(self, name: str):
        # No external-plugin manifest -> get_plugin_details takes the
        # bundled-plugin branch.
        return None

    def is_enabled(self, name: str) -> bool:
        return True

    def router_restart_required(self, name: str) -> bool:
        return False


@pytest.fixture
def fake_manager():
    app.dependency_overrides[get_plugin_manager] = lambda: _FakeManager(_SchemaPlugin())
    yield
    app.dependency_overrides.pop(get_plugin_manager, None)


def test_get_fills_partial_row_with_defaults(client, admin_headers, db_session, fake_manager):
    plugin_service.update_config(db_session, name="cfg_plugin", validated_config={"interval": 5})

    r = client.get("/api/plugins/cfg_plugin/config", headers=admin_headers)

    assert r.status_code == 200
    assert r.json()["config"] == {"interval": 5, "label": "default"}


def test_get_invalid_row_shows_defaults(client, admin_headers, db_session, fake_manager):
    plugin_service.update_config(db_session, name="cfg_plugin", validated_config={"interval": 0})

    r = client.get("/api/plugins/cfg_plugin/config", headers=admin_headers)

    assert r.status_code == 200
    assert r.json()["config"] == {"interval": 10, "label": "default"}


def test_get_plugin_details_fills_partial_row_with_defaults(client, admin_headers, db_session, fake_manager):
    """GET /api/plugins/{name} (the details route the settings form uses) must
    serve the same effective config as GET /{name}/config, not the raw row (#522).
    """
    plugin_service.update_config(db_session, name="cfg_plugin", validated_config={"interval": 5})

    r = client.get("/api/plugins/cfg_plugin", headers=admin_headers)

    assert r.status_code == 200
    assert r.json()["config"] == {"interval": 5, "label": "default"}


def test_put_then_get_round_trips(client, admin_headers, fake_manager):
    r = client.put(
        "/api/plugins/cfg_plugin/config",
        json={"config": {"interval": 3, "label": "x"}},
        headers=admin_headers,
    )
    assert r.status_code == 200

    r = client.get("/api/plugins/cfg_plugin/config", headers=admin_headers)
    assert r.json()["config"] == {"interval": 3, "label": "x"}
