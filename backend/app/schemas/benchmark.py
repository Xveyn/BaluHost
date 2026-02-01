"""
Pydantic schemas for disk benchmark API.

Provides request/response models for:
- Benchmark profiles configuration
- Benchmark start/stop operations
- Progress tracking
- Results display
"""

from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field


# ===== Enums =====

class BenchmarkProfileEnum(str, Enum):
    """Benchmark profile type."""
    QUICK = "quick"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"


class BenchmarkStatusEnum(str, Enum):
    """Status of a benchmark run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BenchmarkTargetTypeEnum(str, Enum):
    """Target type for benchmark."""
    TEST_FILE = "test_file"
    RAW_DEVICE = "raw_device"


# ===== Profile Configuration =====

class BenchmarkTestConfig(BaseModel):
    """Configuration for a single benchmark test."""
    name: str  # e.g., "SEQ1M_Q8T1"
    block_size: str  # e.g., "1m", "4k"
    queue_depth: int
    num_jobs: int = 1
    runtime_seconds: int
    operations: List[str] = ["read", "write"]


class BenchmarkProfileConfig(BaseModel):
    """Configuration for a benchmark profile."""
    name: str
    display_name: str
    description: str
    test_file_size_bytes: int
    tests: List[BenchmarkTestConfig]
    estimated_duration_seconds: int


# Profile configurations as constants
BENCHMARK_PROFILES: Dict[str, BenchmarkProfileConfig] = {
    "quick": BenchmarkProfileConfig(
        name="quick",
        display_name="Quick",
        description="Fast benchmark (~1-2 min) with smaller test file",
        test_file_size_bytes=512 * 1024 * 1024,  # 512 MB
        estimated_duration_seconds=120,
        tests=[
            BenchmarkTestConfig(name="SEQ1M_Q8T1", block_size="1m", queue_depth=8, runtime_seconds=10),
            BenchmarkTestConfig(name="SEQ1M_Q1T1", block_size="1m", queue_depth=1, runtime_seconds=10),
            BenchmarkTestConfig(name="RND4K_Q32T1", block_size="4k", queue_depth=32, runtime_seconds=10),
            BenchmarkTestConfig(name="RND4K_Q1T1", block_size="4k", queue_depth=1, runtime_seconds=10),
        ]
    ),
    "standard": BenchmarkProfileConfig(
        name="standard",
        display_name="Standard",
        description="Balanced benchmark (~5 min) with 1GB test file",
        test_file_size_bytes=1024 * 1024 * 1024,  # 1 GB
        estimated_duration_seconds=300,
        tests=[
            BenchmarkTestConfig(name="SEQ1M_Q8T1", block_size="1m", queue_depth=8, runtime_seconds=30),
            BenchmarkTestConfig(name="SEQ1M_Q1T1", block_size="1m", queue_depth=1, runtime_seconds=30),
            BenchmarkTestConfig(name="SEQ128K_Q32T1", block_size="128k", queue_depth=32, runtime_seconds=30),
            BenchmarkTestConfig(name="RND4K_Q32T1", block_size="4k", queue_depth=32, runtime_seconds=30),
            BenchmarkTestConfig(name="RND4K_Q1T1", block_size="4k", queue_depth=1, runtime_seconds=30),
        ]
    ),
    "comprehensive": BenchmarkProfileConfig(
        name="comprehensive",
        display_name="Comprehensive",
        description="Thorough benchmark (~10+ min) with 4GB test file",
        test_file_size_bytes=4 * 1024 * 1024 * 1024,  # 4 GB
        estimated_duration_seconds=600,
        tests=[
            BenchmarkTestConfig(name="SEQ1M_Q8T1", block_size="1m", queue_depth=8, runtime_seconds=60),
            BenchmarkTestConfig(name="SEQ1M_Q1T1", block_size="1m", queue_depth=1, runtime_seconds=60),
            BenchmarkTestConfig(name="SEQ128K_Q32T1", block_size="128k", queue_depth=32, runtime_seconds=60),
            BenchmarkTestConfig(name="SEQ128K_Q1T1", block_size="128k", queue_depth=1, runtime_seconds=60),
            BenchmarkTestConfig(name="RND4K_Q32T1", block_size="4k", queue_depth=32, runtime_seconds=60),
            BenchmarkTestConfig(name="RND4K_Q1T1", block_size="4k", queue_depth=1, runtime_seconds=60),
            BenchmarkTestConfig(name="RND4K_Q8T8", block_size="4k", queue_depth=8, num_jobs=8, runtime_seconds=60),
        ]
    ),
}


# ===== Disk Information =====

class DiskInfo(BaseModel):
    """Information about an available disk."""
    name: str  # e.g., "sda", "nvme0n1"
    model: Optional[str] = None
    size_bytes: int
    size_display: str  # e.g., "500 GB"
    mount_point: Optional[str] = None
    filesystem: Optional[str] = None
    is_system_disk: bool = False
    is_raid_member: bool = False
    can_benchmark: bool = True
    warning: Optional[str] = None


class AvailableDisksResponse(BaseModel):
    """Response with list of available disks."""
    disks: List[DiskInfo]


# ===== Request Schemas =====

class BenchmarkStartRequest(BaseModel):
    """Request to start a benchmark."""
    disk_name: str
    profile: BenchmarkProfileEnum = BenchmarkProfileEnum.QUICK
    target_type: BenchmarkTargetTypeEnum = BenchmarkTargetTypeEnum.TEST_FILE
    test_directory: Optional[str] = Field(
        default=None,
        description="Directory to create test file in (defaults to disk mount point)"
    )


class BenchmarkPrepareRequest(BaseModel):
    """Request to prepare raw device benchmark (requires confirmation)."""
    disk_name: str
    profile: BenchmarkProfileEnum = BenchmarkProfileEnum.QUICK


class BenchmarkConfirmRequest(BaseModel):
    """Request to confirm and start raw device benchmark."""
    confirmation_token: str
    disk_name: str
    profile: BenchmarkProfileEnum


# ===== Test Result Schemas =====

class TestResultSchema(BaseModel):
    """Result of a single benchmark test."""
    test_name: str
    operation: str  # "read" or "write"
    block_size: str
    queue_depth: int
    num_jobs: int = 1
    throughput_mbps: Optional[float] = None
    iops: Optional[float] = None
    latency_avg_us: Optional[float] = None
    latency_min_us: Optional[float] = None
    latency_max_us: Optional[float] = None
    latency_p99_us: Optional[float] = None
    latency_p95_us: Optional[float] = None
    latency_p50_us: Optional[float] = None
    bandwidth_bytes: Optional[int] = None
    runtime_ms: Optional[int] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===== Benchmark Response Schemas =====

class BenchmarkProgressResponse(BaseModel):
    """Progress information for a running benchmark."""
    id: int
    status: BenchmarkStatusEnum
    progress_percent: float
    current_test: Optional[str] = None
    started_at: Optional[datetime] = None
    estimated_remaining_seconds: Optional[int] = None


class BenchmarkSummaryResults(BaseModel):
    """Summary results in CrystalDiskMark format."""
    # Sequential 1MB Q8T1
    seq_read_mbps: Optional[float] = None
    seq_write_mbps: Optional[float] = None
    # Sequential 1MB Q1T1
    seq_read_q1_mbps: Optional[float] = None
    seq_write_q1_mbps: Optional[float] = None
    # Random 4K Q32T1
    rand_read_iops: Optional[float] = None
    rand_write_iops: Optional[float] = None
    # Random 4K Q1T1
    rand_read_q1_iops: Optional[float] = None
    rand_write_q1_iops: Optional[float] = None


class BenchmarkResponse(BaseModel):
    """Full benchmark response."""
    id: int
    disk_name: str
    disk_model: Optional[str] = None
    disk_size_bytes: Optional[int] = None
    profile: BenchmarkProfileEnum
    target_type: BenchmarkTargetTypeEnum
    status: BenchmarkStatusEnum
    progress_percent: float
    current_test: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    summary: BenchmarkSummaryResults
    test_results: List[TestResultSchema] = []

    class Config:
        from_attributes = True


class BenchmarkListResponse(BaseModel):
    """Paginated list of benchmarks."""
    items: List[BenchmarkResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ===== Profile Response =====

class ProfileListResponse(BaseModel):
    """List of available benchmark profiles."""
    profiles: List[BenchmarkProfileConfig]


# ===== Confirmation Response =====

class BenchmarkPrepareResponse(BaseModel):
    """Response when preparing raw device benchmark."""
    confirmation_token: str
    expires_at: datetime
    disk_name: str
    disk_model: Optional[str] = None
    disk_size_bytes: int
    warning_message: str
    profile: BenchmarkProfileEnum
