"""Filesystem usage enrichment for SMART devices.

Leaf module — lazy-imports raid_service at runtime.
"""
from __future__ import annotations

import logging
import platform

from app.schemas.system import SmartDevice

logger = logging.getLogger(__name__)


def _enrich_with_filesystem_usage(devices: list[SmartDevice]) -> None:
    """Fügt used_bytes, used_percent und mount_point zu SMART-Geräten hinzu.

    Nutzt psutil um Partitionen und deren Nutzung zu ermitteln und gleicht sie
    mit den physischen SMART-Geräten ab.
    """
    try:
        import psutil
    except ImportError:
        logger.warning("psutil nicht verfügbar - keine Filesystem-Nutzungsdaten")
        return

    try:
        partitions = psutil.disk_partitions(all=False)

        # Erstelle Mapping: device_name -> usage_info
        partition_usage: dict[str, tuple[int, int, str]] = {}  # {device: (used, total, mountpoint)}

        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                device_key = partition.device.lower()

                # Windows: Normalisiere Laufwerksbuchstaben (C:\ -> c)
                if platform.system().lower() == 'windows':
                    if ':' in device_key:
                        device_key = device_key.split(':')[0].strip()

                # Aggregiere Nutzung pro physischem Gerät
                if device_key in partition_usage:
                    old_used, old_total, old_mount = partition_usage[device_key]
                    partition_usage[device_key] = (
                        old_used + usage.used,
                        old_total + usage.total,
                        f"{old_mount}, {partition.mountpoint}"
                    )
                else:
                    partition_usage[device_key] = (usage.used, usage.total, partition.mountpoint)

            except (PermissionError, OSError) as e:
                logger.debug(f"Konnte Partition {partition.mountpoint} nicht lesen: {e}")
                continue

        # RAID-aware: Erstelle Mapping member_base_name -> (used, total, mountpoint, array_name)
        raid_member_map: dict[str, tuple[int, int, str | None, str]] = {}
        try:
            from app.services import raid as raid_service
            from app.services.hardware.raid import find_raid_mountpoint
            raid_data = raid_service.get_status()
            if raid_data and raid_data.arrays:
                for array in raid_data.arrays:
                    mountpoint = find_raid_mountpoint(array.name)
                    if mountpoint:
                        try:
                            array_usage = psutil.disk_usage(mountpoint)
                            # Map each member device base name to array usage
                            for member_dev in array.devices:
                                import re as _re
                                base_name = _re.sub(r'\d+$', '', member_dev.name)
                                raid_member_map[base_name] = (
                                    array_usage.used,
                                    array_usage.total,
                                    mountpoint,
                                    array.name,
                                )
                        except (PermissionError, OSError) as e:
                            logger.debug("Could not get usage for RAID mountpoint %s: %s", mountpoint, e)
                    else:
                        # No mountpoint but still track membership
                        for member_dev in array.devices:
                            import re as _re
                            base_name = _re.sub(r'\d+$', '', member_dev.name)
                            raid_member_map[base_name] = (0, 0, None, array.name)
        except Exception as e:
            logger.debug("RAID enrichment failed (non-critical): %s", e)

        # Windows-spezifisch: Versuche Disk-Nummer zu Laufwerksbuchstaben-Mapping
        windows_disk_map: dict[str, str] = {}  # {"/dev/sda": "c", ...}
        if platform.system().lower() == 'windows' and partition_usage:
            import subprocess
            try:
                # Get-PhysicalDisk und Get-Partition Mapping
                ps_cmd = """
                Get-PhysicalDisk | ForEach-Object {
                    $disk = $_
                    Get-Partition -DiskNumber $disk.DeviceId -ErrorAction SilentlyContinue |
                    Where-Object {$_.DriveLetter} | ForEach-Object {
                        Write-Output "$($disk.DeviceId),$($_.DriveLetter)"
                    }
                }
                """
                result = subprocess.run(
                    ['powershell', '-Command', ps_cmd],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10
                )

                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if ',' in line:
                            disk_num, drive_letter = line.strip().split(',')
                            # /dev/sda = Disk 0, /dev/sdb = Disk 1, etc.
                            device_name = f"/dev/sd{chr(ord('a') + int(disk_num))}"
                            windows_disk_map[device_name] = drive_letter.lower()

            except Exception as e:
                logger.debug(f"Windows disk mapping failed: {e}")

        # Anreichere SMART-Geräte mit Nutzungsdaten
        for device in devices:
            # Versuche verschiedene Matching-Strategien
            matched = False
            device_base = device.name.replace('/dev/', '').lower()

            # 0. RAID-Member: Setze used_bytes aus Array-Usage
            if device_base in raid_member_map:
                used, total, mount, array_name = raid_member_map[device_base]
                device.raid_member_of = array_name
                if used > 0:
                    device.used_bytes = used
                    # Prozent relativ zur physischen Disk-Kapazität
                    cap = device.capacity_bytes or 0
                    device.used_percent = (used / cap * 100) if cap > 0 else 0
                    device.mount_point = mount
                    matched = True
                    logger.debug("RAID matched %s -> %s: %d used", device.name, array_name, used)

            # 1. Windows: Nutze Disk-Mapping
            if not matched and device.name in windows_disk_map:
                drive_letter = windows_disk_map[device.name]
                if drive_letter in partition_usage:
                    used, total, mount = partition_usage[drive_letter]
                    device.used_bytes = used
                    device.used_percent = (used / total * 100) if total > 0 else 0
                    device.mount_point = mount
                    matched = True
                    logger.debug(f"Matched {device.name} -> {drive_letter}: {used / (1024**3):.2f} GB used")

            # 2. Linux: Direkte Device-Namen (/dev/sda -> sda)
            if not matched:
                device_key = device.name.replace('/dev/', '').lower()
                for partition_dev, (used, total, mount) in partition_usage.items():
                    if device_key in partition_dev or partition_dev in device_key:
                        device.used_bytes = used
                        device.used_percent = (used / total * 100) if total > 0 else 0
                        device.mount_point = mount
                        matched = True
                        logger.debug(f"Matched {device.name} -> {partition_dev}: {used / (1024**3):.2f} GB used")
                        break

            # 3. Fallback: Wenn keine Nutzungsdaten gefunden, lasse None
            if not matched:
                logger.debug(f"No filesystem usage found for {device.name}")

    except Exception as e:
        logger.error(f"Failed to enrich SMART data with filesystem usage: {e}")
