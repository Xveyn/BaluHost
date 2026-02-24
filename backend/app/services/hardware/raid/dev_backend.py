from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List

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
                    RaidDevice(name="sda1", state="active", disk_type="hdd"),
                    RaidDevice(name="sdb1", state="active", disk_type="hdd"),
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
            raid_array.status = "checking"
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


class DevRaidBackend:
    def __init__(self) -> None:
        self._state = _RaidState()
        # Dynamische Mock-Disks-Liste (zusätzlich zu den Standard 7)
        self._mock_disks: List[tuple[str, str, str, int]] = []  # (disk_name, partition_name, model, size_gb)

    def get_status(self) -> RaidStatusResponse:
        self._state.ensure_default()
        arrays = list(self._state.arrays.values())

        return RaidStatusResponse(
            arrays=arrays,
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
        # OS disk (NVMe) — nicht für RAID verwendbar
        # RAID1 Pool 1: 2x5GB (sda, sdb)
        # RAID1 Pool 2: 2x10GB (sdc, sdd)
        # RAID5 Pool: 3x20GB (sde, sdf, sdg)
        # is_os, is_ssd
        base_mock_disks = [
            ("nvme0n1", "nvme0n1p2", "BaluHost Dev NVMe 500GB (OS)", 500, True, True),
            ("sda", "sda1", "BaluHost Dev Disk 5GB (Mirror A)", 5, False, False),
            ("sdb", "sdb1", "BaluHost Dev Disk 5GB (Mirror B)", 5, False, False),
            ("sdc", "sdc1", "BaluHost Dev Disk 10GB (Backup A)", 10, False, False),
            ("sdd", "sdd1", "BaluHost Dev Disk 10GB (Backup B)", 10, False, False),
            ("sde", "sde1", "BaluHost Dev Disk 20GB (Archive A)", 20, False, False),
            ("sdf", "sdf1", "BaluHost Dev Disk 20GB (Archive B)", 20, False, False),
            ("sdg", "sdg1", "BaluHost Dev Disk 20GB (Archive C)", 20, False, False),
            ("nvme1n1", "nvme1n1p1", "BaluHost Dev SSD Cache 120GB", 120, False, True),
        ]

        # Kombiniere base disks mit dynamisch hinzugefügten
        # Dynamische Disks haben kein is_os_disk/is_ssd Feld (4-Tupel)
        all_mock_disks = base_mock_disks + [(d[0], d[1], d[2], d[3], False, False) for d in self._mock_disks]

        for disk_name, partition_name, model, size_gb, is_os, is_ssd in all_mock_disks:
            in_raid = partition_name in used_devices
            raid_suffix = " (in RAID)" if in_raid else ""
            is_cache = disk_name == "nvme1n1"

            disks.append(
                AvailableDisk(
                    name=disk_name,
                    size_bytes=size_gb * 1024 ** 3,
                    model=model + raid_suffix,
                    is_partitioned=True,
                    partitions=[partition_name],
                    in_raid=in_raid,
                    is_os_disk=is_os,
                    is_ssd=is_ssd,
                    is_cache_device=is_cache,
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

    def _get_dev_disk_type(self, partition_name: str) -> str:
        """Derive disk type from mock disk data for a partition name (e.g. sda1 -> hdd)."""
        # Strip partition number to get parent disk name
        parent = re.sub(r"p?\d+$", "", partition_name)
        base_mock_disks = [
            ("nvme0n1", True), ("sda", False), ("sdb", False),
            ("sdc", False), ("sdd", False), ("sde", False),
            ("sdf", False), ("sdg", False), ("nvme1n1", True),
        ]
        for disk_name, is_ssd in base_mock_disks:
            if parent == disk_name:
                if "nvme" in disk_name:
                    return "nvme"
                return "ssd" if is_ssd else "hdd"
        return "hdd"

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
        devices = [RaidDevice(name=dev, state="active", disk_type=self._get_dev_disk_type(dev)) for dev in payload.devices]
        if payload.spare_devices:
            devices.extend([RaidDevice(name=dev, state="spare", disk_type=self._get_dev_disk_type(dev)) for dev in payload.spare_devices])

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
