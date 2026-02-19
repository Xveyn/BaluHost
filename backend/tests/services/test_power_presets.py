"""
Tests for PowerPresetService (services/power/presets.py).

Covers:
- Preset CRUD operations
- Only one active preset at a time
- System preset protection
- Clock lookup for service properties
- Governor and EPP mapping
"""

import pytest
from unittest.mock import patch, MagicMock

from app.models.power_preset import PowerPreset
from app.services.power.presets import PowerPresetService
from app.schemas.power import ServicePowerProperty, PowerPresetCreate, PowerPresetUpdate


@pytest.fixture
def preset_service():
    return PowerPresetService()


@pytest.fixture
def mock_db():
    """Mock the SessionLocal to return a controlled db session."""
    return MagicMock()


@pytest.fixture
def sample_preset() -> PowerPreset:
    """Create a sample PowerPreset object (not persisted)."""
    preset = PowerPreset(
        id=1,
        name="Test Preset",
        description="For testing",
        is_system_preset=False,
        is_active=False,
        base_clock_mhz=3000,
        idle_clock_mhz=1500,
        low_clock_mhz=2000,
        medium_clock_mhz=2500,
        surge_clock_mhz=4000,
    )
    return preset


# ============================================================================
# Static Helper Methods (no DB)
# ============================================================================

class TestClockLookup:
    """Test clock speed lookup for service power properties."""

    def test_idle_clock(self, sample_preset):
        clock = PowerPresetService.get_clock_for_property(
            sample_preset, ServicePowerProperty.IDLE,
        )
        assert clock == 1500

    def test_low_clock(self, sample_preset):
        clock = PowerPresetService.get_clock_for_property(
            sample_preset, ServicePowerProperty.LOW,
        )
        assert clock == 2000

    def test_medium_clock(self, sample_preset):
        clock = PowerPresetService.get_clock_for_property(
            sample_preset, ServicePowerProperty.MEDIUM,
        )
        assert clock == 2500

    def test_surge_clock(self, sample_preset):
        clock = PowerPresetService.get_clock_for_property(
            sample_preset, ServicePowerProperty.SURGE,
        )
        assert clock == 4000


class TestGovernorMapping:
    """Test CPU governor mapping for power properties."""

    def test_surge_uses_performance(self):
        gov = PowerPresetService.get_governor_for_property(ServicePowerProperty.SURGE)
        assert gov == "performance"

    def test_medium_uses_powersave(self):
        gov = PowerPresetService.get_governor_for_property(ServicePowerProperty.MEDIUM)
        assert gov == "powersave"

    def test_idle_uses_powersave(self):
        gov = PowerPresetService.get_governor_for_property(ServicePowerProperty.IDLE)
        assert gov == "powersave"

    def test_low_uses_powersave(self):
        gov = PowerPresetService.get_governor_for_property(ServicePowerProperty.LOW)
        assert gov == "powersave"


class TestEPPMapping:
    """Test energy performance preference mapping."""

    def test_idle_epp(self):
        epp = PowerPresetService.get_epp_for_property(ServicePowerProperty.IDLE)
        assert epp == "power"

    def test_low_epp(self):
        epp = PowerPresetService.get_epp_for_property(ServicePowerProperty.LOW)
        assert epp == "balance_power"

    def test_medium_epp(self):
        epp = PowerPresetService.get_epp_for_property(ServicePowerProperty.MEDIUM)
        assert epp == "balance_performance"

    def test_surge_epp(self):
        epp = PowerPresetService.get_epp_for_property(ServicePowerProperty.SURGE)
        assert epp == "performance"


# ============================================================================
# CRUD with mocked DB (PowerPresetService uses SessionLocal internally)
# ============================================================================

class TestPresetCRUD:
    """Test preset CRUD with mocked database sessions."""

    @pytest.mark.asyncio
    async def test_list_presets(self, preset_service):
        """list_presets should return a list (may be empty in test DB)."""
        with patch("app.services.power.presets.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_db.execute.return_value = mock_result

            presets = await preset_service.list_presets()
            assert isinstance(presets, list)
            mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_active_preset_none(self, preset_service):
        """get_active_preset returns None when no preset is active."""
        with patch("app.services.power.presets.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            result = await preset_service.get_active_preset()
            assert result is None

    @pytest.mark.asyncio
    async def test_get_preset_by_id(self, preset_service, sample_preset):
        """get_preset_by_id returns the preset if found."""
        with patch("app.services.power.presets.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_preset
            mock_db.execute.return_value = mock_result

            result = await preset_service.get_preset_by_id(1)
            assert result is not None
            assert result.name == "Test Preset"

    @pytest.mark.asyncio
    async def test_get_preset_by_name(self, preset_service, sample_preset):
        """get_preset_by_name returns the preset if found."""
        with patch("app.services.power.presets.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = sample_preset
            mock_db.execute.return_value = mock_result

            result = await preset_service.get_preset_by_name("Test Preset")
            assert result is not None
            assert result.id == 1

    @pytest.mark.asyncio
    async def test_activate_preset_not_found(self, preset_service):
        """activate_preset returns False if preset not found."""
        with patch("app.services.power.presets.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            result = await preset_service.activate_preset(999)
            assert result is False

    @pytest.mark.asyncio
    async def test_delete_system_preset_rejected(self, preset_service):
        """delete_preset returns False for system presets."""
        system_preset = PowerPreset(
            id=1, name="Balanced", is_system_preset=True, is_active=False,
        )
        with patch("app.services.power.presets.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = system_preset
            mock_db.execute.return_value = mock_result

            result = await preset_service.delete_preset(1)
            assert result is False

    @pytest.mark.asyncio
    async def test_delete_active_preset_rejected(self, preset_service):
        """delete_preset returns False for active presets."""
        active_preset = PowerPreset(
            id=1, name="Custom", is_system_preset=False, is_active=True,
        )
        with patch("app.services.power.presets.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = active_preset
            mock_db.execute.return_value = mock_result

            result = await preset_service.delete_preset(1)
            assert result is False
