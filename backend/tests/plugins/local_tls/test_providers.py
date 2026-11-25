"""Tests fuer die DNS-Anbieter-Adapter (Schnittstelle + DuckDNS)."""
import re

import httpx
import pytest

from app.plugins.installed.local_tls.providers import PROVIDERS, get_provider
from app.plugins.installed.local_tls.providers.base import ProviderError
from app.plugins.installed.local_tls.providers.duckdns import DuckDnsProvider

TOKEN = "12345678-1234-1234-1234-123456789abc"
CREDS = {"token": TOKEN}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_duckdns_update_sends_subdomain_and_ip():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="OK")

    DuckDnsProvider().update_address(
        "baluhost.duckdns.org", "192.168.178.53", CREDS, client=_client(handler)
    )
    assert len(seen) == 1
    req = seen[0]
    assert req.url.host == "www.duckdns.org"
    assert req.url.scheme == "https"
    assert req.url.params["domains"] == "baluhost"
    assert req.url.params["ip"] == "192.168.178.53"
    assert req.url.params["token"] == TOKEN


def test_duckdns_ko_raises_without_token_in_message():
    client = _client(lambda r: httpx.Response(200, text="KO"))
    with pytest.raises(ProviderError) as exc:
        DuckDnsProvider().update_address(
            "baluhost.duckdns.org", "192.168.178.53", CREDS, client=client
        )
    assert TOKEN not in str(exc.value)
    assert str(exc.value) == "duckdns rejected the update"


def test_duckdns_transport_error_hides_token():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom " + str(request.url))

    with pytest.raises(ProviderError) as exc:
        DuckDnsProvider().update_address(
            "baluhost.duckdns.org", "192.168.178.53", CREDS, client=_client(handler)
        )
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None


def test_duckdns_validate_domain():
    p = DuckDnsProvider()
    assert p.validate_domain("baluhost.duckdns.org")
    for bad in ("evil.com", "a.b.duckdns.org", "BALUHOST.duckdns.org.", "x.duckdns.org\n"):
        assert not p.validate_domain(bad)


def test_duckdns_lego_env():
    assert DuckDnsProvider().lego_env(CREDS) == {"DUCKDNS_TOKEN": TOKEN}


@pytest.mark.parametrize(
    "ip", ["8.8.8.8", "fe80::1", "::1", "127.0.0.1", "not-an-ip", ""]
)
def test_update_rejects_public_or_v6_ip(ip):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="OK")

    with pytest.raises(ProviderError):
        DuckDnsProvider().update_address(
            "baluhost.duckdns.org", ip, CREDS, client=_client(handler)
        )
    assert calls == []


def test_update_rejects_invalid_domain_or_token():
    calls = []
    client = _client(lambda r: calls.append(r) or httpx.Response(200, text="OK"))
    p = DuckDnsProvider()
    with pytest.raises(ProviderError):
        p.update_address("evil.com", "192.168.1.2", CREDS, client=client)
    with pytest.raises(ProviderError):
        p.update_address("baluhost.duckdns.org", "192.168.1.2", {"token": "x"}, client=client)
    assert calls == []


def test_every_registered_provider_is_complete():
    assert "duckdns" in PROVIDERS
    for pid, prov in PROVIDERS.items():
        assert prov.id == pid
        assert re.fullmatch(r"[a-z0-9_]+", prov.id)
        assert prov.display_name
        assert prov.credential_fields
        assert prov.lego_provider
        assert callable(prov.validate_domain)
        assert callable(prov.lego_env)
        assert callable(prov.update_address)
        assert get_provider(pid) is prov


def test_get_provider_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        get_provider("nope")
