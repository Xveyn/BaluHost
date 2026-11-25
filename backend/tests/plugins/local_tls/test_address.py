"""Tests fuer die LAN-IP-Erkennung (ohne echten ip-Aufruf)."""
import json
import subprocess

import pytest

from app.plugins.installed.local_tls.address import AddressError, current_lan_ip


def _fake(stdout="", returncode=0, calls=None):
    def run(args, **kwargs):
        if calls is not None:
            calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    return run


def test_ip_from_default_route():
    calls = []
    out = json.dumps([{"prefsrc": "192.168.178.53", "dev": "enp12s0"}])
    assert current_lan_ip(run=_fake(out, calls=calls)) == "192.168.178.53"
    assert calls[0][0] == ["ip", "-j", "route", "get", "1.1.1.1"]
    assert calls[0][1]["timeout"] == 5
    assert not calls[0][1].get("shell")


def test_ip_from_interface_override():
    calls = []
    out = json.dumps(
        [{"ifname": "eth0", "addr_info": [{"family": "inet", "local": "10.0.0.7"}]}]
    )
    assert current_lan_ip("eth0", run=_fake(out, calls=calls)) == "10.0.0.7"
    assert calls[0][0] == ["ip", "-j", "-4", "addr", "show", "dev", "eth0"]


def test_public_ip_is_rejected():
    out = json.dumps([{"prefsrc": "8.8.8.8"}])
    with pytest.raises(AddressError):
        current_lan_ip(run=_fake(out))


def test_loopback_is_rejected():
    out = json.dumps([{"prefsrc": "127.0.0.1"}])
    with pytest.raises(AddressError):
        current_lan_ip(run=_fake(out))


@pytest.mark.parametrize("stdout,rc", [("", 2), ("[]", 0), ("not json", 0)])
def test_no_default_route_is_an_error_not_an_update(stdout, rc):
    with pytest.raises(AddressError):
        current_lan_ip(run=_fake(stdout, returncode=rc))


def test_missing_ip_binary_is_an_address_error():
    def run(args, **kwargs):
        raise FileNotFoundError("ip")

    with pytest.raises(AddressError):
        current_lan_ip(run=run)


def test_interface_name_is_validated():
    calls = []
    with pytest.raises(AddressError):
        current_lan_ip("eth0; rm", run=_fake("[]", calls=calls))
    assert calls == []
