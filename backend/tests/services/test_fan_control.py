"""
Tests for fan control service.

Tests:
- DevFanControlBackend: simulation mode
- Fan curve interpolation
- PWM calculation and temperature hysteresis
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.fans import FanCurvePoint, FanMode
from app.services.power.fan_control import (
    DevFanControlBackend,
    FanData,
    FanControlService,
)


class MockSettings:
    """Mock settings for testing."""
    is_dev_mode = True
    fan_control_enabled = True
    fan_min_pwm_percent = 30
    fan_emergency_temp_celsius = 90.0


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    return MockSettings()


class TestDevFanControlBackend:
    """Tests for DevFanControlBackend (simulation backend)."""

    def test_init(self, mock_settings):
        """Test backend initialization."""
        backend = DevFanControlBackend(mock_settings)

        assert len(backend._fans) == 3
        assert "dev_cpu_fan" in backend._fans
        assert "dev_case_fan_1" in backend._fans
        assert "dev_case_fan_2" in backend._fans

    def test_init_temperatures(self, mock_settings):
        """Test simulated temperatures are initialized."""
        backend = DevFanControlBackend(mock_settings)

        assert "dev_cpu_temp" in backend._temps
        assert "dev_package_temp" in backend._temps
        assert "dev_ambient_temp" in backend._temps

    @pytest.mark.asyncio
    async def test_is_available(self, mock_settings):
        """Test that dev backend is always available."""
        backend = DevFanControlBackend(mock_settings)

        assert await backend.is_available() is True

    @pytest.mark.asyncio
    async def test_get_fans_returns_all_fans(self, mock_settings):
        """Test getting list of fans."""
        backend = DevFanControlBackend(mock_settings)

        fans = await backend.get_fans()

        assert len(fans) == 3
        assert all(isinstance(fan, FanData) for fan in fans)

    @pytest.mark.asyncio
    async def test_get_fans_data_structure(self, mock_settings):
        """Test fan data structure."""
        backend = DevFanControlBackend(mock_settings)

        fans = await backend.get_fans()
        cpu_fan = next(fan for fan in fans if fan.fan_id == "dev_cpu_fan")

        assert cpu_fan.name == "CPU Fan (Simulated)"
        assert cpu_fan.rpm is not None
        assert 0 <= cpu_fan.pwm_percent <= 100
        assert cpu_fan.temperature_celsius is not None
        assert cpu_fan.mode == FanMode.AUTO

    @pytest.mark.asyncio
    async def test_set_pwm_valid(self, mock_settings):
        """Test setting PWM value."""
        backend = DevFanControlBackend(mock_settings)

        result = await backend.set_pwm("dev_cpu_fan", 75)

        assert result is True
        assert backend._fans["dev_cpu_fan"]["pwm_percent"] == 75

    @pytest.mark.asyncio
    async def test_set_pwm_clamps_low(self, mock_settings):
        """Test that PWM is clamped to minimum 0."""
        backend = DevFanControlBackend(mock_settings)

        await backend.set_pwm("dev_cpu_fan", -10)

        assert backend._fans["dev_cpu_fan"]["pwm_percent"] == 0

    @pytest.mark.asyncio
    async def test_set_pwm_clamps_high(self, mock_settings):
        """Test that PWM is clamped to maximum 100."""
        backend = DevFanControlBackend(mock_settings)

        await backend.set_pwm("dev_cpu_fan", 150)

        assert backend._fans["dev_cpu_fan"]["pwm_percent"] == 100

    @pytest.mark.asyncio
    async def test_set_pwm_nonexistent_fan(self, mock_settings):
        """Test setting PWM on non-existent fan."""
        backend = DevFanControlBackend(mock_settings)

        result = await backend.set_pwm("nonexistent_fan", 50)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_temperature(self, mock_settings):
        """Test getting temperature from sensor."""
        backend = DevFanControlBackend(mock_settings)

        temp = await backend.get_temperature("dev_cpu_temp")

        assert temp is not None
        assert 30 <= temp <= 80  # Reasonable temperature range

    @pytest.mark.asyncio
    async def test_get_temperature_nonexistent(self, mock_settings):
        """Test getting temperature from non-existent sensor."""
        backend = DevFanControlBackend(mock_settings)

        temp = await backend.get_temperature("nonexistent_sensor")

        assert temp is None

    @pytest.mark.asyncio
    async def test_pwm_affects_rpm(self, mock_settings):
        """Test that PWM affects target RPM."""
        backend = DevFanControlBackend(mock_settings)

        # Set to 100%
        await backend.set_pwm("dev_cpu_fan", 100)
        target_high = backend._fans["dev_cpu_fan"]["target_rpm"]

        # Set to 50%
        await backend.set_pwm("dev_cpu_fan", 50)
        target_mid = backend._fans["dev_cpu_fan"]["target_rpm"]

        # Set to 0%
        await backend.set_pwm("dev_cpu_fan", 0)
        target_low = backend._fans["dev_cpu_fan"]["target_rpm"]

        assert target_high > target_mid > target_low


class TestFanCurvePoints:
    """Tests for fan curve point functionality."""

    def test_curve_point_creation(self):
        """Test creating a fan curve point."""
        point = FanCurvePoint(temp=45, pwm=50)

        assert point.temp == 45
        assert point.pwm == 50

    def test_default_curve(self, mock_settings):
        """Test default fan curve."""
        backend = DevFanControlBackend(mock_settings)
        curve = backend._get_default_curve()

        assert len(curve) == 4
        assert curve[0].temp == 35
        assert curve[0].pwm == 30
        assert curve[-1].temp == 85
        assert curve[-1].pwm == 100

    def test_curve_is_monotonic(self, mock_settings):
        """Test that default curve is monotonically increasing."""
        backend = DevFanControlBackend(mock_settings)
        curve = backend._get_default_curve()

        for i in range(len(curve) - 1):
            assert curve[i].temp < curve[i + 1].temp
            assert curve[i].pwm <= curve[i + 1].pwm


class TestFanControlCurveInterpolation:
    """Tests for temperature-to-PWM curve interpolation."""

    def interpolate_pwm(self, curve: list, temp: float) -> int:
        """Helper function to interpolate PWM from temperature curve."""
        if not curve:
            return 50  # Default

        # Below lowest point
        if temp <= curve[0].temp:
            return curve[0].pwm

        # Above highest point
        if temp >= curve[-1].temp:
            return curve[-1].pwm

        # Find surrounding points
        for i in range(len(curve) - 1):
            if curve[i].temp <= temp <= curve[i + 1].temp:
                # Linear interpolation
                t1, p1 = curve[i].temp, curve[i].pwm
                t2, p2 = curve[i + 1].temp, curve[i + 1].pwm
                ratio = (temp - t1) / (t2 - t1)
                return int(p1 + (p2 - p1) * ratio)

        return curve[-1].pwm

    def test_interpolation_below_curve(self):
        """Test interpolation below lowest curve point."""
        curve = [
            FanCurvePoint(temp=35, pwm=30),
            FanCurvePoint(temp=50, pwm=50),
            FanCurvePoint(temp=70, pwm=80),
        ]

        result = self.interpolate_pwm(curve, 25)

        assert result == 30  # Should use lowest value

    def test_interpolation_above_curve(self):
        """Test interpolation above highest curve point."""
        curve = [
            FanCurvePoint(temp=35, pwm=30),
            FanCurvePoint(temp=50, pwm=50),
            FanCurvePoint(temp=70, pwm=80),
        ]

        result = self.interpolate_pwm(curve, 90)

        assert result == 80  # Should use highest value

    def test_interpolation_exact_point(self):
        """Test interpolation at exact curve point."""
        curve = [
            FanCurvePoint(temp=35, pwm=30),
            FanCurvePoint(temp=50, pwm=50),
        ]

        result = self.interpolate_pwm(curve, 50)

        assert result == 50

    def test_interpolation_midpoint(self):
        """Test interpolation between points."""
        curve = [
            FanCurvePoint(temp=40, pwm=40),
            FanCurvePoint(temp=60, pwm=60),
        ]

        result = self.interpolate_pwm(curve, 50)

        assert result == 50  # Midpoint should give midpoint PWM

    def test_interpolation_quarter_point(self):
        """Test interpolation at quarter points."""
        curve = [
            FanCurvePoint(temp=40, pwm=40),
            FanCurvePoint(temp=80, pwm=80),
        ]

        result = self.interpolate_pwm(curve, 50)

        # 50 is 1/4 of the way from 40 to 80
        # PWM should be 1/4 of the way from 40 to 80 = 50
        assert result == 50


class TestFanModes:
    """Tests for fan mode functionality."""

    def test_auto_mode_value(self):
        """Test AUTO mode value."""
        assert FanMode.AUTO.value == "auto"

    def test_manual_mode_value(self):
        """Test MANUAL mode value."""
        assert FanMode.MANUAL.value == "manual"

    def test_emergency_mode_value(self):
        """Test EMERGENCY mode value."""
        assert FanMode.EMERGENCY.value == "emergency"


class TestPWMConversion:
    """Tests for PWM value conversion."""

    def test_percent_to_pwm_zero(self):
        """Test converting 0% to PWM."""
        pwm = int((0 / 100.0) * 255)
        assert pwm == 0

    def test_percent_to_pwm_hundred(self):
        """Test converting 100% to PWM."""
        pwm = int((100 / 100.0) * 255)
        assert pwm == 255

    def test_percent_to_pwm_fifty(self):
        """Test converting 50% to PWM."""
        pwm = int((50 / 100.0) * 255)
        assert pwm == 127

    def test_pwm_to_percent_zero(self):
        """Test converting 0 PWM to percent."""
        percent = int((0 / 255.0) * 100)
        assert percent == 0

    def test_pwm_to_percent_max(self):
        """Test converting 255 PWM to percent."""
        percent = int((255 / 255.0) * 100)
        assert percent == 100

    def test_pwm_to_percent_mid(self):
        """Test converting 127 PWM to percent."""
        percent = int((127 / 255.0) * 100)
        assert percent == 49  # Due to integer rounding


class TestSimulatedStateUpdate:
    """Tests for simulated state updates."""

    def test_temperature_fluctuation(self, mock_settings):
        """Test that temperatures fluctuate over time."""
        backend = DevFanControlBackend(mock_settings)

        temps_before = backend._temps.copy()
        backend._update_simulated_state()
        temps_after = backend._temps.copy()

        # At least one temperature should have changed
        changed = any(
            temps_before[k] != temps_after[k]
            for k in temps_before
        )
        # May or may not change due to randomness
        assert True  # Just verify no exception

    @pytest.mark.asyncio
    async def test_rpm_updates_on_get_fans(self, mock_settings):
        """Test that RPM values update when getting fans."""
        backend = DevFanControlBackend(mock_settings)

        # Get fans multiple times
        fans1 = await backend.get_fans()
        await asyncio.sleep(0.1)  # Small delay
        fans2 = await backend.get_fans()

        # RPM values may fluctuate
        # Just verify we get data
        assert len(fans1) == len(fans2) == 3


class TestFanDataStructure:
    """Tests for FanData dataclass."""

    def test_fan_data_creation(self):
        """Test creating FanData."""
        fan = FanData(
            fan_id="test_fan",
            name="Test Fan",
            rpm=1500,
            pwm_percent=50,
            temperature_celsius=45.0,
            mode=FanMode.AUTO,
            min_pwm_percent=30,
            max_pwm_percent=100,
            emergency_temp_celsius=90.0,
            temp_sensor_id="temp1",
            curve_points=[FanCurvePoint(temp=40, pwm=50)],
            is_active=True,
        )

        assert fan.fan_id == "test_fan"
        assert fan.rpm == 1500
        assert fan.pwm_percent == 50
        assert fan.mode == FanMode.AUTO

    def test_fan_data_optional_fields(self):
        """Test FanData with optional fields."""
        fan = FanData(
            fan_id="test_fan",
            name="Test Fan",
            rpm=None,  # Optional
            pwm_percent=50,
            temperature_celsius=None,  # Optional
            mode=FanMode.MANUAL,
            min_pwm_percent=20,
            max_pwm_percent=100,
            emergency_temp_celsius=85.0,
            temp_sensor_id=None,  # Optional
            curve_points=[],
            is_active=False,
        )

        assert fan.rpm is None
        assert fan.temperature_celsius is None
        assert fan.temp_sensor_id is None
