from __future__ import annotations

import json
import logging
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.schemas.system import (
    AvailableDisk,
    AvailableDisksResponse,
    CreateArrayRequest,
    DeleteArrayRequest,
    FormatDiskRequest,
    RaidActionResponse,
    RaidArray,
    RaidDevice,
    RaidOptionsRequest,
    RaidSimulationRequest,
    RaidSpeedLimits,
    RaidStatusResponse,
)

from app.services.hardware.raid.parsing import (
    MdstatInfo,
    _derive_array_status,
    _extract_detail_value,
    _map_device_state,
    _parse_mdstat,
)

logger = logging.getLogger(__name__)


class MdadmRaidBackend:
    _MDSTAT_PATH = Path("/proc/mdstat")

    def __init__(self) -> None:
        if not self.is_supported():
            raise RuntimeError("mdadm backend is not available on this system")
        self._lsblk_available = shutil.which("lsblk") is not None

    @staticmethod
    def is_supported() -> bool:
        return platform.system().lower() == "linux" and shutil.which("mdadm") is not None

    def get_status(self) -> RaidStatusResponse:
        mdstat_info = self._read_mdstat()
        array_names = set(mdstat_info.keys()) | set(self._scan_arrays())

        if not array_names:
            return RaidStatusResponse(
                arrays=[],
                speed_limits=self._read_speed_limits(),
            )

        disk_type_map = self._get_disk_type_map()

        arrays: List[RaidArray] = []
        for name in sorted(array_names):
            info = mdstat_info.get(name)
            arrays.append(self._build_array(name, info, disk_type_map))

        speed_limits = self._read_speed_limits()

        return RaidStatusResponse(
            arrays=arrays,
            speed_limits=speed_limits,
        )

    def degrade(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        if not payload.device:
            raise ValueError("Device must be provided when failing a RAID member")

        array_path = self._normalize_array(payload.array)
        device_path = self._normalize_device(payload.device)

        self._run(["mdadm", array_path, "--fail", device_path])
        logger.info("Marked device %s as failed in %s", device_path, array_path)
        return RaidActionResponse(message=f"Array {payload.array} marked as degraded (failed {device_path})")

    def rebuild(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        if not payload.device:
            raise ValueError("Device must be provided to start a rebuild")

        array_path = self._normalize_array(payload.array)
        device_path = self._normalize_device(payload.device)

        # Removing the device might fail if it has already been detached; ignore such errors.
        self._run(["mdadm", array_path, "--remove", device_path], check=False)
        self._run(["mdadm", array_path, "--add", device_path])
        logger.info("Rebuild initiated for %s in %s", device_path, array_path)
        return RaidActionResponse(message=f"Array {payload.array} rebuild started for {device_path}")

    def finalize(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        array_path = self._normalize_array(payload.array)
        self._run(["mdadm", "--wait", array_path], timeout=600)

        status = self.get_status()
        array = next((item for item in status.arrays if item.name == payload.array or f"/dev/{item.name}" == payload.array), None)
        if array and array.status != "optimal":
            raise RuntimeError(f"Array {payload.array} is not optimal yet (current status: {array.status})")

        return RaidActionResponse(message=f"Array {payload.array} synchronized and optimal")

    def configure(self, payload: RaidOptionsRequest) -> RaidActionResponse:
        array_path = self._normalize_array(payload.array)
        actions: List[str] = []

        if payload.enable_bitmap is not None:
            option = "internal" if payload.enable_bitmap else "none"
            self._run(["mdadm", array_path, "--grow", f"--bitmap={option}"])
            actions.append(f"bitmap set to {option}")

        if payload.add_spare:
            device_path = self._normalize_device(payload.add_spare)
            self._run(["mdadm", array_path, "--add", device_path])
            actions.append(f"added spare {device_path}")

        if payload.remove_device:
            device_path = self._normalize_device(payload.remove_device)
            self._run(["mdadm", array_path, "--remove", device_path])
            actions.append(f"removed device {device_path}")

        if payload.write_mostly_device:
            device_path = self._normalize_device(payload.write_mostly_device)
            if payload.write_mostly is False:
                self._run(["mdadm", array_path, "--readwrite", device_path])
                actions.append(f"set {device_path} readwrite")
            else:
                self._run(["mdadm", array_path, "--write-mostly", device_path])
                actions.append(f"set {device_path} write-mostly")

        if payload.trigger_scrub:
            self._set_sync_action(payload.array, "check")
            actions.append("triggered scrub")

        if payload.set_speed_limit_min is not None:
            self._write_proc_value(
                Path("/proc/sys/dev/raid/speed_limit_min"),
                str(max(0, payload.set_speed_limit_min)),
            )
            actions.append(f"speed_limit_min={payload.set_speed_limit_min}")

        if payload.set_speed_limit_max is not None:
            max_value = max(
                payload.set_speed_limit_min or 0,
                payload.set_speed_limit_max,
            )
            self._write_proc_value(
                Path("/proc/sys/dev/raid/speed_limit_max"),
                str(max_value),
            )
            actions.append(f"speed_limit_max={max_value}")

        if not actions:
            raise ValueError("No RAID configuration changes supplied")

        return RaidActionResponse(message="; ".join(actions))

    def _build_array(self, name: str, info: Optional[MdstatInfo],
                      disk_type_map: Optional[Dict[str, str]] = None) -> RaidArray:
        detail = self._run(["mdadm", "--detail", f"/dev/{name}"]).stdout

        level = _extract_detail_value(detail, "Raid Level") or "unknown"
        state_line = _extract_detail_value(detail, "State")

        size_bytes = self._resolve_array_size(name, info, detail)
        resync_progress = self._resolve_progress(info, detail)
        devices = self._parse_devices(detail)
        sync_action = self._read_sync_action(name)
        status = _derive_array_status(state_line, resync_progress, devices, sync_action)
        bitmap_info = _extract_detail_value(detail, "Bitmap")

        # Enrich devices with disk type from lsblk data
        if disk_type_map:
            for dev in devices:
                # Strip partition number to get parent disk (e.g. sda1 -> sda)
                parent = re.sub(r"p?\d+$", "", dev.name)
                dev.disk_type = disk_type_map.get(parent, "hdd")

        return RaidArray(
            name=name,
            level=level.lower(),
            size_bytes=size_bytes,
            status=status,
            devices=devices,
            resync_progress=resync_progress,
            bitmap=bitmap_info,
            sync_action=sync_action,
        )

    def _resolve_array_size(self, name: str, info: Optional[MdstatInfo], detail: str) -> int:
        if info and info.blocks is not None:
            return info.blocks * 1024

        # Try to parse the mdadm detail output
        size_text = _extract_detail_value(detail, "Array Size")
        if size_text:
            # Accept numbers with optional commas (e.g. "2,096,128 blocks")
            blocks_match = re.search(r"([\d,]+)\s+blocks", size_text)
            if blocks_match:
                try:
                    return int(blocks_match.group(1).replace(",", "")) * 1024
                except ValueError:  # pragma: no cover - defensive fallback
                    pass
            byte_match = re.search(r"([\d,]+)\s+bytes", size_text)
            if byte_match:
                try:
                    return int(byte_match.group(1).replace(",", ""))
                except ValueError:  # pragma: no cover - defensive fallback
                    pass

        if self._lsblk_available:
            result = self._run(
                [
                    "lsblk",
                    f"/dev/{name}",
                    "--bytes",
                    "--nodeps",
                    "--noheadings",
                    "--output",
                    "SIZE",
                ]
            )
            size_str = result.stdout.strip().splitlines()[0]
            return int(size_str)

        raise RuntimeError(f"Unable to determine size for RAID array '{name}'")

    def _resolve_progress(self, info: Optional[MdstatInfo], detail: str) -> Optional[float]:
        if info and info.resync_progress is not None:
            return info.resync_progress

        for key in ("Resync Status", "Rebuild Status", "Recovery Status", "Check Status"):
            value = _extract_detail_value(detail, key)
            if not value:
                continue
            match = re.search(r"(\d+(?:\.\d+)?)%", value)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:  # pragma: no cover - defensive conversion
                    return None
        return None

    def _parse_devices(self, detail: str) -> List[RaidDevice]:
        devices: List[RaidDevice] = []
        in_table = False

        for raw_line in detail.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Detect common header markers in various languages (e.g. 'Number', 'Nummer')
            low = line.lower()
            if low.startswith("number") or low.startswith("nummer") or low.startswith("numéro"):
                in_table = True
                continue

            # If header is absent, detect rows starting with an index number (headerless output)
            if not in_table:
                if re.match(r"^\s*\d+\s+", raw_line):
                    in_table = True
                    # fallthrough to parse this row
                else:
                    continue

            if low.startswith("unused devices"):
                break

            parts = line.split()
            if len(parts) < 2:
                continue

            device_path = parts[-1]

            # Typical mdadm table has several leading numeric columns; state tokens often live
            # in columns 5..N-1. Fall back to a best-effort slice if the strict indices are not present.
            if len(parts) >= 6:
                state_tokens = parts[4:-1]
            else:
                state_tokens = parts[1:-1]

            state_text = " ".join(state_tokens)
            devices.append(RaidDevice(name=Path(device_path).name, state=_map_device_state(state_text)))

        return devices

    def _get_disk_type_map(self) -> Dict[str, str]:
        """Build a map of disk name -> type ("hdd", "ssd", "nvme") using lsblk."""
        if not getattr(self, "_lsblk_available", False):
            return {}
        try:
            result = self._run(["lsblk", "-J", "-o", "NAME,ROTA,TYPE"], timeout=10)
            data = json.loads(result.stdout)
            mapping: Dict[str, str] = {}
            for dev in data.get("blockdevices", []):
                if dev.get("type") != "disk":
                    continue
                name = dev.get("name", "")
                if "nvme" in name:
                    mapping[name] = "nvme"
                elif dev.get("rota") is not None and str(dev["rota"]) == "0":
                    mapping[name] = "ssd"
                else:
                    mapping[name] = "hdd"
            return mapping
        except Exception:
            logger.debug("Failed to build disk type map")
            return {}

    def _read_mdstat(self) -> Dict[str, MdstatInfo]:
        if not self._MDSTAT_PATH.exists():
            return {}
        try:
            content = self._MDSTAT_PATH.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem edge case
            logger.debug("Failed to read /proc/mdstat: %s", exc)
            return {}
        return _parse_mdstat(content)

    def _read_sync_action(self, name: str) -> Optional[str]:
        path = Path(f"/sys/block/{name}/md/sync_action")
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def _set_sync_action(self, name: str, action: str) -> None:
        path = Path(f"/sys/block/{name}/md/sync_action")
        if not path.exists():
            raise RuntimeError(f"sync_action control not available for array '{name}'")
        try:
            path.write_text(action, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to set sync_action '{action}' for array '{name}': {exc}") from exc

    def _read_speed_limits(self) -> RaidSpeedLimits:
        min_value = self._read_proc_int(Path("/proc/sys/dev/raid/speed_limit_min"))
        max_value = self._read_proc_int(Path("/proc/sys/dev/raid/speed_limit_max"))
        return RaidSpeedLimits(minimum=min_value, maximum=max_value)

    def _read_proc_int(self, path: Path) -> Optional[int]:
        if not path.exists():
            return None
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def _write_proc_value(self, path: Path, value: str) -> None:
        if not path.exists():
            raise RuntimeError(f"Configuration path '{path}' not available on this system")
        try:
            path.write_text(value, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Failed to write '{value}' to '{path}': {exc}") from exc

    @staticmethod
    def _scan_arrays() -> List[str]:
        try:
            result = subprocess.run(
                ["sudo", "-n", "mdadm", "--detail", "--scan"],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:  # pragma: no cover - diagnostic fallback
            logger.debug("mdadm --detail --scan failed: %s", exc.stderr.strip())
            return []

        names: List[str] = []
        for line in result.stdout.splitlines():
            match = re.search(r"ARRAY\s+(/dev/\S+)", line)
            if match:
                names.append(Path(match.group(1)).name)
        return names

    def _normalize_array(self, array: str) -> str:
        path = array if array.startswith("/dev/") else f"/dev/{array}"
        if not Path(path).exists():
            raise ValueError(f"Unknown RAID array '{array}'")
        return path

    def _normalize_device(self, device: str) -> str:
        path = device if device.startswith("/dev/") else f"/dev/{device}"
        if not Path(path).exists():
            raise ValueError(f"Device '{device}' not found on this system")
        return path

    # Commands that require root privileges via sudo
    _SUDO_COMMANDS = {"mdadm", "smartctl"}

    def _run(self, command: List[str], *, check: bool = True, timeout: int = 60,
             stdin_input: str | None = None) -> subprocess.CompletedProcess[str]:
        # Prepend sudo -n for commands that need root
        if command and command[0] in self._SUDO_COMMANDS:
            command = ["sudo", "-n", *command]
        logger.debug("Executing command: %s", " ".join(command))
        try:
            return subprocess.run(command, check=check, capture_output=True, text=True,
                                  timeout=timeout, input=stdin_input)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            logger.error("Command '%s' failed: %s", " ".join(command), stderr)
            message = stderr or f"Command '{' '.join(command)}' failed with exit code {exc.returncode}"
            raise RuntimeError(message) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Command timed out after {timeout}s: {' '.join(command)}"
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"Required command not found: {command[0]}") from exc

    @staticmethod
    def _has_root_mount(node: dict) -> bool:
        """Recursively check if any descendant is mounted at /."""
        if node.get("mountpoint") == "/":
            return True
        for child in node.get("children", []):
            if MdadmRaidBackend._has_root_mount(child):
                return True
        return False

    def _get_os_disk_name(self) -> str | None:
        """Return the block device name hosting /. Cached after first call."""
        if hasattr(self, "_os_disk_cache"):
            return self._os_disk_cache
        try:
            result = self._run(["lsblk", "-J", "-o", "NAME,TYPE,MOUNTPOINT"], timeout=10)
            data = json.loads(result.stdout)
            for dev in data.get("blockdevices", []):
                if dev.get("type") == "disk" and self._has_root_mount(dev):
                    self._os_disk_cache = dev.get("name")
                    return self._os_disk_cache
        except Exception:
            pass
        self._os_disk_cache = None
        return None

    def get_available_disks(self) -> AvailableDisksResponse:
        """Get list of available disks using lsblk."""
        if not self._lsblk_available:
            raise RuntimeError("lsblk is not available on this system")

        result = self._run(["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,TYPE,FSTYPE,MOUNTPOINT,ROTA"])
        data = json.loads(result.stdout)

        disks = []
        raid_devices = set()

        # Sammle alle Devices die im RAID sind
        status = self.get_status()
        for array in status.arrays:
            for device in array.devices:
                raid_devices.add(device.name)

        cache_device_names: set[str] = set()

        # Parse lsblk output
        for device in data.get("blockdevices", []):
            if device.get("type") != "disk":
                continue

            name = device.get("name", "")
            size_bytes = int(device.get("size", 0))
            model = device.get("model") or None
            partitions = []
            is_partitioned = False

            # Check for partitions
            if "children" in device:
                is_partitioned = True
                for child in device["children"]:
                    partitions.append(child.get("name", ""))
                    # Detect SSD cache mount
                    mp = child.get("mountpoint") or ""
                    if mp.startswith("/mnt/cache-vcl"):
                        cache_device_names.add(name)
                        cache_device_names.add(child.get("name", ""))

            # Check if any partition is in RAID
            in_raid = any(part in raid_devices for part in partitions) or name in raid_devices

            # Check if this is the OS disk (has / mounted)
            is_os_disk = self._has_root_mount(device)

            # SSD detection: ROTA=0 means non-rotational (SSD/NVMe)
            rota = device.get("rota")
            is_ssd = rota is not None and str(rota) == "0"

            # Check if used as SSD cache device
            is_cache = name in cache_device_names or any(p in cache_device_names for p in partitions)

            disks.append(
                AvailableDisk(
                    name=name,
                    size_bytes=size_bytes,
                    model=model,
                    is_partitioned=is_partitioned,
                    partitions=partitions,
                    in_raid=in_raid,
                    is_os_disk=is_os_disk,
                    is_ssd=is_ssd,
                    is_cache_device=is_cache,
                )
            )

        return AvailableDisksResponse(disks=disks)

    def format_disk(self, payload: FormatDiskRequest) -> RaidActionResponse:
        """Format a disk with the specified filesystem."""
        if not payload.disk:
            raise ValueError("Disk name is required")

        # OS-Disk protection
        os_disk = self._get_os_disk_name()
        if os_disk and (payload.disk == os_disk or payload.disk.startswith(os_disk)):
            raise ValueError(f"Cannot format {payload.disk}: it is part of the OS disk ({os_disk})")

        device_path = self._normalize_device(payload.disk)

        # Validate filesystem type
        valid_filesystems = ["ext4", "ext3", "xfs", "btrfs"]
        if payload.filesystem not in valid_filesystems:
            raise ValueError(f"Unsupported filesystem: {payload.filesystem}. Valid options: {', '.join(valid_filesystems)}")

        # Format the disk
        mkfs_cmd = f"mkfs.{payload.filesystem}"
        if not shutil.which(mkfs_cmd):
            raise RuntimeError(f"Command '{mkfs_cmd}' not found on this system")

        cmd = [mkfs_cmd]
        if payload.label:
            if payload.filesystem in ["ext4", "ext3"]:
                cmd.extend(["-L", payload.label])
            elif payload.filesystem == "xfs":
                cmd.extend(["-L", payload.label])
            elif payload.filesystem == "btrfs":
                cmd.extend(["-L", payload.label])

        cmd.append(device_path)

        logger.info("Formatting %s with %s filesystem", device_path, payload.filesystem)
        self._run(cmd, timeout=300)

        label_msg = f" with label '{payload.label}'" if payload.label else ""
        return RaidActionResponse(message=f"Disk {payload.disk} formatted as {payload.filesystem}{label_msg}")

    def create_array(self, payload: CreateArrayRequest) -> RaidActionResponse:
        """Create a new RAID array using mdadm."""
        if not payload.name or not payload.devices:
            raise ValueError("Array name and devices are required")

        # OS-Disk protection
        os_disk = self._get_os_disk_name()
        if os_disk:
            for dev in payload.devices:
                if dev == os_disk or dev.startswith(os_disk):
                    raise ValueError(f"Cannot use {dev} for RAID: it is part of the OS disk ({os_disk})")

        # Validate array name (safety net in case schema validation is bypassed)
        if not re.fullmatch(r"md([0-9]+|_[a-zA-Z0-9]+)", payload.name) or len(payload.name) > 32:
            raise ValueError(
                f"Invalid array name '{payload.name}'. "
                "Name must match 'md<digits>' or 'md_<alphanumerics>' (max 32 chars)."
            )

        # Validate RAID level
        valid_levels = ["raid0", "raid1", "raid5", "raid6", "raid10"]
        if payload.level not in valid_levels:
            raise ValueError(f"Unsupported RAID level: {payload.level}. Valid options: {', '.join(valid_levels)}")

        # Minimum device requirements
        min_devices = {"raid0": 2, "raid1": 2, "raid5": 3, "raid6": 4, "raid10": 4}
        if len(payload.devices) < min_devices.get(payload.level, 2):
            raise ValueError(f"RAID level {payload.level} requires at least {min_devices[payload.level]} devices")

        array_path = f"/dev/{payload.name}"
        if Path(array_path).exists():
            raise ValueError(f"Array '{payload.name}' already exists")

        # Build mdadm command
        cmd = [
            "mdadm",
            "--create",
            array_path,
            "--level=" + payload.level.replace("raid", ""),
            f"--raid-devices={len(payload.devices)}",
        ]

        if payload.spare_devices:
            cmd.append(f"--spare-devices={len(payload.spare_devices)}")

        # Add device paths
        for device in payload.devices:
            cmd.append(self._normalize_device(device))

        for spare in payload.spare_devices:
            cmd.append(self._normalize_device(spare))

        # Optionally assume clean (skip initial resync) only when explicitly allowed
        if getattr(settings, "raid_assume_clean_by_default", False):
            cmd.append("--assume-clean")

        logger.info("Creating RAID array %s with command: %s", payload.name, " ".join(cmd))
        self._run(cmd, timeout=300, stdin_input="y\n" * 3)

        return RaidActionResponse(
            message=f"Array {payload.name} ({payload.level}) created with {len(payload.devices)} devices"
        )

    def delete_array(self, payload: DeleteArrayRequest) -> RaidActionResponse:
        """Delete a RAID array using mdadm."""
        array_path = self._normalize_array(payload.array)

        # Stop the array
        logger.info("Stopping RAID array %s", array_path)
        self._run(["mdadm", "--stop", array_path])

        # Zero superblock on devices if force is enabled
        if payload.force:
            status = self.get_status()
            array = next((a for a in status.arrays if a.name == payload.array or f"/dev/{a.name}" == payload.array), None)
            if array:
                for device in array.devices:
                    device_path = f"/dev/{device.name}"
                    try:
                        logger.info("Zeroing superblock on %s", device_path)
                        self._run(["mdadm", "--zero-superblock", device_path], check=False)
                    except RuntimeError:
                        logger.warning("Failed to zero superblock on %s", device_path)

        return RaidActionResponse(message=f"Array {payload.array} deleted")
