"""Namespace-Erkennung darf nicht am blossen Doppelpunkt haengen (#532)."""
from app.services.power.fan_sources import TempSourceRegistry


def test_legacy_bare_id_gets_hwmon_namespace():
    assert TempSourceRegistry._normalize_id("hwmon3_temp1") == "hwmon:hwmon3_temp1"


def test_stable_bare_id_gets_hwmon_namespace():
    # Enthaelt selbst einen Doppelpunkt -- die alte Heuristik ":" in id"
    # haette die ID unveraendert durchgereicht und die Quelle nicht gefunden.
    assert (TempSourceRegistry._normalize_id("k10temp-pci-00c3:temp1")
            == "hwmon:k10temp-pci-00c3:temp1")


def test_already_namespaced_ids_pass_through():
    for sid in ("hwmon:k10temp-pci-00c3:temp1", "gpu:edge",
                "disk:sda", "mix:abc123"):
        assert TempSourceRegistry._normalize_id(sid) == sid
