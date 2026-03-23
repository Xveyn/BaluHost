"""
Linux production backend for sleep mode using real system commands.
"""
import json
import logging
import shutil
import socket
import subprocess
from datetime import datetime
from typing import Optional

from app.services.power.sleep import SleepBackend

logger = logging.getLogger(__name__)


class LinuxSleepBackend(SleepBackend):
    """Linux production backend using real system commands."""

    async def _run_cmd(self, cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
        """Run a subprocess command safely with list args."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out: %s", cmd)
            return False, "timeout"
        except Exception as e:
            logger.warning("Command failed: %s — %s", cmd, e)
            return False, str(e)

    async def spindown_disks(self, devices: list[str]) -> list[str]:
        spun_down = []
        for device in devices:
            ok, output = await self._run_cmd(["hdparm", "-y", device])
            if ok:
                spun_down.append(device)
                logger.info("Disk spindown: %s", device)
            else:
                logger.warning("Failed to spin down %s: %s", device, output)
        return spun_down

    async def spinup_disks(self, devices: list[str]) -> list[str]:
        spun_up = []
        for device in devices:
            # Reading from disk triggers spinup
            ok, output = await self._run_cmd(["hdparm", "-C", device])
            if ok:
                spun_up.append(device)
                logger.info("Disk spinup: %s", device)
            else:
                logger.warning("Failed to spin up %s: %s", device, output)
        return spun_up

    async def suspend_system(self) -> bool:
        ok, output = await self._run_cmd(["sudo", "systemctl", "suspend"], timeout=30)
        if not ok:
            logger.error("System suspend failed: %s", output)
        return ok

    async def schedule_rtc_wake(self, wake_at: datetime) -> bool:
        timestamp = str(int(wake_at.timestamp()))
        ok, output = await self._run_cmd(["sudo", "rtcwake", "-m", "no", "-l", "-t", timestamp])
        if not ok:
            logger.error("RTC wake schedule failed: %s", output)
        return ok

    async def send_wol_packet(self, mac_address: str, broadcast_address: str) -> bool:
        """Send WoL magic packet via raw socket (no subprocess needed)."""
        try:
            mac_bytes = bytes.fromhex(mac_address.replace(":", "").replace("-", ""))
            magic = b'\xff' * 6 + mac_bytes * 16
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (broadcast_address, 9))
            sock.close()
            logger.info("WoL packet sent to %s via %s", mac_address, broadcast_address)
            return True
        except Exception as e:
            logger.error("Failed to send WoL packet: %s", e)
            return False

    async def get_wol_capability(self) -> list[str]:
        """Check which interfaces support WoL via ethtool."""
        interfaces = []
        # Get network interface names
        try:
            result = subprocess.run(
                ["ip", "-o", "link", "show"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        iface = parts[1].strip()
                        if iface != "lo":
                            # Check WoL support
                            wol_result = subprocess.run(
                                ["ethtool", iface],
                                capture_output=True, text=True, timeout=5,
                            )
                            if wol_result.returncode == 0 and "Wake-on:" in wol_result.stdout:
                                for wol_line in wol_result.stdout.splitlines():
                                    if "Wake-on:" in wol_line and "d" not in wol_line.split(":")[-1]:
                                        interfaces.append(iface)
                                        break
        except Exception as e:
            logger.warning("Failed to check WoL capability: %s", e)
        return interfaces

    async def get_data_disk_devices(self) -> list[str]:
        """Get data disk devices excluding the OS disk (same pattern as RAID backend)."""
        try:
            result = subprocess.run(
                ["lsblk", "-J", "-o", "NAME,TYPE,MOUNTPOINTS"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []

            data = json.loads(result.stdout)
            os_disk_name: Optional[str] = None
            all_disks: list[str] = []

            def _check_mountpoints(device: dict) -> bool:
                """Recursively check if device or children have root mount."""
                mps = device.get("mountpoints", [])
                if mps and "/" in mps:
                    return True
                for child in device.get("children", []):
                    if _check_mountpoints(child):
                        return True
                return False

            for device in data.get("blockdevices", []):
                if device.get("type") == "disk":
                    name = device["name"]
                    if _check_mountpoints(device):
                        os_disk_name = name
                    else:
                        all_disks.append(f"/dev/{name}")

            if os_disk_name:
                logger.debug("OS disk detected: %s (excluded from spindown)", os_disk_name)

            return all_disks
        except Exception as e:
            logger.warning("Failed to enumerate data disks: %s", e)
            return []

    async def check_tool_available(self, tool: str) -> bool:
        return shutil.which(tool) is not None

    async def get_own_mac(self) -> Optional[str]:
        """Detect MAC of the primary NIC via /proc/net/route."""
        return await self._get_own_mac_from_paths(
            "/proc/net/route", "/sys/class/net"
        )

    async def _get_own_mac_from_paths(
        self, route_path: str, net_dir: str
    ) -> Optional[str]:
        """Testable implementation: reads route and sysfs from given paths."""
        try:
            with open(route_path) as f:
                for line in f:
                    parts = line.strip().split()
                    # Find the default route: Destination == 00000000
                    if len(parts) >= 2 and parts[1] == "00000000":
                        iface = parts[0]
                        mac_path = f"{net_dir}/{iface}/address"
                        try:
                            with open(mac_path) as mf:
                                raw = mf.read().strip()
                            if raw and raw != "00:00:00:00:00:00":
                                return raw.upper()
                        except OSError:
                            logger.warning("Cannot read MAC from %s", mac_path)
                            return None
        except OSError:
            logger.debug("Cannot read route table from %s", route_path)
        return None
