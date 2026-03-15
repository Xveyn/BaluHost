"""
Development backend for sleep mode that simulates all operations in-memory.
"""
import asyncio
import logging

from app.services.power.sleep import SleepBackend

logger = logging.getLogger(__name__)


class DevSleepBackend(SleepBackend):
    """Development backend that simulates all sleep operations in-memory."""

    def __init__(self) -> None:
        self._spun_down: set[str] = set()
        self._suspended = False

    async def spindown_disks(self, devices: list[str]) -> list[str]:
        self._spun_down.update(devices)
        logger.info("[DEV] Simulated disk spindown: %s", devices)
        return devices

    async def spinup_disks(self, devices: list[str]) -> list[str]:
        self._spun_down.discard(*devices) if len(devices) == 1 else self._spun_down.difference_update(devices)
        logger.info("[DEV] Simulated disk spinup: %s", devices)
        return devices

    async def suspend_system(self) -> bool:
        self._suspended = True
        logger.info("[DEV] Simulated system suspend")
        # Simulate waking up after a short delay
        await asyncio.sleep(2)
        self._suspended = False
        logger.info("[DEV] Simulated system wake from suspend")
        return True

    async def schedule_rtc_wake(self, wake_at) -> bool:
        logger.info("[DEV] Simulated RTC wake scheduled for %s", wake_at.isoformat())
        return True

    async def send_wol_packet(self, mac_address: str, broadcast_address: str) -> bool:
        logger.info("[DEV] Simulated WoL packet sent to %s via %s", mac_address, broadcast_address)
        return True

    async def get_wol_capability(self) -> list[str]:
        return ["eth0"]

    async def get_data_disk_devices(self) -> list[str]:
        return ["/dev/sda", "/dev/sdb"]

    async def check_tool_available(self, tool: str) -> bool:
        return True
