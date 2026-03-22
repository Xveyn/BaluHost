"""Tests for Fritz!Box WoL feature."""
import pytest
from app.schemas.fritzbox import FritzBoxConfigUpdate, FritzBoxConfigResponse


class TestFritzBoxSchemas:
    """Test Fritz!Box Pydantic schemas."""

    def test_config_update_validates_mac(self):
        update = FritzBoxConfigUpdate(nas_mac_address="aa:bb:cc:dd:ee:ff")
        assert update.nas_mac_address == "AA:BB:CC:DD:EE:FF"

    def test_config_update_rejects_bad_mac(self):
        with pytest.raises(Exception):
            FritzBoxConfigUpdate(nas_mac_address="not-a-mac")

    def test_config_update_port_range(self):
        with pytest.raises(Exception):
            FritzBoxConfigUpdate(port=0)
        with pytest.raises(Exception):
            FritzBoxConfigUpdate(port=70000)

    def test_config_update_all_none_ok(self):
        update = FritzBoxConfigUpdate()
        assert update.host is None
        assert update.port is None

    def test_config_response_has_password_flag(self):
        resp = FritzBoxConfigResponse(
            host="192.168.178.1", port=49000, username="",
            nas_mac_address=None, enabled=False, has_password=True,
        )
        assert resp.has_password is True
