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
from typing import Optional

from sqlalchemy import Column, Integer, BigInteger, Float, DateTime, String, Boolean, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, relationship
import enum

from app.models.base import Base


class MetricType(str, enum.Enum):
    """Types of metrics that can be stored."""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    PROCESS = "process"
    POWER = "power"
    UPTIME = "uptime"


class CpuSample(Base):
    """
    CPU metrics sample.

    Stores individual CPU measurements for historical analysis.
    """

    __tablename__ = "cpu_samples"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # CPU metrics
    usage_percent: Mapped[float] = Column(Float, nullable=False)
    frequency_mhz: Mapped[Optional[float]] = Column(Float, nullable=True)
    temperature_celsius: Mapped[Optional[float]] = Column(Float, nullable=True)
    core_count: Mapped[Optional[int]] = Column(Integer, nullable=True)
    thread_count: Mapped[Optional[int]] = Column(Integer, nullable=True)
    p_core_count: Mapped[Optional[int]] = Column(Integer, nullable=True)  # Intel Performance cores
    e_core_count: Mapped[Optional[int]] = Column(Integer, nullable=True)  # Intel Efficiency cores
    thread_usages: Mapped[Optional[list]] = Column(JSON, nullable=True)  # Per-thread CPU usage percentages (stored as JSON array)

    def __repr__(self) -> str:
        return f"<CpuSample(usage={self.usage_percent}%, timestamp={self.timestamp})>"


class MemorySample(Base):
    """
    Memory metrics sample.

    Stores individual memory measurements for historical analysis.
    """

    __tablename__ = "memory_samples"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Memory metrics (in bytes) - BigInteger for values > 2GB
    used_bytes: Mapped[int] = Column(BigInteger, nullable=False)
    total_bytes: Mapped[int] = Column(BigInteger, nullable=False)
    percent: Mapped[float] = Column(Float, nullable=False)
    available_bytes: Mapped[Optional[int]] = Column(BigInteger, nullable=True)
    baluhost_memory_bytes: Mapped[Optional[int]] = Column(BigInteger, nullable=True)  # BaluHost process memory

    def __repr__(self) -> str:
        return f"<MemorySample(percent={self.percent}%, timestamp={self.timestamp})>"


class NetworkSample(Base):
    """
    Network metrics sample.

    Stores individual network measurements for historical analysis.
    """

    __tablename__ = "network_samples"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Network metrics (in Mbps)
    download_mbps: Mapped[float] = Column(Float, nullable=False)
    upload_mbps: Mapped[float] = Column(Float, nullable=False)

    # Optional: bytes sent/received totals - BigInteger for large values
    bytes_sent: Mapped[Optional[int]] = Column(BigInteger, nullable=True)
    bytes_received: Mapped[Optional[int]] = Column(BigInteger, nullable=True)

    def __repr__(self) -> str:
        return f"<NetworkSample(down={self.download_mbps}Mbps, up={self.upload_mbps}Mbps, timestamp={self.timestamp})>"


class DiskIoSample(Base):
    """
    Disk I/O metrics sample.

    Stores individual disk I/O measurements for historical analysis.
    Each record is per-disk, identified by disk_name.
    """

    __tablename__ = "disk_io_samples"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)
    disk_name: Mapped[str] = Column(String(64), nullable=False, index=True)

    # Throughput metrics (MB/s)
    read_mbps: Mapped[float] = Column(Float, nullable=False)
    write_mbps: Mapped[float] = Column(Float, nullable=False)

    # IOPS metrics
    read_iops: Mapped[float] = Column(Float, nullable=False)
    write_iops: Mapped[float] = Column(Float, nullable=False)

    # Optional: latency and active time
    avg_response_ms: Mapped[Optional[float]] = Column(Float, nullable=True)
    active_time_percent: Mapped[Optional[float]] = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<DiskIoSample(disk={self.disk_name}, read={self.read_mbps}MB/s, write={self.write_mbps}MB/s)>"


class ProcessSample(Base):
    """
    Process metrics sample.

    Tracks BaluHost-related processes (backend, frontend, etc.)
    for historical analysis and crash detection.
    """

    __tablename__ = "process_samples"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Process identification
    process_name: Mapped[str] = Column(String(128), nullable=False, index=True)
    pid: Mapped[int] = Column(Integer, nullable=False)

    # Resource metrics
    cpu_percent: Mapped[float] = Column(Float, nullable=False)
    memory_mb: Mapped[float] = Column(Float, nullable=False)

    # Status info
    status: Mapped[str] = Column(String(32), nullable=False)  # running, sleeping, stopped, zombie
    is_alive: Mapped[bool] = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<ProcessSample(name={self.process_name}, pid={self.pid}, cpu={self.cpu_percent}%)>"


class UptimeSample(Base):
    """
    Uptime metrics sample.

    Stores server and system uptime measurements for historical analysis
    and restart detection.
    """

    __tablename__ = "uptime_samples"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    timestamp: Mapped[datetime] = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Uptime metrics
    server_uptime_seconds: Mapped[int] = Column(BigInteger, nullable=False)  # BaluHost backend uptime
    system_uptime_seconds: Mapped[int] = Column(BigInteger, nullable=False)  # OS/Hardware uptime
    server_start_time: Mapped[datetime] = Column(DateTime, nullable=False)  # When backend was started
    system_boot_time: Mapped[datetime] = Column(DateTime, nullable=False)  # When OS was last booted

    def __repr__(self) -> str:
        return f"<UptimeSample(server={self.server_uptime_seconds}s, system={self.system_uptime_seconds}s, timestamp={self.timestamp})>"


class MonitoringConfig(Base):
    """
    Monitoring configuration per metric type.

    Stores retention policies and collection settings.
    """

    __tablename__ = "monitoring_config"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    metric_type: Mapped[MetricType] = Column(SQLEnum(MetricType), nullable=False, unique=True)

    # Retention policy
    retention_hours: Mapped[int] = Column(Integer, nullable=False, default=168)  # 7 days default

    # Collection settings
    db_persist_interval: Mapped[int] = Column(Integer, nullable=False, default=12)  # Every 12th sample
    is_enabled: Mapped[bool] = Column(Boolean, nullable=False, default=True)

    # Maintenance tracking
    last_cleanup: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    samples_cleaned: Mapped[int] = Column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<MonitoringConfig(type={self.metric_type}, retention={self.retention_hours}h)>"
