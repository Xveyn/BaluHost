"""Prometheus collectors must report failures through the logger (#308).

Each collector swallows its exception so `/api/metrics` keeps serving even
when one data source is broken. That part is deliberate — but the swallowed
error still has to reach the structured production log. Written to `print()`
it lands nowhere a NAS operator looks: a box whose RAID or SMART collection
has been failing for weeks looks perfectly healthy in the logs.
"""

import logging

import pytest

from app.api.routes import metrics


def _explode(*args, **kwargs):
    raise RuntimeError("collector exploded")


def _break_system(monkeypatch):
    monkeypatch.setattr(metrics.psutil, "cpu_percent", _explode)
    return metrics.collect_system_metrics


def _break_raid(monkeypatch):
    from app.services.hardware.raid import api as raid_api

    monkeypatch.setattr(raid_api, "get_status", _explode)
    return metrics.collect_raid_metrics


def _break_smart(monkeypatch):
    from app.services.hardware.smart import api as smart_api

    monkeypatch.setattr(smart_api, "get_smart_status", _explode)
    return metrics.collect_smart_metrics


def _break_database(monkeypatch):
    class _BrokenSession:
        def query(self, *args, **kwargs):
            _explode()

    return lambda: metrics.collect_database_metrics(_BrokenSession())


def _break_app(monkeypatch):
    monkeypatch.setattr(metrics.app_info, "labels", _explode)
    return metrics.collect_app_metrics


@pytest.mark.parametrize(
    "break_collector,subject",
    [
        (_break_system, "system"),
        (_break_raid, "RAID"),
        (_break_smart, "SMART"),
        (_break_database, "database"),
        (_break_app, "app"),
    ],
)
def test_collector_failure_is_logged(break_collector, subject, monkeypatch, caplog):
    """A failing collector logs the error instead of printing it, and never raises."""
    collect = break_collector(monkeypatch)

    with caplog.at_level(logging.WARNING, logger=metrics.logger.name):
        collect()  # must not propagate — the endpoint keeps serving

    records = [r for r in caplog.records if r.name == metrics.logger.name]
    assert records, f"{subject} collection failure never reached the logger"

    messages = [r.getMessage() for r in records]
    assert any("collector exploded" in m for m in messages), (
        f"{subject} log line drops the underlying error: {messages}"
    )
    assert any(subject.lower() in m.lower() for m in messages), (
        f"{subject} log line does not say which collector failed: {messages}"
    )
