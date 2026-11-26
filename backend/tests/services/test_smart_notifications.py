"""Tests for the SMART notification check (#873)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.system import SmartAttribute, SmartDevice, SmartStatusResponse
from app.services.hardware.smart.api import _check_smart_for_notifications


def _attr(name: str, raw: str = "0", status: str = "OK", id: int = 5) -> SmartAttribute:
    return SmartAttribute(
        id=id, name=name, value=100, worst=100, threshold=10, raw=raw, status=status
    )


def _device(name: str, status: str, attrs: list[SmartAttribute]) -> SmartDevice:
    return SmartDevice(
        name=name,
        model="m",
        serial="s",
        temperature=30,
        status=status,
        capacity_bytes=1,
        used_bytes=None,
        used_percent=None,
        mount_point=None,
        last_self_test=None,
        attributes=attrs,
    )


def _status(*devices: SmartDevice) -> SmartStatusResponse:
    return SmartStatusResponse(
        checked_at=datetime.now(timezone.utc), devices=list(devices)
    )


@pytest.fixture
def emitted(monkeypatch):
    calls: list[tuple[str, str, str]] = []

    def failure(disk, details=""):
        calls.append(("FAILURE", disk, details))

    def warning(disk, details=""):
        calls.append(("WARNING", disk, details))

    monkeypatch.setattr("app.services.notifications.events.emit_smart_failure_sync", failure)
    monkeypatch.setattr("app.services.notifications.events.emit_smart_warning_sync", warning)
    return calls


def test_all_three_problems_are_reported(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "PASSED", [_attr("Reallocated_Sector_Ct", raw="8")]),
        _device("/dev/sdb", "FAILED", []),
        _device("/dev/sdc", "PASSED", [_attr("Raw_Read_Error_Rate", status="FAILING", id=1)]),
    ))
    assert emitted == [
        ("WARNING", "/dev/sda", "8 reallocated Sektoren erkannt"),
        ("FAILURE", "/dev/sdb", "Status: FAILED, Modell: m"),
        ("WARNING", "/dev/sdc", "Attribut 'Raw_Read_Error_Rate' ist im FAILING-Zustand"),
    ]


def test_failed_device_skips_its_attribute_checks(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "FAILED", [_attr("Reallocated_Sector_Ct", raw="8")]),
    ))
    assert [e[0] for e in emitted] == ["FAILURE"]


def test_zero_reallocated_sectors_is_silent(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "PASSED", [_attr("Reallocated_Sector_Ct", raw="0")])
    ))
    assert emitted == []


def test_reallocated_count_is_the_first_token(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "PASSED", [_attr("Reallocated_Event_Count", raw="12 (Average 3)")])
    ))
    assert emitted == [("WARNING", "/dev/sda", "12 reallocated Sektoren erkannt")]


def test_unparseable_raw_is_skipped_quietly(emitted):
    _check_smart_for_notifications(_status(
        _device("/dev/sda", "PASSED", [_attr("Reallocated_Sector_Ct", raw="n/a")]),
        _device("/dev/sdb", "FAILED", []),
    ))
    assert emitted == [("FAILURE", "/dev/sdb", "Status: FAILED, Modell: m")]


def test_nvme_without_ata_attributes_is_silent(emitted):
    _check_smart_for_notifications(_status(_device("/dev/nvme0", "PASSED", [
        _attr("Temperature", raw="35", id=194),
        _attr("Available_Spare", raw="100", id=5),
    ])))
    assert emitted == []


def test_error_on_one_device_does_not_stop_the_others(monkeypatch, emitted, caplog):
    # Failure emit for sdb raises; sdc must still be checked.
    def failing_failure(disk, details=""):
        raise RuntimeError("notification store down")

    monkeypatch.setattr(
        "app.services.notifications.events.emit_smart_failure_sync", failing_failure
    )
    _check_smart_for_notifications(_status(
        _device("/dev/sdb", "FAILED", []),
        _device("/dev/sdc", "PASSED", [_attr("Raw_Read_Error_Rate", status="FAILING", id=1)]),
    ))
    assert ("WARNING", "/dev/sdc", "Attribut 'Raw_Read_Error_Rate' ist im FAILING-Zustand") in emitted
    assert any("/dev/sdb" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)
