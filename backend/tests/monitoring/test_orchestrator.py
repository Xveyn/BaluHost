"""
Tests for monitoring orchestrator.

Tests:
- Singleton pattern
- Lifecycle (start/stop)
- Collector coordination
"""
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.services.monitoring.orchestrator import (
    MonitoringOrchestrator,
    DEFAULT_SAMPLE_INTERVAL,
    DEFAULT_BUFFER_SIZE,
    DEFAULT_PERSIST_INTERVAL,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test."""
    MonitoringOrchestrator._instance = None
    yield
    MonitoringOrchestrator._instance = None


class TestSingletonPattern:
    """Tests for singleton pattern."""

    def test_get_instance_creates_singleton(self):
        """Test that get_instance creates a singleton."""
        instance1 = MonitoringOrchestrator.get_instance()
        instance2 = MonitoringOrchestrator.get_instance()

        assert instance1 is instance2

    def test_direct_instantiation_creates_new(self):
        """Test that direct instantiation creates new instances."""
        instance1 = MonitoringOrchestrator()
        instance2 = MonitoringOrchestrator()

        # Direct instantiation should create new instances
        # (unlike get_instance which returns singleton)
        assert instance1 is not instance2


class TestInitialization:
    """Tests for orchestrator initialization."""

    def test_default_configuration(self):
        """Test default configuration values."""
        orchestrator = MonitoringOrchestrator()

        assert orchestrator.sample_interval == DEFAULT_SAMPLE_INTERVAL
        assert orchestrator.buffer_size == DEFAULT_BUFFER_SIZE
        assert orchestrator.persist_interval == DEFAULT_PERSIST_INTERVAL

    def test_custom_configuration(self):
        """Test custom configuration values."""
        orchestrator = MonitoringOrchestrator(
            sample_interval=10.0,
            buffer_size=60,
            persist_interval=6,
        )

        assert orchestrator.sample_interval == 10.0
        assert orchestrator.buffer_size == 60
        assert orchestrator.persist_interval == 6

    def test_collectors_initialized(self):
        """Test that all collectors are initialized."""
        orchestrator = MonitoringOrchestrator()

        assert orchestrator.cpu_collector is not None
        assert orchestrator.memory_collector is not None
        assert orchestrator.network_collector is not None
        assert orchestrator.disk_io_collector is not None
        assert orchestrator.process_tracker is not None
        assert orchestrator.retention_manager is not None

    def test_initial_state(self):
        """Test initial state."""
        orchestrator = MonitoringOrchestrator()

        assert orchestrator._is_running is False
        assert orchestrator._sample_count == 0
        assert orchestrator._monitor_task is None
        assert orchestrator._db_session_factory is None


class TestStartStop:
    """Tests for start/stop functionality."""

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self):
        """Test that start sets is_running flag."""
        orchestrator = MonitoringOrchestrator()
        db_factory = MagicMock()

        # Start in background
        await orchestrator.start(db_factory)

        try:
            assert orchestrator._is_running is True
            assert orchestrator._monitor_task is not None
        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_start_stores_db_factory(self):
        """Test that start stores db session factory."""
        orchestrator = MonitoringOrchestrator()
        db_factory = MagicMock()

        await orchestrator.start(db_factory)

        try:
            assert orchestrator._db_session_factory is db_factory
        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_start_with_custom_interval(self):
        """Test starting with custom sample interval."""
        orchestrator = MonitoringOrchestrator()
        db_factory = MagicMock()

        await orchestrator.start(db_factory, sample_interval=2.0)

        try:
            assert orchestrator.sample_interval == 2.0
        finally:
            await orchestrator.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self):
        """Test that stop clears is_running flag."""
        orchestrator = MonitoringOrchestrator()
        db_factory = MagicMock()

        await orchestrator.start(db_factory)
        await orchestrator.stop()

        assert orchestrator._is_running is False
        assert orchestrator._monitor_task is None

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test stopping when not running doesn't raise."""
        orchestrator = MonitoringOrchestrator()

        # Should not raise
        await orchestrator.stop()

        assert orchestrator._is_running is False

    @pytest.mark.asyncio
    async def test_start_twice_warns(self):
        """Test that starting twice logs warning."""
        orchestrator = MonitoringOrchestrator()
        db_factory = MagicMock()

        await orchestrator.start(db_factory)

        # Second start should just warn, not create another task
        await orchestrator.start(db_factory)

        try:
            assert orchestrator._is_running is True
        finally:
            await orchestrator.stop()


class TestSampling:
    """Tests for sampling functionality."""

    @pytest.mark.asyncio
    async def test_sample_count_increments(self):
        """Test that sample count increments."""
        orchestrator = MonitoringOrchestrator()

        # Manually call _sample_once
        await orchestrator._sample_once()

        assert orchestrator._sample_count == 1

    @pytest.mark.asyncio
    async def test_sample_count_increments_multiple(self):
        """Test multiple samples increment count."""
        orchestrator = MonitoringOrchestrator()

        for _ in range(5):
            await orchestrator._sample_once()

        assert orchestrator._sample_count == 5


class TestPersistence:
    """Tests for persistence logic."""

    @pytest.mark.asyncio
    async def test_persist_interval_triggers_db(self):
        """Test that persist interval triggers database write."""
        orchestrator = MonitoringOrchestrator(persist_interval=3)

        # Mock the DB factory
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=iter([mock_session]))
        orchestrator._db_session_factory = mock_factory

        # Collect samples
        for i in range(3):
            await orchestrator._sample_once()

        # After 3 samples (persist_interval), should have requested session
        assert mock_factory.call_count >= 1


class TestCollectors:
    """Tests for collector configuration."""

    def test_cpu_collector_buffer_size(self):
        """Test CPU collector uses orchestrator buffer size."""
        orchestrator = MonitoringOrchestrator(buffer_size=50)

        assert orchestrator.cpu_collector.buffer_size == 50

    def test_memory_collector_buffer_size(self):
        """Test memory collector uses orchestrator buffer size."""
        orchestrator = MonitoringOrchestrator(buffer_size=50)

        assert orchestrator.memory_collector.buffer_size == 50

    def test_cpu_collector_persist_interval(self):
        """Test CPU collector uses orchestrator persist interval."""
        orchestrator = MonitoringOrchestrator(persist_interval=10)

        assert orchestrator.cpu_collector.persist_interval == 10


class TestConstants:
    """Tests for default constants."""

    def test_default_sample_interval(self):
        """Test default sample interval value."""
        assert DEFAULT_SAMPLE_INTERVAL == 5.0

    def test_default_buffer_size(self):
        """Test default buffer size value."""
        assert DEFAULT_BUFFER_SIZE == 120  # 10 minutes at 5s

    def test_default_persist_interval(self):
        """Test default persist interval value."""
        assert DEFAULT_PERSIST_INTERVAL == 12  # Every minute at 5s
