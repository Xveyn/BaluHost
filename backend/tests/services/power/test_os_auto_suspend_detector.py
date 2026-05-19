"""Tests for ActivePmDetector."""
import sys
from app.services.power import os_auto_suspend as oas


class TestDetector:
    def setup_method(self):
        oas._detector_cache_clear()  # reset cache before each test

    def test_returns_none_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert oas.detect_active_backend() is None

    def test_prefers_kde_when_dbus_says_yes(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: svc == "org.kde.Solid.PowerManagement")
        b = oas.detect_active_backend()
        assert b is not None
        assert b.name == "kde"

    def test_falls_back_to_gnome(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: svc == "org.gnome.SettingsDaemon.Power")
        b = oas.detect_active_backend()
        assert b is not None
        assert b.name == "gnome"

    def test_falls_back_to_logind_when_no_de(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: False)
        etc_systemd = tmp_path / "systemd"
        etc_systemd.mkdir()
        monkeypatch.setattr(oas, "_SYSTEMD_DIR", etc_systemd)
        b = oas.detect_active_backend()
        assert b is not None
        assert b.name == "logind"

    def test_returns_none_when_nothing_detected(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(oas, "_probe_dbus_service", lambda svc: False)
        monkeypatch.setattr(oas, "_SYSTEMD_DIR", tmp_path / "nope")
        assert oas.detect_active_backend() is None

    def test_dbus_timeout_treated_as_unavailable(self, monkeypatch):
        import subprocess as sp
        monkeypatch.setattr(sys, "platform", "linux")
        def fake_run(args, **kwargs):
            raise sp.TimeoutExpired(args, timeout=2.0)
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        # Should not raise; should return None or fall through to logind
        oas.detect_active_backend()  # just no exception

    def test_cache_within_ttl(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        calls = {"n": 0}
        def probe(svc):
            calls["n"] += 1
            return svc == "org.kde.Solid.PowerManagement"
        monkeypatch.setattr(oas, "_probe_dbus_service", probe)
        oas.detect_active_backend()
        oas.detect_active_backend()
        oas.detect_active_backend()
        first_run_count = calls["n"]
        assert first_run_count > 0
        prev = calls["n"]
        oas.detect_active_backend()
        assert calls["n"] == prev
