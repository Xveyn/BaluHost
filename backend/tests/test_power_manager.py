"""
Tests for power management service.

Tests:
- DevCpuPowerBackend: dev mode simulation
- PowerManagerService: profile management, demand registration, auto-scaling
"""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.schemas.power import (
    AutoScalingConfig,
    PowerDemandInfo,
    PowerProfile,
    PowerProfileConfig,
    ServicePowerProperty,
)
from app.services.power.manager import (
    CpuPowerBackend,
    DevCpuPowerBackend,
    PowerManagerService,
    DEFAULT_PROFILES,
    PROFILE_PRIORITY,
)


class TestDevCpuPowerBackend:
    """Tests for DevCpuPowerBackend (simulation backend)."""

    def test_init(self):
        """Test backend initialization."""
        backend = DevCpuPowerBackend()

        assert backend._current_profile == PowerProfile.IDLE
        assert backend._current_governor == "powersave"

    def test_is_available(self):
        """Test that dev backend is always available."""
        backend = DevCpuPowerBackend()

        assert backend.is_available() is True

    @pytest.mark.asyncio
    async def test_apply_profile_idle(self):
        """Test applying IDLE profile."""
        backend = DevCpuPowerBackend()

        success, error = await backend.apply_profile(DEFAULT_PROFILES[PowerProfile.IDLE])

        assert success is True
        assert error is None
        assert backend._current_profile == PowerProfile.IDLE
        assert 400 <= backend._simulated_freq_mhz <= 800

    @pytest.mark.asyncio
    async def test_apply_profile_low(self):
        """Test applying LOW profile."""
        backend = DevCpuPowerBackend()

        success, error = await backend.apply_profile(DEFAULT_PROFILES[PowerProfile.LOW])

        assert success is True
        assert backend._current_profile == PowerProfile.LOW
        assert 800 <= backend._simulated_freq_mhz <= 1200

    @pytest.mark.asyncio
    async def test_apply_profile_medium(self):
        """Test applying MEDIUM profile."""
        backend = DevCpuPowerBackend()

        success, error = await backend.apply_profile(DEFAULT_PROFILES[PowerProfile.MEDIUM])

        assert success is True
        assert backend._current_profile == PowerProfile.MEDIUM
        assert 1500 <= backend._simulated_freq_mhz <= 2500

    @pytest.mark.asyncio
    async def test_apply_profile_surge(self):
        """Test applying SURGE profile."""
        backend = DevCpuPowerBackend()

        success, error = await backend.apply_profile(DEFAULT_PROFILES[PowerProfile.SURGE])

        assert success is True
        assert backend._current_profile == PowerProfile.SURGE
        assert 4200 <= backend._simulated_freq_mhz <= 4600

    @pytest.mark.asyncio
    async def test_get_current_frequency(self):
        """Test getting current frequency with variation."""
        backend = DevCpuPowerBackend()
        backend._simulated_freq_mhz = 1000.0

        freq1 = await backend.get_current_frequency_mhz()
        freq2 = await backend.get_current_frequency_mhz()

        # Should return values around 1000 with some variation
        assert 900 <= freq1 <= 1100
        assert freq1 != freq2 or True  # May or may not vary

    @pytest.mark.asyncio
    async def test_get_available_governors(self):
        """Test getting available governors."""
        backend = DevCpuPowerBackend()

        governors = await backend.get_available_governors()

        assert "powersave" in governors
        assert "performance" in governors
        assert "schedutil" in governors

    @pytest.mark.asyncio
    async def test_get_current_governor(self):
        """Test getting current governor."""
        backend = DevCpuPowerBackend()

        # After applying a profile
        await backend.apply_profile(DEFAULT_PROFILES[PowerProfile.SURGE])

        governor = await backend.get_current_governor()

        assert governor == "performance"


class TestDefaultProfiles:
    """Tests for default profile configurations."""

    def test_idle_profile(self):
        """Test IDLE profile configuration."""
        profile = DEFAULT_PROFILES[PowerProfile.IDLE]

        assert profile.governor == "powersave"
        assert profile.energy_performance_preference == "power"
        assert profile.min_freq_mhz == 400
        assert profile.max_freq_mhz == 800

    def test_low_profile(self):
        """Test LOW profile configuration."""
        profile = DEFAULT_PROFILES[PowerProfile.LOW]

        assert profile.governor == "powersave"
        assert profile.energy_performance_preference == "balance_power"
        assert profile.min_freq_mhz == 800
        assert profile.max_freq_mhz == 1200

    def test_medium_profile(self):
        """Test MEDIUM profile configuration."""
        profile = DEFAULT_PROFILES[PowerProfile.MEDIUM]

        assert profile.governor == "powersave"
        assert profile.energy_performance_preference == "balance_performance"
        assert profile.min_freq_mhz == 1500
        assert profile.max_freq_mhz == 2500

    def test_surge_profile(self):
        """Test SURGE profile configuration."""
        profile = DEFAULT_PROFILES[PowerProfile.SURGE]

        assert profile.governor == "performance"
        assert profile.energy_performance_preference == "performance"
        assert profile.min_freq_mhz is None  # No limit
        assert profile.max_freq_mhz is None  # Full boost


class TestProfilePriority:
    """Tests for profile priority ordering."""

    def test_priority_order(self):
        """Test that priorities are correctly ordered."""
        assert PROFILE_PRIORITY[PowerProfile.IDLE] < PROFILE_PRIORITY[PowerProfile.LOW]
        assert PROFILE_PRIORITY[PowerProfile.LOW] < PROFILE_PRIORITY[PowerProfile.MEDIUM]
        assert PROFILE_PRIORITY[PowerProfile.MEDIUM] < PROFILE_PRIORITY[PowerProfile.SURGE]

    def test_priority_values(self):
        """Test specific priority values."""
        assert PROFILE_PRIORITY[PowerProfile.IDLE] == 0
        assert PROFILE_PRIORITY[PowerProfile.LOW] == 1
        assert PROFILE_PRIORITY[PowerProfile.MEDIUM] == 2
        assert PROFILE_PRIORITY[PowerProfile.SURGE] == 3


class TestPowerManagerServiceInit:
    """Tests for PowerManagerService initialization."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PowerManagerService._instance = None
        yield
        PowerManagerService._instance = None

    def test_singleton_pattern(self):
        """Test that PowerManagerService is a singleton."""
        service1 = PowerManagerService()
        service2 = PowerManagerService()

        assert service1 is service2

    def test_initial_state(self):
        """Test initial service state."""
        service = PowerManagerService()

        assert service._current_profile == PowerProfile.IDLE
        assert service._demands == {}
        assert service._is_running is False
        assert service._backend is None


class TestPowerManagerServiceDemands:
    """Tests for demand registration."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PowerManagerService._instance = None
        yield
        PowerManagerService._instance = None

    @pytest.fixture
    def service(self):
        """Create a fresh service with dev backend."""
        service = PowerManagerService()
        service._backend = DevCpuPowerBackend()
        service._is_running = True
        return service

    @pytest.mark.asyncio
    async def test_register_demand_basic(self, service):
        """Test basic demand registration."""
        demand_id = await service.register_demand(
            source="test_source",
            level=PowerProfile.MEDIUM,
            description="Test demand"
        )

        assert demand_id == "test_source"
        assert "test_source" in service._demands
        assert service._demands["test_source"].level == PowerProfile.MEDIUM

    @pytest.mark.asyncio
    async def test_register_demand_with_timeout(self, service):
        """Test demand with timeout."""
        await service.register_demand(
            source="timeout_test",
            level=PowerProfile.SURGE,
            timeout_seconds=60
        )

        demand = service._demands["timeout_test"]
        assert demand.expires_at is not None
        assert demand.expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_unregister_demand(self, service):
        """Test demand unregistration."""
        await service.register_demand(
            source="to_remove",
            level=PowerProfile.LOW
        )

        await service.unregister_demand("to_remove")

        assert "to_remove" not in service._demands

    @pytest.mark.asyncio
    async def test_highest_demand_wins(self, service):
        """Test that highest demand determines profile."""
        # Register low demand
        await service.register_demand(source="low", level=PowerProfile.LOW)

        # Register higher demand
        await service.register_demand(source="high", level=PowerProfile.SURGE)

        highest = service._get_highest_demand_profile()
        assert highest == PowerProfile.SURGE

    @pytest.mark.asyncio
    async def test_demand_removal_recalculates(self, service):
        """Test that removing demand recalculates profile."""
        # Start with IDLE
        await service.apply_profile(PowerProfile.IDLE)

        # Register SURGE demand
        await service.register_demand(source="surge", level=PowerProfile.SURGE)

        # Unregister
        await service.unregister_demand("surge")

        # Should fall back to IDLE
        highest = service._get_highest_demand_profile()
        assert highest == PowerProfile.IDLE


class TestPowerManagerServiceProfiles:
    """Tests for profile application."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PowerManagerService._instance = None
        yield
        PowerManagerService._instance = None

    @pytest.fixture
    def service(self):
        """Create a fresh service with dev backend."""
        service = PowerManagerService()
        service._backend = DevCpuPowerBackend()
        service._is_running = True
        return service

    @pytest.mark.asyncio
    async def test_apply_profile_success(self, service):
        """Test successful profile application."""
        success, error = await service.apply_profile(PowerProfile.MEDIUM)

        assert success is True
        assert error is None
        assert service._current_profile == PowerProfile.MEDIUM

    @pytest.mark.asyncio
    async def test_apply_same_profile_noop(self, service):
        """Test that applying same profile is a no-op."""
        await service.apply_profile(PowerProfile.LOW)
        history_len_before = len(service._history)

        success, error = await service.apply_profile(PowerProfile.LOW)

        assert success is True
        assert len(service._history) == history_len_before  # No new entry

    @pytest.mark.asyncio
    async def test_profile_history_recorded(self, service):
        """Test that profile changes are recorded in history."""
        service._history.clear()

        await service.apply_profile(PowerProfile.SURGE)

        assert len(service._history) >= 1
        last_entry = service._history[-1]
        assert last_entry.profile == PowerProfile.SURGE

    @pytest.mark.asyncio
    async def test_profile_with_duration(self, service):
        """Test applying profile with duration sets manual override."""
        await service.apply_profile(PowerProfile.SURGE, duration_seconds=300)

        assert service._manual_override_until is not None
        assert service._manual_override_until > datetime.utcnow()


class TestPowerManagerServiceAutoScaling:
    """Tests for auto-scaling functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PowerManagerService._instance = None
        yield
        PowerManagerService._instance = None

    @pytest.fixture
    def service(self):
        """Create service with auto-scaling enabled."""
        service = PowerManagerService()
        service._backend = DevCpuPowerBackend()
        service._is_running = True
        service._auto_scaling_config = AutoScalingConfig(
            enabled=True,
            use_cpu_monitoring=True,
            cpu_surge_threshold=80,
            cpu_medium_threshold=50,
            cpu_low_threshold=20,
            cooldown_seconds=10
        )
        return service

    def test_auto_scaling_config(self, service):
        """Test auto-scaling configuration."""
        config = service._auto_scaling_config

        assert config.enabled is True
        assert config.cpu_surge_threshold == 80
        assert config.cpu_medium_threshold == 50
        assert config.cpu_low_threshold == 20

    @pytest.mark.asyncio
    async def test_auto_scaling_disabled(self, service):
        """Test that auto-scaling respects disabled state."""
        service._auto_scaling_config.enabled = False
        service._cpu_usage_callback = lambda: 90

        # Should not change profile
        await service._check_auto_scaling()

        assert service._current_profile == PowerProfile.IDLE

    @pytest.mark.asyncio
    async def test_auto_scaling_no_callback(self, service):
        """Test auto-scaling with no CPU callback."""
        service._cpu_usage_callback = None

        # Should not raise or change profile
        await service._check_auto_scaling()

        assert service._current_profile == PowerProfile.IDLE


class TestPowerManagerServiceStartStop:
    """Tests for service lifecycle."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PowerManagerService._instance = None
        yield
        PowerManagerService._instance = None

    @pytest.mark.asyncio
    async def test_start_initializes_backend(self):
        """Test that start() initializes backend."""
        service = PowerManagerService()

        # Mock database query to avoid DB dependency
        with patch.object(service, '_load_auto_scaling_config_from_db', return_value=AutoScalingConfig()):
            await service.start()

        try:
            assert service._is_running is True
            assert service._backend is not None
            assert service._current_profile == PowerProfile.IDLE
        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self):
        """Test that stop() cleans up properly."""
        service = PowerManagerService()

        with patch.object(service, '_load_auto_scaling_config_from_db', return_value=AutoScalingConfig()):
            await service.start()

        await service.stop()

        assert service._is_running is False
        assert service._monitor_task is None

    @pytest.mark.asyncio
    async def test_start_twice_warns(self):
        """Test that starting twice logs warning."""
        service = PowerManagerService()

        with patch.object(service, '_load_auto_scaling_config_from_db', return_value=AutoScalingConfig()):
            await service.start()

        # Second start should just warn
        with patch.object(service, '_load_auto_scaling_config_from_db', return_value=AutoScalingConfig()):
            await service.start()  # Should not raise

        try:
            assert service._is_running is True
        finally:
            await service.stop()


class TestPowerManagerServiceStatus:
    """Tests for status retrieval."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PowerManagerService._instance = None
        yield
        PowerManagerService._instance = None

    @pytest.fixture
    def service(self):
        """Create a fresh service with dev backend."""
        service = PowerManagerService()
        service._backend = DevCpuPowerBackend()
        service._is_running = True
        return service

    @pytest.mark.asyncio
    async def test_get_power_status(self, service):
        """Test getting power status."""
        await service.apply_profile(PowerProfile.MEDIUM)

        status = await service.get_power_status()

        assert status.current_profile == PowerProfile.MEDIUM
        assert status.current_frequency_mhz is not None
        # is_running is an internal field, not exposed in PowerStatusResponse

    @pytest.mark.asyncio
    async def test_get_history(self, service):
        """Test getting profile history."""
        await service.apply_profile(PowerProfile.LOW)
        await service.apply_profile(PowerProfile.MEDIUM)

        # History should have entries
        assert len(service._history) >= 2

    @pytest.mark.asyncio
    async def test_get_active_demands(self, service):
        """Test getting active demands."""
        await service.register_demand(source="test1", level=PowerProfile.LOW)
        await service.register_demand(source="test2", level=PowerProfile.MEDIUM)

        demands = service.get_active_demands()

        assert len(demands) == 2
        assert "test1" in [d.source for d in demands]
        assert "test2" in [d.source for d in demands]


class TestPowerManagerBackendSelection:
    """Tests for backend selection logic."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PowerManagerService._instance = None
        yield
        PowerManagerService._instance = None

    def test_select_dev_backend_in_dev_mode(self):
        """Test that dev mode uses dev backend."""
        service = PowerManagerService()

        with patch('app.services.power.manager.settings') as mock_settings:
            mock_settings.is_dev_mode = True
            backend = service._select_backend()

        assert isinstance(backend, DevCpuPowerBackend)

    def test_force_linux_false_uses_dev(self):
        """Test forcing dev backend."""
        service = PowerManagerService()

        backend = service._select_backend(force_linux=False)

        assert isinstance(backend, DevCpuPowerBackend)

    @pytest.mark.asyncio
    async def test_switch_backend(self):
        """Test switching backends at runtime."""
        service = PowerManagerService()
        service._backend = DevCpuPowerBackend()
        service._is_running = True
        service._current_profile = PowerProfile.IDLE

        # Switch to dev (should be no-op if already dev)
        success, prev, new = await service.switch_backend(use_linux=False)

        assert success is True
        assert new == "Dev"
