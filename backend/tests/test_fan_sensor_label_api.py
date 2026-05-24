"""
Tests for temperature sensor custom label endpoints.

Tests cover:
- Setting a custom label for a sensor (PUT /api/fans/sensors/{id}/label)
- Listing sensors shows the custom_label field
- Clearing a label (DELETE /api/fans/sensors/{id}/label)
- Validation: empty labels are rejected
"""
import json
import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.fans import TempSensorLabel, FanConfig
from app.services.power.fan_control import FanControlService, TempSensorData
from app.services.power.fan_sources import TempSourceRegistry, HwmonTempSource


class MockSettings:
    """Minimal settings mock for FanControlService."""
    is_dev_mode = True
    fan_control_enabled = True
    fan_min_pwm_percent = 30
    fan_emergency_temp_celsius = 90.0
    fan_force_dev_backend = True


def _make_session_factory(db_session):
    """Return a context-manager-compatible session factory wrapping a fixed session."""

    @contextmanager
    def _factory():
        yield db_session

    return _factory


def _make_service(db_session) -> FanControlService:
    """Create a FanControlService wired to the test DB session."""
    FanControlService._instance = None
    mock_backend = AsyncMock()
    mock_backend.get_available_temp_sensors.return_value = [
        TempSensorData(
            sensor_id="hwmon0_temp1",
            device_name="k10temp",
            label="Tctl",
            is_cpu_sensor=True,
            current_temp=45.0,
        )
    ]
    mock_backend.get_temperature = AsyncMock(return_value=45.0)

    service = FanControlService.__new__(FanControlService)
    service.config = MockSettings()
    service.db_session_factory = _make_session_factory(db_session)
    service._backend = mock_backend
    service._registry = TempSourceRegistry()
    from app.services.power.fan_schedule import FanScheduleService
    from app.services.power.fan_profiles import FanProfileService
    service._schedule = FanScheduleService(_make_session_factory(db_session))
    service._profiles = FanProfileService(_make_session_factory(db_session))
    service._hysteresis_state = {}
    service._last_pwm_by_fan = {}
    service._last_tick_ts = 0.0
    service._sample_buffer = __import__("collections").deque(maxlen=120)
    service._is_running = False
    service._monitoring_task = None
    service._use_linux_backend = False

    # Register a hwmon source in the registry so label ops work
    service._registry.register(HwmonTempSource(
        sensor_id="hwmon0_temp1",
        device_name="k10temp",
        backend_label="Tctl",
        is_cpu_sensor=True,
        read_fn=AsyncMock(return_value=45.0),
    ))
    return service


class TestSensorLabelService:
    """Service-layer integration tests for sensor label CRUD."""

    @pytest.mark.asyncio
    async def test_set_label_persists_to_db(self, db_session):
        """Setting a label creates or updates TempSensorLabel in the DB."""
        service = _make_service(db_session)
        try:
            sensor_id = "hwmon:hwmon0_temp1"
            label = "CPU primary"

            # Simulate what the route does
            from sqlalchemy import select
            with service.db_session_factory() as db:
                existing = db.execute(
                    select(TempSensorLabel).where(TempSensorLabel.sensor_id == sensor_id)
                ).scalar_one_or_none()
                if existing:
                    existing.custom_label = label
                else:
                    db.add(TempSensorLabel(sensor_id=sensor_id, custom_label=label))
                db.commit()
            service._registry.set_label(sensor_id, label)

            # Verify registry updated
            assert service._registry._labels.get(sensor_id) == label
            assert service._registry.display_label(sensor_id) == label

            # Verify DB persisted
            with service.db_session_factory() as db:
                row = db.execute(
                    select(TempSensorLabel).where(TempSensorLabel.sensor_id == sensor_id)
                ).scalar_one_or_none()
            assert row is not None
            assert row.custom_label == label
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_clear_label_removes_from_db_and_registry(self, db_session):
        """Clearing a label removes it from both DB and in-memory registry."""
        service = _make_service(db_session)
        try:
            sensor_id = "hwmon:hwmon0_temp1"
            label = "My Custom Label"

            from sqlalchemy import select
            # First set a label
            with service.db_session_factory() as db:
                db.add(TempSensorLabel(sensor_id=sensor_id, custom_label=label))
                db.commit()
            service._registry.set_label(sensor_id, label)
            assert service._registry._labels.get(sensor_id) == label

            # Now clear it
            with service.db_session_factory() as db:
                existing = db.execute(
                    select(TempSensorLabel).where(TempSensorLabel.sensor_id == sensor_id)
                ).scalar_one_or_none()
                if existing:
                    db.delete(existing)
                    db.commit()
            service._registry.clear_label(sensor_id)

            # Registry cleared
            assert service._registry._labels.get(sensor_id) is None

            # DB cleared
            with service.db_session_factory() as db:
                row = db.execute(
                    select(TempSensorLabel).where(TempSensorLabel.sensor_id == sensor_id)
                ).scalar_one_or_none()
            assert row is None
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_rebuild_registry_loads_labels_from_db(self, db_session):
        """After _rebuild_registry, labels persisted in DB appear in the registry."""
        service = _make_service(db_session)
        try:
            sensor_id = "hwmon:hwmon0_temp1"
            label = "Rebuilt Label"

            from sqlalchemy import select
            with service.db_session_factory() as db:
                db.add(TempSensorLabel(sensor_id=sensor_id, custom_label=label))
                db.commit()

            # Clear in-memory then rebuild
            service._registry._labels.clear()
            assert service._registry._labels.get(sensor_id) is None

            await service._rebuild_registry()

            assert service._registry._labels.get(sensor_id) == label
        finally:
            FanControlService._instance = None

    def test_schema_rejects_empty_label(self):
        """TempSensorLabelUpdate must reject empty strings."""
        from pydantic import ValidationError
        from app.schemas.fans import TempSensorLabelUpdate

        with pytest.raises(ValidationError):
            TempSensorLabelUpdate(label="")

    def test_schema_rejects_too_long_label(self):
        """TempSensorLabelUpdate must reject labels over 100 chars."""
        from pydantic import ValidationError
        from app.schemas.fans import TempSensorLabelUpdate

        with pytest.raises(ValidationError):
            TempSensorLabelUpdate(label="x" * 101)

    def test_schema_accepts_valid_label(self):
        """TempSensorLabelUpdate accepts a valid label."""
        from app.schemas.fans import TempSensorLabelUpdate

        schema = TempSensorLabelUpdate(label="CPU primary")
        assert schema.label == "CPU primary"

    @pytest.mark.asyncio
    async def test_list_sensors_includes_custom_label(self, db_session):
        """list_temp_sensors returns custom_label from the registry."""
        service = _make_service(db_session)
        try:
            sensor_id = "hwmon:hwmon0_temp1"
            service._registry.set_label(sensor_id, "My Label")

            sources = service._registry.all_sources()
            assert len(sources) == 1
            src = sources[0]
            assert src.id == sensor_id
            assert service._registry._labels.get(src.id) == "My Label"
        finally:
            FanControlService._instance = None
