"""
Monitoring API routes.

Provides endpoints for:
- CPU, Memory, Network, Disk I/O current values and history
- Process tracking
- Retention configuration (admin only)
- Database statistics
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_current_admin
from app.models.user import User
from app.models.monitoring import MetricType
from app.schemas.monitoring import (
    DataSource,
    TimeRangeEnum,
    CurrentCpuResponse,
    CurrentMemoryResponse,
    CurrentNetworkResponse,
    CurrentDiskIoResponse,
    CurrentProcessResponse,
    CpuHistoryResponse,
    MemoryHistoryResponse,
    NetworkHistoryResponse,
    DiskIoHistoryResponse,
    ProcessHistoryResponse,
    RetentionConfigResponse,
    RetentionConfigUpdate,
    RetentionConfigListResponse,
    DatabaseStatsResponse,
    MetricDatabaseStats,
    MonitoringStatusResponse,
)
from app.services.monitoring.orchestrator import get_monitoring_orchestrator

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _parse_time_range(time_range: TimeRangeEnum) -> timedelta:
    """Convert time range enum to timedelta."""
    mapping = {
        TimeRangeEnum.TEN_MINUTES: timedelta(minutes=10),
        TimeRangeEnum.ONE_HOUR: timedelta(hours=1),
        TimeRangeEnum.TWENTY_FOUR_HOURS: timedelta(hours=24),
        TimeRangeEnum.SEVEN_DAYS: timedelta(days=7),
    }
    return mapping.get(time_range, timedelta(hours=1))


# ===== CPU Endpoints =====

@router.get("/cpu/current", response_model=CurrentCpuResponse)
async def get_cpu_current(
    current_user: User = Depends(get_current_user),
):
    """Get current CPU metrics."""
    orchestrator = get_monitoring_orchestrator()
    sample = orchestrator.get_cpu_current()

    if sample is None:
        raise HTTPException(status_code=503, detail="No CPU data available yet")

    return CurrentCpuResponse(
        timestamp=sample.timestamp,
        usage_percent=sample.usage_percent,
        frequency_mhz=sample.frequency_mhz,
        temperature_celsius=sample.temperature_celsius,
        core_count=sample.core_count,
        thread_count=sample.thread_count,
        p_core_count=sample.p_core_count,
        e_core_count=sample.e_core_count,
        thread_usages=sample.thread_usages,
    )


@router.get("/cpu/history", response_model=CpuHistoryResponse)
async def get_cpu_history(
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get CPU metrics history."""
    orchestrator = get_monitoring_orchestrator()
    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        samples = orchestrator.cpu_collector.get_history_memory(limit)
        source_str = "memory"
    else:
        start = datetime.utcnow() - duration
        samples = orchestrator.cpu_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        # Fallback to memory buffer if database is empty
        if not samples:
            samples = orchestrator.cpu_collector.get_history_memory(limit)
            source_str = "memory (fallback)"

    return CpuHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )


# ===== Memory Endpoints =====

@router.get("/memory/current", response_model=CurrentMemoryResponse)
async def get_memory_current(
    current_user: User = Depends(get_current_user),
):
    """Get current memory metrics."""
    orchestrator = get_monitoring_orchestrator()
    sample = orchestrator.get_memory_current()

    if sample is None:
        raise HTTPException(status_code=503, detail="No memory data available yet")

    return CurrentMemoryResponse(
        timestamp=sample.timestamp,
        used_bytes=sample.used_bytes,
        total_bytes=sample.total_bytes,
        percent=sample.percent,
        available_bytes=sample.available_bytes,
        baluhost_memory_bytes=sample.baluhost_memory_bytes,
    )


@router.get("/memory/history", response_model=MemoryHistoryResponse)
async def get_memory_history(
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get memory metrics history."""
    orchestrator = get_monitoring_orchestrator()
    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        samples = orchestrator.memory_collector.get_history_memory(limit)
        source_str = "memory"
    else:
        start = datetime.utcnow() - duration
        samples = orchestrator.memory_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        # Fallback to memory buffer if database is empty
        if not samples:
            samples = orchestrator.memory_collector.get_history_memory(limit)
            source_str = "memory (fallback)"

    return MemoryHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )


# ===== Network Endpoints =====

@router.get("/network/current", response_model=CurrentNetworkResponse)
async def get_network_current(
    current_user: User = Depends(get_current_user),
):
    """Get current network metrics."""
    orchestrator = get_monitoring_orchestrator()
    sample = orchestrator.get_network_current()

    if sample is None:
        raise HTTPException(status_code=503, detail="No network data available yet")

    return CurrentNetworkResponse(
        timestamp=sample.timestamp,
        download_mbps=sample.download_mbps,
        upload_mbps=sample.upload_mbps,
    )


@router.get("/network/history", response_model=NetworkHistoryResponse)
async def get_network_history(
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get network metrics history."""
    orchestrator = get_monitoring_orchestrator()
    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        samples = orchestrator.network_collector.get_history_memory(limit)
        source_str = "memory"
    else:
        start = datetime.utcnow() - duration
        samples = orchestrator.network_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        # Fallback to memory buffer if database is empty
        if not samples:
            samples = orchestrator.network_collector.get_history_memory(limit)
            source_str = "memory (fallback)"

    return NetworkHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )


# ===== Disk I/O Endpoints =====

@router.get("/disk-io/current", response_model=CurrentDiskIoResponse)
async def get_disk_io_current(
    current_user: User = Depends(get_current_user),
):
    """Get current disk I/O metrics for all disks."""
    orchestrator = get_monitoring_orchestrator()
    disks = orchestrator.get_disk_io_current()

    return CurrentDiskIoResponse(disks=disks)


@router.get("/disk-io/history", response_model=DiskIoHistoryResponse)
async def get_disk_io_history(
    disk_name: Optional[str] = Query(default=None, description="Filter by disk name"),
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get disk I/O metrics history."""
    orchestrator = get_monitoring_orchestrator()
    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        if disk_name:
            disks = {disk_name: orchestrator.disk_io_collector.get_disk_history(disk_name)}
        else:
            disks = orchestrator.disk_io_collector.get_all_disk_histories()
        source_str = "memory"
    else:
        # Get from database
        start = datetime.utcnow() - duration
        samples = orchestrator.disk_io_collector.get_history_db(db, start=start, limit=limit)

        # Fallback to memory buffer if database query returned no results at all
        if not samples:
            if disk_name:
                disks = {disk_name: orchestrator.disk_io_collector.get_disk_history(disk_name)}
            else:
                disks = orchestrator.disk_io_collector.get_all_disk_histories()
            source_str = "memory (fallback)"
        else:
            # Group by disk name
            disks = {}
            for sample in samples:
                if disk_name and sample.disk_name != disk_name:
                    continue
                if sample.disk_name not in disks:
                    disks[sample.disk_name] = []
                disks[sample.disk_name].append(sample)
            source_str = "database"

    total_samples = sum(len(s) for s in disks.values())

    return DiskIoHistoryResponse(
        disks=disks,
        available_disks=orchestrator.disk_io_collector.get_available_disks(),
        sample_count=total_samples,
        source=source_str,
    )


# ===== Process Endpoints =====

@router.get("/processes/current", response_model=CurrentProcessResponse)
async def get_processes_current(
    current_user: User = Depends(get_current_user),
):
    """Get current BaluHost process status."""
    orchestrator = get_monitoring_orchestrator()
    processes = orchestrator.get_process_current()

    return CurrentProcessResponse(processes=processes)


@router.get("/processes/history", response_model=ProcessHistoryResponse)
async def get_processes_history(
    process_name: Optional[str] = Query(default=None, description="Filter by process name"),
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get BaluHost process history."""
    orchestrator = get_monitoring_orchestrator()
    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        if process_name:
            processes = {process_name: orchestrator.process_tracker.get_process_history(process_name)}
        else:
            processes = orchestrator.process_tracker.get_all_histories()
        source_str = "memory"
    else:
        # Get from database
        start = datetime.utcnow() - duration
        samples = orchestrator.process_tracker.get_history_db(db, process_name=process_name, start=start)

        # Fallback to memory buffer if database query returned no results at all
        if not samples:
            if process_name:
                processes = {process_name: orchestrator.process_tracker.get_process_history(process_name)}
            else:
                processes = orchestrator.process_tracker.get_all_histories()
            source_str = "memory (fallback)"
        else:
            # Group by process name
            processes = {}
            for sample in samples:
                if sample.process_name not in processes:
                    processes[sample.process_name] = []
                processes[sample.process_name].append(sample)
            source_str = "database"

    total_samples = sum(len(s) for s in processes.values())

    # Count crashes
    crashes = 0
    for samples in processes.values():
        for s in samples:
            if not s.is_alive:
                crashes += 1

    return ProcessHistoryResponse(
        processes=processes,
        sample_count=total_samples,
        source=source_str,
        crashes_detected=crashes,
    )


# ===== Retention Configuration (Admin Only) =====

@router.get("/config/retention", response_model=RetentionConfigListResponse)
async def get_retention_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Get retention configuration for all metric types (admin only)."""
    orchestrator = get_monitoring_orchestrator()
    configs = []

    for metric_type in MetricType:
        config = orchestrator.retention_manager.get_config(db, metric_type)
        configs.append(RetentionConfigResponse(
            metric_type=metric_type.value,
            retention_hours=config.retention_hours,
            db_persist_interval=config.db_persist_interval,
            is_enabled=config.is_enabled,
            last_cleanup=config.last_cleanup,
            samples_cleaned=config.samples_cleaned,
        ))

    return RetentionConfigListResponse(configs=configs)


@router.put("/config/retention/{metric_type}", response_model=RetentionConfigResponse)
async def update_retention_config(
    metric_type: str,
    update: RetentionConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Update retention configuration for a metric type (admin only)."""
    orchestrator = get_monitoring_orchestrator()

    try:
        mt = MetricType(metric_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid metric type: {metric_type}")

    config = orchestrator.retention_manager.set_retention(db, mt, update.retention_hours)

    return RetentionConfigResponse(
        metric_type=config.metric_type.value,
        retention_hours=config.retention_hours,
        db_persist_interval=config.db_persist_interval,
        is_enabled=config.is_enabled,
        last_cleanup=config.last_cleanup,
        samples_cleaned=config.samples_cleaned,
    )


# ===== Database Statistics (Admin Only) =====

@router.get("/stats/database", response_model=DatabaseStatsResponse)
async def get_database_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Get database statistics for all metric types (admin only)."""
    orchestrator = get_monitoring_orchestrator()

    db_stats = orchestrator.retention_manager.get_database_stats(db)
    size_stats = orchestrator.retention_manager.estimate_database_size(db)

    metrics = {}
    total_samples = 0

    for metric_type, stats in db_stats.items():
        if "error" in stats:
            continue

        metrics[metric_type] = MetricDatabaseStats(
            metric_type=metric_type,
            count=stats["count"],
            oldest=datetime.fromisoformat(stats["oldest"]) if stats["oldest"] else None,
            newest=datetime.fromisoformat(stats["newest"]) if stats["newest"] else None,
            retention_hours=stats["retention_hours"],
            last_cleanup=datetime.fromisoformat(stats["last_cleanup"]) if stats["last_cleanup"] else None,
            total_cleaned=stats["total_cleaned"],
            estimated_size_bytes=size_stats.get(metric_type, 0),
        )
        total_samples += stats["count"]

    return DatabaseStatsResponse(
        metrics=metrics,
        total_samples=total_samples,
        total_size_bytes=size_stats.get("total", 0),
    )


# ===== Monitoring Status =====

@router.get("/status", response_model=MonitoringStatusResponse)
async def get_monitoring_status(
    current_user: User = Depends(get_current_user),
):
    """Get overall monitoring status."""
    orchestrator = get_monitoring_orchestrator()
    stats = orchestrator.get_stats()

    return MonitoringStatusResponse(
        is_running=stats["is_running"],
        sample_count=stats["sample_count"],
        sample_interval=stats["sample_interval"],
        buffer_size=stats["buffer_size"],
        persist_interval=stats["persist_interval"],
        last_cleanup=datetime.fromisoformat(stats["last_cleanup"]) if stats["last_cleanup"] else None,
        collectors=stats["collectors"],
    )


# ===== Manual Cleanup Trigger (Admin Only) =====

@router.post("/cleanup", response_model=dict)
async def trigger_cleanup(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Manually trigger retention cleanup (admin only)."""
    orchestrator = get_monitoring_orchestrator()
    results = orchestrator.retention_manager.run_all_cleanup(db)

    return {
        "message": "Cleanup completed",
        "deleted": results,
        "total": sum(results.values()),
    }
