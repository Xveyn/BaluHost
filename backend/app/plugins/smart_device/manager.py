"""SmartDeviceManager — web-worker-side coordinator.

No polling. Handles CRUD, command dispatch, and state reads from SHM
(with DB fallback).  Credential encryption via VPNEncryption.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.plugins.smart_device.base import SmartDevicePlugin
from app.plugins.smart_device.schemas import (
    SmartDeviceCreate,
    SmartDeviceUpdate,
)
from app.services.monitoring.shm import SMART_DEVICES_FILE, read_shm
from app.services.vpn.encryption import VPNEncryption

logger = logging.getLogger(__name__)


class SmartDeviceManager:
    """Web-worker-side coordinator for smart devices.

    Responsibilities:
    - CRUD operations on SmartDevice rows
    - Command dispatch to the correct SmartDevicePlugin
    - State reads from SHM (monitoring worker writes) or DB fallback
    - Credential encryption / decryption

    This manager does NOT poll devices itself; polling is handled by
    :class:`SmartDevicePoller` running in the monitoring worker process.
    """

    _instance: Optional["SmartDeviceManager"] = None

    def __init__(self) -> None:
        # Loaded plugin instances, keyed by plugin_name
        self._plugins: Dict[str, SmartDevicePlugin] = {}

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "SmartDeviceManager":
        """Return the process-level singleton."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (used in tests)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Plugin registry
    # ------------------------------------------------------------------

    def register_plugin(self, plugin: SmartDevicePlugin) -> None:
        """Register a loaded SmartDevicePlugin instance."""
        name = plugin.metadata.name
        self._plugins[name] = plugin
        logger.debug("SmartDeviceManager: registered plugin '%s'", name)

    def get_plugin(self, plugin_name: str) -> Optional[SmartDevicePlugin]:
        """Return a loaded plugin by name, or None."""
        return self._plugins.get(plugin_name)

    def list_plugins(self) -> List[SmartDevicePlugin]:
        """Return all registered SmartDevicePlugin instances."""
        return list(self._plugins.values())

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_device(
        self,
        db: Session,
        data: SmartDeviceCreate,
        created_by_user_id: int,
    ) -> SmartDevice:
        """Persist a new SmartDevice with encrypted config.

        Args:
            db: SQLAlchemy session.
            data: Validated create request.
            created_by_user_id: ID of the user creating the device.

        Returns:
            Newly created SmartDevice ORM instance.

        Raises:
            ValueError: If the plugin is unknown or config encryption fails.
        """
        plugin = self._plugins.get(data.plugin_name)
        if plugin is None:
            raise ValueError(
                f"Unknown plugin '{data.plugin_name}'. "
                f"Available: {list(self._plugins.keys())}"
            )

        # Derive capabilities from device type info
        capabilities: List[str] = []
        for dt in plugin.get_device_types():
            if dt.type_id == data.device_type_id:
                capabilities = [c.value for c in dt.capabilities]
                break

        config_secret: Optional[str] = None
        if data.config:
            config_json = json.dumps(data.config)
            from app.core.config import settings as app_settings
            if app_settings.vpn_encryption_key:
                try:
                    config_secret = VPNEncryption.encrypt_key(config_json)
                except Exception as exc:
                    raise ValueError(f"Failed to encrypt device config: {exc}") from exc
            else:
                # Dev mode without encryption key — store as plaintext
                logger.warning(
                    "VPN_ENCRYPTION_KEY not set — storing device config in plaintext. "
                    "Set VPN_ENCRYPTION_KEY in .env for production."
                )
                config_secret = config_json

        device = SmartDevice(
            name=data.name,
            plugin_name=data.plugin_name,
            device_type_id=data.device_type_id,
            address=data.address,
            mac_address=data.mac_address,
            capabilities=capabilities,
            config_secret=config_secret,
            is_active=True,
            is_online=False,
            created_by_user_id=created_by_user_id,
        )
        db.add(device)
        db.commit()
        db.refresh(device)

        # Notify the plugin about the new device (best-effort)
        if data.config:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(
                        plugin.connect_device(str(device.id), data.config)
                    )
            except Exception as exc:
                logger.warning(
                    "Could not schedule connect_device for device %d: %s",
                    device.id, exc,
                )

        logger.info(
            "Created smart device %d ('%s', plugin=%s)",
            device.id, device.name, device.plugin_name,
        )
        return device

    def get_device(self, db: Session, device_id: int) -> Optional[SmartDevice]:
        """Fetch a SmartDevice by primary key."""
        return db.query(SmartDevice).filter(SmartDevice.id == device_id).first()

    def list_devices(self, db: Session, plugin_name: Optional[str] = None) -> List[SmartDevice]:
        """List all SmartDevices, optionally filtered by plugin.

        Args:
            db: SQLAlchemy session.
            plugin_name: If given, only return devices for this plugin.

        Returns:
            List of SmartDevice ORM instances, newest first.
        """
        q = db.query(SmartDevice)
        if plugin_name:
            q = q.filter(SmartDevice.plugin_name == plugin_name)
        return q.order_by(SmartDevice.created_at.desc()).all()

    def update_device(
        self,
        db: Session,
        device: SmartDevice,
        data: SmartDeviceUpdate,
    ) -> SmartDevice:
        """Apply a partial update to a SmartDevice.

        Args:
            db: SQLAlchemy session.
            device: Existing ORM instance (already fetched).
            data: Validated update payload.

        Returns:
            Updated SmartDevice ORM instance.
        """
        update_fields = data.model_dump(exclude_unset=True)

        if "config" in update_fields and update_fields["config"] is not None:
            config_json = json.dumps(update_fields.pop("config"))
            from app.core.config import settings as app_settings
            if app_settings.vpn_encryption_key:
                try:
                    device.config_secret = VPNEncryption.encrypt_key(config_json)
                except Exception as exc:
                    raise ValueError(f"Failed to re-encrypt device config: {exc}") from exc
            else:
                device.config_secret = config_json
        else:
            update_fields.pop("config", None)

        _ALLOWED_UPDATE_FIELDS = {"name", "address", "is_active"}
        for field, value in update_fields.items():
            if field in _ALLOWED_UPDATE_FIELDS:
                setattr(device, field, value)

        device.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(device)
        logger.info("Updated smart device %d ('%s')", device.id, device.name)
        return device

    def delete_device(self, db: Session, device: SmartDevice) -> None:
        """Permanently delete a SmartDevice and its samples.

        Also calls disconnect_device on the plugin (best-effort).
        """
        plugin = self._plugins.get(device.plugin_name)
        if plugin is not None:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(plugin.disconnect_device(str(device.id)))
            except Exception as exc:
                logger.debug("disconnect_device for %d failed: %s", device.id, exc)

        db.delete(device)
        db.commit()
        logger.info("Deleted smart device %d", device.id)

    # ------------------------------------------------------------------
    # Config decryption (internal use only)
    # ------------------------------------------------------------------

    def _decrypt_config(self, device: SmartDevice) -> Dict[str, Any]:
        """Decrypt and return the device config dict (or empty dict)."""
        if not device.config_secret:
            return {}
        from app.core.config import settings as app_settings
        if app_settings.vpn_encryption_key:
            try:
                return json.loads(VPNEncryption.decrypt_key(device.config_secret))
            except Exception as exc:
                logger.warning(
                    "Could not decrypt config for device %d: %s", device.id, exc
                )
                return {}
        else:
            # No encryption key — config was stored as plaintext
            try:
                return json.loads(device.config_secret)
            except Exception as exc:
                logger.warning(
                    "Could not parse config for device %d: %s", device.id, exc
                )
                return {}

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    async def execute_command(
        self,
        device_id: int,
        capability: str,
        command: str,
        params: Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        """Execute a command on a smart device.

        Args:
            device_id: Target device primary key.
            capability: Capability group ('switch', 'dimmer', 'color').
            command: Command name ('turn_on', 'turn_off', 'set_brightness', etc.).
            params: Additional parameters (e.g. {'brightness': 80}).
            db: SQLAlchemy session (used for DB fallback / device lookup).

        Returns:
            Dict with 'success', optional 'state', and optional 'error'.

        Raises:
            ValueError: If device or plugin not found, or unknown command.
        """
        device = self.get_device(db, device_id)
        if device is None:
            raise ValueError(f"Device {device_id} not found")

        plugin = self._plugins.get(device.plugin_name)
        if plugin is None:
            raise ValueError(
                f"Plugin '{device.plugin_name}' is not loaded. "
                "Cannot execute command."
            )

        device_id_str = str(device_id)
        result_state: Optional[Any] = None

        # --- switch ---
        if capability == "switch":
            from app.plugins.smart_device.capabilities import Switch
            if not isinstance(plugin, Switch):
                raise ValueError(
                    f"Plugin '{device.plugin_name}' does not implement Switch capability"
                )
            if command == "turn_on":
                result_state = await plugin.turn_on(device_id_str)
            elif command == "turn_off":
                result_state = await plugin.turn_off(device_id_str)
            else:
                raise ValueError(f"Unknown switch command: '{command}'")

        # --- dimmer ---
        elif capability == "dimmer":
            from app.plugins.smart_device.capabilities import Dimmer
            if not isinstance(plugin, Dimmer):
                raise ValueError(
                    f"Plugin '{device.plugin_name}' does not implement Dimmer capability"
                )
            if command == "set_brightness":
                brightness = int(params.get("brightness", 100))
                result_state = await plugin.set_brightness(device_id_str, brightness)
            else:
                raise ValueError(f"Unknown dimmer command: '{command}'")

        # --- color ---
        elif capability == "color":
            from app.plugins.smart_device.capabilities import ColorControl
            if not isinstance(plugin, ColorControl):
                raise ValueError(
                    f"Plugin '{device.plugin_name}' does not implement ColorControl capability"
                )
            if command == "set_color":
                result_state = await plugin.set_color(
                    device_id_str,
                    int(params.get("hue", 0)),
                    int(params.get("saturation", 100)),
                    int(params.get("brightness", 100)),
                )
            elif command == "set_color_temp":
                result_state = await plugin.set_color_temp(
                    device_id_str,
                    int(params.get("kelvin", 4000)),
                )
            else:
                raise ValueError(f"Unknown color command: '{command}'")

        else:
            raise ValueError(f"Unknown capability: '{capability}'")

        state_dict: Optional[Dict[str, Any]] = None
        if result_state is not None:
            if hasattr(result_state, "model_dump"):
                state_dict = result_state.model_dump(mode="json")
            else:
                state_dict = dict(result_state)

        return {"success": True, "state": state_dict, "error": None}

    # ------------------------------------------------------------------
    # State read
    # ------------------------------------------------------------------

    def get_device_state(self, device_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """Read current state from SHM, falling back to the latest DB sample.

        Args:
            device_id: SmartDevice primary key.
            db: SQLAlchemy session (used for DB fallback).

        Returns:
            State dict (capability → state data) or None if unavailable.
        """
        # 1. Try SHM (monitoring worker writes every poll)
        shm_data = read_shm(SMART_DEVICES_FILE, max_age_seconds=15.0)
        if shm_data:
            devices_map = shm_data.get("devices", {})
            entry = devices_map.get(str(device_id))
            if entry:
                return entry.get("state")

        # 2. DB fallback: latest sample per capability
        try:
            samples = (
                db.query(SmartDeviceSample)
                .filter(SmartDeviceSample.device_id == device_id)
                .order_by(SmartDeviceSample.timestamp.desc())
                .limit(10)
                .all()
            )
            if not samples:
                return None

            # Aggregate: most recent sample per capability
            state: Dict[str, Any] = {}
            seen: set = set()
            for sample in samples:
                if sample.capability not in seen:
                    seen.add(sample.capability)
                    try:
                        state[sample.capability] = json.loads(sample.data_json)
                    except Exception:
                        state[sample.capability] = sample.data_json
            return state if state else None
        except Exception as exc:
            logger.debug("DB state fallback failed for device %d: %s", device_id, exc)
            return None

    # ------------------------------------------------------------------
    # Device type aggregation
    # ------------------------------------------------------------------

    def get_all_device_types(self) -> List[Dict[str, Any]]:
        """Return all device types across all loaded smart-device plugins."""
        result = []
        for plugin in self._plugins.values():
            for dt in plugin.get_device_types():
                result.append(
                    {
                        "type_id": dt.type_id,
                        "display_name": dt.display_name,
                        "manufacturer": dt.manufacturer,
                        "capabilities": [c.value for c in dt.capabilities],
                        "config_schema": dt.config_schema,
                        "icon": dt.icon,
                        "plugin_name": plugin.metadata.name,
                    }
                )
        return result

    # ------------------------------------------------------------------
    # Power summary
    # ------------------------------------------------------------------

    def get_power_summary(self, db: Session) -> Dict[str, Any]:
        """Aggregate current power readings across all online devices.

        Returns a summary dict suitable for PowerSummaryResponse.
        """
        shm_data = read_shm(SMART_DEVICES_FILE, max_age_seconds=30.0)
        devices_shm: Dict[str, Any] = {}
        if shm_data:
            devices_shm = shm_data.get("devices", {})

        all_devices = self.list_devices(db)
        total_watts = 0.0
        per_device = []

        for device in all_devices:
            if not device.is_active or not device.is_online:
                continue

            watts = 0.0
            entry = devices_shm.get(str(device.id))
            if entry:
                state = entry.get("state", {})
                pm = state.get("power_monitor")
                if pm and isinstance(pm, dict):
                    watts = float(pm.get("watts", 0.0))

            if watts > 0.0:
                total_watts += watts
                per_device.append(
                    {"device_id": device.id, "name": device.name, "watts": watts}
                )

        return {
            "total_watts": total_watts,
            "device_count": len(per_device),
            "devices": per_device,
        }


# ---------------------------------------------------------------------------
# Module-level accessor
# ---------------------------------------------------------------------------

def get_smart_device_manager() -> SmartDeviceManager:
    """Return the process-level SmartDeviceManager singleton."""
    return SmartDeviceManager.get_instance()
