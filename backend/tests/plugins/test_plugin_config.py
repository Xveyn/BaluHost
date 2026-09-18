"""PluginBase.get_config() - the one read path for stored plugin config (#522)."""
from typing import Any, Dict

from pydantic import BaseModel, Field

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


class _NoSchemaPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="plain_plugin", version="1.0.0", display_name="Plain",
            description="test", author="test",
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {"a": 1}


class _Bare(_SchemaPlugin):
    """A plugin with a schema but no get_default_config() override."""

    def get_default_config(self) -> Dict[str, Any]:
        return {}


def _store(db, name: str, config) -> None:
    plugin_service.update_config(db, name=name, validated_config=config)


def test_no_row_returns_defaults(db_session):
    assert _SchemaPlugin().get_config(db_session) == {"interval": 10, "label": "default"}


def test_stored_value_wins(db_session):
    _store(db_session, "cfg_plugin", {"interval": 5, "label": "mine"})
    assert _SchemaPlugin().get_config(db_session) == {"interval": 5, "label": "mine"}


def test_partial_row_is_filled_with_defaults(db_session):
    """A row written by an older plugin version lacks newer fields."""
    _store(db_session, "cfg_plugin", {"interval": 5})
    assert _SchemaPlugin().get_config(db_session) == {"interval": 5, "label": "default"}


def test_invalid_row_falls_back_to_defaults(db_session):
    _store(db_session, "cfg_plugin", {"interval": 0})  # violates ge=1
    assert _SchemaPlugin().get_config(db_session) == {"interval": 10, "label": "default"}


def test_empty_row_returns_defaults(db_session):
    _store(db_session, "cfg_plugin", {})
    assert _SchemaPlugin().get_config(db_session) == {"interval": 10, "label": "default"}


def test_json_string_row_is_parsed(db_session):
    """Tapo's former direct read tolerated a JSON string; keep that tolerance."""
    _store(db_session, "cfg_plugin", '{"interval": 7}')
    assert _SchemaPlugin().get_config(db_session) == {"interval": 7, "label": "default"}


def test_plugin_without_schema_returns_stored_dict(db_session):
    _store(db_session, "plain_plugin", {"a": 2, "b": 3})
    assert _NoSchemaPlugin().get_config(db_session) == {"a": 2, "b": 3}


def test_plugin_without_schema_and_row_returns_defaults(db_session):
    assert _NoSchemaPlugin().get_config(db_session) == {"a": 1}


def test_schema_without_default_override_gets_schema_defaults(db_session):
    assert _Bare().get_config(db_session) == {"interval": 10, "label": "default"}


def test_invalid_row_fallback_validates_bare_default(db_session):
    """A plugin with a schema but no get_default_config() override must still
    get the schema's own defaults for an invalid stored row, not {} (#522).
    """
    _store(db_session, "cfg_plugin", {"interval": 0})  # violates ge=1

    assert _Bare().get_config(db_session) == {"interval": 10, "label": "default"}


def test_invalid_row_logs_name_not_values(db_session):
    # Patch the module logger directly: caplog depends on propagation to the
    # root logger, which the structured-logging setup may switch off.
    from unittest.mock import patch

    from app.plugins import config as config_mod

    _store(db_session, "cfg_plugin", {"interval": 0, "label": "s3cr3t"})
    with patch.object(config_mod.logger, "warning") as warn:
        _SchemaPlugin().get_config(db_session)

    rendered = warn.call_args.args[0] % warn.call_args.args[1:]
    assert "cfg_plugin" in rendered
    assert "s3cr3t" not in rendered
