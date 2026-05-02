"""
Tests for the cross-worker GPU power command queue.

Mirrors test_power_command_queue.py for the GPU manager. Covers the
round-trip a secondary Uvicorn worker takes when it cannot drive the
GPU backend directly.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.models.gpu_power import GpuPowerCommand, GpuPowerDemand, GpuPowerRuntimeState
from app.services.power.gpu import command_queue


@pytest.fixture(autouse=True)
def _gpu_power_tables():
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
        db.commit()
    finally:
        db.close()


def _read_row(command_id: int):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        return db.query(GpuPowerCommand).filter(GpuPowerCommand.id == command_id).first()
    finally:
        db.close()


class TestEnqueue:
    def test_enqueue_returns_id_and_persists_pending(self):
        cmd_id = command_queue.enqueue_command(
            "register_demand", payload={"source": "rebuild"}
        )
        assert cmd_id is not None
        row = _read_row(cmd_id)
        assert row is not None
        assert row.command == "register_demand"
        assert row.status == "pending"
        assert json.loads(row.payload_json)["source"] == "rebuild"


class _StubManager:
    def __init__(self):
        self._is_running = True
        self._primary_set_config = AsyncMock(return_value=(True, None))
        self._primary_register_demand = AsyncMock(return_value="src")
        self._primary_unregister_demand = AsyncMock(return_value=True)


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_set_config_dispatches_and_marks_applied(self):
        manager = _StubManager()
        cmd_id = command_queue.enqueue_command(
            "set_config", payload={"enabled": True, "monitor_interval_seconds": 5}
        )
        loop_task = asyncio.create_task(command_queue.run_poll_loop(manager))
        try:
            success, error = await command_queue.wait_for_completion(cmd_id, timeout_s=2.0)
        finally:
            manager._is_running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        assert success is True
        assert error is None
        manager._primary_set_config.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_register_demand_dispatches(self):
        manager = _StubManager()
        cmd_id = command_queue.enqueue_command(
            "register_demand",
            payload={"source": "backup", "timeout_seconds": 600, "description": "x"},
        )
        loop_task = asyncio.create_task(command_queue.run_poll_loop(manager))
        try:
            success, _ = await command_queue.wait_for_completion(cmd_id, timeout_s=2.0)
        finally:
            manager._is_running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        assert success is True
        manager._primary_register_demand.assert_awaited_once()
        kwargs = manager._primary_register_demand.await_args.kwargs
        assert kwargs["source"] == "backup"
        assert kwargs["timeout_seconds"] == 600

    @pytest.mark.asyncio
    async def test_unregister_demand_returns_failure_when_not_found(self):
        manager = _StubManager()
        manager._primary_unregister_demand = AsyncMock(return_value=False)
        cmd_id = command_queue.enqueue_command(
            "unregister_demand", payload={"source": "ghost"}
        )
        loop_task = asyncio.create_task(command_queue.run_poll_loop(manager))
        try:
            success, error = await command_queue.wait_for_completion(cmd_id, timeout_s=2.0)
        finally:
            manager._is_running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        assert success is False
        assert "no demand" in (error or "")

    @pytest.mark.asyncio
    async def test_invalid_set_config_payload_marks_failed(self):
        manager = _StubManager()
        cmd_id = command_queue.enqueue_command(
            "set_config", payload={"monitor_interval_seconds": "not-an-int"}
        )
        loop_task = asyncio.create_task(command_queue.run_poll_loop(manager))
        try:
            success, error = await command_queue.wait_for_completion(cmd_id, timeout_s=2.0)
        finally:
            manager._is_running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        assert success is False
        assert "invalid config payload" in (error or "")
        manager._primary_set_config.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_command_marked_failed(self):
        manager = _StubManager()
        cmd_id = command_queue.enqueue_command("warp_speed")
        loop_task = asyncio.create_task(command_queue.run_poll_loop(manager))
        try:
            success, error = await command_queue.wait_for_completion(cmd_id, timeout_s=2.0)
        finally:
            manager._is_running = False
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        assert success is False
        assert "unknown command" in (error or "")


class TestTimeout:
    @pytest.mark.asyncio
    async def test_caller_timeout_marks_pending_as_failed(self):
        cmd_id = command_queue.enqueue_command("set_config", payload={"enabled": True})
        success, error = await command_queue.wait_for_completion(cmd_id, timeout_s=0.6)
        assert success is False
        assert "timed out" in (error or "")
        row = _read_row(cmd_id)
        assert row.status == "failed"
        assert row.error_message and "timed out" in row.error_message
