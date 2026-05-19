"""Tests for the inspector's new KDE/GNOME idle-suspend surfacing."""
from pathlib import Path

from app.services.power import os_sleep_inspector as ins
from app.services.power import os_auto_suspend as oas


class FakeBackend:
    def __init__(self, name, value, available=True):
        self.name = name
        self.label = f"fake-{name}"
        self._value = value
        self._available = available
    def is_available(self): return self._available
    def read(self): return self._value
    def write(self, v): pass


def _patch_linux(monkeypatch, tmp_path: Path):
    """Patch the module to appear to be running on Linux with a real systemd dir."""
    systemd = tmp_path / "etc" / "systemd"
    systemd.mkdir(parents=True)
    monkeypatch.setattr(ins, "_SYSTEMD_DIR", systemd)
    monkeypatch.setattr(ins.sys, "platform", "linux")


class TestInspectorIdleBackendIntegration:
    def test_kde_idle_suspend_emits_info_issue(self, monkeypatch, tmp_path):
        ins._cache_clear()
        _patch_linux(monkeypatch, tmp_path)
        fb = FakeBackend("kde", oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        kde_issues = [i for i in report.issues if i.key.startswith("pm.kde")]
        assert len(kde_issues) == 1
        assert kde_issues[0].severity == "info"
        assert "15" in kde_issues[0].message or "15" in (kde_issues[0].detail or "")

    def test_gnome_idle_emits_info_issue(self, monkeypatch, tmp_path):
        ins._cache_clear()
        _patch_linux(monkeypatch, tmp_path)
        fb = FakeBackend("gnome", oas.AutoSuspendValue(enabled=True, timeout_minutes=20, action="hibernate"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        gnome_issues = [i for i in report.issues if i.key.startswith("pm.gnome")]
        assert len(gnome_issues) == 1
        assert "hibernate" in gnome_issues[0].message.lower() or "hibernate" in (gnome_issues[0].detail or "").lower()

    def test_logind_active_no_pm_issue(self, monkeypatch, tmp_path):
        ins._cache_clear()
        _patch_linux(monkeypatch, tmp_path)
        fb = FakeBackend("logind", oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        pm_issues = [i for i in report.issues if i.key.startswith("pm.")]
        assert pm_issues == []

    def test_disabled_pm_no_issue(self, monkeypatch, tmp_path):
        ins._cache_clear()
        _patch_linux(monkeypatch, tmp_path)
        fb = FakeBackend("kde", oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore"))
        monkeypatch.setattr(oas, "detect_active_backend", lambda: fb)
        monkeypatch.setattr(ins, "_parse_systemd_ini", lambda *a, **kw: {})
        monkeypatch.setattr(ins, "_merge_drop_ins", lambda base, *a, **kw: base)
        monkeypatch.setattr(ins, "_systemctl_is_enabled", lambda names: {n: "static" for n in names})
        report = ins.inspect_os_sleep(force_refresh=True)
        pm_issues = [i for i in report.issues if i.key.startswith("pm.")]
        assert pm_issues == []
