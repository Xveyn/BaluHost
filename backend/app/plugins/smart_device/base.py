"""Base class for smart device plugins."""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.plugins.base import PluginBase
from app.plugins.smart_device.capabilities import DeviceCapability


class DeviceTypeInfo(BaseModel):
    """Describes a type of device this plugin handles."""
    type_id: str = Field(..., description="Unique type identifier, e.g. 'tapo_p115'")
    display_name: str = Field(..., description="Human-readable name, e.g. 'TP-Link Tapo P115'")
    manufacturer: str = Field(..., description="Manufacturer name")
    capabilities: List[DeviceCapability] = Field(..., description="Supported capabilities")
    config_schema: Optional[Dict[str, Any]] = Field(default=None, description="JSON Schema for device-specific config (credentials, etc.)")
    icon: str = Field(default="plug", description="Lucide icon name")


class DiscoveredDevice(BaseModel):
    """A device found during network discovery."""
    suggested_name: str
    device_type_id: str
    address: str
    mac_address: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class SmartDevicePlugin(PluginBase):
    """Base class for smart device plugins.

    Extends PluginBase with device-specific lifecycle.
    Subclasses MUST set category='smart_device' in metadata.
    """

    @abstractmethod
    def get_device_types(self) -> List[DeviceTypeInfo]:
        """Return the device types this plugin supports."""
        ...

    async def discover_devices(self) -> List[DiscoveredDevice]:
        """Scan the network for compatible devices. Optional."""
        return []

    @abstractmethod
    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        """Establish connection to a device. Called on startup and after add."""
        ...

    async def disconnect_device(self, device_id: str) -> None:
        """Disconnect from a device. Called on removal and shutdown."""
        pass

    @abstractmethod
    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        """Poll device state. Return dict mapping capability name to state data.

        Example return: {"switch": SwitchState(...), "power_monitor": PowerReading(...)}
        """
        ...

    def get_poll_interval_seconds(self) -> float:
        """Override to set custom polling interval. Default 5s."""
        return 5.0

    async def poll_device_mock(self, device_id: str) -> Dict[str, Any]:
        """Return mock data for dev mode. Override for Windows compatibility."""
        return {}
