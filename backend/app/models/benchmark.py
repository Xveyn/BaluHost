"""
SQLAlchemy models for disk benchmarking.

Stores benchmark runs and individual test results for historical analysis:
- DiskBenchmark: Main benchmark run with summary results
- BenchmarkTestResult: Detailed results for each individual test
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional, List

from sqlalchemy import Column, Integer, BigInteger, Float, DateTime, String, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped
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

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)

    # Disk identification
    disk_name: Mapped[str] = Column(String(64), nullable=False, index=True)  # e.g., "sda", "nvme0n1"
    disk_model: Mapped[Optional[str]] = Column(String(256), nullable=True)
    disk_size_bytes: Mapped[Optional[int]] = Column(BigInteger, nullable=True)

    # Benchmark configuration
    profile: Mapped[BenchmarkProfile] = Column(
        SQLEnum(BenchmarkProfile, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BenchmarkProfile.QUICK
    )
    target_type: Mapped[BenchmarkTargetType] = Column(
        SQLEnum(BenchmarkTargetType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BenchmarkTargetType.TEST_FILE
    )
    test_file_path: Mapped[Optional[str]] = Column(String(512), nullable=True)
    test_file_size_bytes: Mapped[Optional[int]] = Column(BigInteger, nullable=True)

    # Status tracking
    status: Mapped[BenchmarkStatus] = Column(
        SQLEnum(BenchmarkStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BenchmarkStatus.PENDING,
        index=True
    )
    progress_percent: Mapped[float] = Column(Float, nullable=False, default=0.0)
    current_test: Mapped[Optional[str]] = Column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = Column(String(1024), nullable=True)

    # Timing
    created_at: Mapped[datetime] = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = Column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = Column(Float, nullable=True)

    # Summary results (populated after completion)
    # Sequential 1MB Q8T1
    seq_read_mbps: Mapped[Optional[float]] = Column(Float, nullable=True)
    seq_write_mbps: Mapped[Optional[float]] = Column(Float, nullable=True)
    # Sequential 1MB Q1T1
    seq_read_q1_mbps: Mapped[Optional[float]] = Column(Float, nullable=True)
    seq_write_q1_mbps: Mapped[Optional[float]] = Column(Float, nullable=True)
    # Random 4K Q32T1
    rand_read_iops: Mapped[Optional[float]] = Column(Float, nullable=True)
    rand_write_iops: Mapped[Optional[float]] = Column(Float, nullable=True)
    # Random 4K Q1T1
    rand_read_q1_iops: Mapped[Optional[float]] = Column(Float, nullable=True)
    rand_write_q1_iops: Mapped[Optional[float]] = Column(Float, nullable=True)

    # User who initiated the benchmark
    user_id: Mapped[Optional[int]] = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationship to detailed results
    test_results: Mapped[List[BenchmarkTestResult]] = relationship("BenchmarkTestResult", back_populates="benchmark", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<DiskBenchmark(id={self.id}, disk={self.disk_name}, status={self.status.value})>"


class BenchmarkTestResult(Base):
    """
    Detailed result for an individual benchmark test.

    Each benchmark run consists of multiple tests (read/write with various block sizes).
    """

    __tablename__ = "benchmark_test_results"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    benchmark_id: Mapped[int] = Column(Integer, ForeignKey("disk_benchmarks.id", ondelete="CASCADE"), nullable=False, index=True)

    # Test identification
    test_name: Mapped[str] = Column(String(64), nullable=False)  # e.g., "SEQ1M_Q8T1", "RND4K_Q32T1"
    operation: Mapped[str] = Column(String(16), nullable=False)  # "read" or "write"
    block_size: Mapped[str] = Column(String(16), nullable=False)  # e.g., "1m", "4k"
    queue_depth: Mapped[int] = Column(Integer, nullable=False)
    num_jobs: Mapped[int] = Column(Integer, nullable=False, default=1)

    # Performance results
    throughput_mbps: Mapped[Optional[float]] = Column(Float, nullable=True)
    iops: Mapped[Optional[float]] = Column(Float, nullable=True)

    # Latency results (microseconds)
    latency_avg_us: Mapped[Optional[float]] = Column(Float, nullable=True)
    latency_min_us: Mapped[Optional[float]] = Column(Float, nullable=True)
    latency_max_us: Mapped[Optional[float]] = Column(Float, nullable=True)
    latency_p99_us: Mapped[Optional[float]] = Column(Float, nullable=True)
    latency_p95_us: Mapped[Optional[float]] = Column(Float, nullable=True)
    latency_p50_us: Mapped[Optional[float]] = Column(Float, nullable=True)

    # Additional metrics
    bandwidth_bytes: Mapped[Optional[int]] = Column(BigInteger, nullable=True)
    runtime_ms: Mapped[Optional[int]] = Column(Integer, nullable=True)

    # Timestamp
    completed_at: Mapped[datetime] = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationship
    benchmark: Mapped[DiskBenchmark] = relationship("DiskBenchmark", back_populates="test_results")

    def __repr__(self) -> str:
        return f"<BenchmarkTestResult(test={self.test_name}, op={self.operation}, mbps={self.throughput_mbps})>"
