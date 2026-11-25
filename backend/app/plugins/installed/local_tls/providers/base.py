"""Schnittstelle fuer DNS-Anbieter-Adapter des Plugins local_tls.

Adapter-Regeln (verbindlich fuer jeden Anbieter):

- Nur HTTPS zum eigenen Anbieter-Host, Timeout hoechstens 15 s.
- Kein Shell-Aufruf, keine Dateizugriffe.
- Domain und IP werden vor jedem Aufruf validiert; die IP muss privat und
  IPv4 sein (v1) -- Loopback, oeffentliche und IPv6-Adressen werden abgelehnt.
- Das Token steht nie in Exceptions, Logs oder URLs in Meldungen. Fehler der
  HTTP-Bibliothek enthalten oft die volle URL und werden deshalb als
  neutraler ``ProviderError`` ohne Ursache (``from None``) neu geworfen.
"""
import ipaddress
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.network_utils import is_private_or_local_ip


class ProviderError(Exception):
    """Fehler eines DNS-Anbieters. Meldung enthaelt nie Token oder Token-URL."""


@dataclass(frozen=True)
class CredentialField:
    name: str
    label_key: str
    secret: bool
    pattern: str


class DnsProvider(Protocol):
    id: str
    display_name: str
    credential_fields: tuple[CredentialField, ...]
    lego_provider: str

    def validate_domain(self, domain: str) -> bool: ...

    def lego_env(self, credentials: dict[str, str]) -> dict[str, str]: ...

    def update_address(
        self,
        domain: str,
        ip: str,
        credentials: dict[str, str],
        *,
        client: httpx.Client | None = None,
    ) -> None: ...


def is_private_ipv4(ip: str) -> bool:
    """True, wenn ip eine private (nicht-Loopback, nicht-Link-Local) IPv4 ist."""
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return not (
        addr.is_loopback
        or addr.is_link_local
        or not is_private_or_local_ip(str(addr))
    )


def require_private_ipv4(ip: str) -> None:
    """Wirft ProviderError, wenn ip keine private (nicht-Loopback) IPv4 ist."""
    if not is_private_ipv4(ip):
        raise ProviderError("address must be a private IPv4 address")
