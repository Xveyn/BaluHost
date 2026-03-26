"""
Monitoring API routes.

Provides endpoints for:
- CPU, Memory, Network, Disk I/O current values and history
- Process tracking
- Retention configuration (admin only)
- Database statistics
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_current_admin
from app.core.rate_limiter import user_limiter, get_limit
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
    CurrentUptimeResponse,
    CpuHistoryResponse,
    MemoryHistoryResponse,
    NetworkHistoryResponse,
    DiskIoHistoryResponse,
    ProcessHistoryResponse,
    UptimeHistoryResponse,
    UptimeSampleSchema,
    SleepEventSchema,
    RetentionConfigResponse,
    RetentionConfigUpdate,
    RetentionConfigListResponse,
    DatabaseStatsResponse,
    MetricDatabaseStats,
    MonitoringStatusResponse,
)
from app.models.sleep import SleepStateLog
from app.services.monitoring.orchestrator import get_monitoring_orchestrator

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

import logging

_logger = logging.getLogger(__name__)


def _generate_synthetic_uptime_history(
    duration: timedelta,
    limit: int = 1000,
) -> List[UptimeSampleSchema]:
    """Generate synthetic uptime samples from known server/system start times.

    Used as last-resort fallback when neither memory buffer nor database
    has history data (e.g. monitoring_worker not running).
    """
    import time as _time
    import psutil
    from app.services.telemetry import _SERVER_START_TIME
    from app.core.config import settings

    now = datetime.now(timezone.utc)
    range_start = now - duration

    # Server info
    server_start = datetime.fromtimestamp(_SERVER_START_TIME, tz=timezone.utc)

    # System info
    if getattr(settings, "is_dev_mode", False):
        system_boot = server_start
    else:
        try:
            boot_time = psutil.boot_time()
            system_boot = datetime.fromtimestamp(boot_time, tz=timezone.utc)
        except Exception:
            system_boot = server_start

    # Don't generate samples before server started
    effective_start = max(range_start, server_start)
    if effective_start >= now:
        return []

    total_seconds = (now - effective_start).total_seconds()
    if total_seconds <= 0:
        return []

    # Aim for ~60-120 samples for good bucket coverage in the frontend
    target_samples = min(limit, 120)
    step_s = max(5.0, total_seconds / target_samples)

    samples: List[UptimeSampleSchema] = []
    t = effective_start
    while t <= now and len(samples) < limit:
        server_uptime = int((t - server_start).total_seconds())
        system_uptime = int((t - system_boot).total_seconds())

        samples.append(UptimeSampleSchema(
            timestamp=t,
            server_uptime_seconds=server_uptime,
            system_uptime_seconds=system_uptime,
            server_start_time=server_start,
            system_boot_time=system_boot,
        ))
        t += timedelta(seconds=step_s)

    return samples


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
@user_limiter.limit(get_limit("system_monitor"))
async def get_cpu_current(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current CPU metrics."""
    orchestrator = get_monitoring_orchestrator()
    sample = orchestrator.get_cpu_current_with_db_fallback(db)

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
@user_limiter.limit(get_limit("system_monitor"))
async def get_cpu_history(
    request: Request,
    response: Response,
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
        samples = orchestrator.get_cpu_history(limit)
        source_str = "memory"
        # Fallback to DB when memory buffer is empty (e.g. secondary worker)
        if not samples:
            start = datetime.now(timezone.utc) - duration
            samples = orchestrator.cpu_collector.get_history_db(db, start=start, limit=limit)
            source_str = "database (fallback)"
    else:
        start = datetime.now(timezone.utc) - duration
        samples = orchestrator.cpu_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        # Fallback to memory buffer if database is empty
        if not samples:
            samples = orchestrator.get_cpu_history(limit)
            source_str = "memory (fallback)"

    return CpuHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )


# ===== Memory Endpoints =====

@router.get("/memory/current", response_model=CurrentMemoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_memory_current(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current memory metrics."""
    orchestrator = get_monitoring_orchestrator()
    sample = orchestrator.get_memory_current_with_db_fallback(db)

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
@user_limiter.limit(get_limit("system_monitor"))
async def get_memory_history(
    request: Request,
    response: Response,
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
        samples = orchestrator.get_memory_history(limit)
        source_str = "memory"
        # Fallback to DB when memory buffer is empty (e.g. secondary worker)
        if not samples:
            start = datetime.now(timezone.utc) - duration
            samples = orchestrator.memory_collector.get_history_db(db, start=start, limit=limit)
            source_str = "database (fallback)"
    else:
        start = datetime.now(timezone.utc) - duration
        samples = orchestrator.memory_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        # Fallback to memory buffer if database is empty
        if not samples:
            samples = orchestrator.get_memory_history(limit)
            source_str = "memory (fallback)"

    return MemoryHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )


# ===== Network Endpoints =====

@router.get("/network/current", response_model=CurrentNetworkResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_network_current(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current network metrics."""
    orchestrator = get_monitoring_orchestrator()
    sample = orchestrator.get_network_current_with_db_fallback(db)

    if sample is None:
        raise HTTPException(status_code=503, detail="No network data available yet")

    # Get interface type (with SHM fallback)
    interface_type = orchestrator.get_network_interface_type()

    return CurrentNetworkResponse(
        timestamp=sample.timestamp,
        download_mbps=sample.download_mbps,
        upload_mbps=sample.upload_mbps,
        interface_type=interface_type,
    )


@router.get("/network/history", response_model=NetworkHistoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_network_history(
    request: Request,
    response: Response,
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
        samples = orchestrator.get_network_history(limit)
        source_str = "memory"
        # Fallback to DB when memory buffer is empty (e.g. secondary worker)
        if not samples:
            start = datetime.now(timezone.utc) - duration
            samples = orchestrator.network_collector.get_history_db(db, start=start, limit=limit)
            source_str = "database (fallback)"
    else:
        start = datetime.now(timezone.utc) - duration
        samples = orchestrator.network_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        # Fallback to memory buffer if database is empty
        if not samples:
            samples = orchestrator.get_network_history(limit)
            source_str = "memory (fallback)"

    return NetworkHistoryResponse(
        samples=samples,
        sample_count=len(samples),
        source=source_str,
    )


# ===== Disk I/O Endpoints =====

@router.get("/disk-io/current", response_model=CurrentDiskIoResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_disk_io_current(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current disk I/O metrics for all disks."""
    orchestrator = get_monitoring_orchestrator()
    disks = orchestrator.get_disk_io_current_with_db_fallback(db)

    return CurrentDiskIoResponse(disks=disks)


@router.get("/disk-io/history", response_model=DiskIoHistoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_disk_io_history(
    request: Request,
    response: Response,
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

    disks: Dict[str, list] = {}

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        hist = orchestrator.get_disk_io_history(disk_name)
        if disk_name:
            disks = {disk_name: hist} if isinstance(hist, list) else {disk_name: []}
        else:
            disks = hist if isinstance(hist, dict) else {}
        source_str = "memory"
        # Fallback to DB when memory buffer is empty (e.g. secondary worker)
        if not any(disks.values()):
            start = datetime.now(timezone.utc) - duration
            samples = orchestrator.disk_io_collector.get_history_db(db, start=start, limit=limit)
            if samples:
                disks = {}
                for sample in samples:
                    if disk_name and sample.disk_name != disk_name:
                        continue
                    if sample.disk_name not in disks:
                        disks[sample.disk_name] = []
                    disks[sample.disk_name].append(sample)
                source_str = "database (fallback)"
    else:
        # Get from database
        start = datetime.now(timezone.utc) - duration
        samples = orchestrator.disk_io_collector.get_history_db(db, start=start, limit=limit)

        # Fallback to memory buffer if database query returned no results at all
        if not samples:
            hist = orchestrator.get_disk_io_history(disk_name)
            if disk_name:
                disks = {disk_name: hist} if isinstance(hist, list) else {disk_name: []}
            else:
                disks = hist if isinstance(hist, dict) else {}
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

    # Derive available_disks with SHM fallback
    available_disks = orchestrator.get_disk_io_available_disks()
    if not available_disks:
        available_disks = list(disks.keys())

    return DiskIoHistoryResponse(
        disks=disks,
        available_disks=available_disks,
        sample_count=total_samples,
        source=source_str,
    )


# ===== Process Endpoints =====

@router.get("/processes/current", response_model=CurrentProcessResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_processes_current(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
):
    """Get current BaluHost process status."""
    orchestrator = get_monitoring_orchestrator()
    processes = orchestrator.get_process_current()

    return CurrentProcessResponse(processes=processes)


@router.get("/processes/history", response_model=ProcessHistoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_processes_history(
    request: Request,
    response: Response,
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
        # Fallback to DB when memory buffer is empty (e.g. secondary worker)
        if not any(processes.values()):
            start = datetime.now(timezone.utc) - duration
            samples = orchestrator.process_tracker.get_history_db(db, process_name=process_name, start=start)
            if samples:
                processes = {}
                for sample in samples:
                    if sample.process_name not in processes:
                        processes[sample.process_name] = []
                    processes[sample.process_name].append(sample)
                source_str = "database (fallback)"
    else:
        # Get from database
        start = datetime.now(timezone.utc) - duration
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


# ===== Uptime Endpoints =====

@router.get("/uptime/current", response_model=CurrentUptimeResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_uptime_current(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current server and system uptime."""
    orchestrator = get_monitoring_orchestrator()
    sample = orchestrator.get_uptime_current_with_db_fallback(db)

    if sample is not None:
        return CurrentUptimeResponse(
            timestamp=sample.timestamp,
            server_uptime_seconds=sample.server_uptime_seconds,
            system_uptime_seconds=sample.system_uptime_seconds,
            server_start_time=sample.server_start_time,
            system_boot_time=sample.system_boot_time,
        )

    # Fallback: compute live (uptime is always available)
    import time
    import psutil
    from app.services.telemetry import _SERVER_START_TIME
    from app.core.config import settings

    now = time.time()
    server_uptime = int(now - _SERVER_START_TIME)
    server_start = datetime.fromtimestamp(_SERVER_START_TIME, tz=timezone.utc)

    if getattr(settings, "is_dev_mode", False):
        system_boot = server_start
        system_uptime = server_uptime
    else:
        try:
            boot_time = psutil.boot_time()
            system_boot = datetime.fromtimestamp(boot_time, tz=timezone.utc)
            system_uptime = int(now - boot_time)
        except Exception:
            system_boot = server_start
            system_uptime = server_uptime

    return CurrentUptimeResponse(
        timestamp=datetime.now(timezone.utc),
        server_uptime_seconds=server_uptime,
        system_uptime_seconds=system_uptime,
        server_start_time=server_start,
        system_boot_time=system_boot,
    )


@router.get("/uptime/history", response_model=UptimeHistoryResponse)
@user_limiter.limit(get_limit("system_monitor"))
async def get_uptime_history(
    request: Request,
    response: Response,
    time_range: TimeRangeEnum = Query(default=TimeRangeEnum.ONE_HOUR),
    source: DataSource = Query(default=DataSource.AUTO),
    limit: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get uptime metrics history."""
    orchestrator = get_monitoring_orchestrator()
    duration = _parse_time_range(time_range)

    if source == DataSource.MEMORY or (source == DataSource.AUTO and duration <= timedelta(minutes=10)):
        samples = orchestrator.get_uptime_history(limit)
        source_str = "memory"
        if not samples:
            start = datetime.now(timezone.utc) - duration
            samples = orchestrator.uptime_collector.get_history_db(db, start=start, limit=limit)
            source_str = "database (fallback)"
    else:
        start = datetime.now(timezone.utc) - duration
        samples = orchestrator.uptime_collector.get_history_db(db, start=start, limit=limit)
        source_str = "database"
        if not samples:
            samples = orchestrator.get_uptime_history(limit)
            source_str = "memory (fallback)"

    # Last-resort fallback: generate synthetic history from known start times.
    # Ensures the frontend always shows uptime status even when the
    # monitoring_worker process is not running or hasn't persisted yet.
    if not samples:
        samples = _generate_synthetic_uptime_history(duration, limit)
        source_str = "live (computed)"

    # Query sleep state events for the time range
    range_start = datetime.now(timezone.utc) - duration

    # Get the most recent event before range start to know initial state
    initial_event = db.query(SleepStateLog).filter(
        SleepStateLog.timestamp < range_start
    ).order_by(SleepStateLog.timestamp.desc()).first()

    sleep_rows = db.query(SleepStateLog).filter(
        SleepStateLog.timestamp >= range_start
    ).order_by(SleepStateLog.timestamp.asc()).all()

    # Build sleep events list (include initial event if it exists)
    all_sleep_rows = ([initial_event] if initial_event else []) + list(sleep_rows)
    sleep_events = [
        SleepEventSchema(
            timestamp=row.timestamp,
            previous_state=row.previous_state,
            new_state=row.new_state,
            duration_seconds=row.duration_seconds,
        )
        for row in all_sleep_rows
    ]

    return UptimeHistoryResponse(
        samples=samples,
        sleep_events=sleep_events,
        sample_count=len(samples),
        source=source_str,
    )


# ===== Retention Configuration (Admin Only) =====

@router.get("/config/retention", response_model=RetentionConfigListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_retention_config(
    request: Request,
    response: Response,
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
            retention_hours=cast(int, config.retention_hours),
            db_persist_interval=cast(int, config.db_persist_interval),
            is_enabled=cast(bool, config.is_enabled),
            last_cleanup=cast(Optional[datetime], config.last_cleanup),
            samples_cleaned=cast(int, config.samples_cleaned),
        ))

    return RetentionConfigListResponse(configs=configs)


@router.put("/config/retention/{metric_type}", response_model=RetentionConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_retention_config(
    request: Request,
    response: Response,
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
        retention_hours=cast(int, config.retention_hours),
        db_persist_interval=cast(int, config.db_persist_interval),
        is_enabled=cast(bool, config.is_enabled),
        last_cleanup=cast(Optional[datetime], config.last_cleanup),
        samples_cleaned=cast(int, config.samples_cleaned),
    )


# ===== Database Statistics (Admin Only) =====

@router.get("/stats/database", response_model=DatabaseStatsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_database_stats(
    request: Request,
    response: Response,
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
@user_limiter.limit(get_limit("system_monitor"))
async def get_monitoring_status(
    request: Request,
    response: Response,
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
@user_limiter.limit(get_limit("admin_operations"))
async def trigger_cleanup(
    request: Request,
    response: Response,
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
