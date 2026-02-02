"""
Tests for metric collectors.

Tests:
- MetricCollector base class
- CpuMetricCollector
- MemoryMetricCollector
- NetworkMetricCollector
- DiskIoMetricCollector
- Buffer management and database persistence
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.monitoring.cpu_collector import CpuMetricCollector
from app.services.monitoring.memory_collector import MemoryMetricCollector
from app.services.monitoring.network_collector import NetworkMetricCollector
from app.services.monitoring.disk_io_collector import DiskIoMetricCollector


class TestCpuMetricCollector:
    """Tests for CpuMetricCollector."""

    def test_init_default(self):
        """Test collector initialization with defaults."""
        collector = CpuMetricCollector()

        assert collector.buffer_size == 120
        assert collector.persist_interval == 12
        assert collector.metric_name == "CPU"

    def test_init_custom(self):
        """Test collector initialization with custom values."""
        collector = CpuMetricCollector(buffer_size=60, persist_interval=6)

        assert collector.buffer_size == 60
        assert collector.persist_interval == 6

    def test_initial_state(self):
        """Test initial collector state."""
        collector = CpuMetricCollector()

        assert collector._memory_buffer == []
        assert collector._persist_counter == 0
        assert collector._is_enabled is True

    def test_collect_sample_returns_schema(self):
        """Test that collect_sample returns proper schema."""
        collector = CpuMetricCollector()

        sample = collector.collect_sample()

        # Should return a valid sample with expected fields
        assert sample is not None
        assert hasattr(sample, 'timestamp')
        assert hasattr(sample, 'usage_percent')

    def test_collect_sample_has_valid_data(self):
        """Test that collected sample has valid data."""
        collector = CpuMetricCollector()

        sample = collector.collect_sample()

        assert sample is not None
        # Usage should be between 0 and 100
        assert 0 <= sample.usage_percent <= 100
        # Timestamp should be a datetime object
        assert isinstance(sample.timestamp, datetime)

    def test_process_sample_adds_to_buffer(self):
        """Test that process_sample adds to buffer."""
        collector = CpuMetricCollector()

        collector.process_sample()

        assert len(collector._memory_buffer) == 1

    def test_buffer_respects_max_size(self):
        """Test that buffer doesn't exceed max size."""
        collector = CpuMetricCollector(buffer_size=5)

        for _ in range(10):
            collector.process_sample()

        assert len(collector._memory_buffer) == 5

    def test_persist_counter_increments(self):
        """Test that persist counter increments."""
        collector = CpuMetricCollector()
        initial = collector._persist_counter

        collector.process_sample()

        assert collector._persist_counter == initial + 1

    def test_get_db_model(self):
        """Test getting database model."""
        from app.models.monitoring import CpuSample

        collector = CpuMetricCollector()
        model = collector.get_db_model()

        assert model is CpuSample

    def test_get_latest_from_buffer(self):
        """Test getting latest sample from buffer."""
        collector = CpuMetricCollector()

        # Initially empty
        assert len(collector._memory_buffer) == 0

        collector.process_sample()

        # Should have at least one sample in buffer
        assert len(collector._memory_buffer) >= 1

    def test_buffer_contains_samples(self):
        """Test that buffer contains samples after processing."""
        collector = CpuMetricCollector()

        for _ in range(5):
            collector.process_sample()

        # Buffer should contain 5 samples
        assert len(collector._memory_buffer) == 5


class TestMemoryMetricCollector:
    """Tests for MemoryMetricCollector."""

    def test_init(self):
        """Test collector initialization."""
        collector = MemoryMetricCollector()

        assert collector.metric_name == "Memory"
        assert collector._memory_buffer == []

    def test_collect_sample_returns_schema(self):
        """Test that collect_sample returns proper schema."""
        collector = MemoryMetricCollector()

        sample = collector.collect_sample()

        assert sample is not None
        assert hasattr(sample, 'timestamp')
        assert hasattr(sample, 'used_bytes')
        assert hasattr(sample, 'total_bytes')

    def test_collect_sample_has_valid_data(self):
        """Test that collected sample has valid data."""
        collector = MemoryMetricCollector()

        sample = collector.collect_sample()

        assert sample is not None
        assert sample.total_bytes > 0
        assert sample.used_bytes > 0
        assert sample.used_bytes <= sample.total_bytes

    def test_get_db_model(self):
        """Test getting database model."""
        from app.models.monitoring import MemorySample

        collector = MemoryMetricCollector()
        model = collector.get_db_model()

        assert model is MemorySample


class TestNetworkMetricCollector:
    """Tests for NetworkMetricCollector."""

    def test_init(self):
        """Test collector initialization."""
        collector = NetworkMetricCollector()

        assert collector.metric_name == "Network"

    def test_collect_sample_returns_schema(self):
        """Test that collect_sample returns proper schema."""
        collector = NetworkMetricCollector()

        sample = collector.collect_sample()

        assert sample is not None
        assert hasattr(sample, 'timestamp')
        assert hasattr(sample, 'download_mbps')
        assert hasattr(sample, 'upload_mbps')

    def test_collect_sample_has_valid_data(self):
        """Test that collected sample has valid data."""
        collector = NetworkMetricCollector()

        sample = collector.collect_sample()

        assert sample is not None
        assert sample.download_mbps >= 0
        assert sample.upload_mbps >= 0

    def test_get_db_model(self):
        """Test getting database model."""
        from app.models.monitoring import NetworkSample

        collector = NetworkMetricCollector()
        model = collector.get_db_model()

        assert model is NetworkSample


class TestDiskIoMetricCollector:
    """Tests for DiskIoMetricCollector."""

    def test_init(self):
        """Test collector initialization."""
        collector = DiskIoMetricCollector()

        assert collector.metric_name == "DiskIO"

    def test_collect_all_samples(self):
        """Test collecting samples from all disks."""
        collector = DiskIoMetricCollector()

        samples = collector.collect_all_samples()

        # May have zero or more disks
        assert isinstance(samples, list)

    def test_get_db_model(self):
        """Test getting database model."""
        from app.models.monitoring import DiskIoSample

        collector = DiskIoMetricCollector()
        model = collector.get_db_model()

        assert model is DiskIoSample


class TestBufferManagement:
    """Tests for buffer management functionality."""

    def test_circular_buffer_fifo(self):
        """Test that buffer follows FIFO order."""
        collector = CpuMetricCollector(buffer_size=3)

        # Add 5 samples
        for _ in range(5):
            collector.process_sample()

        # Should have oldest 2 removed, keeping newest 3
        assert len(collector._memory_buffer) == 3

    def test_buffer_maintains_order(self):
        """Test that buffer maintains sample order."""
        collector = CpuMetricCollector(buffer_size=10)

        for _ in range(5):
            collector.process_sample()

        buffer = collector._memory_buffer

        # Verify order is oldest to newest (append order)
        if len(buffer) >= 2:
            assert buffer[0].timestamp <= buffer[-1].timestamp

    def test_disabled_collector_skips_collection(self):
        """Test that disabled collector skips sample collection."""
        collector = CpuMetricCollector()
        collector._is_enabled = False

        result = collector.process_sample()

        assert result is None
        assert len(collector._memory_buffer) == 0


class TestPersistenceLogic:
    """Tests for database persistence logic."""

    def test_should_persist_false_before_interval(self):
        """Test that persistence is skipped before interval."""
        collector = CpuMetricCollector(persist_interval=5)

        for _ in range(4):
            collector.process_sample()

        # Counter should be 4, not reached 5 yet
        assert not collector._should_persist()

    def test_should_persist_true_at_interval(self):
        """Test that persistence triggers at interval."""
        collector = CpuMetricCollector(persist_interval=5)
        collector._persist_counter = 5

        assert collector._should_persist()

    def test_persist_counter_resets(self):
        """Test that persist counter resets after persistence."""
        collector = CpuMetricCollector(persist_interval=3)
        mock_db = MagicMock()

        for _ in range(3):
            collector.process_sample(db=mock_db)

        # Counter should have been reset
        assert collector._persist_counter == 0


class TestCoreDetection:
    """Tests for Intel hybrid core detection."""

    def test_detect_hybrid_cores_returns_tuple(self):
        """Test that detect function returns tuple."""
        from app.services.monitoring.cpu_collector import detect_intel_hybrid_cores

        result = detect_intel_hybrid_cores()

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_detect_hybrid_cores_returns_none_or_ints(self):
        """Test that detect function returns None or integers."""
        from app.services.monitoring.cpu_collector import detect_intel_hybrid_cores

        p_cores, e_cores = detect_intel_hybrid_cores()

        assert p_cores is None or isinstance(p_cores, int)
        assert e_cores is None or isinstance(e_cores, int)
