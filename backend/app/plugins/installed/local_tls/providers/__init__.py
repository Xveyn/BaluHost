"""Registry der DNS-Anbieter-Adapter."""
from .base import CredentialField, DnsProvider, ProviderError
from .duckdns import DuckDnsProvider

PROVIDERS: dict[str, DnsProvider] = {
    p.id: p for p in (DuckDnsProvider(),)
}


def get_provider(provider_id: str) -> DnsProvider:
    """Liefert den Adapter; KeyError bei unbekannter ID."""
    return PROVIDERS[provider_id]


__all__ = [
    "CredentialField",
    "DnsProvider",
    "ProviderError",
    "PROVIDERS",
    "get_provider",
]
