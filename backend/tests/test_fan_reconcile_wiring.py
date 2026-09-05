"""Vorbedingungen und Gate des Identitaets-Abgleichs (#532)."""
from unittest.mock import MagicMock

import pytest

from app.services.power import fan_control as fan_control_module
from app.services.power.fan_control import FanControlService


def _service(monkeypatch, *, primary: bool, linux: bool):
    FanControlService._instance = None
    config = MagicMock()
    config.fan_control_enabled = True
    config.is_dev_mode = False
    service = FanControlService(config, MagicMock())
    service._use_linux_backend = linux
    monkeypatch.setattr(fan_control_module.lifespan, "IS_PRIMARY_WORKER",
                        primary, raising=False)
    return service


def test_skips_when_not_primary_worker(monkeypatch):
    service = _service(monkeypatch, primary=False, linux=True)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_on_dev_backend(monkeypatch):
    # is_available() faellt bei 0 gefundenen Lueftern auch in Produktion auf
    # das Dev-Backend zurueck. Liefe der Abgleich dann, deaktivierte er in
    # einem Rutsch alle hwmon-Zeilen.
    service = _service(monkeypatch, primary=True, linux=False)
    assert service._should_reconcile(chip_count=3) is False


def test_skips_when_scan_found_no_chip(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=0) is False


def test_runs_when_all_preconditions_hold(monkeypatch):
    service = _service(monkeypatch, primary=True, linux=True)
    assert service._should_reconcile(chip_count=3) is True
