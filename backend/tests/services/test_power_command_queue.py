"""
Tests for the cross-worker power command queue.

Covers the round-trip a secondary Uvicorn worker takes when it cannot drive
the CPU backend directly: enqueue command → primary's poll loop dispatches →
caller observes ``status='applied'`` and a clean error message on failure.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import engine
from app.models.power import PowerCommand, PowerDemand, PowerRuntimeState
from app.services.power import command_queue


@pytest.fixture(autouse=True)
def _power_tables():
    """Make sure the new power tables exist in the global SessionLocal DB."""
    tables = [PowerRuntimeState.__table__, PowerDemand.__table__, PowerCommand.__table__]
    inspector = inspect(engine)
    for table in tables:
        if not inspector.has_table(table.name):
            table.create(bind=engine, checkfirst=True)

    SessionTesting = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionTesting()
    try:
        if not db.query(PowerRuntimeState).filter(PowerRuntimeState.id == 1).first():
            db.add(PowerRuntimeState(id=1, current_profile="idle"))
            db.commit()
    finally:
        db.close()

    yield

    db = SessionTesting()
    try:
        db.query(PowerCommand).delete()
        db.query(PowerDemand).delete()
        db.commit()
    finally:
        db.close()


def _read_row(command_id: int):
    SessionTesting = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionTesting()
    try:
        return db.query(PowerCommand).filter(PowerCommand.id == command_id).first()
    finally:
        db.close()


class TestEnqueue:
    def test_enqueue_returns_id_and_persists_pending(self):
        cmd_id = command_queue.enqueue_command("apply_profile", payload={"profile": "low"})
        assert cmd_id is not None

        row = _read_row(cmd_id)
        assert row is not None
        assert row.command == "apply_profile"
        assert row.status == "pending"
        assert json.loads(row.payload_json) == {"profile": "low"}

    def test_enqueue_stores_requester_default(self):
        cmd_id = command_queue.enqueue_command("disable_dynamic_mode")
        assert cmd_id is not None
        row = _read_row(cmd_id)
        assert row.requested_by is not None and row.requested_by.startswith("pid=")


class _StubManager:
    """Minimal manager surface that the dispatch layer expects."""

    def __init__(self):
        self._is_running = True
        self._primary_apply_profile = AsyncMock(return_value=(True, None))
        self._primary_enable_dynamic_mode = AsyncMock(return_value=(True, None))
        self._primary_disable_dynamic_mode = AsyncMock(return_value=(True, None))
        self._primary_switch_backend = AsyncMock(return_value=(True, "Dev", "Linux"))


class TestPollLoop:
    @pytest.mark.asyncio
    async def test_apply_profile_dispatches_and_marks_applied(self):
        manager = _StubManager()

        cmd_id = command_queue.enqueue_command(
            "apply_profile", payload={"profile": "medium", "reason": "queued_test"}
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
        manager._primary_apply_profile.assert_awaited_once()
        called_args = manager._primary_apply_profile.await_args
        # First positional arg should be a PowerProfile enum
        from app.schemas.power import PowerProfile

        assert called_args.args[0] == PowerProfile.MEDIUM
        assert called_args.kwargs["reason"] == "queued_test"

    @pytest.mark.asyncio
    async def test_invalid_profile_marks_failed_with_message(self):
        manager = _StubManager()

        cmd_id = command_queue.enqueue_command(
            "apply_profile", payload={"profile": "ludicrous"}
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
        assert error is not None
        assert "invalid profile payload" in error
        manager._primary_apply_profile.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatcher_returns_failure_message(self):
        manager = _StubManager()
        manager._primary_apply_profile = AsyncMock(return_value=(False, "backend off"))

        cmd_id = command_queue.enqueue_command(
            "apply_profile", payload={"profile": "low"}
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
        assert error == "backend off"

    @pytest.mark.asyncio
    async def test_unknown_command_marked_failed(self):
        manager = _StubManager()

        cmd_id = command_queue.enqueue_command("teleport_cpu")
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
        cmd_id = command_queue.enqueue_command("apply_profile", payload={"profile": "low"})
        # No poll loop running — should hit the timeout path
        success, error = await command_queue.wait_for_completion(cmd_id, timeout_s=0.6)
        assert success is False
        assert "timed out" in (error or "")

        row = _read_row(cmd_id)
        assert row.status == "failed"
        assert row.error_message and "timed out" in row.error_message
