from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Protocol, TYPE_CHECKING, cast

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

logger = logging.getLogger(__name__)
import datetime
import json
import uuid
import time

# Type-only import for annotations; runtime import uses `_APScheduler`.
if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

try:
    from apscheduler.schedulers.background import BackgroundScheduler as _APScheduler
except Exception:  # pragma: no cover - scheduler optional
    _APScheduler = None


class RaidBackend(Protocol):
    def get_status(self) -> RaidStatusResponse:
        ...

    def degrade(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def rebuild(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def finalize(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        ...

    def configure(self, payload: RaidOptionsRequest) -> RaidActionResponse:
        ...

    def get_available_disks(self) -> AvailableDisksResponse:
        ...

    def format_disk(self, payload: FormatDiskRequest) -> RaidActionResponse:
        ...

    def create_array(self, payload: CreateArrayRequest) -> RaidActionResponse:
        ...

    def delete_array(self, payload: DeleteArrayRequest) -> RaidActionResponse:
        ...


@dataclass
class _RaidState:
    arrays: Dict[str, RaidArray] = field(default_factory=dict)
    speed_limit_min: int = 5000
    speed_limit_max: int = 200000

    @staticmethod
    def _default_size_bytes() -> int:
        quota = settings.nas_quota_bytes
        if quota is not None and quota > 0:
            return quota
        # Fallback to the dev-mode default (5 GiB per disk, 2x5GB RAID1) when no quota has been configured.
        return 5 * 1024 ** 3

    def ensure_default(self) -> None:
        if self.arrays:
            self.refresh_defaults()
            return

        size_bytes = self._default_size_bytes()
        self.arrays = {
            "md0": RaidArray(
                name="md0",
                level="raid1",
                size_bytes=size_bytes,
                status="optimal",
                devices=[
                    RaidDevice(name="sda1", state="active"),
                    RaidDevice(name="sdb1", state="active"),
                ],
                resync_progress=None,
                bitmap="internal",
                sync_action="idle",
            )
        }

    def refresh_defaults(self) -> None:
        size_bytes = self._default_size_bytes()
        for raid_array in self.arrays.values():
            raid_array.size_bytes = size_bytes

    def configure(self, payload: RaidOptionsRequest) -> None:
        self.ensure_default()
        raid_array = self.arrays.get(payload.array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{payload.array}'")

        if payload.enable_bitmap is not None:
            raid_array.bitmap = "internal" if payload.enable_bitmap else None

        if payload.add_spare:
            if any(dev.name == payload.add_spare for dev in raid_array.devices):
                raise ValueError(f"Device '{payload.add_spare}' already part of RAID '{payload.array}'")
            raid_array.devices.append(RaidDevice(name=payload.add_spare, state="spare"))

        if payload.remove_device:
            for idx, dev in enumerate(list(raid_array.devices)):
                if dev.name == payload.remove_device:
                    raid_array.devices.pop(idx)
                    break
            else:
                raise ValueError(f"Device '{payload.remove_device}' not part of RAID '{payload.array}'")

        if payload.write_mostly_device:
            target = None
            for dev in raid_array.devices:
                if dev.name == payload.write_mostly_device:
                    target = dev
                    break
            if target is None:
                raise ValueError(
                    f"Device '{payload.write_mostly_device}' not part of RAID '{payload.array}'"
                )
            if payload.write_mostly is False:
                target.state = "active"
            else:
                target.state = "write-mostly"

        if payload.trigger_scrub:
            raid_array.sync_action = "check"
            raid_array.resync_progress = 0.0
        else:
            if raid_array.sync_action == "check":
                raid_array.sync_action = "idle"
                raid_array.resync_progress = None

        if payload.set_speed_limit_min is not None:
            self.speed_limit_min = max(0, payload.set_speed_limit_min)
        if payload.set_speed_limit_max is not None:
            self.speed_limit_max = max(self.speed_limit_min, payload.set_speed_limit_max)

    def degrade(self, array: str, device: str | None = None) -> None:
        self.ensure_default()
        raid_array = self.arrays.get(array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{array}'")

        target_device = device or raid_array.devices[0].name
        for dev in raid_array.devices:
            if dev.name == target_device:
                dev.state = "failed"
                raid_array.status = "degraded"
                raid_array.resync_progress = None
                break
        else:
            raise KeyError(f"Device '{target_device}' not part of RAID '{array}'")

    def rebuild(self, array: str, device: str | None = None) -> None:
        self.ensure_default()
        raid_array = self.arrays.get(array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{array}'")

        target_device = device or raid_array.devices[0].name
        for dev in raid_array.devices:
            if dev.name == target_device:
                dev.state = "rebuilding"
                raid_array.status = "rebuilding"
                raid_array.resync_progress = 42.0
                break
        else:
            raise KeyError(f"Device '{target_device}' not part of RAID '{array}'")

    def finalize_rebuild(self, array: str) -> None:
        raid_array = self.arrays.get(array)
        if not raid_array:
            raise KeyError(f"Unknown RAID array '{array}'")

        for dev in raid_array.devices:
            if dev.state in {"failed", "rebuilding"}:
                dev.state = "active"
        raid_array.status = "optimal"
        raid_array.resync_progress = None


@dataclass
class MdstatInfo:
    blocks: Optional[int] = None
    resync_progress: Optional[float] = None


def _parse_mdstat(content: str) -> Dict[str, MdstatInfo]:
    arrays: Dict[str, MdstatInfo] = {}
    current: Optional[str] = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("Personalities") or line.startswith("unused devices"):
            continue

        if not line.startswith(" "):
            parts = line.split()
            if not parts:
                continue
            name = parts[0].rstrip(":")
            arrays[name] = MdstatInfo()
            current = name
            continue

        if current is None:
            continue

        info = arrays[current]
        if info.blocks is None:
            # Accept numbers with optional commas (e.g. "2,096,128 blocks")
            match = re.search(r"([\d,]+)\s+blocks", line)
            if match:
                try:
                    info.blocks = int(match.group(1).replace(",", ""))
                except ValueError:  # pragma: no cover - defensive fallback
                    info.blocks = None

        lowered = line.lower()
        if info.resync_progress is None and any(
            keyword in lowered for keyword in ("resync", "recover", "rebuild", "reshape", "check")
        ):
            progress_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if progress_match:
                try:
                    info.resync_progress = float(progress_match.group(1))
                except ValueError:  # pragma: no cover - defensive conversion
                    info.resync_progress = None
            # If no explicit percentage is present, try to infer progress from a fraction like (259212/2096128).
            if info.resync_progress is None:
                frac_match = re.search(r"\(([\d,]+)\/([\d,]+)\)", line)
                if frac_match:
                    try:
                        num = int(frac_match.group(1).replace(",", ""))
                        den = int(frac_match.group(2).replace(",", ""))
                        if den > 0:
                            info.resync_progress = (num / den) * 100.0
                    except ValueError:  # pragma: no cover - defensive
                        pass

    return arrays


def _extract_detail_value(detail: str, key: str) -> Optional[str]:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:\s*(.+)$", re.MULTILINE)
    match = pattern.search(detail)
    if match:
        return match.group(1).strip()
    return None


def _map_device_state(state_text: str) -> str:
    text = state_text.lower()
    if "faulty" in text or "failed" in text:
        return "failed"
    if "remove" in text:
        return "removed"
    if "spare" in text and ("rebuild" in text or "recover" in text):
        return "rebuilding"
    if "rebuild" in text or "recover" in text:
        return "rebuilding"
    if "spare" in text:
        return "spare"
    if "blocked" in text:
        return "blocked"
    if "writemostly" in text:
        return "write-mostly"
    if "sync" in text or "active" in text:
        return "active"
    return text or "unknown"


def _derive_array_status(state_text: Optional[str], progress: Optional[float], devices: List[RaidDevice]) -> str:
    if state_text:
        lowered = state_text.lower()
        if any(keyword in lowered for keyword in ("resync", "recover", "rebuild", "reshape", "check")):
            return "rebuilding"
        if "degraded" in lowered or "faulty" in lowered:
            return "degraded"
        if "inactive" in lowered or "stop" in lowered:
            return "inactive"

    if progress is not None:
        return "rebuilding"

    if any(dev.state in {"failed", "removed"} for dev in devices):
        return "degraded"

    return "optimal"


class DevRaidBackend:
    def __init__(self) -> None:
        self._state = _RaidState()
        # Dynamische Mock-Disks-Liste (zusätzlich zu den Standard 7)
        self._mock_disks: List[tuple[str, str, str, int]] = []  # (disk_name, partition_name, model, size_gb)

    def get_status(self) -> RaidStatusResponse:
        self._state.ensure_default()
        return RaidStatusResponse(
            arrays=list(self._state.arrays.values()),
            speed_limits=RaidSpeedLimits(
                minimum=self._state.speed_limit_min,
                maximum=self._state.speed_limit_max,
            ),
        )

    def degrade(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        try:
            self._state.degrade(payload.array, payload.device)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        return RaidActionResponse(message=f"Array {payload.array} marked as degraded")

    def rebuild(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        try:
            self._state.rebuild(payload.array, payload.device)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        return RaidActionResponse(message=f"Array {payload.array} rebuild started")

    def finalize(self, payload: RaidSimulationRequest) -> RaidActionResponse:
        try:
            self._state.finalize_rebuild(payload.array)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        return RaidActionResponse(message=f"Array {payload.array} restored to optimal state")

    def configure(self, payload: RaidOptionsRequest) -> RaidActionResponse:
        try:
            self._state.configure(payload)
        except (KeyError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

        return RaidActionResponse(message="RAID configuration updated (dev mode)")

    def get_available_disks(self) -> AvailableDisksResponse:
        """Return simulated available disks for dev mode (7 base disks + dynamically added)."""
        self._state.ensure_default()
        
        # Sammle alle bereits verwendeten Geräte
        used_devices = set()
        for array in self._state.arrays.values():
            for device in array.devices:
                used_devices.add(device.name)
        
        disks = []
        
        # Mock Disks: Konsistent mit SMART-Service (_mock_status)
        # RAID1 Pool 1: 2x5GB (sda, sdb)
        # RAID1 Pool 2: 2x10GB (sdc, sdd)
        # RAID5 Pool: 3x20GB (sde, sdf, sdg)
        base_mock_disks = [
            ("sda", "sda1", "BaluHost Dev Disk 5GB (Mirror A)", 5),
            ("sdb", "sdb1", "BaluHost Dev Disk 5GB (Mirror B)", 5),
            ("sdc", "sdc1", "BaluHost Dev Disk 10GB (Backup A)", 10),
            ("sdd", "sdd1", "BaluHost Dev Disk 10GB (Backup B)", 10),
            ("sde", "sde1", "BaluHost Dev Disk 20GB (Archive A)", 20),
            ("sdf", "sdf1", "BaluHost Dev Disk 20GB (Archive B)", 20),
            ("sdg", "sdg1", "BaluHost Dev Disk 20GB (Archive C)", 20),
        ]
        
        # Kombiniere base disks mit dynamisch hinzugefügten
        all_mock_disks = base_mock_disks + self._mock_disks
        
        for disk_name, partition_name, model, size_gb in all_mock_disks:
            in_raid = partition_name in used_devices
            raid_suffix = " (in RAID)" if in_raid else ""
            
            disks.append(
                AvailableDisk(
                    name=disk_name,
                    size_bytes=size_gb * 1024 ** 3,
                    model=model + raid_suffix,
                    is_partitioned=True,
                    partitions=[partition_name],
                    in_raid=in_raid,
                )
            )
        
        return AvailableDisksResponse(disks=disks)
    
    def add_mock_disk(self, letter: str, size_gb: int, name: str, purpose: str) -> RaidActionResponse:
        """Dev-Mode: Add a simulated mock disk dynamically."""
        disk_name = f"sd{letter}"
        partition_name = f"sd{letter}1"
        
        # Prüfe ob Disk bereits existiert
        existing_disks = self.get_available_disks()
        if any(d.name == disk_name for d in existing_disks.disks):
            raise ValueError(f"Disk /dev/{disk_name} already exists")
        
        # Validierung
        if size_gb < 1 or size_gb > 1000:
            raise ValueError("Disk size must be between 1 and 1000 GB")
        
        if not name or len(name.strip()) == 0:
            raise ValueError("Disk name cannot be empty")
        
        # Füge Mock-Disk hinzu
        purpose_suffix = f" ({purpose.capitalize()})" if purpose else ""
        full_model = f"{name} {size_gb}GB{purpose_suffix}"
        self._mock_disks.append((disk_name, partition_name, full_model, size_gb))
        
        logger.info(f"[DEV MODE] Added mock disk: /dev/{disk_name} ({size_gb}GB) - {full_model}")
        return RaidActionResponse(
            message=f"Mock disk /dev/{disk_name} ({size_gb}GB) successfully added"
        )

    def format_disk(self, payload: FormatDiskRequest) -> RaidActionResponse:
        """Simulate disk formatting in dev mode."""
        if not payload.disk:
            raise ValueError("Disk name is required")
        logger.info("[DEV MODE] Formatting disk %s with %s filesystem", payload.disk, payload.filesystem)
        label_msg = f" with label '{payload.label}'" if payload.label else ""
        return RaidActionResponse(
            message=f"[DEV MODE] Disk {payload.disk} formatted as {payload.filesystem}{label_msg}"
        )

    def create_array(self, payload: CreateArrayRequest) -> RaidActionResponse:
        """Simulate RAID array creation in dev mode."""
        if not payload.name or not payload.devices:
            raise ValueError("Array name and devices are required")
        
        # RAID-Level spezifische Validierung
        level = payload.level.lower()
        min_devices = 2
        if level in ("raid0", "raid1"):
            min_devices = 2
        elif level == "raid5":
            min_devices = 3
        elif level == "raid6":
            min_devices = 4
        elif level == "raid10":
            min_devices = 4
        
        if len(payload.devices) < min_devices:
            raise ValueError(f"{payload.level.upper()} requires at least {min_devices} devices")
        
        # Prüfe ob Array bereits existiert
        if payload.name in self._state.arrays:
            raise ValueError(f"Array '{payload.name}' already exists")
        
        # Sammle alle bereits verwendeten Geräte
        used_devices = set()
        for array in self._state.arrays.values():
            for device in array.devices:
                used_devices.add(device.name)
        
        # Prüfe ob Geräte bereits in Verwendung sind
        for dev in payload.devices:
            if dev in used_devices:
                raise ValueError(f"Device '{dev}' is already part of another RAID array")
        
        if payload.spare_devices:
            for dev in payload.spare_devices:
                if dev in used_devices or dev in payload.devices:
                    raise ValueError(f"Spare device '{dev}' is already in use")
        
        # Berechne Array-Größe basierend auf RAID-Level
        device_count = len(payload.devices)
        
        # Bestimme Disk-Größen basierend auf Gerät (konsistent mit get_available_disks)
        # sda, sdb = 5GB; sdc, sdd = 10GB; sde, sdf, sdg = 20GB
        disk_sizes = {
            "sda1": 5 * 1024 ** 3, "sdb1": 5 * 1024 ** 3,
            "sdc1": 10 * 1024 ** 3, "sdd1": 10 * 1024 ** 3,
            "sde1": 20 * 1024 ** 3, "sdf1": 20 * 1024 ** 3, "sdg1": 20 * 1024 ** 3,
        }
        
        # Verwende kleinste Disk-Größe im Array für Berechnung
        device_sizes = [disk_sizes.get(dev, 5 * 1024 ** 3) for dev in payload.devices]
        min_disk_size = min(device_sizes) if device_sizes else 5 * 1024 ** 3
        
        if level == "raid0":
            # RAID 0: Alle Disks addieren
            array_size = sum(device_sizes)
        elif level == "raid1":
            # RAID 1: Kleinste Disk
            array_size = min_disk_size
        elif level == "raid5":
            # RAID 5: (n-1) * kleinste disk_size
            array_size = min_disk_size * (device_count - 1)
        elif level == "raid6":
            # RAID 6: (n-2) * kleinste disk_size
            array_size = min_disk_size * (device_count - 2)
        elif level == "raid10":
            # RAID 10: n/2 * kleinste disk_size
            array_size = min_disk_size * (device_count // 2)
        else:
            array_size = min_disk_size
        
        # Erstelle neues Array
        devices = [RaidDevice(name=dev, state="active") for dev in payload.devices]
        if payload.spare_devices:
            devices.extend([RaidDevice(name=dev, state="spare") for dev in payload.spare_devices])
        
        self._state.arrays[payload.name] = RaidArray(
            name=payload.name,
            level=payload.level,
            size_bytes=array_size,
            status="optimal",
            devices=devices,
            resync_progress=None,
            bitmap="internal",
            sync_action="idle",
        )
        
        logger.info("[DEV MODE] Created RAID array %s with level %s and %d devices", 
                   payload.name, payload.level, device_count)
        return RaidActionResponse(
            message=f"[DEV MODE] Array {payload.name} ({payload.level}) created with {len(payload.devices)} devices"
        )

    def delete_array(self, payload: DeleteArrayRequest) -> RaidActionResponse:
        """Simulate RAID array deletion in dev mode."""
        if payload.array not in self._state.arrays:
            raise ValueError(f"Array '{payload.array}' does not exist")
        
        del self._state.arrays[payload.array]
        logger.info("[DEV MODE] Deleted RAID array %s", payload.array)
        return RaidActionResponse(message=f"[DEV MODE] Array {payload.array} deleted")


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
            # No RAID arrays configured - return empty response instead of crashing
            return RaidStatusResponse(
                arrays=[],
                speed_limits=self._read_speed_limits(),
            )

        arrays: List[RaidArray] = []
        for name in sorted(array_names):
            info = mdstat_info.get(name)
            arrays.append(self._build_array(name, info))

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

    def _build_array(self, name: str, info: Optional[MdstatInfo]) -> RaidArray:
        detail = self._run(["mdadm", f"/dev/{name}", "--detail"]).stdout

        level = _extract_detail_value(detail, "Raid Level") or "unknown"
        state_line = _extract_detail_value(detail, "State")

        size_bytes = self._resolve_array_size(name, info, detail)
        resync_progress = self._resolve_progress(info, detail)
        devices = self._parse_devices(detail)
        status = _derive_array_status(state_line, resync_progress, devices)
        bitmap_info = _extract_detail_value(detail, "Bitmap")
        sync_action = self._read_sync_action(name)

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
                ["mdadm", "--detail", "--scan"],
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

    def _run(self, command: List[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        logger.debug("Executing command: %s", " ".join(command))
        try:
            return subprocess.run(command, check=check, capture_output=True, text=True, timeout=timeout)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            logger.error("Command '%s' failed: %s", " ".join(command), stderr)
            message = stderr or f"Command '{' '.join(command)}' failed with exit code {exc.returncode}"
            raise RuntimeError(message) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(f"Required command not found: {command[0]}") from exc

    def get_available_disks(self) -> AvailableDisksResponse:
        """Get list of available disks using lsblk."""
        if not self._lsblk_available:
            raise RuntimeError("lsblk is not available on this system")
        
        result = self._run(["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,TYPE,FSTYPE"])
        import json
        data = json.loads(result.stdout)
        
        disks = []
        raid_devices = set()
        
        # Sammle alle Devices die im RAID sind
        status = self.get_status()
        for array in status.arrays:
            for device in array.devices:
                raid_devices.add(device.name)
        
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
                partitions = [child.get("name", "") for child in device["children"]]
            
            # Check if any partition is in RAID
            in_raid = any(part in raid_devices for part in partitions) or name in raid_devices
            
            disks.append(
                AvailableDisk(
                    name=name,
                    size_bytes=size_bytes,
                    model=model,
                    is_partitioned=is_partitioned,
                    partitions=partitions,
                    in_raid=in_raid,
                )
            )
        
        return AvailableDisksResponse(disks=disks)

    def format_disk(self, payload: FormatDiskRequest) -> RaidActionResponse:
        """Format a disk with the specified filesystem."""
        if not payload.disk:
            raise ValueError("Disk name is required")
        
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
        self._run(cmd, timeout=300)
        
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


def _select_backend() -> RaidBackend:
    # Respect explicit override in settings first (useful for tests or CI)
    if getattr(settings, "raid_force_dev_backend", False):
        logger.debug("Using development RAID backend (forced by settings)")
        return DevRaidBackend()

    # Non-Linux hosts cannot use mdadm -> fall back to dev backend
    if platform.system().lower() != "linux":
        logger.debug("Non-Linux host detected; using development RAID backend")
        return DevRaidBackend()

    # If nas_mode explicitly requests dev, use dev backend
    if getattr(settings, "is_dev_mode", False):
        logger.debug("Using development RAID backend (nas_mode=dev)")
        return DevRaidBackend()

    # Otherwise prefer the mdadm backend when available
    if MdadmRaidBackend.is_supported():
        logger.info("Using mdadm RAID backend")
        return MdadmRaidBackend()

    raise RuntimeError("No supported RAID backend available on this system")


_backend = _select_backend()


def _payload_to_dict(payload: object) -> object:
    try:
        # Pydantic v2
        return payload.model_dump()  # type: ignore[attr-defined]
    except Exception:
        try:
            return payload.dict()  # type: ignore[attr-defined]
        except Exception:
            return str(payload)


def _audit_event(action: str, payload: object | None = None, dry_run: bool = False) -> None:
    """Append a compact audit record to the configured audit file (best-effort).

    The function never raises; failures are logged only.
    """
    record = {
        "timestamp": datetime.datetime.now(timezone.utc).isoformat() + "Z",
        "action": action,
        "dry_run": bool(dry_run),
        "payload": _payload_to_dict(payload) if payload is not None else None,
    }
    logger.info("RAID audit: %s", json.dumps(record, default=str))
    audit_path = getattr(settings, "raid_audit_log", None)
    if not audit_path:
        return
    try:
        p = Path(audit_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:  # pragma: no cover - best-effort logging
        logger.debug("Failed to write RAID audit record to %s: %s", audit_path, exc)


def get_status() -> RaidStatusResponse:
    return _backend.get_status()


def simulate_failure(payload: RaidSimulationRequest) -> RaidActionResponse:
    _audit_event("simulate_failure", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_backend, DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.degrade(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _backend.degrade(payload)


def simulate_rebuild(payload: RaidSimulationRequest) -> RaidActionResponse:
    _audit_event("simulate_rebuild", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_backend, DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.rebuild(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _backend.rebuild(payload)


def finalize_rebuild(payload: RaidSimulationRequest) -> RaidActionResponse:
    _audit_event("finalize_rebuild", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_backend, DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.finalize(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _backend.finalize(payload)


def configure_array(payload: RaidOptionsRequest) -> RaidActionResponse:
    _audit_event("configure_array", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_backend, DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.configure(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _backend.configure(payload)


def get_available_disks() -> AvailableDisksResponse:
    return _backend.get_available_disks()


def format_disk(payload: FormatDiskRequest) -> RaidActionResponse:
    _audit_event("format_disk", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_backend, DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.format_disk(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _backend.format_disk(payload)


def create_array(payload: CreateArrayRequest) -> RaidActionResponse:
    _audit_event("create_array", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_backend, DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.create_array(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _backend.create_array(payload)


def delete_array(payload: DeleteArrayRequest) -> RaidActionResponse:
    _audit_event("delete_array", payload, dry_run=getattr(settings, "raid_dry_run", False))
    if getattr(settings, "raid_dry_run", False) and not isinstance(_backend, DevRaidBackend):
        dev = DevRaidBackend()
        resp = dev.delete_array(payload)
        resp.message = "[DRY-RUN] " + resp.message
        return resp
    return _backend.delete_array(payload)


def add_mock_disk(letter: str, size_gb: int, name: str, purpose: str) -> RaidActionResponse:
    """Dev-Mode only: Add a mock disk dynamically."""
    if not isinstance(_backend, DevRaidBackend):
        raise RuntimeError("Mock disk management is only available in dev mode")
    return _backend.add_mock_disk(letter, size_gb, name, purpose)


# Two-step confirmation store for destructive operations
_confirmations: Dict[str, Dict] = {}


def request_confirmation(action: str, payload: object, ttl_seconds: int = 3600) -> dict:
    """Create a one-time confirmation token for a destructive RAID action.

    Returns a dict with `token` and `expires_at` (unix timestamp).
    """
    token = uuid.uuid4().hex
    expires_at = int(time.time()) + int(ttl_seconds)
    _confirmations[token] = {
        "action": action,
        "payload": _payload_to_dict(payload),
        "expires_at": expires_at,
    }
    logger.info("RAID confirmation requested: %s token=%s expires_at=%s", action, token, expires_at)
    _audit_event("request_confirmation", {"action": action, "token": token}, dry_run=False)
    return {"token": token, "expires_at": expires_at}


def execute_confirmation(token: str) -> RaidActionResponse:
    """Execute a previously requested confirmation token.

    Raises KeyError if token invalid or expired, or RuntimeError on action failure.
    """
    entry = _confirmations.get(token)
    if not entry:
        raise KeyError("Invalid confirmation token")
    if int(time.time()) > int(entry.get("expires_at", 0)):
        del _confirmations[token]
        raise KeyError("Confirmation token expired")

    action = entry["action"]
    payload = entry["payload"]

    # Remove token to make it one-time
    del _confirmations[token]

    # Dispatch supported destructive actions
    try:
        if action == "delete_array":
            req = DeleteArrayRequest(**payload)
            resp = delete_array(req)
        elif action == "format_disk":
            req = FormatDiskRequest(**payload)
            resp = format_disk(req)
        elif action == "create_array":
            req = CreateArrayRequest(**payload)
            resp = create_array(req)
        else:
            raise RuntimeError(f"Unsupported confirmed action: {action}")
    except Exception as exc:
        logger.exception("Failed to execute confirmed action %s: %s", action, exc)
        _audit_event("execute_confirmation_failed", {"action": action, "error": str(exc)}, dry_run=False)
        raise

    _audit_event("execute_confirmation", {"action": action, "token": token}, dry_run=False)
    return resp


# Scheduler for periodic RAID scrubs
_scrub_scheduler: Optional["BackgroundScheduler"] = None


def _perform_scrub_job() -> None:
    from app.services.scheduler_service import log_scheduler_execution, complete_scheduler_execution

    execution_id = log_scheduler_execution("raid_scrub", job_id="raid_scrub")
    try:
        logger.info("RAID scrub job: starting automatic scrub")
        result = scrub_now(None)
        logger.info("RAID scrub job: completed")
        complete_scheduler_execution(
            execution_id,
            success=True,
            result={"message": result.message if result else "Scrub completed"}
        )
    except Exception as exc:  # pragma: no cover - runtime safety
        logger.exception("RAID scrub job failed: %s", exc)
        complete_scheduler_execution(execution_id, success=False, error=str(exc))


def scrub_now(array: str | None = None) -> RaidActionResponse:
    """Trigger an immediate scrub/check on a specific array or all arrays.

    When `array` is None, all known arrays will be triggered.
    """
    # Build payload(s) using RaidOptionsRequest
    if array:
        payload = RaidOptionsRequest(array=array, trigger_scrub=True)
        return _backend.configure(payload)

    # Trigger scrub for all arrays
    status = None
    try:
        status = _backend.get_status()
    except Exception:
        # If get_status fails (e.g., no arrays), raise a clear error
        raise RuntimeError("Unable to determine RAID arrays for scrubbing")

    messages: list[str] = []
    for arr in status.arrays:
        try:
            payload = RaidOptionsRequest(array=arr.name, trigger_scrub=True)
            resp = _backend.configure(payload)
            messages.append(resp.message)
        except Exception as exc:
            logger.warning("Failed to trigger scrub on %s: %s", arr.name, exc)
            messages.append(f"{arr.name}: error: {exc}")

    return RaidActionResponse(message="; ".join(messages))


def start_scrub_scheduler() -> None:
    global _scrub_scheduler
    if not getattr(settings, "raid_scrub_enabled", False):
        logger.debug("RAID scrub scheduler disabled by settings")
        return
    if _APScheduler is None:
        logger.warning("APScheduler not available; RAID scrub scheduler skipped")
        return
    if _scrub_scheduler is not None:
        logger.debug("RAID scrub scheduler already running")
        return

    # Create scheduler (narrow type for the static analyzer)
    scheduler: "BackgroundScheduler" = _APScheduler()
    _scrub_scheduler = scheduler
    interval_hours = max(1, int(getattr(settings, "raid_scrub_interval_hours", 168)))
    scheduler.add_job(
        func=_perform_scrub_job,
        trigger="interval",
        hours=interval_hours,
        id="raid_scrub",
        name="Periodic RAID scrub",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("RAID scrub scheduler started (every %d hours)", interval_hours)


def stop_scrub_scheduler() -> None:
    global _scrub_scheduler
    if _scrub_scheduler is None:
        return
    try:
        _scrub_scheduler.shutdown(wait=False)
    except Exception:
        logger.debug("Error while shutting down RAID scrub scheduler")
    _scrub_scheduler = None


def get_scrub_scheduler_status() -> dict:
    """
    Get RAID scrub scheduler status for service status monitoring.

    Returns:
        Dict with service status information for admin dashboard
    """
    is_running = _scrub_scheduler is not None and _scrub_scheduler.running
    interval_hours = max(1, int(getattr(settings, "raid_scrub_interval_hours", 168)))

    # Get next run time if scheduler is running
    next_run = None
    if is_running:
        try:
            job = _scrub_scheduler.get_job("raid_scrub")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except Exception:
            pass

    return {
        "is_running": is_running,
        "interval_seconds": interval_hours * 3600,
        "config_enabled": getattr(settings, "raid_scrub_enabled", False),
        "next_run": next_run,
    }
