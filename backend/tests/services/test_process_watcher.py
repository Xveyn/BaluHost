"""Tests for boost-rule process matching (filled in across Tasks 6-8)."""
from app.models.power_boost_rule import PowerBoostRule


def test_power_boost_rule_model_importable():
    assert PowerBoostRule.__tablename__ == "power_boost_rules"
