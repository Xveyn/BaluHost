"""upstream_dns IP-validation for the Pi-hole container resolv.conf (audit #7)."""
from app.services.pihole.docker_backend import _build_resolv_lines


def test_valid_ips_become_nameserver_lines():
    assert _build_resolv_lines("1.1.1.1;1.0.0.1") == "nameserver 1.1.1.1\nnameserver 1.0.0.1"


def test_ipv6_allowed():
    assert _build_resolv_lines("2606:4700:4700::1111") == "nameserver 2606:4700:4700::1111"


def test_shell_metachar_entry_is_dropped():
    # An injection attempt is not a valid IP → excluded entirely.
    assert _build_resolv_lines("1.1.1.1; rm -rf /") == "nameserver 1.1.1.1"


def test_all_invalid_yields_empty():
    assert _build_resolv_lines("not-an-ip;$(whoami)") == ""


def test_whitespace_and_blanks_ignored():
    assert _build_resolv_lines(" 8.8.8.8 ; ; 8.8.4.4 ") == "nameserver 8.8.8.8\nnameserver 8.8.4.4"
