"""Tests for os_auto_suspend service-layer helpers."""
from app.services.power import os_auto_suspend as oas
from app.schemas.sleep import OsAutoSuspendUpdate, OsAutoSuspendAction


class FakeBackend:
    name = "kde"
    label = "KDE PowerDevil"
    def __init__(self, value):
        self._value = value
        self.writes = []
    def is_available(self): return True
    def read(self): return self._value
    def write(self, v):
        self.writes.append(v)
        self._value = v


class TestServiceLayer:
    def test_get_unsupported_when_no_backend(self, monkeypatch):
        monkeypatch.setattr(oas, "detect_active_backend", lambda: None)
        resp = oas.get_os_auto_suspend()
        assert resp.supported is False
        assert resp.source == "none"
        assert resp.timeout_minutes == 0

    def test_get_reads_from_active_backend(self, monkeypatch):
        fb = FakeBackend(oas.AutoSuspendValue(enabled=True, timeout_minutes=20, action="suspend"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        resp = oas.get_os_auto_suspend()
        assert resp.supported is True
        assert resp.source == "kde"
        assert resp.backend_label == "KDE PowerDevil"
        assert resp.enabled is True
        assert resp.timeout_minutes == 20

    def test_set_writes_and_returns_readback(self, monkeypatch):
        fb = FakeBackend(oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="suspend"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        update = OsAutoSuspendUpdate(
            enabled=True, timeout_minutes=30, action=OsAutoSuspendAction.HIBERNATE
        )
        resp = oas.set_os_auto_suspend(update)
        assert len(fb.writes) == 1
        assert fb.writes[0].timeout_minutes == 30
        assert fb.writes[0].action == "hibernate"
        assert resp.enabled is True
        assert resp.action == "hibernate"

    def test_set_raises_when_no_backend(self, monkeypatch):
        monkeypatch.setattr(oas, "detect_active_backend", lambda: None)
        import pytest
        with pytest.raises(RuntimeError, match="no active power manager"):
            oas.set_os_auto_suspend(OsAutoSuspendUpdate(
                enabled=True, timeout_minutes=15, action=OsAutoSuspendAction.SUSPEND
            ))
