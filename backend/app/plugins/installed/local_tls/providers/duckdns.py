"""DuckDNS-Adapter (HTTPS-Update-API, ein Token)."""
import re

import httpx

from .base import CredentialField, ProviderError, require_private_ipv4

_DOMAIN_RE = re.compile(r"([a-z0-9-]{1,63})\.duckdns\.org")
_TOKEN_RE = re.compile(r"[0-9a-f-]{36}")
_UPDATE_URL = "https://www.duckdns.org/update"
_TIMEOUT = 15.0


class DuckDnsProvider:
    id = "duckdns"
    display_name = "DuckDNS"
    lego_provider = "duckdns"
    credential_fields = (
        CredentialField(
            name="token",
            label_key="providers.duckdns.token",
            secret=True,
            pattern=r"^[0-9a-f-]{36}$",
        ),
    )

    def validate_domain(self, domain: str) -> bool:
        return _DOMAIN_RE.fullmatch(domain) is not None

    def lego_env(self, credentials: dict[str, str]) -> dict[str, str]:
        return {"DUCKDNS_TOKEN": credentials["token"]}

    def update_address(
        self,
        domain: str,
        ip: str,
        credentials: dict[str, str],
        *,
        client: httpx.Client | None = None,
    ) -> None:
        match = _DOMAIN_RE.fullmatch(domain)
        if match is None:
            raise ProviderError("invalid duckdns domain")
        require_private_ipv4(ip)
        token = credentials.get("token", "")
        if _TOKEN_RE.fullmatch(token) is None:
            raise ProviderError("invalid duckdns token")
        params = {"domains": match.group(1), "token": token, "ip": ip}
        own = client is None
        http = client or httpx.Client(timeout=_TIMEOUT)
        try:
            response = http.get(_UPDATE_URL, params=params, timeout=_TIMEOUT)
            body = response.text.strip()
        except httpx.HTTPError:
            raise ProviderError("duckdns request failed") from None
        finally:
            if own:
                http.close()
        if response.status_code != 200 or body != "OK":
            raise ProviderError("duckdns rejected the update")
