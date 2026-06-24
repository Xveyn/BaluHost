"""Tests for FritzBoxVPNService.parse_fritzbox_config secret redaction (issue #258)."""
import pytest

from app.services.vpn.fritzbox import FritzBoxVPNService


# A valid complete config to verify normal parsing still works
_VALID_CONFIG = """\
[Interface]
PrivateKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
Address = 10.0.0.2/32
DNS = 8.8.8.8

[Peer]
PublicKey = BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=
PresharedKey = CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC=
AllowedIPs = 0.0.0.0/0
Endpoint = example.com:51820
PersistentKeepalive = 25
"""

# A config with PrivateKey under [Interface] but missing the required 'endpoint'
# and 'listen_port' fields, which triggers the ValueError with the debug dump.
_MISSING_ENDPOINT_CONFIG = """\
[Interface]
PrivateKey = SUPERSECRETPRIVATEKEYVALUE12345678901234567=
Address = 10.0.0.2/32
DNS = 8.8.8.8

[Peer]
PublicKey = BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=
PresharedKey = SUPERSECRETPRESHAREDKEYVALUE123456789012345=
AllowedIPs = 0.0.0.0/0
"""

_INTERFACE_PRIVATE_KEY = "SUPERSECRETPRIVATEKEYVALUE12345678901234567="
_PEER_PRESHARED_KEY = "SUPERSECRETPRESHAREDKEYVALUE123456789012345="


def test_parse_raises_valueerror_on_missing_endpoint():
    """ValueError is raised when Endpoint is absent (behavior preserved)."""
    with pytest.raises(ValueError):
        FritzBoxVPNService.parse_fritzbox_config(_MISSING_ENDPOINT_CONFIG)


def test_interface_privatekey_not_in_error_message():
    """PrivateKey value must NOT appear in the ValueError message."""
    with pytest.raises(ValueError) as exc_info:
        FritzBoxVPNService.parse_fritzbox_config(_MISSING_ENDPOINT_CONFIG)
    assert _INTERFACE_PRIVATE_KEY not in str(exc_info.value)


def test_peer_presharedkey_not_in_error_message():
    """PresharedKey value must NOT appear in the ValueError message."""
    with pytest.raises(ValueError) as exc_info:
        FritzBoxVPNService.parse_fritzbox_config(_MISSING_ENDPOINT_CONFIG)
    assert _PEER_PRESHARED_KEY not in str(exc_info.value)


def test_redacted_marker_present_in_error_message():
    """<redacted> marker must appear in the debug dump embedded in the error."""
    with pytest.raises(ValueError) as exc_info:
        FritzBoxVPNService.parse_fritzbox_config(_MISSING_ENDPOINT_CONFIG)
    assert "<redacted>" in str(exc_info.value)


def test_valid_config_parsed_correctly():
    """Normal parsing still works; no regression on the happy path."""
    result = FritzBoxVPNService.parse_fritzbox_config(_VALID_CONFIG)
    assert result["private_key"] == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    assert result["peer_public_key"] == "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB="
    assert result["preshared_key"] == "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC="
    assert result["endpoint"] == "example.com:51820"
