"""
SQLAlchemy models for disk benchmarking.

Stores benchmark runs and individual test results for historical analysis:
- DiskBenchmark: Main benchmark run with summary results
- BenchmarkTestResult: Detailed results for each individual test
"""

from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, Float, DateTime, String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from app.models.base import Base


class BenchmarkStatus(str, enum.Enum):
    """Status of a benchmark run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BenchmarkProfile(str, enum.Enum):
    """Benchmark profile type."""
    QUICK = "quick"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"


class BenchmarkTargetType(str, enum.Enum):
    """Target type for benchmark."""
    TEST_FILE = "test_file"
    RAW_DEVICE = "raw_device"


class DiskBenchmark(Base):
    """
    Main benchmark run record.

    Stores metadata about the benchmark and summary results.
    """

    __tablename__ = "disk_benchmarks"

    id = Column(Integer, primary_key=True, index=True)

    # Disk identification
    disk_name = Column(String(64), nullable=False, index=True)  # e.g., "sda", "nvme0n1"
    disk_model = Column(String(256), nullable=True)
    disk_size_bytes = Column(BigInteger, nullable=True)

    # Benchmark configuration
    profile = Column(
        SQLEnum(BenchmarkProfile, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BenchmarkProfile.QUICK
    )
    target_type = Column(
        SQLEnum(BenchmarkTargetType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BenchmarkTargetType.TEST_FILE
    )
    test_file_path = Column(String(512), nullable=True)  # Path to test file if using test_file mode
    test_file_size_bytes = Column(BigInteger, nullable=True)

    # Status tracking
    status = Column(
        SQLEnum(BenchmarkStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BenchmarkStatus.PENDING,
        index=True
    )
    progress_percent = Column(Float, nullable=False, default=0.0)
    current_test = Column(String(64), nullable=True)  # Name of currently running test
    error_message = Column(String(1024), nullable=True)

    # Timing
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Summary results (populated after completion)
    # Sequential 1MB Q8T1
    seq_read_mbps = Column(Float, nullable=True)
    seq_write_mbps = Column(Float, nullable=True)
    # Sequential 1MB Q1T1
    seq_read_q1_mbps = Column(Float, nullable=True)
    seq_write_q1_mbps = Column(Float, nullable=True)
    # Random 4K Q32T1
    rand_read_iops = Column(Float, nullable=True)
    rand_write_iops = Column(Float, nullable=True)
    # Random 4K Q1T1
    rand_read_q1_iops = Column(Float, nullable=True)
    rand_write_q1_iops = Column(Float, nullable=True)

    # User who initiated the benchmark
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationship to detailed results
    test_results = relationship("BenchmarkTestResult", back_populates="benchmark", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DiskBenchmark(id={self.id}, disk={self.disk_name}, status={self.status.value})>"


class BenchmarkTestResult(Base):
    """
    Detailed result for an individual benchmark test.

    Each benchmark run consists of multiple tests (read/write with various block sizes).
    """

    __tablename__ = "benchmark_test_results"

    id = Column(Integer, primary_key=True, index=True)
    benchmark_id = Column(Integer, ForeignKey("disk_benchmarks.id", ondelete="CASCADE"), nullable=False, index=True)

    # Test identification
    test_name = Column(String(64), nullable=False)  # e.g., "SEQ1M_Q8T1", "RND4K_Q32T1"
    operation = Column(String(16), nullable=False)  # "read" or "write"
    block_size = Column(String(16), nullable=False)  # e.g., "1m", "4k"
    queue_depth = Column(Integer, nullable=False)
    num_jobs = Column(Integer, nullable=False, default=1)

    # Performance results
    throughput_mbps = Column(Float, nullable=True)  # For sequential tests
    iops = Column(Float, nullable=True)  # For random tests

    # Latency results (microseconds)
    latency_avg_us = Column(Float, nullable=True)
    latency_min_us = Column(Float, nullable=True)
    latency_max_us = Column(Float, nullable=True)
    latency_p99_us = Column(Float, nullable=True)
    latency_p95_us = Column(Float, nullable=True)
    latency_p50_us = Column(Float, nullable=True)

    # Additional metrics
    bandwidth_bytes = Column(BigInteger, nullable=True)  # Total bytes transferred
    runtime_ms = Column(Integer, nullable=True)  # Actual test runtime

    # Timestamp
    completed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    benchmark = relationship("DiskBenchmark", back_populates="test_results")

    def __repr__(self) -> str:
        return f"<BenchmarkTestResult(test={self.test_name}, op={self.operation}, mbps={self.throughput_mbps})>"
