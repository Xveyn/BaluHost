"""Tests for the PluginStorage model (round-trip persistence)."""
from app.models.plugin_storage import PluginStorage


def test_plugin_storage_roundtrip(db_session):
    row = PluginStorage(plugin_name="weather", user_id=1, key="units", value={"temp": "C"})
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.value == {"temp": "C"}
    assert row.plugin_name == "weather"
