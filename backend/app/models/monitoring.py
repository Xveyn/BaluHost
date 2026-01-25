"""
SQLAlchemy models for system monitoring.

Stores historical system metrics for long-term analysis and statistics:
- CPU samples (usage, frequency, temperature)
- Memory samples (used, total, percent)
- Network samples (download/upload speed)
- Disk I/O samples (read/write throughput, IOPS)
- Process samples (BaluHost process tracking)
- Monitoring configuration (retention policies)
"""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, DateTime, String, Boolean, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
import enum

from app.models.base import Base


class MetricType(str, enum.Enum):
    """Types of metrics that can be stored."""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    PROCESS = "process"


class CpuSample(Base):
    """
    CPU metrics sample.

    Stores individual CPU measurements for historical analysis.
    """

    __tablename__ = "cpu_samples"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # CPU metrics
    usage_percent = Column(Float, nullable=False)
    frequency_mhz = Column(Float, nullable=True)
    temperature_celsius = Column(Float, nullable=True)
    core_count = Column(Integer, nullable=True)
    thread_count = Column(Integer, nullable=True)
    p_core_count = Column(Integer, nullable=True)  # Intel Performance cores
    e_core_count = Column(Integer, nullable=True)  # Intel Efficiency cores
    thread_usages = Column(JSON, nullable=True)  # Per-thread CPU usage percentages (stored as JSON array)

    def __repr__(self) -> str:
        return f"<CpuSample(usage={self.usage_percent}%, timestamp={self.timestamp})>"


class MemorySample(Base):
    """
    Memory metrics sample.

    Stores individual memory measurements for historical analysis.
    """

    __tablename__ = "memory_samples"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Memory metrics (in bytes)
    used_bytes = Column(Integer, nullable=False)
    total_bytes = Column(Integer, nullable=False)
    percent = Column(Float, nullable=False)
    available_bytes = Column(Integer, nullable=True)
    baluhost_memory_bytes = Column(Integer, nullable=True)  # BaluHost process memory

    def __repr__(self) -> str:
        return f"<MemorySample(percent={self.percent}%, timestamp={self.timestamp})>"


class NetworkSample(Base):
    """
    Network metrics sample.

    Stores individual network measurements for historical analysis.
    """

    __tablename__ = "network_samples"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Network metrics (in Mbps)
    download_mbps = Column(Float, nullable=False)
    upload_mbps = Column(Float, nullable=False)

    # Optional: bytes sent/received totals
    bytes_sent = Column(Integer, nullable=True)
    bytes_received = Column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<NetworkSample(down={self.download_mbps}Mbps, up={self.upload_mbps}Mbps, timestamp={self.timestamp})>"


class DiskIoSample(Base):
    """
    Disk I/O metrics sample.

    Stores individual disk I/O measurements for historical analysis.
    Each record is per-disk, identified by disk_name.
    """

    __tablename__ = "disk_io_samples"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)
    disk_name = Column(String(64), nullable=False, index=True)

    # Throughput metrics (MB/s)
    read_mbps = Column(Float, nullable=False)
    write_mbps = Column(Float, nullable=False)

    # IOPS metrics
    read_iops = Column(Float, nullable=False)
    write_iops = Column(Float, nullable=False)

    # Optional: latency and active time
    avg_response_ms = Column(Float, nullable=True)
    active_time_percent = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<DiskIoSample(disk={self.disk_name}, read={self.read_mbps}MB/s, write={self.write_mbps}MB/s)>"


class ProcessSample(Base):
    """
    Process metrics sample.

    Tracks BaluHost-related processes (backend, frontend, etc.)
    for historical analysis and crash detection.
    """

    __tablename__ = "process_samples"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Process identification
    process_name = Column(String(128), nullable=False, index=True)
    pid = Column(Integer, nullable=False)

    # Resource metrics
    cpu_percent = Column(Float, nullable=False)
    memory_mb = Column(Float, nullable=False)

    # Status info
    status = Column(String(32), nullable=False)  # running, sleeping, stopped, zombie
    is_alive = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<ProcessSample(name={self.process_name}, pid={self.pid}, cpu={self.cpu_percent}%)>"


class MonitoringConfig(Base):
    """
    Monitoring configuration per metric type.

    Stores retention policies and collection settings.
    """

    __tablename__ = "monitoring_config"

    id = Column(Integer, primary_key=True, index=True)
    metric_type = Column(SQLEnum(MetricType), nullable=False, unique=True)

    # Retention policy
    retention_hours = Column(Integer, nullable=False, default=168)  # 7 days default

    # Collection settings
    db_persist_interval = Column(Integer, nullable=False, default=12)  # Every 12th sample
    is_enabled = Column(Boolean, nullable=False, default=True)

    # Maintenance tracking
    last_cleanup = Column(DateTime, nullable=True)
    samples_cleaned = Column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<MonitoringConfig(type={self.metric_type}, retention={self.retention_hours}h)>"
