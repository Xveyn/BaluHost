"""MonitoringWorker publishes SMART disk summary to SHM.

Regression test for disk:* sources never appearing in the fan_control
registry: SMART scans were cached per-process, and the fan_control service
in each web worker had no shared view of disk temperatures. A centralized
SHM publish lets every web worker read the same fresh data.
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.services.monitoring.worker_service import MonitoringWorker
from app.services.monitoring.shm import SMART_SUMMARY_FILE


def _mock_smart_status(*devices):
    return SimpleNamespace(devices=list(devices))


def _device(name: str, temp):
    return SimpleNamespace(name=name, temperature=temp)


def test_smart_summary_snapshot_writes_devices_with_temps():
    worker = MonitoringWorker()
    captured: dict = {}

    def _capture(filename, data):
        if filename == SMART_SUMMARY_FILE:
            captured["data"] = data

    payload = _mock_smart_status(
        _device("sda", 38),
        _device("nvme0n1", 42),
    )

    with patch("app.services.monitoring.worker_service.write_shm", side_effect=_capture), \
         patch("app.services.hardware.smart.api.get_smart_status", return_value=payload):
        worker._write_smart_summary_snapshot()

    assert "data" in captured, "snapshot did not write SMART_SUMMARY_FILE"
    devices = captured["data"]["devices"]
    assert devices == [
        {"name": "sda", "temperature_celsius": 38.0},
        {"name": "nvme0n1", "temperature_celsius": 42.0},
    ]
    assert "timestamp" in captured["data"]


def test_smart_summary_snapshot_omits_devices_without_temperature():
    """Devices that don't report a temperature are skipped — fan_control
    can't use them anyway and they'd clutter the SensorsPanel."""
    worker = MonitoringWorker()
    captured: dict = {}

    def _capture(filename, data):
        if filename == SMART_SUMMARY_FILE:
            captured["data"] = data

    payload = _mock_smart_status(
        _device("sda", 38),
        _device("sdb", None),
    )

    with patch("app.services.monitoring.worker_service.write_shm", side_effect=_capture), \
         patch("app.services.hardware.smart.api.get_smart_status", return_value=payload):
        worker._write_smart_summary_snapshot()

    devices = captured["data"]["devices"]
    assert [d["name"] for d in devices] == ["sda"]


def test_smart_summary_snapshot_handles_empty_status():
    worker = MonitoringWorker()
    captured: dict = {}

    def _capture(filename, data):
        if filename == SMART_SUMMARY_FILE:
            captured["data"] = data

    with patch("app.services.monitoring.worker_service.write_shm", side_effect=_capture), \
         patch("app.services.hardware.smart.api.get_smart_status",
               return_value=_mock_smart_status()):
        worker._write_smart_summary_snapshot()

    assert captured["data"]["devices"] == []


def test_smart_summary_snapshot_swallows_smart_scan_errors():
    """A failing SMART scan must not break the monitoring loop."""
    worker = MonitoringWorker()

    with patch("app.services.monitoring.worker_service.write_shm"), \
         patch("app.services.hardware.smart.api.get_smart_status",
               side_effect=RuntimeError("smartctl unavailable")):
        worker._write_smart_summary_snapshot()  # must not raise
