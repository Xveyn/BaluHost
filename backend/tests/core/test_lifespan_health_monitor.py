"""Der SMART-Health-Monitor laeuft nur auf dem primaeren Worker (#872).

Der SMART-Cooldown liegt nur im Prozessspeicher; mit Monitor in jedem Worker
liefen 4-6 smartctl-Laeufe gleichzeitig. Getestet wird
`_start_health_monitor_if_primary()` direkt (`SKIP_APP_INIT=1` -- `_startup()`
laeuft in der Suite nie), die Aufrufstelle aus dem Quelltext.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.core import lifespan as lifespan_module
from app.core import service_registry
from app.services import jobs, service_status


@pytest.fixture
def registry_snapshot():
    previous = dict(service_status._service_registry)
    yield
    service_status._service_registry.clear()
    service_status._service_registry.update(previous)


@pytest.fixture
async def no_real_checks(monkeypatch):
    monkeypatch.setattr(jobs, "_health_task", None)
    monkeypatch.setattr(jobs.settings, "is_dev_mode", False)
    monkeypatch.setattr(jobs, "run_health_checks", lambda: None)
    yield
    await jobs.stop_health_monitor()


@pytest.mark.asyncio
async def test_the_primary_starts_the_health_monitor(monkeypatch, no_real_checks):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", True)
    await lifespan_module._start_health_monitor_if_primary()
    assert jobs._health_task is not None and not jobs._health_task.done()


@pytest.mark.asyncio
async def test_a_secondary_worker_starts_no_health_monitor(monkeypatch, no_real_checks):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", False)
    await lifespan_module._start_health_monitor_if_primary()
    assert jobs._health_task is None


def test_startup_starts_it_only_after_the_primary_is_elected():
    tree = ast.parse(textwrap.dedent(inspect.getsource(lifespan_module._startup)))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

    def lines(name):
        return [
            c.lineno
            for c in calls
            if getattr(c.func, "id", None) == name
            or getattr(c.func, "attr", None) == name
        ]

    assert lines("start_health_monitor") == []
    assert min(lines("_try_become_primary")) < min(lines("_start_health_monitor_if_primary"))


@pytest.mark.asyncio
async def test_admin_restart_on_a_secondary_starts_nothing(
    monkeypatch, registry_snapshot, no_real_checks
):
    service_registry.register_all_services(is_primary_worker=False, discovery_service=None)
    await service_status._service_registry["health_monitor"]["start"]()
    assert jobs._health_task is None


@pytest.mark.asyncio
async def test_admin_restart_on_the_primary_starts_the_loop(
    monkeypatch, registry_snapshot, no_real_checks
):
    service_registry.register_all_services(is_primary_worker=True, discovery_service=None)
    await service_status._service_registry["health_monitor"]["start"]()
    assert jobs._health_task is not None


def test_health_monitor_status_comes_from_the_primary_on_secondaries(registry_snapshot):
    service_registry.register_all_services(is_primary_worker=False, discovery_service=None)
    assert service_status._service_registry["health_monitor"]["get_status"] is not jobs.get_status
