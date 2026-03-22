"""Tests for Server Profile WoL feature (Phase 3)."""
import pytest
from app.schemas.server_profile import (
    ServerProfileBase,
    ServerProfileCreate,
    ServerProfileUpdate,
    ServerProfileResponse,
    ServerStartResponse,
)


class TestServerProfileWolSchemas:
    """Test wol_mac_address field in server profile schemas."""

    def test_create_with_mac(self):
        profile = ServerProfileCreate(
            name="Test",
            ssh_host="192.168.1.100",
            ssh_username="root",
            ssh_private_key="-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
            wol_mac_address="aa:bb:cc:dd:ee:ff",
        )
        assert profile.wol_mac_address == "AA:BB:CC:DD:EE:FF"

    def test_create_without_mac(self):
        profile = ServerProfileCreate(
            name="Test",
            ssh_host="192.168.1.100",
            ssh_username="root",
            ssh_private_key="-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
        )
        assert profile.wol_mac_address is None

    def test_update_with_mac(self):
        update = ServerProfileUpdate(wol_mac_address="aa:bb:cc:dd:ee:ff")
        assert update.wol_mac_address == "AA:BB:CC:DD:EE:FF"

    def test_update_rejects_invalid_mac(self):
        with pytest.raises(Exception):
            ServerProfileUpdate(wol_mac_address="not-a-mac")

    def test_start_response_includes_method(self):
        resp = ServerStartResponse(
            profile_id=1,
            status="starting",
            message="WoL sent",
            method="wol",
        )
        assert resp.method == "wol"

    def test_start_response_default_method(self):
        resp = ServerStartResponse(
            profile_id=1,
            status="starting",
            message="Started via SSH",
        )
        assert resp.method == "ssh"
