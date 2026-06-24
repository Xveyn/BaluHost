"""Tests for the PluginStorage model (round-trip persistence)."""

# Note: the SQLite test DB does not enforce foreign keys, so bare user_id values (1, 2) need no seeded users row.

import pytest

from app.models.plugin_storage import PluginStorage
from app.services import plugin_storage_service as svc


def test_plugin_storage_roundtrip(db_session):
    row = PluginStorage(plugin_name="weather", user_id=1, key="units", value={"temp": "C"})
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    assert row.value == {"temp": "C"}
    assert row.plugin_name == "weather"


def test_set_get_delete(db_session):
    svc.set_value(db_session, "weather", 1, "units", {"t": "C"})
    found, value = svc.get_value(db_session, "weather", 1, "units")
    assert found and value == {"t": "C"}
    assert svc.list_keys(db_session, "weather", 1) == ["units"]
    assert svc.delete_value(db_session, "weather", 1, "units") is True
    found, _ = svc.get_value(db_session, "weather", 1, "units")
    assert found is False


def test_per_user_isolation(db_session):
    svc.set_value(db_session, "weather", 1, "k", "A")
    svc.set_value(db_session, "weather", 2, "k", "B")
    _, v1 = svc.get_value(db_session, "weather", 1, "k")
    _, v2 = svc.get_value(db_session, "weather", 2, "k")
    assert v1 == "A" and v2 == "B"
    assert svc.list_keys(db_session, "weather", 1) == ["k"]


def test_value_size_quota(db_session):
    big = "x" * (svc.MAX_VALUE_BYTES + 1)
    with pytest.raises(svc.StorageQuotaError):
        svc.set_value(db_session, "weather", 1, "k", big)


def test_key_count_quota(db_session):
    for i in range(svc.MAX_KEYS):
        svc.set_value(db_session, "weather", 1, f"k{i}", i)
    with pytest.raises(svc.StorageQuotaError):
        svc.set_value(db_session, "weather", 1, "overflow", 1)
