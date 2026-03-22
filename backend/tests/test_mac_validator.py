"""Tests for shared MAC address validator."""
import pytest
from app.schemas.validators import validate_mac_address


class TestValidateMacAddress:
    """Test the reusable MAC address validator."""

    def test_none_passes_through(self):
        assert validate_mac_address(None) is None

    def test_empty_string_becomes_none(self):
        assert validate_mac_address("") is None

    def test_valid_colon_format(self):
        assert validate_mac_address("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"

    def test_valid_dash_format(self):
        assert validate_mac_address("AA-BB-CC-DD-EE-FF") == "AA:BB:CC:DD:EE:FF"

    def test_mixed_case_normalized(self):
        assert validate_mac_address("aA:Bb:cC:dD:eE:fF") == "AA:BB:CC:DD:EE:FF"

    def test_invalid_too_short(self):
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("AA:BB:CC")

    def test_invalid_bad_chars(self):
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("GG:HH:II:JJ:KK:LL")

    def test_invalid_no_separator(self):
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("AABBCCDDEEFF")

    def test_invalid_wrong_separator(self):
        with pytest.raises(ValueError, match="Invalid MAC address"):
            validate_mac_address("AA.BB.CC.DD.EE.FF")

    def test_whitespace_stripped(self):
        assert validate_mac_address("  AA:BB:CC:DD:EE:FF  ") == "AA:BB:CC:DD:EE:FF"
