"""Scheduler jobs write their power demand directly to the DB (no HTTP)."""
import inspect
from datetime import timedelta

import pytest
import requests

import app.services.scheduler.worker as worker_module
from app.schemas.power import PowerProfile
from app.services.power.config_store import list_active_demands
from app.services.scheduler.power_demand import (
    register_scheduler_demand,
    unregister_scheduler_demand,
)

pytestmark = pytest.mark.usefixtures("power_tables_in_global_db")


def _no_http(*a, **kw):
    raise AssertionError("Scheduler darf für Demands kein HTTP benutzen")


def test_register_writes_the_row_without_http(monkeypatch):
    monkeypatch.setattr(requests, "post", _no_http)
    monkeypatch.setattr(requests, "delete", _no_http)
    assert register_scheduler_demand("backup") is True
    d = {x.source: x for x in list_active_demands()}["scheduler:backup"]
    assert d.level == PowerProfile.SURGE
    assert d.expires_at - d.registered_at == timedelta(seconds=3600)


def test_unregister_removes_the_row():
    register_scheduler_demand("backup")
    unregister_scheduler_demand("backup")
    assert "scheduler:backup" not in {x.source for x in list_active_demands()}


def test_idle_and_unknown_jobs_register_nothing():
    for name in ("sync_check", "auto_update", "notification_check", "gibt_es_nicht"):
        assert register_scheduler_demand(name) is False
    assert list_active_demands() == []


def test_worker_has_no_http_loopback_for_demands():
    src = inspect.getsource(worker_module)
    assert "/api/power/demands" not in src and "X-Service-Token" not in src


def test_worker_methods_delegate(monkeypatch):
    calls = []
    monkeypatch.setattr(worker_module, "register_scheduler_demand", lambda n: calls.append(("reg", n)) or True)
    monkeypatch.setattr(worker_module, "unregister_scheduler_demand", lambda n: calls.append(("unreg", n)))
    w = worker_module.SchedulerWorker()
    w._register_power_demand("backup")
    w._unregister_power_demand("backup")
    assert calls == [("reg", "backup"), ("unreg", "backup")]


def test_failed_upsert_writes_no_registered_log_row(monkeypatch):
    import app.services.scheduler.power_demand as power_demand

    calls = []
    monkeypatch.setattr(power_demand.config_store, "upsert_demand", lambda **kw: False)
    monkeypatch.setattr(
        power_demand.config_store, "persist_demand_log", lambda **kw: calls.append(kw)
    )
    assert register_scheduler_demand("backup") is False
    assert calls == []
