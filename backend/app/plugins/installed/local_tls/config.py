"""Einstellungen des Plugins local_tls (``InstalledPlugin.config``).

Kein Geheimnis hier: der Anbieter-Token liegt verschluesselt in
``local_tls_state.provider_secret`` und wird nur ueber die eigene Route gesetzt.
Domain, Interface und E-Mail landen als Argumente im lego-/ip-Aufruf; was mit
``-`` beginnt, wird deshalb abgelehnt (keine Option-Injektion).
"""
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.plugins.installed.local_tls import providers

_IFACE_RE = re.compile(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,14}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LABEL_RE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


class LocalTlsConfig(BaseModel):
    """Domain, DNS-Anbieter und Optionen fuer Adress- und Zertifikats-Check."""

    domain: str = Field(
        default="",
        max_length=253,
        description="DNS-Name, der auf die LAN-IP der Box zeigt (z. B. meinebox.duckdns.org)",
    )
    provider: str = Field(default="duckdns", description="DNS-Anbieter")
    interface: Optional[str] = Field(
        default=None,
        description="Netzwerkschnittstelle fuer die LAN-IP (leer = Standardroute)",
    )
    email: Optional[str] = Field(
        default=None,
        max_length=254,
        description="Optionale Kontakt-E-Mail fuer Let's Encrypt",
    )
    staging: bool = Field(
        default=False,
        description="Let's-Encrypt-Staging verwenden (Testzertifikate, nicht vertrauenswuerdig)",
    )

    @field_validator("domain", mode="before")
    @classmethod
    def _normalize_domain(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, value: str) -> str:
        if value not in providers.PROVIDERS:
            raise ValueError("unknown DNS provider")
        return value

    @field_validator("interface", mode="before")
    @classmethod
    def _check_interface(cls, value: object) -> object:
        if isinstance(value, str):
            value = _blank_to_none(value)
            if value is not None and not _IFACE_RE.fullmatch(value):
                raise ValueError("invalid interface name")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def _check_email(cls, value: object) -> object:
        if isinstance(value, str):
            value = _blank_to_none(value)
            if value is not None and not _EMAIL_RE.fullmatch(value):
                raise ValueError("invalid e-mail address")
        return value

    @model_validator(mode="after")
    def _check_domain(self) -> "LocalTlsConfig":
        if not self.domain:
            return self
        labels = self.domain.split(".")
        if not all(_LABEL_RE.fullmatch(label) for label in labels):
            raise ValueError("invalid domain")
        if not providers.get_provider(self.provider).validate_domain(self.domain):
            raise ValueError("domain does not belong to the selected DNS provider")
        return self
