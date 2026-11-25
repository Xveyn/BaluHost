"""API-Modelle des Plugins local_tls (Pydantic).

Der Anbieter-Token kommt nur in ``CredentialsRequest`` vor, nie in einer Antwort.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CredentialsRequest(BaseModel):
    # Laenge und Muster prueft die Route selbst: eine Pydantic-Validierung
    # wuerde den Token in der 422-Antwort (``input``) zurueckspiegeln.
    token: str


class StatusResponse(BaseModel):
    configured: bool
    lego: str
    lego_version: Optional[str] = None
    current_ip: Optional[str] = None
    last_ip: Optional[str] = None
    last_ip_set_at: Optional[datetime] = None
    last_dns_at: Optional[datetime] = None
    last_dns_ok: Optional[bool] = None
    last_dns_reason: Optional[str] = None
    cert_not_after: Optional[datetime] = None
    cert_fingerprint: Optional[str] = None
    served_matches: Optional[bool] = None
    last_renew_at: Optional[datetime] = None
    last_renew_ok: Optional[bool] = None
    last_renew_reason: Optional[str] = None
    running: bool
    token_set: bool
    nginx_hint: Optional[str] = None
