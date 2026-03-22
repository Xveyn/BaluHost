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


from unittest.mock import patch, AsyncMock, MagicMock
import httpx


class TestFritzBoxWoLService:
    """Test FritzBoxWoLService with mocked httpx."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the module-level singleton between tests."""
        import app.services.power.fritzbox_wol as mod
        mod._fritzbox_wol = None
        yield
        mod._fritzbox_wol = None

    @pytest.fixture(autouse=True)
    def disable_dev_mode(self):
        """Disable dev mode for all service tests (unless overridden per-test)."""
        with patch('app.services.power.fritzbox_wol.settings') as mock_settings:
            mock_settings.is_dev_mode = False
            yield mock_settings

    def _make_service(self):
        from app.services.power.fritzbox_wol import FritzBoxWoLService
        return FritzBoxWoLService()

    def _mock_config(self, enabled=True, host="192.168.178.1", port=49000,
                     username="", password_encrypted="", nas_mac_address="AA:BB:CC:DD:EE:FF"):
        config = MagicMock()
        config.enabled = enabled
        config.host = host
        config.port = port
        config.username = username
        config.password_encrypted = password_encrypted
        config.nas_mac_address = nas_mac_address
        return config

    @pytest.mark.asyncio
    async def test_send_wol_success(self):
        service = self._make_service()
        config = self._mock_config()

        soap_body = '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:X_AVM-DE_WakeOnLANByMACAddressResponse xmlns:u="urn:dslforum-org:service:Hosts:1"></u:X_AVM-DE_WakeOnLANByMACAddressResponse></s:Body></s:Envelope>'
        mock_response = httpx.Response(200, text=soap_body)

        with patch.object(service, '_load_config', return_value=config), \
             patch.object(service, '_decrypt_password', return_value="secret"), \
             patch('httpx.AsyncClient.post', new_callable=AsyncMock, return_value=mock_response):
            result = await service.send_wol()
            assert result is True

    @pytest.mark.asyncio
    async def test_send_wol_not_enabled(self):
        service = self._make_service()
        config = self._mock_config(enabled=False)

        with patch.object(service, '_load_config', return_value=config):
            result = await service.send_wol()
            assert result is False

    @pytest.mark.asyncio
    async def test_send_wol_no_config(self):
        service = self._make_service()

        with patch.object(service, '_load_config', return_value=None):
            result = await service.send_wol()
            assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        service = self._make_service()
        config = self._mock_config()

        mock_response = httpx.Response(200, text='<?xml version="1.0"?><scpd></scpd>')

        with patch.object(service, '_load_config', return_value=config), \
             patch.object(service, '_decrypt_password', return_value="secret"), \
             patch('httpx.AsyncClient.get', new_callable=AsyncMock, return_value=mock_response):
            ok, msg = await service.test_connection()
            assert ok is True

    @pytest.mark.asyncio
    async def test_test_connection_auth_failure(self):
        service = self._make_service()
        config = self._mock_config()

        mock_response = httpx.Response(401, text='Unauthorized')

        with patch.object(service, '_load_config', return_value=config), \
             patch.object(service, '_decrypt_password', return_value="wrong"), \
             patch('httpx.AsyncClient.get', new_callable=AsyncMock, return_value=mock_response):
            ok, msg = await service.test_connection()
            assert ok is False
            assert "Authentication failed" in msg

    @pytest.mark.asyncio
    async def test_test_connection_timeout(self):
        service = self._make_service()
        config = self._mock_config()

        with patch.object(service, '_load_config', return_value=config), \
             patch.object(service, '_decrypt_password', return_value="secret"), \
             patch('httpx.AsyncClient.get', new_callable=AsyncMock, side_effect=httpx.ConnectTimeout("timeout")):
            ok, msg = await service.test_connection()
            assert ok is False
            assert "timed out" in msg.lower()

    @pytest.mark.asyncio
    async def test_send_wol_dev_mode(self):
        service = self._make_service()

        with patch('app.services.power.fritzbox_wol.settings') as mock_settings:
            mock_settings.is_dev_mode = True
            result = await service.send_wol(mac="AA:BB:CC:DD:EE:FF")
            assert result is True


from fastapi.testclient import TestClient


class TestFritzBoxRoutes:
    """Integration tests for Fritz!Box API routes."""

    def test_get_config_requires_admin(self, client: TestClient):
        resp = client.get("/api/fritzbox/config")
        assert resp.status_code == 401

    def test_get_config_returns_defaults(self, client: TestClient, admin_headers: dict):
        resp = client.get("/api/fritzbox/config", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["host"] == "192.168.178.1"
        assert data["port"] == 49000
        assert data["enabled"] is False
        assert data["has_password"] is False
        # Password must never be exposed
        assert "password" not in data
        assert "password_encrypted" not in data

    def test_update_config(self, client: TestClient, admin_headers: dict):
        resp = client.put(
            "/api/fritzbox/config",
            headers=admin_headers,
            json={"host": "192.168.178.2", "port": 49443},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["host"] == "192.168.178.2"
        assert data["port"] == 49443

    def test_wol_fails_when_not_enabled(self, client: TestClient, admin_headers: dict):
        resp = client.post("/api/fritzbox/wol", headers=admin_headers)
        assert resp.status_code == 400

    def test_test_connection_not_enabled(self, client: TestClient, admin_headers: dict):
        resp = client.post("/api/fritzbox/test", headers=admin_headers)
        # Dev mode returns 200 with simulated message; non-enabled returns 200 or 400
        assert resp.status_code in (200, 400)
