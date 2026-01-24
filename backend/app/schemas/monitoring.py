"""
Pydantic schemas for system monitoring API.

Provides request/response models for:
- CPU, Memory, Network, Disk I/O metrics
- Process tracking
- Retention configuration
"""

from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field


# ===== Metric Type Enum =====

class MetricTypeEnum(str, Enum):
    """Types of metrics."""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    DISK_IO = "disk_io"
    PROCESS = "process"


class DataSource(str, Enum):
    """Data source for history queries."""
    AUTO = "auto"
    MEMORY = "memory"
    DATABASE = "database"


# ===== Sample Schemas =====

class CpuSampleSchema(BaseModel):
    """CPU metrics sample."""
    timestamp: datetime
    usage_percent: float
    frequency_mhz: Optional[float] = None
    temperature_celsius: Optional[float] = None
    core_count: Optional[int] = None
    thread_count: Optional[int] = None
    p_core_count: Optional[int] = None  # Intel Performance cores
    e_core_count: Optional[int] = None  # Intel Efficiency cores

    class Config:
        from_attributes = True


class MemorySampleSchema(BaseModel):
    """Memory metrics sample."""
    timestamp: datetime
    used_bytes: int
    total_bytes: int
    percent: float
    available_bytes: Optional[int] = None
    baluhost_memory_bytes: Optional[int] = None  # Memory used by BaluHost processes

    class Config:
        from_attributes = True


class NetworkSampleSchema(BaseModel):
    """Network metrics sample."""
    timestamp: datetime
    download_mbps: float
    upload_mbps: float
    bytes_sent: Optional[int] = None
    bytes_received: Optional[int] = None

    class Config:
        from_attributes = True


class DiskIoSampleSchema(BaseModel):
    """Disk I/O metrics sample."""
    timestamp: datetime
    disk_name: str
    read_mbps: float
    write_mbps: float
    read_iops: float
    write_iops: float
    avg_response_ms: Optional[float] = None
    active_time_percent: Optional[float] = None

    class Config:
        from_attributes = True


class ProcessSampleSchema(BaseModel):
    """Process metrics sample."""
    timestamp: datetime
    process_name: str
    pid: int
    cpu_percent: float
    memory_mb: float
    status: str
    is_alive: bool = True

    class Config:
        from_attributes = True


# ===== Request Schemas =====

class MetricHistoryRequest(BaseModel):
    """Request parameters for metric history."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    source: DataSource = DataSource.AUTO
    limit: int = Field(default=1000, ge=1, le=10000)


class TimeRangeEnum(str, Enum):
    """Predefined time ranges."""
    TEN_MINUTES = "10m"
    ONE_HOUR = "1h"
    TWENTY_FOUR_HOURS = "24h"
    SEVEN_DAYS = "7d"


# ===== Response Schemas =====

class CurrentCpuResponse(BaseModel):
    """Current CPU metrics response."""
    timestamp: datetime
    usage_percent: float
    frequency_mhz: Optional[float] = None
    temperature_celsius: Optional[float] = None
    core_count: Optional[int] = None
    thread_count: Optional[int] = None
    p_core_count: Optional[int] = None  # Intel Performance cores
    e_core_count: Optional[int] = None  # Intel Efficiency cores


class CurrentMemoryResponse(BaseModel):
    """Current memory metrics response."""
    timestamp: datetime
    used_bytes: int
    total_bytes: int
    percent: float
    available_bytes: Optional[int] = None
    baluhost_memory_bytes: Optional[int] = None  # Memory used by BaluHost processes


class CurrentNetworkResponse(BaseModel):
    """Current network metrics response."""
    timestamp: datetime
    download_mbps: float
    upload_mbps: float


class CurrentDiskIoResponse(BaseModel):
    """Current disk I/O metrics response."""
    disks: Dict[str, Optional[DiskIoSampleSchema]]


class CurrentProcessResponse(BaseModel):
    """Current process status response."""
    processes: Dict[str, Optional[ProcessSampleSchema]]


class MetricHistoryResponse(BaseModel):
    """Generic metric history response."""
    metric_type: str
    samples: List
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    sample_count: int
    source: str  # "memory" or "database"


class CpuHistoryResponse(BaseModel):
    """CPU history response."""
    samples: List[CpuSampleSchema]
    sample_count: int
    source: str


class MemoryHistoryResponse(BaseModel):
    """Memory history response."""
    samples: List[MemorySampleSchema]
    sample_count: int
    source: str


class NetworkHistoryResponse(BaseModel):
    """Network history response."""
    samples: List[NetworkSampleSchema]
    sample_count: int
    source: str


class DiskIoHistoryResponse(BaseModel):
    """Disk I/O history response."""
    disks: Dict[str, List[DiskIoSampleSchema]]
    available_disks: List[str]
    sample_count: int
    source: str


class ProcessHistoryResponse(BaseModel):
    """Process history response."""
    processes: Dict[str, List[ProcessSampleSchema]]
    sample_count: int
    source: str
    crashes_detected: int = 0


# ===== Retention Configuration =====

class RetentionConfigResponse(BaseModel):
    """Retention configuration for a metric type."""
    metric_type: str
    retention_hours: int
    db_persist_interval: int
    is_enabled: bool
    last_cleanup: Optional[datetime] = None
    samples_cleaned: int = 0


class RetentionConfigUpdate(BaseModel):
    """Update retention configuration."""
    retention_hours: int = Field(..., ge=1, le=8760, description="Retention period in hours (1-8760)")


class RetentionConfigListResponse(BaseModel):
    """List of all retention configurations."""
    configs: List[RetentionConfigResponse]


# ===== Database Stats =====

class MetricDatabaseStats(BaseModel):
    """Database statistics for a metric type."""
    metric_type: str
    count: int
    oldest: Optional[datetime] = None
    newest: Optional[datetime] = None
    retention_hours: int
    last_cleanup: Optional[datetime] = None
    total_cleaned: int = 0
    estimated_size_bytes: int = 0


class DatabaseStatsResponse(BaseModel):
    """Database statistics for all metrics."""
    metrics: Dict[str, MetricDatabaseStats]
    total_samples: int
    total_size_bytes: int


# ===== Monitoring Status =====

class MonitoringStatusResponse(BaseModel):
    """Overall monitoring status."""
    is_running: bool
    sample_count: int
    sample_interval: float
    buffer_size: int
    persist_interval: int
    last_cleanup: Optional[datetime] = None
    collectors: Dict[str, bool]
