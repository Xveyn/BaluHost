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


from unittest.mock import patch, MagicMock, AsyncMock


class TestStartServerWolFallback:
    """Test SSH-fail-to-WoL fallback in start endpoint."""

    def _mock_profile(self, power_on_command="start", wol_mac_address="AA:BB:CC:DD:EE:FF"):
        profile = MagicMock()
        profile.id = 1
        profile.ssh_host = "192.168.1.100"
        profile.ssh_port = 22
        profile.ssh_username = "root"
        profile.ssh_key_encrypted = "encrypted"
        profile.power_on_command = power_on_command
        profile.wol_mac_address = wol_mac_address
        profile.vpn_profile_id = None
        return profile

    @pytest.mark.asyncio
    async def test_wol_fallback_no_profile(self):
        """When profile is None, no fallback."""
        from app.api.routes.server_profiles import _try_wol_fallback
        result = await _try_wol_fallback(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_wol_fallback_local(self):
        """When SSH fails and MAC is set, try local WoL."""
        from app.api.routes.server_profiles import _try_wol_fallback
        profile = self._mock_profile()

        with patch('app.api.routes.server_profiles._is_fritzbox_enabled', return_value=False):
            with patch('app.api.routes.server_profiles.get_sleep_manager') as mock_mgr:
                manager = MagicMock()
                manager.send_wol = AsyncMock(return_value=True)
                mock_mgr.return_value = manager

                result = await _try_wol_fallback(profile)
                assert result is not None
                assert result["success"] is True
                manager.send_wol.assert_called_once()

    @pytest.mark.asyncio
    async def test_wol_fallback_no_mac(self):
        """When SSH fails but no MAC configured, no fallback."""
        from app.api.routes.server_profiles import _try_wol_fallback
        profile = self._mock_profile(wol_mac_address=None)

        result = await _try_wol_fallback(profile)
        assert result is None

    @pytest.mark.asyncio
    async def test_wol_fallback_fritzbox(self):
        """When Fritz!Box is enabled, use Fritz!Box WoL."""
        from app.api.routes.server_profiles import _try_wol_fallback
        profile = self._mock_profile()

        with patch('app.api.routes.server_profiles._is_fritzbox_enabled', return_value=True):
            with patch('app.api.routes.server_profiles.get_fritzbox_wol_service') as mock_fb:
                fb_service = MagicMock()
                fb_service.send_wol = AsyncMock(return_value=True)
                mock_fb.return_value = fb_service

                result = await _try_wol_fallback(profile)
                assert result is not None
                assert result["success"] is True
                fb_service.send_wol.assert_called_once_with(mac="AA:BB:CC:DD:EE:FF")
