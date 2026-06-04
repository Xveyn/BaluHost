"""
Tests for energy statistics service (services/power/energy.py).

Covers:
- Saving power samples
- Period stats aggregation
- Today/week/month convenience methods
- Energy price config CRUD
- Cumulative energy data calculation
"""

import json
import pytest
from datetime import datetime, timedelta, timezone

from app.models.smart_device import SmartDevice, SmartDeviceSample
from app.models.energy_price_config import EnergyPriceConfig
from app.services.power.energy import (
    save_power_sample,
    get_period_stats,
    get_energy_price_config,
    update_energy_price_config,
    get_cumulative_energy_data,
    get_cumulative_energy_total,
    get_hourly_samples,
)


@pytest.fixture
def smart_device(db_session) -> SmartDevice:
    """Create a mock SmartDevice for testing."""
    device = SmartDevice(
        name="Test NAS Monitor",
        plugin_name="tapo_smart_plug",
        device_type_id="tapo_p110",
        address="192.168.1.100",
        capabilities=["power_monitor", "switch"],
        is_active=True,
        is_online=True,
        created_by_user_id=1,
    )
    db_session.add(device)
    db_session.commit()
    db_session.refresh(device)
    return device


@pytest.fixture
def sample_data(db_session, smart_device) -> list[SmartDeviceSample]:
    """Create some power samples for testing."""
    now = datetime.now(timezone.utc)
    samples = []
    for i in range(10):
        watts = 50.0 + i * 2
        data = {
            "current_power": watts,
            "voltage": 230.0,
            "current_ma": int((0.22 + i * 0.01) * 1000),
            "energy_today_wh": 1500,
            "is_online": True,
        }
        sample = SmartDeviceSample(
            device_id=smart_device.id,
            capability="power_monitor",
            data_json=json.dumps(data),
            timestamp=now - timedelta(minutes=i * 5),
        )
        db_session.add(sample)
        samples.append(sample)
    db_session.commit()
    return samples


# ============================================================================
# Save Power Sample
# ============================================================================

class TestSavePowerSample:
    """Test saving power samples."""

    def test_save_sample(self, db_session, smart_device):
        sample = save_power_sample(
            db_session,
            device_id=smart_device.id,
            watts=65.0,
            voltage=230.5,
            current=0.28,
            energy_today=2.1,
        )

        assert sample.id is not None
        data = json.loads(sample.data_json)
        assert data["current_power"] == 65.0
        assert sample.device_id == smart_device.id
        assert data["is_online"] is True

    def test_save_sample_offline(self, db_session, smart_device):
        sample = save_power_sample(
            db_session,
            device_id=smart_device.id,
            watts=0.0,
            voltage=None,
            current=None,
            energy_today=None,
            is_online=False,
        )

        data = json.loads(sample.data_json)
        assert data["is_online"] is False
        assert data["voltage"] is None


# ============================================================================
# Period Stats
# ============================================================================

class TestPeriodStats:
    """Test energy period statistics aggregation."""

    def test_get_period_stats(self, db_session, smart_device, sample_data):
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=2)

        stats = get_period_stats(db_session, smart_device.id, start, now)

        assert stats is not None
        assert stats.device_id == smart_device.id
        assert stats.device_name == "Test NAS Monitor"
        assert stats.samples_count == 10
        assert stats.avg_watts > 0
        assert stats.min_watts > 0
        assert stats.max_watts >= stats.min_watts
        assert stats.uptime_percentage == 100.0

    def test_get_period_stats_no_data(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)

        stats = get_period_stats(db_session, smart_device.id, start, now)
        assert stats is None

    def test_get_period_stats_unknown_device(self, db_session):
        now = datetime.now(timezone.utc)
        stats = get_period_stats(db_session, 999999, now - timedelta(hours=1), now)
        assert stats is None

    def test_get_period_stats_with_offline_samples(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        # Add online and offline samples
        for i in range(5):
            is_online = i < 3
            watts = 50.0 if is_online else 0.0
            data = {
                "current_power": watts,
                "voltage": 230.0 if is_online else None,
                "current_ma": 220 if is_online else None,
                "energy_today_wh": 1500 if is_online else None,
                "is_online": is_online,
            }
            db_session.add(SmartDeviceSample(
                device_id=smart_device.id,
                capability="power_monitor",
                data_json=json.dumps(data),
                timestamp=now - timedelta(minutes=i * 5),
            ))
        db_session.commit()

        stats = get_period_stats(
            db_session, smart_device.id,
            now - timedelta(hours=1), now,
        )

        assert stats is not None
        assert stats.uptime_percentage == 60.0
        assert stats.downtime_minutes == 10  # 2 offline * 5 min


# ============================================================================
# Energy Price Config
# ============================================================================

class TestEnergyPriceConfig:
    """Test energy price configuration."""

    def test_get_creates_default(self, db_session):
        config = get_energy_price_config(db_session)

        assert config is not None
        assert config.cost_per_kwh == 0.40
        assert config.currency == "EUR"

    def test_get_returns_existing(self, db_session):
        # First call creates
        config1 = get_energy_price_config(db_session)
        # Second call returns same
        config2 = get_energy_price_config(db_session)

        assert config1.id == config2.id

    def test_update_price_config(self, db_session, regular_user):
        config = update_energy_price_config(
            db_session,
            cost_per_kwh=0.35,
            currency="USD",
            user_id=regular_user.id,
        )

        assert config.cost_per_kwh == 0.35
        assert config.currency == "USD"
        assert config.updated_by_user_id == regular_user.id


# ============================================================================
# Cumulative Energy Data
# ============================================================================

class TestCumulativeEnergyData:
    """Test cumulative energy data for charting."""

    def test_cumulative_data_today(self, db_session, smart_device, sample_data):
        result = get_cumulative_energy_data(
            db_session, smart_device.id, "today", 0.40,
        )

        assert result is not None
        assert result["device_id"] == smart_device.id
        assert result["period"] == "today"
        assert isinstance(result["data_points"], list)

    def test_cumulative_data_unknown_device(self, db_session):
        result = get_cumulative_energy_data(db_session, 999999, "today", 0.40)
        assert result is None

    def test_cumulative_data_no_samples(self, db_session, smart_device):
        result = get_cumulative_energy_data(
            db_session, smart_device.id, "today", 0.40,
        )

        assert result is not None
        assert result["total_kwh"] == 0.0
        assert result["data_points"] == []


# ============================================================================
# Cumulative Custom Range
# ============================================================================

class TestCumulativeCustomRange:
    def test_explicit_range_filters_window(self, db_session, smart_device, sample_data):
        # sample_data has 10 samples at now, now-5m, ... now-45m
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=12)  # captures samples at 0,5,10 min ago
        result = get_cumulative_energy_data(
            db_session, smart_device.id, "today", 0.40, start=start, end=now,
        )
        assert result is not None
        assert result["period"] == "custom"
        # Only samples within [start, now] are counted (3 of them: 0,5,10 min ago)
        assert len(result["data_points"]) == 3

    def test_empty_range_returns_two_zero_boundary_points(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=400)
        end = now - timedelta(days=399)  # no samples exist here
        result = get_cumulative_energy_data(
            db_session, smart_device.id, "today", 0.40, start=start, end=end,
        )
        assert result is not None
        assert result["period"] == "custom"
        assert result["total_kwh"] == 0.0
        assert result["total_cost"] == 0.0
        assert len(result["data_points"]) == 2
        assert result["data_points"][0]["instant_watts"] == 0.0
        assert result["data_points"][0]["cumulative_kwh"] == 0.0
        assert result["data_points"][0]["timestamp"] == start.isoformat()
        assert result["data_points"][1]["timestamp"] == end.isoformat()

    def test_no_range_keeps_period_label(self, db_session, smart_device, sample_data):
        result = get_cumulative_energy_data(db_session, smart_device.id, "today", 0.40)
        assert result["period"] == "today"


# ============================================================================
# Cumulative Total Custom Range
# ============================================================================

class TestCumulativeTotalCustomRange:
    def test_total_explicit_range(self, db_session, smart_device, sample_data):
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=12)
        result = get_cumulative_energy_total(db_session, "today", 0.40, start=start, end=now)
        assert result["period"] == "custom"
        assert result["device_name"] == "Total"
        assert len(result["data_points"]) >= 1

    def test_total_empty_range_zero_boundaries(self, db_session, smart_device):
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=400)
        end = now - timedelta(days=399)
        result = get_cumulative_energy_total(db_session, "today", 0.40, start=start, end=end)
        assert result["period"] == "custom"
        assert result["total_kwh"] == 0.0
        assert len(result["data_points"]) == 2
        assert result["data_points"][0]["timestamp"] == start.isoformat()
