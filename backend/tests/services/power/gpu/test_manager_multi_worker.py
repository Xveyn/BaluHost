"""
Multi-worker tests for GpuPowerManagerService.

Cover the new primary/follower behaviour: followers route mutations
through the DB-backed command queue, runtime state and demands are
shared across "workers" via the gpu_power_runtime_state and
gpu_power_demands tables.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.models.gpu_power import GpuPowerCommand, GpuPowerDemand, GpuPowerRuntimeState
from app.schemas.gpu_power import GpuPowerConfig, GpuPowerState
from app.services.power.gpu.manager import GpuPowerManagerService


@pytest.fixture(autouse=True)
def _gpu_power_tables_in_global_db():
    tables = [
        GpuPowerRuntimeState.__table__,
        GpuPowerDemand.__table__,
        GpuPowerCommand.__table__,
    ]
    inspector = inspect(engine)
    for table in tables:
        if not inspector.has_table(table.name):
            table.create(bind=engine, checkfirst=True)

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        if not db.query(GpuPowerRuntimeState).filter(GpuPowerRuntimeState.id == 1).first():
            db.add(GpuPowerRuntimeState(id=1, current_state="active"))
            db.commit()
    finally:
        db.close()

    yield

    db = Session()
    try:
        db.query(GpuPowerCommand).delete()
        db.query(GpuPowerDemand).delete()
        db.query(GpuPowerRuntimeState).delete()
        db.add(GpuPowerRuntimeState(id=1, current_state="active"))
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_singleton():
    GpuPowerManagerService._instance = None
    yield
    GpuPowerManagerService._instance = None


class TestFollowerRouting:
    @pytest.mark.asyncio
    async def test_follower_register_demand_writes_to_db(self):
        """A follower's register_demand must round-trip through the DB."""
        from app.models.power import PowerCommand  # noqa: F401  (ensure CPU tables exist too if cross-imported)

        follower = GpuPowerManagerService()
        follower._is_running = True
        follower._primary = False
        follower._backend = None

        async def fake_primary_worker():
            for _ in range(20):
                Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
                db = Session()
                try:
                    row = (
                        db.query(GpuPowerCommand)
                        .filter(GpuPowerCommand.status == "pending")
                        .order_by(GpuPowerCommand.id.asc())
                        .first()
                    )
                    if row is not None:
                        # Simulate primary applying the command
                        if row.command == "register_demand":
                            from app.services.power.gpu.runtime_state_store import upsert_demand
                            from datetime import datetime, timezone
                            import json
                            payload = json.loads(row.payload_json)
                            upsert_demand(
                                source=payload["source"],
                                registered_at=datetime.now(timezone.utc),
                                expires_at=None,
                                description=payload.get("description"),
                            )
                        row.status = "applied"
                        db.commit()
                        return row.id, row.command, row.payload_json
                finally:
                    db.close()
                await asyncio.sleep(0.05)
            return None

        worker_task = asyncio.create_task(fake_primary_worker())
        await follower.register_demand(source="follower_test", description="x")
        result = await worker_task

        assert result is not None
        cmd_id, command, payload_json = result
        assert command == "register_demand"
        assert "follower_test" in (payload_json or "")

        # Verify DB-backed demand visible to any worker
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db = Session()
        try:
            row = db.query(GpuPowerDemand).filter(GpuPowerDemand.source == "follower_test").first()
            assert row is not None
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_follower_get_status_reads_from_runtime_state(self):
        """A follower's get_status must reflect the primary's published state."""
        from app.services.power.gpu.runtime_state_store import update_runtime_state

        # Primary publishes detection result to the shared row
        update_runtime_state(
            current_state="active",
            detected=True,
            vendor="amd",
            has_write_permission=True,
        )

        follower = GpuPowerManagerService()
        follower._is_running = True
        follower._primary = False
        follower._backend = None

        status = await follower.get_status()
        assert status.detected is True
        assert status.vendor == "amd"
        assert status.has_write_permission is True
        assert status.current_state == GpuPowerState.ACTIVE


class TestPrimaryDemandPath:
    @pytest.mark.asyncio
    async def test_primary_register_demand_persists_to_db(self):
        """Primary register_demand must upsert into gpu_power_demands."""
        primary = GpuPowerManagerService()
        primary._is_running = True
        primary._primary = True
        primary._backend = None  # avoid hardware path; transition is skipped because state already ACTIVE
        primary._state = GpuPowerState.ACTIVE

        await primary.register_demand(source="db_persist_test", description="x")

        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db = Session()
        try:
            row = db.query(GpuPowerDemand).filter(GpuPowerDemand.source == "db_persist_test").first()
            assert row is not None
            assert row.description == "x"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_primary_unregister_demand_clears_db_and_cache(self):
        primary = GpuPowerManagerService()
        primary._is_running = True
        primary._primary = True
        primary._backend = None
        primary._state = GpuPowerState.ACTIVE

        await primary.register_demand(source="to_remove")
        ok = await primary.unregister_demand("to_remove")
        assert ok is True

        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db = Session()
        try:
            row = db.query(GpuPowerDemand).filter(GpuPowerDemand.source == "to_remove").first()
            assert row is None
        finally:
            db.close()
        assert "to_remove" not in primary._demands


class TestRuntimeStatePersistence:
    @pytest.mark.asyncio
    async def test_set_config_round_trip_via_command_queue(self):
        """Follower set_config should hit primary path through the queue."""
        from app.services.power.gpu.config_store import load_gpu_power_config

        follower = GpuPowerManagerService()
        follower._is_running = True
        follower._primary = False
        follower._backend = None

        async def fake_primary_worker():
            for _ in range(20):
                Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
                db = Session()
                try:
                    row = (
                        db.query(GpuPowerCommand)
                        .filter(GpuPowerCommand.status == "pending")
                        .order_by(GpuPowerCommand.id.asc())
                        .first()
                    )
                    if row is not None:
                        if row.command == "set_config":
                            import json
                            from app.services.power.gpu.config_store import save_gpu_power_config
                            cfg = GpuPowerConfig(**json.loads(row.payload_json))
                            save_gpu_power_config(cfg)
                        row.status = "applied"
                        db.commit()
                        return
                finally:
                    db.close()
                await asyncio.sleep(0.05)

        new_cfg = GpuPowerConfig(enabled=True, monitor_interval_seconds=7)
        worker_task = asyncio.create_task(fake_primary_worker())
        ok, err = await follower.set_config(new_cfg)
        await worker_task

        assert ok is True
        assert err is None
        loaded = load_gpu_power_config()
        assert loaded.enabled is True
        assert loaded.monitor_interval_seconds == 7
