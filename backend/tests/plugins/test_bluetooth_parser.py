"""Parser-Tests gegen die auf BaluNode gemessene GetManagedObjects-Ausgabe.

Die Fixture ist ein Mitschnitt (scripts/debug/bluez_probe.py dump --anonymize),
kein erfundener Payload — neu messen statt von Hand editieren. Die Randfaelle
weiter unten sind bewusst kleine, synthetische Dicts.
"""
import json
from pathlib import Path

import pytest

from app.plugins.installed.bluetooth.bluez import (
    AdapterInfo,
    device_path,
    kind_for_icon,
    normalize_address,
    parse_objects,
    select_adapter,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bluez_balunode.json"


def _snapshot():
    return parse_objects(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _by_name(snapshot, name):
    return next(d for d in snapshot.devices if d.name == name)


class TestMeasuredFixture:
    def test_exactly_one_adapter_the_dongle(self):
        snap = _snapshot()
        assert len(snap.adapters) == 1
        assert snap.adapters[0].path == "/org/bluez/hci0"
        assert snap.adapters[0].address == "AA:AA:AA:AA:AA:01"

    def test_the_xbox_controller_is_a_paired_controller(self):
        xbox = _by_name(_snapshot(), "Xbox Wireless Controller")
        assert kind_for_icon(xbox.icon) == "controller"
        assert xbox.paired is True

    def test_the_jbl_is_paired_audio(self):
        jbl = _by_name(_snapshot(), "JBL TUNE510BT")
        assert kind_for_icon(jbl.icon) == "audio"
        assert jbl.paired is True

    def test_every_device_hangs_off_the_adapter(self):
        snap = _snapshot()
        assert snap.devices
        assert all(d.adapter_path == "/org/bluez/hci0" for d in snap.devices)

    def test_no_real_mac_survived_anonymization(self):
        text = FIXTURE.read_text(encoding="utf-8").upper()
        for real in ("40:8E:2C", "C8:2B:6B", "A0:AD:9F", "40_8E_2C", "C8_2B_6B"):
            assert real not in text


class TestSyntheticEdgeCases:
    def _objects(self, **device_props):
        props = {"Address": "AA:AA:AA:AA:AA:02", "Adapter": "/org/bluez/hci0", "Paired": False}
        props.update(device_props)
        return {
            "/org/bluez/hci0": {"org.bluez.Adapter1": {
                "Address": "AA:AA:AA:AA:AA:01", "Alias": "BaluNode",
                "Powered": True, "Discovering": False,
            }},
            "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_02": {"org.bluez.Device1": props},
        }

    def test_name_falls_back_alias_then_name_then_address(self):
        assert parse_objects(self._objects(Alias="A", Name="N")).devices[0].name == "A"
        assert parse_objects(self._objects(Name="N")).devices[0].name == "N"
        assert parse_objects(self._objects()).devices[0].name == "AA:AA:AA:AA:AA:02"

    def test_battery_comes_from_battery1(self):
        objects = self._objects()
        objects["/org/bluez/hci0/dev_AA_AA_AA_AA_AA_02"]["org.bluez.Battery1"] = {"Percentage": 80}
        assert parse_objects(objects).devices[0].battery_percent == 80

    def test_missing_battery_is_none_not_zero(self):
        assert parse_objects(self._objects()).devices[0].battery_percent is None

    def test_raw_types_are_ignored(self):
        snap = parse_objects(self._objects(ManufacturerData={"6": "0a0b"}, RSSI=-60))
        assert snap.devices[0].rssi == -60
        assert not hasattr(snap.devices[0], "manufacturer_data")

    def test_a_device_with_a_malformed_address_is_skipped(self):
        assert parse_objects(self._objects(Address="nonsense")).devices == ()


@pytest.mark.parametrize("icon,kind", [
    ("input-gaming", "controller"),
    ("audio-headphones", "audio"),
    ("audio-headset", "audio"),
    ("audio-card", "audio"),
    ("input-keyboard", "input"),
    ("input-mouse", "input"),
    ("input-tablet", "input"),
    ("phone", "other"),
    (None, "other"),
])
def test_kind_for_icon(icon, kind):
    assert kind_for_icon(icon) == kind


class TestAddresses:
    def test_normalize_uppercases_and_validates(self):
        assert normalize_address(" aa:bb:cc:dd:ee:0f ") == "AA:BB:CC:DD:EE:0F"
        assert normalize_address("AA-BB-CC-DD-EE-0F") is None
        assert normalize_address("/org/bluez/hci0") is None
        assert normalize_address("") is None

    def test_device_path_is_built_from_the_address(self):
        assert device_path("/org/bluez/hci0", "AA:BB:CC:DD:EE:0F") == \
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_0F"


def _adapter(address, path="/org/bluez/hci0"):
    return AdapterInfo(path=path, address=address, name="x", powered=True, discovering=False)


class TestSelectAdapter:
    def test_unset_and_exactly_one_uses_it(self):
        a = _adapter("AA:AA:AA:AA:AA:01")
        assert select_adapter((a,), "") == (a, None, None)

    def test_unset_and_several_refuses_to_guess(self):
        chosen, detail, _ = select_adapter(
            (_adapter("AA:AA:AA:AA:AA:01"), _adapter("AA:AA:AA:AA:AA:09", "/org/bluez/hci1")), "",
        )
        assert chosen is None
        assert "BLUETOOTH_ADAPTER_ADDRESS" in detail

    def test_set_and_present_uses_it_and_warns_about_the_other(self):
        b = _adapter("AA:AA:AA:AA:AA:09", "/org/bluez/hci1")
        chosen, detail, warning = select_adapter((_adapter("AA:AA:AA:AA:AA:01"), b), "AA:AA:AA:AA:AA:09")
        assert chosen == b and detail is None and warning

    def test_set_and_missing_never_falls_back(self):
        chosen, detail, _ = select_adapter((_adapter("AA:AA:AA:AA:AA:01"),), "AA:AA:AA:AA:AA:09")
        assert chosen is None
        assert "AA:AA:AA:AA:AA:09" in detail

    def test_no_adapter_at_all(self):
        chosen, detail, _ = select_adapter((), "")
        assert chosen is None and detail


class TestAdapterSetting:
    def test_empty_is_allowed(self):
        from app.core.config import Settings
        assert Settings(bluetooth_adapter_address="").bluetooth_adapter_address == ""

    def test_a_mac_is_uppercased(self):
        from app.core.config import Settings
        value = Settings(bluetooth_adapter_address="a0:ad:9f:6f:43:f1").bluetooth_adapter_address
        assert value == "A0:AD:9F:6F:43:F1"

    def test_garbage_is_rejected(self):
        from app.core.config import Settings
        with pytest.raises(ValueError):
            Settings(bluetooth_adapter_address="hci0")
