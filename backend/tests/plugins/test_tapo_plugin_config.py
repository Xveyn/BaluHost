"""Validation tests for the Tapo plugin config schema."""
import pytest
from pydantic import ValidationError

from app.plugins.installed.tapo_smart_plug import TapoPluginConfig


def test_default_retention_is_30():
    assert TapoPluginConfig().retention_days == 30


@pytest.mark.parametrize("value", [0, 1, 30, 365])
def test_accepts_valid_retention(value):
    assert TapoPluginConfig(retention_days=value).retention_days == value


@pytest.mark.parametrize("value", [-1, 366, 1000])
def test_rejects_out_of_range(value):
    with pytest.raises(ValidationError):
        TapoPluginConfig(retention_days=value)


def test_schema_exposes_presets_and_unlimited():
    schema = TapoPluginConfig.model_json_schema()
    prop = schema["properties"]["retention_days"]
    assert prop["x-presets"] == [7, 30, 90, 180]
    assert prop["x-unlimited-value"] == 0
