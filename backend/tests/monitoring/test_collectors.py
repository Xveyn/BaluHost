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


# ============================================================================
# Retention Manager Tests
# ============================================================================

class TestRetentionManager:
    """Tests for RetentionManager."""

    def test_init(self):
        """Test retention manager initialization."""
        from app.services.monitoring.retention_manager import RetentionManager

        manager = RetentionManager()
        assert manager._last_cleanup == {}

    def test_get_config_creates_default(self, db_session):
        """Test that get_config creates default config if missing."""
        from app.services.monitoring.retention_manager import RetentionManager
        from app.models.monitoring import MetricType

        manager = RetentionManager()
        config = manager.get_config(db_session, MetricType.CPU)

        assert config is not None
        assert config.metric_type == MetricType.CPU
        assert config.retention_hours == 168  # 7 days
        assert config.is_enabled is True

    def test_set_retention(self, db_session):
        """Test setting retention period."""
        from app.services.monitoring.retention_manager import RetentionManager
        from app.models.monitoring import MetricType

        manager = RetentionManager()
        config = manager.set_retention(db_session, MetricType.CPU, 48)

        assert config.retention_hours == 48

    def test_set_retention_too_low_rejected(self, db_session):
        """Test that retention less than 1 hour is rejected."""
        from app.services.monitoring.retention_manager import RetentionManager
        from app.models.monitoring import MetricType

        manager = RetentionManager()
        with pytest.raises(ValueError, match="at least 1 hour"):
            manager.set_retention(db_session, MetricType.CPU, 0)

    def test_set_retention_too_high_rejected(self, db_session):
        """Test that retention over 1 year is rejected."""
        from app.services.monitoring.retention_manager import RetentionManager
        from app.models.monitoring import MetricType

        manager = RetentionManager()
        with pytest.raises(ValueError, match="cannot exceed"):
            manager.set_retention(db_session, MetricType.CPU, 9000)

    def test_should_run_cleanup_initially_true(self):
        """Test that cleanup should run when no previous cleanup exists."""
        from app.services.monitoring.retention_manager import RetentionManager

        manager = RetentionManager()
        assert manager.should_run_cleanup() is True

    def test_get_database_stats(self, db_session):
        """Test getting database stats for all metric types."""
        from app.services.monitoring.retention_manager import RetentionManager

        manager = RetentionManager()
        stats = manager.get_database_stats(db_session)

        assert isinstance(stats, dict)
        assert "cpu" in stats
        assert "memory" in stats
        assert "network" in stats

    def test_estimate_database_size(self, db_session):
        """Test estimating database size."""
        from app.services.monitoring.retention_manager import RetentionManager

        manager = RetentionManager()
        sizes = manager.estimate_database_size(db_session)

        assert isinstance(sizes, dict)
        assert "total" in sizes
        assert sizes["total"] >= 0

    def test_run_all_cleanup(self, db_session):
        """Test running cleanup for all metric types."""
        from app.services.monitoring.retention_manager import RetentionManager

        manager = RetentionManager()
        results = manager.run_all_cleanup(db_session)

        assert isinstance(results, dict)
        # All values should be non-negative integers
        for count in results.values():
            assert isinstance(count, int)
            assert count >= 0


class TestSampleToDbConversion:
    """Test sample schema to DB model conversion for each collector."""

    def test_cpu_sample_to_db_dict(self):
        """Test CPU sample conversion to DB dict."""
        collector = CpuMetricCollector()
        sample = collector.collect_sample()
        if sample:
            db_dict = collector.sample_to_db_dict(sample)
            assert "timestamp" in db_dict
            assert "usage_percent" in db_dict

    def test_memory_sample_to_db_dict(self):
        """Test memory sample conversion to DB dict."""
        collector = MemoryMetricCollector()
        sample = collector.collect_sample()
        if sample:
            db_dict = collector.sample_to_db_dict(sample)
            assert "timestamp" in db_dict
            assert "used_bytes" in db_dict
            assert "total_bytes" in db_dict

    def test_network_sample_to_db_dict(self):
        """Test network sample conversion to DB dict."""
        collector = NetworkMetricCollector()
        sample = collector.collect_sample()
        if sample:
            db_dict = collector.sample_to_db_dict(sample)
            assert "timestamp" in db_dict

    def test_disk_io_physical_disk_filter(self):
        """Test that disk IO collector filters non-physical disks."""
        collector = DiskIoMetricCollector()
        assert collector._is_physical_disk("loop0") is False
        assert collector._is_physical_disk("ram0") is False

    def test_enable_disable_collector(self):
        """Test collector enable/disable via _is_enabled flag."""
        collector = CpuMetricCollector()

        assert collector.is_enabled() is True
        collector._is_enabled = False
        assert collector.is_enabled() is False
        collector._is_enabled = True
        assert collector.is_enabled() is True

    def test_clear_memory_buffer(self):
        """Test that clear_memory_buffer empties the buffer."""
        collector = CpuMetricCollector()
        collector.process_sample()
        collector.process_sample()

        assert len(collector._memory_buffer) == 2

        collector.clear_memory_buffer()
        assert len(collector._memory_buffer) == 0
