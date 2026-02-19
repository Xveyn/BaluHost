"""Tests for network utility functions."""
import pytest
from app.core.network_utils import is_private_or_local_ip, is_localhost


class TestIsPrivateOrLocalIP:
    """Tests for is_private_or_local_ip() function."""

    # Localhost addresses
    def test_ipv4_localhost(self):
        assert is_private_or_local_ip("127.0.0.1") is True

    def test_ipv6_localhost(self):
        assert is_private_or_local_ip("::1") is True

    def test_localhost_string(self):
        assert is_private_or_local_ip("localhost") is True
        assert is_private_or_local_ip("LOCALHOST") is True
        assert is_private_or_local_ip("LocalHost") is True

    # Private IPv4 ranges (RFC 1918)
    def test_class_a_private(self):
        """10.0.0.0/8 - Class A private network."""
        assert is_private_or_local_ip("10.0.0.1") is True
        assert is_private_or_local_ip("10.8.0.1") is True  # WireGuard VPN
        assert is_private_or_local_ip("10.255.255.255") is True

    def test_class_b_private(self):
        """172.16.0.0/12 - Class B private network."""
        assert is_private_or_local_ip("172.16.0.1") is True
        assert is_private_or_local_ip("172.31.255.255") is True
        # 172.32.0.0 is NOT private
        assert is_private_or_local_ip("172.32.0.1") is False

    def test_class_c_private(self):
        """192.168.0.0/16 - Class C private network."""
        assert is_private_or_local_ip("192.168.0.1") is True
        assert is_private_or_local_ip("192.168.1.100") is True
        assert is_private_or_local_ip("192.168.255.255") is True

    # Link-local addresses
    def test_ipv4_link_local(self):
        """169.254.0.0/16 - IPv4 link-local (APIPA)."""
        assert is_private_or_local_ip("169.254.1.1") is True
        assert is_private_or_local_ip("169.254.255.255") is True

    def test_ipv6_link_local(self):
        """fe80::/10 - IPv6 link-local."""
        assert is_private_or_local_ip("fe80::1") is True
        assert is_private_or_local_ip("fe80::abcd:1234:5678:9abc") is True

    # IPv6 unique local addresses (ULA)
    def test_ipv6_unique_local(self):
        """fc00::/7 - IPv6 unique local addresses."""
        assert is_private_or_local_ip("fc00::1") is True
        assert is_private_or_local_ip("fd00::1") is True
        assert is_private_or_local_ip("fd12:3456:789a::1") is True

    # Public IP addresses (should return False)
    def test_public_ipv4(self):
        """Public IPv4 addresses should return False."""
        assert is_private_or_local_ip("8.8.8.8") is False
        assert is_private_or_local_ip("1.1.1.1") is False
        assert is_private_or_local_ip("93.184.216.34") is False  # example.com
        assert is_private_or_local_ip("142.250.185.14") is False  # google.com

    def test_public_ipv6(self):
        """Public IPv6 addresses should return False."""
        assert is_private_or_local_ip("2001:4860:4860::8888") is False  # Google DNS
        assert is_private_or_local_ip("2606:4700:4700::1111") is False  # Cloudflare

    # IPv6-mapped IPv4 addresses
    def test_ipv6_mapped_ipv4_private(self):
        """IPv6-mapped IPv4 private addresses."""
        assert is_private_or_local_ip("::ffff:192.168.1.1") is True
        assert is_private_or_local_ip("::ffff:10.0.0.1") is True
        assert is_private_or_local_ip("::ffff:127.0.0.1") is True

    def test_ipv6_mapped_ipv4_public(self):
        """IPv6-mapped IPv4 public addresses."""
        assert is_private_or_local_ip("::ffff:8.8.8.8") is False

    # Edge cases
    def test_none_input(self):
        assert is_private_or_local_ip(None) is False

    def test_empty_string(self):
        assert is_private_or_local_ip("") is False

    def test_invalid_ip(self):
        assert is_private_or_local_ip("not-an-ip") is False
        assert is_private_or_local_ip("256.256.256.256") is False
        assert is_private_or_local_ip("192.168.1") is False

    def test_whitespace(self):
        assert is_private_or_local_ip(" ") is False
        assert is_private_or_local_ip("  192.168.1.1  ") is False  # No trimming


class TestIsLocalhost:
    """Tests for is_localhost() function."""

    # Valid localhost addresses
    def test_ipv4_localhost(self):
        assert is_localhost("127.0.0.1") is True

    def test_ipv6_localhost(self):
        assert is_localhost("::1") is True

    def test_localhost_string(self):
        assert is_localhost("localhost") is True
        assert is_localhost("LOCALHOST") is True
        assert is_localhost("LocalHost") is True

    def test_ipv6_mapped_localhost(self):
        """IPv6-mapped IPv4 loopback."""
        assert is_localhost("::ffff:127.0.0.1") is True

    # Loopback range (127.0.0.0/8)
    def test_ipv4_loopback_range(self):
        """Entire 127.0.0.0/8 is loopback."""
        assert is_localhost("127.0.0.2") is True
        assert is_localhost("127.255.255.255") is True

    # Private IPs are NOT localhost
    def test_private_ips_not_localhost(self):
        """Private IPs should NOT be considered localhost."""
        assert is_localhost("192.168.1.1") is False
        assert is_localhost("10.0.0.1") is False
        assert is_localhost("172.16.0.1") is False

    # Public IPs are NOT localhost
    def test_public_ips_not_localhost(self):
        """Public IPs should NOT be considered localhost."""
        assert is_localhost("8.8.8.8") is False
        assert is_localhost("2001:4860:4860::8888") is False

    # Edge cases
    def test_none_input(self):
        assert is_localhost(None) is False

    def test_empty_string(self):
        assert is_localhost("") is False

    def test_invalid_ip(self):
        assert is_localhost("not-an-ip") is False
        assert is_localhost("999.999.999.999") is False
