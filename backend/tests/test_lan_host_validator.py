"""Tests for the LAN-host / LAN-URL SSRF-hardening validators.

Policy (Posten 4, admin-gated SSRF hardening):
- IP literals must be private/local (RFC1918, loopback, link-local, IPv6-ULA).
- Public IP literals are rejected.
- Hostnames are allowed as-is (NOT resolved — no DNS in the validator).
- None / empty → None.
"""
import pytest

from app.schemas.validators import validate_lan_host, validate_lan_url


class TestValidateLanHost:
    def test_none_returns_none(self):
        assert validate_lan_host(None) is None

    def test_empty_returns_none(self):
        assert validate_lan_host("") is None
        assert validate_lan_host("   ") is None

    def test_private_ipv4_allowed(self):
        assert validate_lan_host("192.168.1.50") == "192.168.1.50"
        assert validate_lan_host("10.0.0.1") == "10.0.0.1"
        assert validate_lan_host("172.16.0.1") == "172.16.0.1"

    def test_loopback_allowed(self):
        assert validate_lan_host("127.0.0.1") == "127.0.0.1"

    def test_link_local_allowed(self):
        assert validate_lan_host("169.254.1.1") == "169.254.1.1"

    def test_private_ipv6_allowed(self):
        assert validate_lan_host("fd00::1") == "fd00::1"

    def test_hostname_allowed_unresolved(self):
        assert validate_lan_host("fritz.box") == "fritz.box"
        assert validate_lan_host("pi.hole") == "pi.hole"
        assert validate_lan_host("localhost") == "localhost"

    def test_public_ipv4_rejected(self):
        with pytest.raises(ValueError):
            validate_lan_host("1.2.3.4")
        with pytest.raises(ValueError):
            validate_lan_host("8.8.8.8")

    def test_public_ipv6_rejected(self):
        with pytest.raises(ValueError):
            validate_lan_host("2001:4860:4860::8888")

    def test_ipv6_mapped_public_ipv4_rejected(self):
        with pytest.raises(ValueError):
            validate_lan_host("::ffff:1.2.3.4")

    def test_whitespace_stripped(self):
        assert validate_lan_host("  192.168.1.50  ") == "192.168.1.50"


class TestValidateLanUrl:
    def test_none_returns_none(self):
        assert validate_lan_url(None) is None

    def test_empty_returns_none(self):
        assert validate_lan_url("") is None

    def test_private_host_url_allowed(self):
        assert validate_lan_url("http://192.168.1.50:80") == "http://192.168.1.50:80"

    def test_hostname_url_allowed(self):
        assert validate_lan_url("http://pi.hole") == "http://pi.hole"

    def test_https_allowed(self):
        assert validate_lan_url("https://192.168.1.50") == "https://192.168.1.50"

    def test_public_host_url_rejected(self):
        with pytest.raises(ValueError):
            validate_lan_url("http://1.2.3.4:80")

    def test_non_http_scheme_rejected(self):
        with pytest.raises(ValueError):
            validate_lan_url("file:///etc/passwd")
        with pytest.raises(ValueError):
            validate_lan_url("gopher://192.168.1.50")

    def test_missing_host_rejected(self):
        with pytest.raises(ValueError):
            validate_lan_url("http://")


class TestFritzBoxConfigUpdateHost:
    def test_public_ip_host_rejected(self):
        from app.schemas.fritzbox import FritzBoxConfigUpdate
        with pytest.raises(ValueError):
            FritzBoxConfigUpdate(host="1.2.3.4")

    def test_private_ip_host_allowed(self):
        from app.schemas.fritzbox import FritzBoxConfigUpdate
        assert FritzBoxConfigUpdate(host="192.168.178.1").host == "192.168.178.1"

    def test_hostname_allowed(self):
        from app.schemas.fritzbox import FritzBoxConfigUpdate
        assert FritzBoxConfigUpdate(host="fritz.box").host == "fritz.box"

    def test_host_omitted_is_none(self):
        from app.schemas.fritzbox import FritzBoxConfigUpdate
        assert FritzBoxConfigUpdate().host is None


class TestSmartDeviceAddress:
    def test_create_public_ip_rejected(self):
        from app.plugins.smart_device.schemas import SmartDeviceCreate
        with pytest.raises(ValueError):
            SmartDeviceCreate(
                name="Plug", plugin_name="tapo_smart_plug",
                device_type_id="p110", address="1.2.3.4",
            )

    def test_create_private_ip_allowed(self):
        from app.plugins.smart_device.schemas import SmartDeviceCreate
        dev = SmartDeviceCreate(
            name="Plug", plugin_name="tapo_smart_plug",
            device_type_id="p110", address="192.168.1.55",
        )
        assert dev.address == "192.168.1.55"

    def test_update_public_ip_rejected(self):
        from app.plugins.smart_device.schemas import SmartDeviceUpdate
        with pytest.raises(ValueError):
            SmartDeviceUpdate(address="8.8.8.8")

    def test_update_address_omitted_is_none(self):
        from app.plugins.smart_device.schemas import SmartDeviceUpdate
        assert SmartDeviceUpdate().address is None


class TestPiholeConfigUpdateUrls:
    def test_public_pihole_url_rejected(self):
        from app.schemas.pihole import PiholeConfigUpdateRequest
        with pytest.raises(ValueError):
            PiholeConfigUpdateRequest(pihole_url="http://1.2.3.4:80")

    def test_private_pihole_url_allowed(self):
        from app.schemas.pihole import PiholeConfigUpdateRequest
        req = PiholeConfigUpdateRequest(pihole_url="http://192.168.1.50:80")
        assert req.pihole_url == "http://192.168.1.50:80"

    def test_public_remote_pihole_url_rejected(self):
        from app.schemas.pihole import PiholeConfigUpdateRequest
        with pytest.raises(ValueError):
            PiholeConfigUpdateRequest(remote_pihole_url="http://9.9.9.9")

    def test_hostname_pihole_url_allowed(self):
        from app.schemas.pihole import PiholeConfigUpdateRequest
        req = PiholeConfigUpdateRequest(pihole_url="http://pi.hole")
        assert req.pihole_url == "http://pi.hole"
