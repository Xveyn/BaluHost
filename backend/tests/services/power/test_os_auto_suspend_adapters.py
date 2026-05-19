"""Tests for os_auto_suspend adapters and shared types."""
import subprocess

from app.services.power import os_auto_suspend as oas


class TestAutoSuspendValue:
    def test_construct_and_compare(self):
        v1 = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        v2 = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        assert v1 == v2
        assert v1.timeout_minutes == 15

    def test_frozen(self):
        import dataclasses
        v = oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        try:
            v.timeout_minutes = 30  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("expected FrozenInstanceError")


class TestParseIdleActionSec:
    """Direct unit tests for the time-parsing helper."""

    def test_empty_returns_zero(self):
        assert oas._parse_idle_action_sec("") == 0

    def test_whitespace_only_returns_zero(self):
        assert oas._parse_idle_action_sec("   ") == 0

    def test_minutes_suffix(self):
        assert oas._parse_idle_action_sec("15min") == 15

    def test_seconds_suffix(self):
        assert oas._parse_idle_action_sec("900s") == 15

    def test_raw_integer_treated_as_seconds(self):
        assert oas._parse_idle_action_sec("900") == 15

    def test_with_surrounding_whitespace(self):
        assert oas._parse_idle_action_sec("  15min  ") == 15

    def test_uppercase_suffix_handled(self):
        assert oas._parse_idle_action_sec("15MIN") == 15

    def test_negative_clamped_to_zero(self):
        assert oas._parse_idle_action_sec("-15min") == 0
        assert oas._parse_idle_action_sec("-900s") == 0
        assert oas._parse_idle_action_sec("-900") == 0

    def test_float_string_returns_zero(self):
        assert oas._parse_idle_action_sec("1.5min") == 0

    def test_garbage_returns_zero(self):
        assert oas._parse_idle_action_sec("abc") == 0

    def test_very_large_value_passes_through(self):
        assert oas._parse_idle_action_sec("99999min") == 99999


class TestLogindAdapterRead:
    def _make_adapter(self, monkeypatch, tmp_path, conf_text=""):
        conf = tmp_path / "logind.conf"
        conf.write_text(conf_text)
        monkeypatch.setattr(oas, "_LOGIND_CONF", conf)
        monkeypatch.setattr(oas, "_LOGIND_DROPIN_DIRS", (tmp_path / "logind.conf.d",))
        return oas.LogindAdapter()

    def test_read_empty_file_means_disabled(self, monkeypatch, tmp_path):
        a = self._make_adapter(monkeypatch, tmp_path, "")
        v = a.read()
        assert v.enabled is False
        assert v.action == "ignore"
        assert v.timeout_minutes == 15  # sentinel default for UI re-enabling

    def test_read_idle_action_suspend(self, monkeypatch, tmp_path):
        a = self._make_adapter(
            monkeypatch, tmp_path,
            "[Login]\nIdleAction=suspend\nIdleActionSec=15min\n",
        )
        v = a.read()
        assert v.enabled is True
        assert v.action == "suspend"
        assert v.timeout_minutes == 15

    def test_read_idle_action_sec_raw_seconds(self, monkeypatch, tmp_path):
        a = self._make_adapter(
            monkeypatch, tmp_path,
            "[Login]\nIdleAction=hibernate\nIdleActionSec=900\n",
        )
        v = a.read()
        assert v.action == "hibernate"
        assert v.timeout_minutes == 15

    def test_read_idle_action_sec_seconds_suffix(self, monkeypatch, tmp_path):
        a = self._make_adapter(
            monkeypatch, tmp_path,
            "[Login]\nIdleAction=suspend\nIdleActionSec=900s\n",
        )
        v = a.read()
        assert v.timeout_minutes == 15

    def test_read_drop_in_overrides_base(self, monkeypatch, tmp_path):
        conf = tmp_path / "logind.conf"
        conf.write_text("[Login]\nIdleAction=ignore\n")
        drop_dir = tmp_path / "logind.conf.d"
        drop_dir.mkdir()
        (drop_dir / "30-baluhost.conf").write_text(
            "[Login]\nIdleAction=suspend\nIdleActionSec=10min\n"
        )
        monkeypatch.setattr(oas, "_LOGIND_CONF", conf)
        monkeypatch.setattr(oas, "_LOGIND_DROPIN_DIRS", (drop_dir,))
        v = oas.LogindAdapter().read()
        assert v.action == "suspend"
        assert v.timeout_minutes == 10


class TestLogindAdapterWrite:
    def test_write_invokes_sudo_helper_with_correct_args(self, monkeypatch):
        captured: dict = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        oas.LogindAdapter().write(
            oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
        )
        assert captured["args"] == [
            "sudo", "-n", oas._HELPER_PATH,
            "--timeout", "900", "--action", "suspend",
        ]
        assert captured["kwargs"]["check"] is True
        assert captured["kwargs"]["timeout"] == oas._SUDO_TIMEOUT_SECONDS

    def test_write_disabled_passes_ignore(self, monkeypatch):
        captured: dict = {}
        def fake_run(args, **kwargs):
            captured["args"] = args
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        oas.LogindAdapter().write(
            oas.AutoSuspendValue(enabled=False, timeout_minutes=15, action="ignore")
        )
        assert "--action" in captured["args"]
        assert captured["args"][captured["args"].index("--action") + 1] == "ignore"

    def test_write_raises_on_helper_failure(self, monkeypatch):
        def fake_run(args, **kwargs):
            raise subprocess.CalledProcessError(2, args, stderr="bad args")
        monkeypatch.setattr(oas.subprocess, "run", fake_run)
        import pytest
        with pytest.raises(RuntimeError, match="logind helper failed"):
            oas.LogindAdapter().write(
                oas.AutoSuspendValue(enabled=True, timeout_minutes=15, action="suspend")
            )
