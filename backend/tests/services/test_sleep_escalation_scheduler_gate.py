"""Auto-escalation to suspend waits for a running scheduler job (C4)."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.schemas.sleep import SleepState
from tests.services.test_sleep_foreign_inhibitor_integration import (
    _build_service,
    _config,
)


async def _run_escalation(svc, *, job_running):
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_always_awake", return_value=False), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc, "_foreign_inhibitor", return_value=None), \
         patch.object(svc, "_scheduler_job_running", return_value=job_running), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()
    return mock_suspend


@pytest.mark.asyncio
async def test_escalation_skipped_while_a_scheduler_job_runs():
    (await _run_escalation(_build_service(), job_running=True)).assert_not_called()


@pytest.mark.asyncio
async def test_escalation_proceeds_without_a_running_job():
    (await _run_escalation(_build_service(), job_running=False)).assert_awaited_once()


def test_unreadable_scheduler_state_counts_as_running(monkeypatch):
    def broken(db, own_execution_id=None):
        raise OperationalError("SELECT", {}, Exception("db weg"))

    monkeypatch.setattr(
        "app.services.power.scheduled_reboot.another_scheduler_job_running", broken
    )
    assert _build_service()._scheduler_job_running() is True
