from __future__ import annotations

import logging
import platform
import re
import subprocess
import time
from typing import List, Tuple

import psutil

from app.core.config import settings
from app.schemas.system import (
    CPUStats,
    DiskStats,
    MemoryStats,
    ProcessInfo,
    ProcessListResponse,
    QuotaStatus,
    StorageBreakdownResponse,
    StorageDeviceEntry,
    StorageInfo,
    SystemInfo,
)
from app.services import files as file_service
from app.services import telemetry as telemetry_service
from app.services.hardware.sensors import get_cpu_sensor_data

logger = logging.getLogger(__name__)


def _get_cpu_model() -> str | None:
    """Ermittelt das CPU-Modell plattformunabhängig."""
    try:
        system = platform.system()
        model = None
        
        if system == "Windows":
            # Windows: PowerShell für Marketing-Namen
            result = subprocess.run(
                ["powershell", "-Command", 
                 "Get-CimInstance -ClassName Win32_Processor | Select-Object -ExpandProperty Name"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                model = result.stdout.strip()
        
        elif system == "Linux":
            # Linux: /proc/cpuinfo
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("model name"):
                        model = line.split(":", 1)[1].strip()
                        break
        
        elif system == "Darwin":
            # macOS: sysctl
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                model = result.stdout.strip()
        
        # Fallback auf platform.processor()
        if not model:
            model = platform.processor()
        
        # Bereinige den CPU-Namen
        if model and model.strip():
            model = model.strip()
            # Entferne überflüssige Suffixe wie "12-Core Processor", "CPU", etc.
            model = re.sub(r'\s+\d+-Core\s+Processor\s*$', '', model, flags=re.IGNORECASE)
            model = re.sub(r'\s+Processor\s*$', '', model, flags=re.IGNORECASE)
            model = re.sub(r'\s+CPU\s*$', '', model, flags=re.IGNORECASE)
            # Entferne mehrfache Leerzeichen
            model = re.sub(r'\s+', ' ', model).strip()
            return model if model else None
            
    except Exception as e:
        logger.debug(f"Fehler beim Ermitteln des CPU-Modells: {e}")
    
    return None


def _get_memory_info() -> Tuple[int | None, str | None]:
    """Ermittelt RAM-Geschwindigkeit (MT/s) und Typ (DDR4/DDR5)."""
    try:
        if platform.system() == "Windows":
            # Windows: PowerShell verwenden
            result = subprocess.run(
                ["powershell", "-Command", 
                 "Get-CimInstance -ClassName Win32_PhysicalMemory | Select-Object -First 1 Speed, SMBIOSMemoryType"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                if len(lines) >= 3:  # Header + Separator + Data
                    data_line = lines[2].strip()
                    parts = data_line.split()
                    if len(parts) >= 2:
                        speed_mts = int(parts[0])
                        memory_type_code = int(parts[1])
                        
                        # SMBIOSMemoryType Codes: 26=DDR4, 34=DDR5, 24=DDR3
                        memory_type_map = {
                            20: "DDR",
                            21: "DDR2",
                            24: "DDR3",
                            26: "DDR4",
                            34: "DDR5"
                        }
                        memory_type = memory_type_map.get(memory_type_code, f"Type {memory_type_code}")
                        
                        return speed_mts, memory_type
        
        elif platform.system() == "Linux":
            # Linux: dmidecode verwenden (benötigt root)
            result = subprocess.run(
                ["sudo", "dmidecode", "-t", "memory"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                speed_mts = None
                memory_type = None
                
                for line in result.stdout.split('\n'):
                    if "Speed:" in line and "MT/s" in line:
                        match = re.search(r'(\d+)\s*MT/s', line)
                        if match:
                            speed_mts = int(match.group(1))
                    elif "Type:" in line:
                        match = re.search(r'Type:\s*(DDR\d*)', line)
                        if match:
                            memory_type = match.group(1)
                
                if speed_mts or memory_type:
                    return speed_mts, memory_type
    
    except Exception as e:
        logger.debug(f"Fehler beim Ermitteln der RAM-Informationen: {e}")
    
    return None, None


def get_system_info() -> SystemInfo:
    telemetry_cpu_usage = telemetry_service.get_latest_cpu_usage()
    telemetry_memory_sample = telemetry_service.get_latest_memory_sample()

    if settings.is_dev_mode:
        # Storage: Calculate from actual dev-storage directory
        total_storage = settings.nas_quota_bytes or 5 * 1024 ** 3
        used_storage = min(file_service.calculate_used_bytes(), total_storage)
        free_storage = max(total_storage - used_storage, 0)

        # Memory: Use telemetry data if available, otherwise use psutil
        if telemetry_memory_sample is not None:
            memory_total = telemetry_memory_sample.total
            memory_used = telemetry_memory_sample.used
            memory_free = telemetry_memory_sample.total - telemetry_memory_sample.used
        else:
            # Fallback to actual system memory via psutil
            try:
                virtual_mem = psutil.virtual_memory()
                memory_total = virtual_mem.total
                memory_used = virtual_mem.total - virtual_mem.available
                memory_free = virtual_mem.available
            except Exception:
                # Last resort simulation
                memory_total = 8 * 1024 ** 3
                memory_used = 3 * 1024 ** 3
                memory_free = memory_total - memory_used

        # CPU: Use telemetry or psutil
        cpu_usage = telemetry_cpu_usage if telemetry_cpu_usage is not None else 18.5
        if telemetry_cpu_usage == 0.0:
            cpu_usage = 18.5
        cpu_cores = psutil.cpu_count(logical=True) or 4
        
        # CPU Frequency and Temperature from sensor service
        cpu_sensor_data = get_cpu_sensor_data()
        cpu_frequency = cpu_sensor_data.frequency_mhz
        cpu_temperature = cpu_sensor_data.temperature_celsius

        # Uptime: Use server uptime (since backend started)
        uptime_seconds = telemetry_service.get_server_uptime()

        # Hardware-Informationen abrufen
        cpu_model = _get_cpu_model()
        ram_speed, ram_type = _get_memory_info()

        return SystemInfo(
            cpu=CPUStats(usage=cpu_usage, cores=cpu_cores, frequency_mhz=cpu_frequency, temperature_celsius=cpu_temperature, model=cpu_model),
            memory=MemoryStats(total=memory_total, used=memory_used, free=memory_free, speed_mts=ram_speed, type=ram_type),
            disk=DiskStats(total=total_storage, used=used_storage, free=free_storage),
            uptime=uptime_seconds,
            system_uptime=uptime_seconds,  # Dev mode: same as server uptime
            dev_mode=True,
        )

    try:
        cpu_usage = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count(logical=True) or 1
        
        # Use sensor service for frequency and temperature
        cpu_sensor_data = get_cpu_sensor_data()
        cpu_frequency = cpu_sensor_data.frequency_mhz
        cpu_temperature = cpu_sensor_data.temperature_celsius

        virtual_mem = psutil.virtual_memory()
        disk_usage = psutil.disk_usage(settings.nas_storage_path)
        uptime_seconds = time.time() - psutil.boot_time()
    except Exception:  # pragma: no cover - fallback on unsupported systems
        cpu_usage = 12.5
        cpu_count = 4
        cpu_frequency = None
        cpu_temperature = None
        virtual_mem = psutil._common.svmem(  # type: ignore[attr-defined]
            total=8 * 1024 ** 3,
            available=6 * 1024 ** 3,
            percent=25.0,
            used=2 * 1024 ** 3,
            free=6 * 1024 ** 3,
            active=0,
            inactive=0,
            buffers=0,
            cached=0,
            shared=0,
            slab=0,
        )
        disk_usage = psutil._common.sdiskusage(  # type: ignore[attr-defined]
            total=10 * 1024 ** 3,
            used=2 * 1024 ** 3,
            free=8 * 1024 ** 3,
            percent=20.0,
        )
        uptime_seconds = 3600.0

    effective_cpu_usage = telemetry_cpu_usage if telemetry_cpu_usage is not None else cpu_usage
    if telemetry_memory_sample is not None:
        memory_total = telemetry_memory_sample.total
        memory_used = telemetry_memory_sample.used
        memory_free = telemetry_memory_sample.total - telemetry_memory_sample.used
    else:
        memory_total = virtual_mem.total
        memory_used = virtual_mem.total - virtual_mem.available
        memory_free = virtual_mem.available

    # Use server uptime (since backend started)
    server_uptime = telemetry_service.get_server_uptime()

    # Hardware-Informationen abrufen
    cpu_model = _get_cpu_model()
    ram_speed, ram_type = _get_memory_info()

    return SystemInfo(
        cpu=CPUStats(usage=effective_cpu_usage, cores=cpu_count, frequency_mhz=cpu_frequency, temperature_celsius=cpu_temperature, model=cpu_model),
        memory=MemoryStats(total=memory_total, used=memory_used, free=memory_free, speed_mts=ram_speed, type=ram_type),
        disk=DiskStats(total=disk_usage.total, used=disk_usage.used, free=disk_usage.free),
        uptime=server_uptime,
        system_uptime=uptime_seconds,
        dev_mode=False,
    )


def get_storage_info() -> StorageInfo:
    if settings.is_dev_mode:
        total_storage = settings.nas_quota_bytes or 5 * 1024 ** 3
        used_storage = min(file_service.calculate_used_bytes(), total_storage)
        free_storage = max(total_storage - used_storage, 0)
        percent = (used_storage / total_storage * 100) if total_storage else 0.0

        return StorageInfo(
            filesystem="baluhost-dev",
            total=total_storage,
            used=used_storage,
            available=free_storage,
            use_percent=f"{percent:.0f}%",
            mount_point=settings.nas_storage_path,
        )

    try:
        disk = psutil.disk_usage(settings.nas_storage_path)
        filesystem = platform.system().lower()
    except Exception:  # pragma: no cover - fallback when disk usage unavailable
        disk = psutil._common.sdiskusage(  # type: ignore[attr-defined]
            total=10 * 1024 ** 3,
            used=2 * 1024 ** 3,
            free=8 * 1024 ** 3,
            percent=20.0,
        )
        filesystem = "mockfs"

    used_percent = f"{disk.percent:.0f}%"
    return StorageInfo(
        filesystem=filesystem,
        total=disk.total,
        used=disk.used,
        available=disk.free,
        use_percent=used_percent,
        mount_point=settings.nas_storage_path,
    )


def get_aggregated_storage_info() -> StorageInfo:
    """Gibt aggregierte Speicherinformationen über alle Festplatten zurück.
    
    Berücksichtigt SMART-Daten aller Festplatten und RAID-Arrays.
    Bei RAID wird die effektive Kapazität berechnet.
    
    Diese Funktion verwendet IMMER die echten Festplatten-Daten aus SMART,
    auch im Dev-Mode, um die tatsächliche Hardware-Kapazität anzuzeigen.
    """
    from app.services.hardware import smart as smart_service
    from app.services.hardware import raid as raid_service
    
    try:
        # Hole SMART-Daten für alle Festplatten (auch im Dev-Mode)
        smart_data = smart_service.get_smart_status()
        logger.info(f"get_aggregated_storage_info: Found {len(smart_data.devices)} SMART devices")

        # Hole RAID-Informationen
        try:
            raid_data = raid_service.get_status()
            has_raid = bool(raid_data.arrays)
        except Exception:
            has_raid = False
            raid_data = None

        total_capacity = 0
        total_used = 0
        device_count = 0
        raid_effective = False

        if has_raid and raid_data and raid_data.arrays:
            # RAID ist aktiv - verwende find_raid_mountpoint() für zuverlässige Erkennung
            from app.services.hardware.raid import find_raid_mountpoint
            raid_effective = True

            for array in raid_data.arrays:
                mountpoint = find_raid_mountpoint(array.name)
                if mountpoint:
                    usage = psutil.disk_usage(mountpoint)
                    total_capacity += usage.total
                    total_used += usage.used
                    device_count += len(array.devices)
                else:
                    # Fallback: Array-Größe aus RAID-Status nutzen
                    total_capacity += array.size_bytes
                    device_count += len(array.devices)
                    # Used bytes vom ersten passenden SMART-Device holen
                    member_base_names = {re.sub(r'\d+$', '', dev.name) for dev in array.devices}
                    for smart_dev in smart_data.devices:
                        dev_base = smart_dev.name.replace('/dev/', '').lower()
                        if dev_base in member_base_names and smart_dev.used_bytes is not None:
                            total_used += smart_dev.used_bytes
                            break  # Bei RAID 1 nur einmal zählen
                    logger.info("RAID %s not mounted, using size_bytes=%d as capacity", array.name, array.size_bytes)
        else:
            # Kein RAID - summiere alle einzelnen Festplatten
            logger.info(f"Aggregating {len(smart_data.devices)} devices without RAID")
            for device in smart_data.devices:
                if device.capacity_bytes is not None:
                    total_capacity += device.capacity_bytes
                    device_count += 1
                    logger.info(f"Device {device.name}: capacity={device.capacity_bytes / (1024**3):.2f} GB")
                else:
                    logger.warning(f"Device {device.name}: no capacity_bytes")
                
                if device.used_bytes is not None:
                    total_used += device.used_bytes
                    logger.info(f"Device {device.name}: used={device.used_bytes / (1024**3):.2f} GB")
                else:
                    logger.info(f"Device {device.name}: no used_bytes")
        
        # Berechne verfügbaren Speicher und Prozentsatz
        total_available = max(total_capacity - total_used, 0)
        use_percent = (total_used / total_capacity * 100) if total_capacity > 0 else 0.0
        
        logger.info(f"Aggregated storage: total={total_capacity / (1024**3):.2f} GB, used={total_used / (1024**3):.2f} GB, percent={use_percent:.1f}%")
        
        # Wenn Kapazität vorhanden, aber keine Nutzungsdaten, hole sie von psutil
        if total_capacity > 0 and total_used == 0:
            logger.info("Have capacity but no usage data from SMART, getting usage from psutil")
            try:
                partitions = psutil.disk_partitions(all=False)

                for partition in partitions:
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        total_used += usage.used
                    except (PermissionError, OSError):
                        pass
                
                total_available = max(total_capacity - total_used, 0)
                use_percent = (total_used / total_capacity * 100) if total_capacity > 0 else 0.0
            except Exception as e:
                logger.error("Failed to get usage via psutil: %s", e)
        
        # Wenn keine SMART-Daten verfügbar sind, versuche direkt psutil für alle Partitionen
        if total_capacity == 0:
            logger.warning("No SMART capacity data available, trying direct psutil approach")
            try:
                partitions = psutil.disk_partitions(all=False)
                seen_devices = set()
                
                for partition in partitions:
                    # Überspringe Duplikate basierend auf Device
                    if partition.device in seen_devices:
                        continue
                    seen_devices.add(partition.device)
                    
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        total_capacity += usage.total
                        total_used += usage.used
                        device_count += 1
                    except (PermissionError, OSError):
                        pass
                
                total_available = max(total_capacity - total_used, 0)
                use_percent = (total_used / total_capacity * 100) if total_capacity > 0 else 0.0
                
                if total_capacity > 0:
                    return StorageInfo(
                        filesystem="psutil-aggregated",
                        total=total_capacity,
                        used=total_used,
                        available=total_available,
                        use_percent=f"{use_percent:.1f}%",
                        mount_point=f"{device_count} partitions",
                    )
            except Exception as e:
                logger.error("Failed to get storage via psutil: %s", e)
            
            # Letzter Fallback
            return get_storage_info()
        
        return StorageInfo(
            filesystem="aggregated" if not raid_effective else "raid-aggregated",
            total=total_capacity,
            used=total_used,
            available=total_available,
            use_percent=f"{use_percent:.1f}%",
            mount_point=f"{device_count} devices" + (" (RAID)" if raid_effective else ""),
        )
        
    except Exception as e:
        logger.warning("Failed to get aggregated storage info, falling back: %s", e)
        return get_storage_info()


def get_storage_breakdown() -> StorageBreakdownResponse:
    """Return per-array/device storage breakdown with usage data.

    Each RAID array becomes one entry.  Standalone SMART devices that are
    not part of any array are listed individually.
    """
    from app.services.hardware import smart as smart_service
    from app.services.hardware import raid as raid_service
    from app.services.hardware.raid import find_raid_mountpoint

    entries: list[StorageDeviceEntry] = []

    try:
        smart_data = smart_service.get_smart_status()
    except Exception:
        smart_data = None

    try:
        raid_data = raid_service.get_status()
    except Exception:
        raid_data = None

    raid_member_devices: set[str] = set()

    if raid_data and raid_data.arrays:
        for array in raid_data.arrays:
            # Collect member base names so we can exclude them later
            for dev in array.devices:
                raid_member_devices.add(re.sub(r'\d+$', '', dev.name))

            # Determine disk_type from majority of non-cache devices
            non_cache_types = [d.disk_type for d in array.devices if d.state not in ("spare",)]
            if non_cache_types:
                disk_type = max(set(non_cache_types), key=non_cache_types.count)
            else:
                disk_type = "hdd"

            level_short = array.level.replace("raid", "").upper()
            label = f"RAID {level_short} ({disk_type.upper()})"

            # Get usage via mountpoint
            mountpoint = find_raid_mountpoint(array.name)
            if mountpoint:
                try:
                    usage = psutil.disk_usage(mountpoint)
                    entries.append(StorageDeviceEntry(
                        name=array.name,
                        label=label,
                        level=array.level,
                        disk_type=disk_type,
                        capacity_bytes=usage.total,
                        used_bytes=usage.used,
                        available_bytes=usage.free,
                        use_percent=round(usage.percent, 1),
                        device_count=len(array.devices),
                    ))
                    continue
                except Exception:
                    pass

            # Fallback: use array size_bytes from RAID status
            used = 0
            if smart_data:
                member_bases = {re.sub(r'\d+$', '', d.name) for d in array.devices}
                for sd in smart_data.devices:
                    dev_base = sd.name.replace('/dev/', '').lower()
                    if dev_base in member_bases and sd.used_bytes is not None:
                        used = sd.used_bytes
                        break

            cap = array.size_bytes
            avail = max(cap - used, 0)
            pct = round((used / cap * 100), 1) if cap > 0 else 0.0

            entries.append(StorageDeviceEntry(
                name=array.name,
                label=label,
                level=array.level,
                disk_type=disk_type,
                capacity_bytes=cap,
                used_bytes=used,
                available_bytes=avail,
                use_percent=pct,
                device_count=len(array.devices),
            ))

    # Add standalone devices not in any RAID
    if smart_data:
        for device in smart_data.devices:
            dev_base = device.name.replace('/dev/', '').lower()
            if dev_base in raid_member_devices:
                continue
            if device.capacity_bytes is None or device.capacity_bytes == 0:
                continue

            is_ssd = "nvme" in dev_base or "ssd" in (device.model or "").lower()
            dtype = "nvme" if "nvme" in dev_base else ("ssd" if is_ssd else "hdd")
            label = f"{dtype.upper()} Disk"

            used = device.used_bytes or 0
            cap = device.capacity_bytes
            avail = max(cap - used, 0)
            pct = round((used / cap * 100), 1) if cap > 0 else 0.0

            entries.append(StorageDeviceEntry(
                name=dev_base,
                label=label,
                level=None,
                disk_type=dtype,
                capacity_bytes=cap,
                used_bytes=used,
                available_bytes=avail,
                use_percent=pct,
                device_count=1,
            ))

    total_cap = sum(e.capacity_bytes for e in entries)
    total_used = sum(e.used_bytes for e in entries)
    total_avail = max(total_cap - total_used, 0)
    total_pct = round((total_used / total_cap * 100), 1) if total_cap > 0 else 0.0

    # Raw capacity = sum of all physical disk capacities (before RAID redundancy)
    total_raw = 0
    if smart_data:
        for device in smart_data.devices:
            if device.capacity_bytes and device.capacity_bytes > 0:
                total_raw += device.capacity_bytes
    if total_raw == 0:
        total_raw = total_cap  # Fallback if no SMART data

    return StorageBreakdownResponse(
        entries=entries,
        total_capacity=total_cap,
        total_raw_capacity=total_raw,
        total_used=total_used,
        total_available=total_avail,
        total_use_percent=total_pct,
    )


def get_process_list(limit: int = 20) -> ProcessListResponse:
    processes: List[ProcessInfo] = []
    try:
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "username"]):
            info = proc.info
            processes.append(
                ProcessInfo(
                    pid=info.get("pid", 0),
                    name=info.get("name") or "unknown",
                    cpu=float(info.get("cpu_percent") or 0.0),
                    memory=float(info.get("memory_percent") or 0.0),
                    user=info.get("username") or "unknown",
                )
            )
    except Exception:  # pragma: no cover - fallback for unsupported platforms
        processes = [
            ProcessInfo(pid=1234, name="node server", cpu=2.5, memory=1.2, user="root"),
            ProcessInfo(pid=5678, name="uvicorn", cpu=1.1, memory=0.8, user="baluhost"),
        ]

    processes.sort(key=lambda proc: proc.memory, reverse=True)
    return ProcessListResponse(processes=processes[:limit])


def get_quota_status() -> QuotaStatus:
    used_bytes = file_service.calculate_used_bytes()
    limit = settings.nas_quota_bytes

    if limit is None:
        return QuotaStatus(
            limit_bytes=None,
            used_bytes=used_bytes,
            available_bytes=None,
            percent_used=None,
        )

    available = max(limit - used_bytes, 0)
    percent = min((used_bytes / limit) * 100, 100.0) if limit else None
    return QuotaStatus(
        limit_bytes=limit,
        used_bytes=used_bytes,
        available_bytes=available,
        percent_used=percent,
    )
