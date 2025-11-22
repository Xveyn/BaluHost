from __future__ import annotations

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


def get_system_info() -> SystemInfo:
    telemetry_cpu_usage = telemetry_service.get_latest_cpu_usage()
    telemetry_memory_sample = telemetry_service.get_latest_memory_sample()

    if settings.is_dev_mode:
        total_storage = settings.nas_quota_bytes or 10 * 1024 ** 3
        used_storage = min(file_service.calculate_used_bytes(), total_storage)
        free_storage = max(total_storage - used_storage, 0)

        simulated_memory_total = 8 * 1024 ** 3
        simulated_memory_used = 3 * 1024 ** 3
        simulated_memory_free = simulated_memory_total - simulated_memory_used

        if telemetry_memory_sample is not None:
            percent = telemetry_memory_sample.percent or (
                (telemetry_memory_sample.used / telemetry_memory_sample.total) * 100
                if telemetry_memory_sample.total
                else 0.0
            )
            ratio = max(0.0, min(percent / 100.0, 1.0))
            memory_total = simulated_memory_total
            memory_used = int(simulated_memory_total * ratio)
            memory_free = simulated_memory_total - memory_used
        else:
            memory_total = simulated_memory_total
            memory_used = simulated_memory_used
            memory_free = simulated_memory_free

        cpu_usage = telemetry_cpu_usage if telemetry_cpu_usage is not None else 18.5
        if telemetry_cpu_usage == 0.0:
            cpu_usage = 18.5
        cpu_cores = psutil.cpu_count(logical=True) or 4

        return SystemInfo(
            cpu=CPUStats(usage=cpu_usage, cores=cpu_cores),
            memory=MemoryStats(total=memory_total, used=memory_used, free=memory_free),
            disk=DiskStats(total=total_storage, used=used_storage, free=free_storage),
            uptime=4 * 3600.0,
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

    return SystemInfo(
        cpu=CPUStats(usage=effective_cpu_usage, cores=cpu_count),
        memory=MemoryStats(total=memory_total, used=memory_used, free=memory_free),
        disk=DiskStats(total=disk_usage.total, used=disk_usage.used, free=disk_usage.free),
        uptime=uptime_seconds,
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
