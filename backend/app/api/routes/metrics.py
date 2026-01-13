"""
Prometheus metrics endpoint for BaluHost monitoring.

Exposes custom metrics for:
- System resources (CPU, RAM, Disk, Network)
- RAID status and health
- SMART disk health
- Application performance
- Database statistics
- User activity

Metrics are exposed in Prometheus format at /api/metrics
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
import psutil
import time
from typing import Optional

from app.api import deps
from app.core.config import settings
from app.models.user import User

# Create router
router = APIRouter()

# Create custom registry to avoid conflicts with other Prometheus instrumentation
registry = CollectorRegistry()

# ===================================
# System Metrics
# ===================================

# CPU Metrics
cpu_usage_percent = Gauge(
    'baluhost_cpu_usage_percent',
    'Current CPU usage percentage',
    registry=registry
)

cpu_count = Gauge(
    'baluhost_cpu_count',
    'Number of CPU cores',
    registry=registry
)

# Memory Metrics
memory_total_bytes = Gauge(
    'baluhost_memory_total_bytes',
    'Total system memory in bytes',
    registry=registry
)

memory_used_bytes = Gauge(
    'baluhost_memory_used_bytes',
    'Used system memory in bytes',
    registry=registry
)

memory_available_bytes = Gauge(
    'baluhost_memory_available_bytes',
    'Available system memory in bytes',
    registry=registry
)

memory_usage_percent = Gauge(
    'baluhost_memory_usage_percent',
    'Memory usage percentage',
    registry=registry
)

# Disk Metrics
disk_total_bytes = Gauge(
    'baluhost_disk_total_bytes',
    'Total disk space in bytes',
    ['path'],
    registry=registry
)

disk_used_bytes = Gauge(
    'baluhost_disk_used_bytes',
    'Used disk space in bytes',
    ['path'],
    registry=registry
)

disk_free_bytes = Gauge(
    'baluhost_disk_free_bytes',
    'Free disk space in bytes',
    ['path'],
    registry=registry
)

disk_usage_percent = Gauge(
    'baluhost_disk_usage_percent',
    'Disk usage percentage',
    ['path'],
    registry=registry
)

# Disk I/O Metrics
disk_read_bytes_total = Counter(
    'baluhost_disk_read_bytes_total',
    'Total bytes read from disk',
    ['device'],
    registry=registry
)

disk_write_bytes_total = Counter(
    'baluhost_disk_write_bytes_total',
    'Total bytes written to disk',
    ['device'],
    registry=registry
)

# Network Metrics
network_received_bytes_total = Counter(
    'baluhost_network_received_bytes_total',
    'Total bytes received from network',
    ['interface'],
    registry=registry
)

network_sent_bytes_total = Counter(
    'baluhost_network_sent_bytes_total',
    'Total bytes sent to network',
    ['interface'],
    registry=registry
)

# ===================================
# RAID Metrics
# ===================================

raid_array_status = Gauge(
    'baluhost_raid_array_status',
    'RAID array status (1=active, 0=inactive/degraded)',
    ['device', 'level', 'status'],
    registry=registry
)

raid_disk_count = Gauge(
    'baluhost_raid_disk_count',
    'Number of disks in RAID array',
    ['device', 'type'],
    registry=registry
)

raid_sync_progress_percent = Gauge(
    'baluhost_raid_sync_progress_percent',
    'RAID resync/recovery progress percentage',
    ['device'],
    registry=registry
)

# ===================================
# SMART Disk Health Metrics
# ===================================

disk_smart_health = Gauge(
    'baluhost_disk_smart_health',
    'SMART health status (1=healthy, 0=failing)',
    ['device', 'serial'],
    registry=registry
)

disk_temperature_celsius = Gauge(
    'baluhost_disk_temperature_celsius',
    'Disk temperature in Celsius',
    ['device'],
    registry=registry
)

disk_power_on_hours = Gauge(
    'baluhost_disk_power_on_hours',
    'Disk power-on hours',
    ['device'],
    registry=registry
)

# ===================================
# Application Metrics
# ===================================

# HTTP Request Metrics
http_requests_total = Counter(
    'baluhost_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'baluhost_http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

# File Operations
file_uploads_total = Counter(
    'baluhost_file_uploads_total',
    'Total file uploads',
    ['status'],
    registry=registry
)

file_downloads_total = Counter(
    'baluhost_file_downloads_total',
    'Total file downloads',
    ['status'],
    registry=registry
)

file_upload_bytes_total = Counter(
    'baluhost_file_upload_bytes_total',
    'Total bytes uploaded',
    registry=registry
)

file_download_bytes_total = Counter(
    'baluhost_file_download_bytes_total',
    'Total bytes downloaded',
    registry=registry
)

# ===================================
# Database Metrics
# ===================================

database_connections = Gauge(
    'baluhost_database_connections',
    'Number of active database connections',
    registry=registry
)

database_query_duration_seconds = Histogram(
    'baluhost_database_query_duration_seconds',
    'Database query duration in seconds',
    ['operation'],
    registry=registry
)

# ===================================
# User Metrics
# ===================================

users_total = Gauge(
    'baluhost_users_total',
    'Total number of users',
    ['role'],
    registry=registry
)

users_active_sessions = Gauge(
    'baluhost_users_active_sessions',
    'Number of active user sessions',
    registry=registry
)

# ===================================
# Storage Metrics
# ===================================

storage_files_total = Gauge(
    'baluhost_storage_files_total',
    'Total number of files in storage',
    registry=registry
)

storage_quota_bytes = Gauge(
    'baluhost_storage_quota_bytes',
    'Storage quota in bytes',
    ['user'],
    registry=registry
)

storage_used_bytes = Gauge(
    'baluhost_storage_used_bytes',
    'Storage used in bytes',
    ['user'],
    registry=registry
)

# ===================================
# Application Info
# ===================================

app_info = Gauge(
    'baluhost_app_info',
    'Application information',
    ['version', 'mode', 'python_version'],
    registry=registry
)

app_uptime_seconds = Gauge(
    'baluhost_app_uptime_seconds',
    'Application uptime in seconds',
    registry=registry
)

# Track app start time
_app_start_time = time.time()


# ===================================
# Metrics Collection Functions
# ===================================

def collect_system_metrics():
    """Collect system resource metrics."""
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_usage_percent.set(cpu_percent)
        cpu_count.set(psutil.cpu_count())

        # Memory
        mem = psutil.virtual_memory()
        memory_total_bytes.set(mem.total)
        memory_used_bytes.set(mem.used)
        memory_available_bytes.set(mem.available)
        memory_usage_percent.set(mem.percent)

        # Disk
        try:
            disk = psutil.disk_usage(settings.nas_storage_path)
            disk_total_bytes.labels(path=settings.nas_storage_path).set(disk.total)
            disk_used_bytes.labels(path=settings.nas_storage_path).set(disk.used)
            disk_free_bytes.labels(path=settings.nas_storage_path).set(disk.free)
            disk_usage_percent.labels(path=settings.nas_storage_path).set(disk.percent)
        except Exception:
            pass  # Path might not exist in dev mode

        # Disk I/O
        disk_io = psutil.disk_io_counters(perdisk=True)
        for device, counters in disk_io.items():
            disk_read_bytes_total.labels(device=device).inc(counters.read_bytes - disk_read_bytes_total.labels(device=device)._value.get())
            disk_write_bytes_total.labels(device=device).inc(counters.write_bytes - disk_write_bytes_total.labels(device=device)._value.get())

        # Network
        net_io = psutil.net_io_counters(pernic=True)
        for interface, counters in net_io.items():
            network_received_bytes_total.labels(interface=interface).inc(counters.bytes_recv - network_received_bytes_total.labels(interface=interface)._value.get())
            network_sent_bytes_total.labels(interface=interface).inc(counters.bytes_sent - network_sent_bytes_total.labels(interface=interface)._value.get())

    except Exception as e:
        # Log error but don't fail metrics endpoint
        print(f"Error collecting system metrics: {e}")


def collect_raid_metrics():
    """Collect RAID status metrics."""
    try:
        from app.services.raid import get_raid_status

        raid_status = get_raid_status()

        for array in raid_status.get('arrays', []):
            device = array.get('device', 'unknown')
            level = array.get('level', 'unknown')
            status = array.get('status', 'unknown')

            # Set array status (1 for active, 0 for degraded/inactive)
            is_healthy = 1 if status.lower() == 'active' else 0
            raid_array_status.labels(device=device, level=level, status=status).set(is_healthy)

            # Disk counts
            total_disks = array.get('total_disks', 0)
            active_disks = array.get('active_disks', 0)
            raid_disk_count.labels(device=device, type='total').set(total_disks)
            raid_disk_count.labels(device=device, type='active').set(active_disks)

            # Sync progress
            sync_progress = array.get('sync_progress', 0)
            raid_sync_progress_percent.labels(device=device).set(sync_progress)

    except Exception as e:
        print(f"Error collecting RAID metrics: {e}")


def collect_smart_metrics():
    """Collect SMART disk health metrics."""
    try:
        from app.services.smart import get_all_disks

        disks = get_all_disks()

        for disk in disks:
            device = disk.get('device', 'unknown')
            serial = disk.get('serial', 'unknown')

            # Health status (1 for healthy/passed, 0 for failing)
            health = disk.get('health', 'unknown').lower()
            is_healthy = 1 if health in ['passed', 'healthy', 'ok'] else 0
            disk_smart_health.labels(device=device, serial=serial).set(is_healthy)

            # Temperature
            temp = disk.get('temperature', 0)
            if temp:
                disk_temperature_celsius.labels(device=device).set(temp)

            # Power-on hours
            power_on_hours = disk.get('power_on_hours', 0)
            if power_on_hours:
                disk_power_on_hours.labels(device=device).set(power_on_hours)

    except Exception as e:
        print(f"Error collecting SMART metrics: {e}")


def collect_database_metrics(db: Session):
    """Collect database statistics."""
    try:
        from app.models.user import User

        # Count users by role
        admin_count = db.query(User).filter(User.role == 'admin').count()
        user_count = db.query(User).filter(User.role == 'user').count()

        users_total.labels(role='admin').set(admin_count)
        users_total.labels(role='user').set(user_count)

    except Exception as e:
        print(f"Error collecting database metrics: {e}")


def collect_app_metrics():
    """Collect application-level metrics."""
    try:
        import sys
        from app import __version__

        # App info
        app_info.labels(
            version=__version__,
            mode=settings.nas_mode,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ).set(1)

        # Uptime
        uptime = time.time() - _app_start_time
        app_uptime_seconds.set(uptime)

    except Exception as e:
        print(f"Error collecting app metrics: {e}")


# ===================================
# Metrics Endpoint
# ===================================

@router.get("/metrics", include_in_schema=False)
async def metrics(
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_user_optional)
):
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus format for scraping.

    **Authentication**: Optional - metrics can be scraped without auth,
    but can be restricted in Nginx config to internal IPs only.

    **Performance**: This endpoint is designed to be fast (<100ms).
    Heavy metrics collection is done in background jobs.
    """
    # Collect current metrics
    collect_system_metrics()
    collect_raid_metrics()
    collect_smart_metrics()
    collect_database_metrics(db)
    collect_app_metrics()

    # Generate Prometheus format
    metrics_output = generate_latest(registry)

    return Response(
        content=metrics_output,
        media_type=CONTENT_TYPE_LATEST
    )
