"""Fritz!Box TR-064 Wake-on-LAN service."""
import logging
import xml.etree.ElementTree as ET
from typing import Optional

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.fritzbox import FritzBoxConfig

logger = logging.getLogger(__name__)

# TR-064 SOAP constants
_SERVICE_TYPE = "urn:dslforum-org:service:Hosts:1"
_WOL_ACTION = "X_AVM-DE_WakeOnLANByMACAddress"
_CONTROL_URL = "/upnp/control/hosts"
_SCPD_URL = "/hostsSCPD.xml"
_TIMEOUT = 10.0


def _build_soap_envelope(mac_address: str) -> str:
    """Build SOAP envelope for WoL action."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
        ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:{_WOL_ACTION} xmlns:u="{_SERVICE_TYPE}">'
        f"<NewMACAddress>{mac_address}</NewMACAddress>"
        f"</u:{_WOL_ACTION}>"
        "</s:Body>"
        "</s:Envelope>"
    )


class FritzBoxWoLService:
    """Send WoL via Fritz!Box TR-064 SOAP API.

    Singleton service — instantiated once, loads config from DB per call.
    In dev mode, simulates success without network calls.
    """

    async def send_wol(self, mac: Optional[str] = None) -> bool:
        """Send WoL via Fritz!Box. Returns True on success.

        Args:
            mac: Target MAC address. If None, uses nas_mac_address from config.
        """
        if settings.is_dev_mode:
            logger.info("[DEV] Simulated Fritz!Box WoL for MAC %s", mac or "config")
            return True

        config = self._load_config()
        if not config:
            logger.warning("Fritz!Box WoL: no config found")
            return False
        if not config.enabled:
            logger.warning("Fritz!Box WoL: integration not enabled")
            return False

        target_mac = mac or config.nas_mac_address
        if not target_mac:
            logger.warning("Fritz!Box WoL: no MAC address configured or provided")
            return False

        password = self._decrypt_password(config.password_encrypted)
        url = f"http://{config.host}:{config.port}{_CONTROL_URL}"
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{_SERVICE_TYPE}#{_WOL_ACTION}"',
        }
        body = _build_soap_envelope(target_mac)

        try:
            auth = httpx.DigestAuth(config.username, password)
            async with httpx.AsyncClient(auth=auth, timeout=_TIMEOUT) as client:
                resp = await client.post(url, content=body, headers=headers)

            if resp.status_code == 200:
                fault = self._parse_soap_fault(resp.text)
                if fault:
                    logger.error("Fritz!Box SOAP fault: %s", fault)
                    return False
                logger.info("Fritz!Box WoL sent successfully for %s", target_mac)
                return True

            if resp.status_code == 401:
                logger.error("Fritz!Box auth failed (401)")
                return False

            logger.error("Fritz!Box WoL failed: HTTP %d", resp.status_code)
            return False

        except httpx.ConnectTimeout:
            logger.error("Fritz!Box connection timed out at %s:%s", config.host, config.port)
            return False
        except httpx.ConnectError:
            logger.error("Fritz!Box not reachable at %s:%s", config.host, config.port)
            return False
        except Exception as e:
            logger.error("Fritz!Box WoL error: %s", e)
            return False

    async def test_connection(self) -> tuple[bool, str]:
        """Test Fritz!Box TR-064 connectivity.

        Returns:
            (success, message) tuple.
        """
        if settings.is_dev_mode:
            return True, "Dev mode: Fritz!Box connection simulated"

        config = self._load_config()
        if not config:
            return False, "Fritz!Box not configured"
        if not config.enabled:
            return False, "Fritz!Box integration not enabled"

        password = self._decrypt_password(config.password_encrypted)
        url = f"http://{config.host}:{config.port}{_SCPD_URL}"

        try:
            auth = httpx.DigestAuth(config.username, password)
            async with httpx.AsyncClient(auth=auth, timeout=_TIMEOUT) as client:
                resp = await client.get(url)

            if resp.status_code == 200:
                return True, f"Connected to Fritz!Box at {config.host}:{config.port}"
            if resp.status_code == 401:
                return False, "Authentication failed — check username/password"
            return False, f"Unexpected response: HTTP {resp.status_code}"

        except httpx.ConnectTimeout:
            return False, "Connection timed out"
        except httpx.ConnectError:
            return False, f"Fritz!Box not reachable at {config.host}:{config.port}"
        except Exception as e:
            return False, f"Connection error: {e}"

    def _load_config(self) -> Optional[FritzBoxConfig]:
        """Load Fritz!Box config from DB."""
        try:
            db = SessionLocal()
            try:
                return db.execute(
                    select(FritzBoxConfig).where(FritzBoxConfig.id == 1)
                ).scalar_one_or_none()
            finally:
                db.close()
        except Exception as e:
            logger.warning("Failed to load Fritz!Box config: %s", e)
            return None

    def _decrypt_password(self, encrypted: str) -> str:
        """Decrypt stored password. Returns empty string if not set or decryption fails."""
        if not encrypted:
            return ""
        try:
            from app.services.vpn.encryption import VPNEncryption
            return VPNEncryption.decrypt_key(encrypted)
        except Exception:
            logger.debug("Fritz!Box password decryption failed (key may not be set)")
            return ""

    @staticmethod
    def _parse_soap_fault(xml_text: str) -> Optional[str]:
        """Extract SOAP fault message from response XML."""
        try:
            root = ET.fromstring(xml_text)
            ns = {"s": "http://schemas.xmlsoap.org/soap/envelope/"}
            fault = root.find(".//s:Fault", ns)
            if fault is not None:
                faultstring = fault.findtext("faultstring", "Unknown SOAP fault")
                return faultstring
        except ET.ParseError:
            pass
        return None


# Module-level singleton
_fritzbox_wol: Optional[FritzBoxWoLService] = None


def get_fritzbox_wol_service() -> FritzBoxWoLService:
    """Get the singleton FritzBoxWoLService instance."""
    global _fritzbox_wol
    if _fritzbox_wol is None:
        _fritzbox_wol = FritzBoxWoLService()
    return _fritzbox_wol
