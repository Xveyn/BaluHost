"""Plugin local_tls: feste Adresse im Heimnetz.

Haelt einen DNS-Namen (v1: DuckDNS) auf der LAN-IP der Box und holt bzw.
erneuert per lego (DNS-01) ein Let's-Encrypt-Zertifikat dafuer, das nginx aus
``<data>/live/`` ausliefert. Keine neuen Root-Rechte: genutzt wird nur die
bestehende sudoers-Regel ``systemctl reload nginx``. Siehe CLAUDE.md.
"""
# NB: kein ``from __future__ import annotations`` (vgl. bluetooth): das Plugin
# liefert einen Router mit Pydantic-Bodies hinter slowapis Limiter.
import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.plugins.base import (
    BackgroundTaskSpec,
    PluginBase,
    PluginEventSpec,
    PluginMetadata,
)
from app.plugins.installed.local_tls import service
from app.plugins.installed.local_tls.config import LocalTlsConfig

logger = logging.getLogger(__name__)

ADDRESS_CHECK_SECONDS = 300
CERT_CHECK_SECONDS = 86400
CERT_LOCK_WAIT_SECONDS = 60
_ACTION_URL = "/settings?tab=integrations"


class LocalTlsPlugin(PluginBase):
    """Bundled Plugin fuer DNS-Namen + Zertifikat im Heimnetz."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="local_tls",
            version="1.0.0",
            display_name="Feste Adresse im Heimnetz",
            description=(
                "Hält einen DNS-Namen auf der LAN-IP der Box und erneuert dafür "
                "ein Let's-Encrypt-Zertifikat (lego, DNS-01)."
            ),
            author="Xveyn",
            category="network",
            required_permissions=[
                "network:outbound",
                "system:execute",
                "db:write",
                "task:background",
                "notification:send",
            ],
        )

    def get_config_schema(self) -> type:
        return LocalTlsConfig

    def get_default_config(self) -> Dict[str, Any]:
        return LocalTlsConfig().model_dump()

    def load_config(self, db: Session) -> LocalTlsConfig:
        """Typisierte Sicht auf ``get_config(db)`` (der einzige Lesepfad, #522)."""
        return LocalTlsConfig(**self.get_config(db))

    def get_router(self):
        """Admin-Routen (routes.py), lazy importiert wie bei steam_gaming."""
        from app.plugins.installed.local_tls.routes import router  # noqa: PLC0415

        return router

    def get_background_tasks(self) -> List[BackgroundTaskSpec]:
        return [
            BackgroundTaskSpec(
                name="address_check",
                func=self._address_check,
                interval_seconds=ADDRESS_CHECK_SECONDS,
                run_on_startup=True,
            ),
            BackgroundTaskSpec(
                name="cert_check",
                func=self._cert_check,
                interval_seconds=CERT_CHECK_SECONDS,
                run_on_startup=True,
            ),
        ]

    async def _address_check(self) -> None:
        # run_check faengt alles ab und loggt ohne Token.
        await service.run_check(service.run_address_check, self.load_config)

    async def _cert_check(self) -> None:
        # Startet zusammen mit dem Adress-Check; ohne Warten auf dessen Lock
        # fiele der Zertifikats-Check (samt Ablaufwarnung) einen Tag aus.
        await service.run_check(
            service.run_cert_check, self.load_config, lock_wait=CERT_LOCK_WAIT_SECONDS
        )

    def get_notification_events(self) -> List[PluginEventSpec]:
        return [
            PluginEventSpec(
                id=service.EVENT_CERT_EXPIRING,
                notification_type="warning",
                priority=1,
                title_template="Zertifikat für {domain} läuft bald ab",
                message_template=(
                    "Das Zertifikat für {domain} läuft in {days} Tagen ab und wurde "
                    "bisher nicht automatisch erneuert."
                ),
                action_url=_ACTION_URL,
                cooldown_seconds=86400,
            ),
            PluginEventSpec(
                id=service.EVENT_RENEW_FAILED,
                notification_type="critical",
                priority=2,
                title_template="Zertifikat für {domain} nicht erneuert",
                message_template=(
                    "Erneuern oder Installieren des Zertifikats für {domain} ist "
                    "gescheitert: {reason}"
                ),
                action_url=_ACTION_URL,
                cooldown_seconds=86400,
            ),
            PluginEventSpec(
                id=service.EVENT_DNS_UPDATE_FAILED,
                notification_type="warning",
                priority=1,
                title_template="DNS-Eintrag für {domain} nicht aktualisiert",
                message_template=(
                    "Die Heimnetz-Adresse für {domain} konnte nicht gesetzt werden: {reason}"
                ),
                action_url=_ACTION_URL,
                cooldown_seconds=3600,
            ),
            PluginEventSpec(
                id=service.EVENT_ADDRESS_CHANGED,
                notification_type="info",
                priority=0,
                title_template="Neue Heimnetz-Adresse für {domain}",
                message_template="{domain} zeigt jetzt auf {ip}.",
                action_url=_ACTION_URL,
                cooldown_seconds=0,
            ),
        ]
