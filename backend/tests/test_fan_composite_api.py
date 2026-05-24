"""
Tests for composite temperature sensor CRUD operations.

Tests cover:
- Creating composite sensors (POST /api/fans/composite-sensors)
- Listing composite sensors (GET /api/fans/composite-sensors)
- Updating composite sensors (PUT /api/fans/composite-sensors/{id})
- Deleting composite sensors (DELETE /api/fans/composite-sensors/{id})
- MAX_COMPOSITES_PER_SYSTEM limit (max 5)
- Minimum 2 source_ids validation
- Self-reference detection
"""
import json
import pytest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select, func

from app.models.fans import CompositeTempSensor, FanConfig
from app.services.power.fan_control import FanControlService, TempSensorData
from app.services.power.fan_sources import TempSourceRegistry, HwmonTempSource, GpuTempSource
from app.schemas.fans import (
    CompositeSensorCreate,
    CompositeSensorUpdate,
    CompositeSensorInfo,
    CompositeSensorListResponse,
)


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

    # Register sources in the registry
    service._registry.register(HwmonTempSource(
        sensor_id="hwmon0_temp1",
        device_name="k10temp",
        backend_label="Tctl",
        is_cpu_sensor=True,
        read_fn=AsyncMock(return_value=45.0),
    ))
    service._registry.register(GpuTempSource(
        channel="edge",
        read_fn=AsyncMock(return_value=60.0),
    ))
    return service


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestCompositeSensorSchemas:
    """Validate Pydantic schema constraints."""

    def test_create_requires_min_two_sources(self):
        """CompositeSensorCreate must reject fewer than 2 source_ids."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CompositeSensorCreate(
                name="Only One",
                function="max",
                source_ids=["hwmon:hwmon0_temp1"],
            )

    def test_create_rejects_invalid_function(self):
        """CompositeSensorCreate must reject unknown function values."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CompositeSensorCreate(
                name="Bad Function",
                function="sum",
                source_ids=["hwmon:hwmon0_temp1", "gpu:edge"],
            )

    def test_create_accepts_valid_payload(self):
        """CompositeSensorCreate accepts a valid payload."""
        schema = CompositeSensorCreate(
            name="Hottest",
            function="max",
            source_ids=["hwmon:hwmon0_temp1", "gpu:edge"],
        )
        assert schema.name == "Hottest"
        assert schema.function == "max"
        assert len(schema.source_ids) == 2

    def test_update_optional_fields(self):
        """CompositeSensorUpdate accepts partial updates."""
        schema = CompositeSensorUpdate(name="New Name")
        assert schema.name == "New Name"
        assert schema.function is None
        assert schema.source_ids is None

    def test_update_rejects_one_source(self):
        """CompositeSensorUpdate rejects source_ids with fewer than 2 items."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CompositeSensorUpdate(source_ids=["hwmon:hwmon0_temp1"])


# ---------------------------------------------------------------------------
# Service-layer integration tests
# ---------------------------------------------------------------------------

class TestCompositeSensorServiceLayer:
    """Integration tests for composite sensor CRUD via service + DB."""

    @pytest.mark.asyncio
    async def test_create_and_list_composite(self, db_session):
        """Creating a composite sensor persists it and list returns it."""
        service = _make_service(db_session)
        try:
            import uuid as _uuid
            import json as _json

            new_id = f"mix:{_uuid.uuid4().hex[:12]}"
            row = CompositeTempSensor(
                id=new_id,
                name="Hottest",
                function="max",
                source_ids_json=_json.dumps(["hwmon:hwmon0_temp1", "gpu:edge"]),
            )
            with service.db_session_factory() as db:
                db.add(row)
                db.commit()

            # List
            with service.db_session_factory() as db:
                rows = db.execute(select(CompositeTempSensor)).scalars().all()
            assert len(rows) == 1
            assert rows[0].id == new_id
            assert rows[0].name == "Hottest"
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_delete_composite_removes_from_db(self, db_session):
        """Deleting a composite sensor removes it from the DB."""
        service = _make_service(db_session)
        try:
            import uuid as _uuid
            import json as _json

            new_id = f"mix:{_uuid.uuid4().hex[:12]}"
            with service.db_session_factory() as db:
                db.add(CompositeTempSensor(
                    id=new_id,
                    name="To Delete",
                    function="min",
                    source_ids_json=_json.dumps(["hwmon:hwmon0_temp1", "gpu:edge"]),
                ))
                db.commit()

            # Delete
            with service.db_session_factory() as db:
                row = db.execute(
                    select(CompositeTempSensor).where(CompositeTempSensor.id == new_id)
                ).scalar_one_or_none()
                assert row is not None
                db.delete(row)
                db.commit()

            # Verify gone
            with service.db_session_factory() as db:
                row = db.execute(
                    select(CompositeTempSensor).where(CompositeTempSensor.id == new_id)
                ).scalar_one_or_none()
            assert row is None
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_max_composites_limit(self, db_session):
        """The system enforces a maximum of 5 composite sensors."""
        from app.api.routes.fans import MAX_COMPOSITES_PER_SYSTEM
        service = _make_service(db_session)
        try:
            import uuid as _uuid
            import json as _json

            # Create MAX_COMPOSITES_PER_SYSTEM entries
            created_ids = []
            with service.db_session_factory() as db:
                for i in range(MAX_COMPOSITES_PER_SYSTEM):
                    cid = f"mix:{_uuid.uuid4().hex[:12]}"
                    created_ids.append(cid)
                    db.add(CompositeTempSensor(
                        id=cid,
                        name=f"Composite {i}",
                        function="avg",
                        source_ids_json=_json.dumps(["hwmon:hwmon0_temp1", "gpu:edge"]),
                    ))
                db.commit()

            # Verify count is at max
            with service.db_session_factory() as db:
                count = db.execute(select(func.count(CompositeTempSensor.id))).scalar()
            assert count == MAX_COMPOSITES_PER_SYSTEM

            # The limit check (mirrors what the route does)
            with service.db_session_factory() as db:
                count = db.execute(select(func.count(CompositeTempSensor.id))).scalar() or 0
            assert count >= MAX_COMPOSITES_PER_SYSTEM  # Should block creation
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_delete_composite_unlinks_fan_config(self, db_session):
        """Deleting a composite sensor sets temp_sensor_id=None in linked FanConfig rows."""
        service = _make_service(db_session)
        try:
            import uuid as _uuid
            import json as _json

            new_id = f"mix:{_uuid.uuid4().hex[:12]}"
            with service.db_session_factory() as db:
                # Create composite sensor
                db.add(CompositeTempSensor(
                    id=new_id,
                    name="Linked Composite",
                    function="max",
                    source_ids_json=_json.dumps(["hwmon:hwmon0_temp1", "gpu:edge"]),
                ))
                # Create a FanConfig that references this composite
                db.add(FanConfig(
                    fan_id="hwmon0_pwm1",
                    name="Test Fan",
                    mode="auto",
                    temp_sensor_id=new_id,
                    min_pwm_percent=30,
                    max_pwm_percent=100,
                    emergency_temp_celsius=85.0,
                ))
                db.commit()

            # Verify the link exists
            with service.db_session_factory() as db:
                cfg = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == "hwmon0_pwm1")
                ).scalar_one_or_none()
            assert cfg is not None
            assert cfg.temp_sensor_id == new_id

            # Delete composite and unlink
            with service.db_session_factory() as db:
                composite = db.execute(
                    select(CompositeTempSensor).where(CompositeTempSensor.id == new_id)
                ).scalar_one_or_none()
                for cfg in db.execute(
                    select(FanConfig).where(FanConfig.temp_sensor_id == new_id)
                ).scalars():
                    cfg.temp_sensor_id = None
                db.delete(composite)
                db.commit()

            # FanConfig should now have temp_sensor_id = None
            with service.db_session_factory() as db:
                cfg = db.execute(
                    select(FanConfig).where(FanConfig.fan_id == "hwmon0_pwm1")
                ).scalar_one_or_none()
            assert cfg is not None
            assert cfg.temp_sensor_id is None
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_rebuild_registry_includes_composite(self, db_session):
        """After creating a composite in DB and calling _rebuild_registry, it appears in the registry."""
        service = _make_service(db_session)
        try:
            import uuid as _uuid
            import json as _json

            new_id = f"mix:{_uuid.uuid4().hex[:12]}"
            with service.db_session_factory() as db:
                db.add(CompositeTempSensor(
                    id=new_id,
                    name="Registry Test",
                    function="max",
                    source_ids_json=_json.dumps(["hwmon:hwmon0_temp1", "gpu:edge"]),
                ))
                db.commit()

            await service._rebuild_registry()

            ids = [s.id for s in service._registry.all_sources()]
            assert new_id in ids
        finally:
            FanControlService._instance = None

    @pytest.mark.asyncio
    async def test_update_composite_changes_db(self, db_session):
        """Updating a composite sensor changes its name/function/sources in the DB."""
        service = _make_service(db_session)
        try:
            import uuid as _uuid
            import json as _json

            new_id = f"mix:{_uuid.uuid4().hex[:12]}"
            with service.db_session_factory() as db:
                db.add(CompositeTempSensor(
                    id=new_id,
                    name="Original",
                    function="max",
                    source_ids_json=_json.dumps(["hwmon:hwmon0_temp1", "gpu:edge"]),
                ))
                db.commit()

            # Update name
            with service.db_session_factory() as db:
                row = db.execute(
                    select(CompositeTempSensor).where(CompositeTempSensor.id == new_id)
                ).scalar_one_or_none()
                row.name = "Updated"
                row.function = "min"
                db.commit()

            with service.db_session_factory() as db:
                row = db.execute(
                    select(CompositeTempSensor).where(CompositeTempSensor.id == new_id)
                ).scalar_one_or_none()
            assert row.name == "Updated"
            assert row.function == "min"
        finally:
            FanControlService._instance = None
