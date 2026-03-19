"""Tapo Smart Plug Plugin for BaluHost.

Provides Tapo P110/P115 smart plug integration with:
- Switch capability (on/off control)
- Power monitoring capability (watts, voltage, current, energy)

Uses plugp100 v5.x library for real hardware communication (prod mode)
and a mock service for dev mode (Windows compatible).

This plugin has no custom routes; all interaction goes through the
unified ``/api/smart-devices/`` API.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.plugins.base import DashboardPanelSpec, PluginMetadata
from app.plugins.smart_device.base import DeviceTypeInfo, SmartDevicePlugin
from app.services.monitoring.shm import SMART_DEVICES_FILE, read_shm
from app.plugins.smart_device.capabilities import (
    DeviceCapability,
    PowerReading,
    SwitchState,
)

logger = logging.getLogger(__name__)


@dataclass
class _DeviceInfo:
    """Cached connection info for a device, stored during connect_device()."""

    ip: str
    email: str
    password: str


class TapoSmartPlugPlugin(SmartDevicePlugin):
    """Tapo P110/P115 smart plug plugin for BaluHost.

    Capabilities: Switch (on/off), PowerMonitor (watts, voltage, etc.)

    In production mode, uses ``TapoService`` which communicates with real
    hardware via the plugp100 library.  In dev mode, uses ``TapoMockService``
    which returns realistic simulated data.
    """

    def __init__(self) -> None:
        # Lazy-initialized service instances
        self._service: Optional[Any] = None
        self._mock_service: Optional[Any] = None

        # device_id (str) -> _DeviceInfo (ip, email, password)
        self._device_info: Dict[str, _DeviceInfo] = {}

    # ------------------------------------------------------------------
    # PluginBase metadata
    # ------------------------------------------------------------------

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="tapo_smart_plug",
            version="1.0.0",
            display_name="Tapo Smart Plug",
            description="TP-Link Tapo P110/P115 smart plug integration with power monitoring",
            author="BaluHost",
            category="smart_device",
            required_permissions=["device:control", "network:outbound", "db:write"],
        )

    # ------------------------------------------------------------------
    # SmartDevicePlugin: device types
    # ------------------------------------------------------------------

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="tapo_p110",
                display_name="Tapo P110",
                manufacturer="TP-Link",
                capabilities=[
                    DeviceCapability.SWITCH,
                    DeviceCapability.POWER_MONITOR,
                ],
                config_schema={
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "description": "Tapo account email"},
                        "password": {"type": "string", "description": "Tapo account password"},
                    },
                    "required": ["email", "password"],
                },
                icon="plug",
            ),
            DeviceTypeInfo(
                type_id="tapo_p115",
                display_name="Tapo P115",
                manufacturer="TP-Link",
                capabilities=[
                    DeviceCapability.SWITCH,
                    DeviceCapability.POWER_MONITOR,
                ],
                config_schema={
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "description": "Tapo account email"},
                        "password": {"type": "string", "description": "Tapo account password"},
                    },
                    "required": ["email", "password"],
                },
                icon="plug",
            ),
        ]

    # ------------------------------------------------------------------
    # Translations (i18n)
    # ------------------------------------------------------------------

    def get_translations(self) -> dict[str, dict[str, str]] | None:
        return {
            "en": {
                "display_name": "Tapo Smart Plug",
                "description": "TP-Link Tapo P110/P115 smart plug integration with power monitoring",
                "panel_title": "Power Monitoring",
            },
            "de": {
                "display_name": "Tapo Steckdose",
                "description": "TP-Link Tapo P110/P115 Steckdosen-Integration mit Leistungsüberwachung",
                "panel_title": "Stromverbrauch",
            },
        }

    # ------------------------------------------------------------------
    # Dashboard Panel
    # ------------------------------------------------------------------

    def get_dashboard_panel(self) -> Optional[DashboardPanelSpec]:
        return DashboardPanelSpec(
            panel_type="gauge",
            title="Power Monitoring",
            icon="zap",
            accent="from-amber-500 to-orange-500",
        )

    async def get_dashboard_data(self, db: Any) -> Optional[dict]:
        """Aggregate power data from the Smart Device system (SHM/DB).

        Returns GaugePanelData-compatible dict:
        - value: total watts across all online power-monitoring devices
        - meta: "X devices monitored"
        - submeta: "Energy today: X.XX kWh"
        - progress: percentage of assumed max power (default 150W)
        - delta + delta_tone: "live" (trend from SHM)
        """
        from app.models.smart_device import SmartDevice

        shm_data = read_shm(SMART_DEVICES_FILE, max_age_seconds=30.0)
        devices_shm: Dict[str, Any] = {}
        if shm_data:
            devices_shm = shm_data.get("devices", {})

        # Get all active devices for this plugin
        all_devices = (
            db.query(SmartDevice)
            .filter(
                SmartDevice.plugin_name == "tapo_smart_plug",
                SmartDevice.is_active == True,  # noqa: E712
                SmartDevice.is_online == True,  # noqa: E712
            )
            .all()
        )

        total_watts = 0.0
        total_energy_kwh = 0.0
        device_count = 0

        for device in all_devices:
            entry = devices_shm.get(str(device.id))
            if not entry:
                continue
            state = entry.get("state", {})
            pm = state.get("power_monitor")
            if pm and isinstance(pm, dict):
                watts = float(pm.get("watts", 0.0))
                energy = float(pm.get("energy_today_kwh", 0.0))
                if watts > 0.0 or energy > 0.0:
                    total_watts += watts
                    total_energy_kwh += energy
                    device_count += 1

        if device_count == 0:
            return None

        max_power = 150.0
        progress = min((total_watts / max_power) * 100, 100.0)

        return {
            "value": f"{total_watts:.1f} W",
            "meta": f"{device_count} {'device' if device_count == 1 else 'devices'} monitored",
            "submeta": f"Energy today: {total_energy_kwh:.2f} kWh",
            "progress": round(progress, 1),
            "delta_tone": "live",
        }

    # ------------------------------------------------------------------
    # SmartDevicePlugin: lifecycle
    # ------------------------------------------------------------------

    async def on_startup(self) -> None:
        """Initialize the service layer (lazy, no-op here)."""
        logger.info("TapoSmartPlugPlugin started")

    async def on_shutdown(self) -> None:
        """Clean up cached clients on shutdown."""
        if self._service is not None:
            self._service.clear_cache()
        if self._mock_service is not None:
            self._mock_service.clear()
        self._device_info.clear()
        logger.info("TapoSmartPlugPlugin shut down")

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        """Establish connection to a Tapo device and cache credentials.

        Called by SmartDeviceManager when a device is created or on startup.
        The config dict is already decrypted by the manager.

        Args:
            device_id: String device ID.
            config: Decrypted config dict with ``email`` and ``password`` keys.

        Returns:
            True if connection succeeded (or mock mode always True).
        """
        email = config.get("email", "")
        password = config.get("password", "")

        if not email or not password:
            logger.warning(
                "Tapo device %s: missing email or password in config", device_id
            )
            return False

        # We need the device IP; fetch from DB if not in config
        ip = config.get("address", "")
        if not ip:
            ip = self._resolve_device_address(device_id)
        if not ip:
            logger.warning("Tapo device %s: no IP address available", device_id)
            return False

        # Store for later use during polling / commands
        self._device_info[device_id] = _DeviceInfo(ip=ip, email=email, password=password)

        # Attempt real connection in prod mode
        service = self._get_service()
        if service is self._get_mock_service():
            await service.connect(device_id)
            return True

        return await service.connect(device_id, ip, email, password)

    async def disconnect_device(self, device_id: str) -> None:
        """Disconnect from a device and clear cached state.

        Args:
            device_id: String device ID.
        """
        info = self._device_info.pop(device_id, None)
        if self._service is not None:
            self._service.disconnect(device_id)
        if self._mock_service is not None:
            self._mock_service.disconnect(device_id)

        if info:
            logger.debug("Disconnected Tapo device %s", device_id)

    # ------------------------------------------------------------------
    # SmartDevicePlugin: polling
    # ------------------------------------------------------------------

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        """Poll a real Tapo device for current state.

        If the device info is not cached (e.g., poller running in a
        separate process), it will be fetched from the database.

        Args:
            device_id: String device ID.

        Returns:
            Dict mapping capability name to state model.
        """
        info = self._ensure_device_info(device_id)
        if info is None:
            logger.warning(
                "Tapo device %s: no connection info available for polling",
                device_id,
            )
            return {}

        service = self._get_real_service()
        return await service.poll(device_id, info.ip, info.email, info.password)

    async def poll_device_mock(self, device_id: str) -> Dict[str, Any]:
        """Return mock data for dev mode.

        Args:
            device_id: String device ID.

        Returns:
            Dict mapping capability name to mock state models.
        """
        mock = self._get_mock_service()
        return await mock.poll(device_id)

    def get_poll_interval_seconds(self) -> float:
        """Tapo devices are polled every 5 seconds."""
        return 5.0

    # ------------------------------------------------------------------
    # Switch capability
    # ------------------------------------------------------------------

    async def turn_on(self, device_id: str) -> SwitchState:
        """Turn the smart plug ON.

        Args:
            device_id: String device ID.

        Returns:
            Updated SwitchState.
        """
        if self._is_dev_mode():
            return await self._get_mock_service().turn_on(device_id)

        info = self._ensure_device_info(device_id)
        if info is None:
            raise RuntimeError(f"No connection info for device {device_id}")
        return await self._get_real_service().turn_on(
            device_id, info.ip, info.email, info.password
        )

    async def turn_off(self, device_id: str) -> SwitchState:
        """Turn the smart plug OFF.

        Args:
            device_id: String device ID.

        Returns:
            Updated SwitchState.
        """
        if self._is_dev_mode():
            return await self._get_mock_service().turn_off(device_id)

        info = self._ensure_device_info(device_id)
        if info is None:
            raise RuntimeError(f"No connection info for device {device_id}")
        return await self._get_real_service().turn_off(
            device_id, info.ip, info.email, info.password
        )

    async def get_switch_state(self, device_id: str) -> SwitchState:
        """Get current switch state by polling the device.

        Args:
            device_id: String device ID.

        Returns:
            Current SwitchState.
        """
        if self._is_dev_mode():
            result = await self._get_mock_service().poll(device_id)
            return result["switch"]

        info = self._ensure_device_info(device_id)
        if info is None:
            raise RuntimeError(f"No connection info for device {device_id}")
        result = await self._get_real_service().poll(
            device_id, info.ip, info.email, info.password
        )
        return result["switch"]

    # ------------------------------------------------------------------
    # PowerMonitor capability
    # ------------------------------------------------------------------

    async def get_power(self, device_id: str) -> PowerReading:
        """Get current power reading from the device.

        Args:
            device_id: String device ID.

        Returns:
            Current PowerReading.
        """
        if self._is_dev_mode():
            return await self._get_mock_service().get_power(device_id)

        info = self._ensure_device_info(device_id)
        if info is None:
            raise RuntimeError(f"No connection info for device {device_id}")
        return await self._get_real_service().get_power(
            device_id, info.ip, info.email, info.password
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_dev_mode(self) -> bool:
        """Check if running in dev mode."""
        try:
            from app.core.config import settings
            return settings.is_dev_mode
        except Exception:
            return False

    def _get_service(self) -> Any:
        """Return the appropriate service (real or mock) based on mode."""
        if self._is_dev_mode():
            return self._get_mock_service()
        return self._get_real_service()

    def _get_real_service(self) -> Any:
        """Lazily create and return the real TapoService."""
        if self._service is None:
            from app.plugins.installed.tapo_smart_plug.service import TapoService
            self._service = TapoService()
        return self._service

    def _get_mock_service(self) -> Any:
        """Lazily create and return the mock TapoMockService."""
        if self._mock_service is None:
            from app.plugins.installed.tapo_smart_plug.mock import TapoMockService
            self._mock_service = TapoMockService()
        return self._mock_service

    def _resolve_device_address(self, device_id: str) -> Optional[str]:
        """Fetch device IP address from the database.

        Used when ``connect_device`` config doesn't include ``address``
        or when the poller needs to look up a device not yet in the cache.

        Args:
            device_id: String device ID.

        Returns:
            IP address string or None.
        """
        try:
            from app.models.smart_device import SmartDevice
            from app.core.database import SessionLocal

            db = SessionLocal()
            try:
                device = (
                    db.query(SmartDevice)
                    .filter(SmartDevice.id == int(device_id))
                    .first()
                )
                return device.address if device else None
            finally:
                db.close()
        except Exception as exc:
            logger.debug("Could not resolve address for device %s: %s", device_id, exc)
            return None

    def _ensure_device_info(self, device_id: str) -> Optional[_DeviceInfo]:
        """Return cached device info, or try to load it from DB.

        When the plugin runs in the poller (a separate process), the
        ``connect_device`` method may not have been called.  In that case
        we fetch the encrypted config from the database and decrypt it.

        Args:
            device_id: String device ID.

        Returns:
            _DeviceInfo or None if unavailable.
        """
        if device_id in self._device_info:
            return self._device_info[device_id]

        # Attempt to load from DB (the poller has its own plugin instance)
        try:
            from app.models.smart_device import SmartDevice
            from app.core.database import SessionLocal
            from app.services.vpn.encryption import VPNEncryption

            db = SessionLocal()
            try:
                device = (
                    db.query(SmartDevice)
                    .filter(SmartDevice.id == int(device_id))
                    .first()
                )
                if device is None:
                    return None

                ip = device.address
                if not ip:
                    return None

                # Decrypt config
                config: Dict[str, Any] = {}
                if device.config_secret:
                    from app.core.config import settings as app_settings
                    if app_settings.vpn_encryption_key:
                        try:
                            config = json.loads(
                                VPNEncryption.decrypt_key(device.config_secret)
                            )
                        except Exception as exc:
                            logger.warning(
                                "Could not decrypt config for device %s: %s",
                                device_id, exc,
                            )
                            return None
                    else:
                        try:
                            config = json.loads(device.config_secret)
                        except Exception as exc:
                            logger.warning(
                                "Could not parse config for device %s: %s",
                                device_id, exc,
                            )
                            return None

                email = config.get("email", "")
                password = config.get("password", "")
                if not email or not password:
                    logger.warning(
                        "Tapo device %s: missing credentials in config", device_id
                    )
                    return None

                info = _DeviceInfo(ip=ip, email=email, password=password)
                self._device_info[device_id] = info
                return info
            finally:
                db.close()

        except Exception as exc:
            logger.debug(
                "Could not load device info for %s from DB: %s", device_id, exc
            )
            return None
