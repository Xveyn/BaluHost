from __future__ import annotations

import logging
import platform
import time
from typing import List

import psutil

from app.core.config import settings
from app.schemas.system import (
    CPUStats,
    DiskStats,
    MemoryStats,
    ProcessInfo,
    ProcessListResponse,
    QuotaStatus,
    StorageInfo,
    SystemInfo,
)
from app.services import files as file_service
from app.services import telemetry as telemetry_service

logger = logging.getLogger(__name__)


def get_system_info() -> SystemInfo:
    telemetry_cpu_usage = telemetry_service.get_latest_cpu_usage()
    telemetry_memory_sample = telemetry_service.get_latest_memory_sample()

    if settings.is_dev_mode:
        # Storage: Calculate from actual dev-storage directory
        total_storage = settings.nas_quota_bytes or 10 * 1024 ** 3
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

        # Uptime: Use server uptime (since backend started)
        uptime_seconds = telemetry_service.get_server_uptime()

        return SystemInfo(
            cpu=CPUStats(usage=cpu_usage, cores=cpu_cores),
            memory=MemoryStats(total=memory_total, used=memory_used, free=memory_free),
            disk=DiskStats(total=total_storage, used=used_storage, free=free_storage),
            uptime=uptime_seconds,
        )

    try:
        cpu_usage = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count(logical=True) or 1

        virtual_mem = psutil.virtual_memory()
        disk_usage = psutil.disk_usage(settings.nas_storage_path)
        uptime_seconds = time.time() - psutil.boot_time()
    except Exception:  # pragma: no cover - fallback on unsupported systems
        cpu_usage = 12.5
        cpu_count = 4
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
        memory_used = virtual_mem.used
        memory_free = virtual_mem.free

    # Use server uptime (since backend started)
    server_uptime = telemetry_service.get_server_uptime()

    return SystemInfo(
        cpu=CPUStats(usage=effective_cpu_usage, cores=cpu_count),
        memory=MemoryStats(total=memory_total, used=memory_used, free=memory_free),
        disk=DiskStats(total=disk_usage.total, used=disk_usage.used, free=disk_usage.free),
        uptime=server_uptime,
    )


def get_storage_info() -> StorageInfo:
    if settings.is_dev_mode:
        total_storage = settings.nas_quota_bytes or 10 * 1024 ** 3
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
    from app.services import smart as smart_service
    from app.services import raid as raid_service
    
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
            # RAID ist aktiv - verwende RAID-effektive Kapazität
            raid_effective = True
            
            for array in raid_data.arrays:
                total_capacity += array.size_bytes
                device_count += len(array.devices)
            
            # Bei RAID: Verwende psutil für tatsächliche Nutzung des RAID-Volumes
            # (nicht die Summe der einzelnen Geräte, da RAID Daten spiegelt/verteilt)
            try:
                import psutil
                partitions = psutil.disk_partitions()
                
                # Finde RAID mount points (normalerweise /md0, /md1, etc. oder Windows RAID volumes)
                for partition in partitions:
                    if '/md' in partition.device or 'raid' in partition.device.lower():
                        try:
                            usage = psutil.disk_usage(partition.mountpoint)
                            total_used += usage.used
                        except (PermissionError, OSError):
                            pass
                
                # Fallback: Wenn keine RAID-Partitionen gefunden, verwende Durchschnitt der Geräte
                if total_used == 0:
                    device_count_with_usage = 0
                    device_sum_used = 0
                    for device in smart_data.devices:
                        if device.used_bytes is not None and device.used_bytes > 0:
                            device_sum_used += device.used_bytes
                            device_count_with_usage += 1
                    
                    # Für RAID 1/5/6: Nutze den Durchschnitt, nicht die Summe
                    if device_count_with_usage > 0:
                        total_used = device_sum_used // device_count_with_usage
                        
            except Exception as e:
                logger.debug("Could not get RAID usage from psutil: %s", e)
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
                import psutil
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
                import psutil
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
