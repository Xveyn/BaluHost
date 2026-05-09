"""Tests for os_sleep_inspector low-level helpers."""
import sys
from pathlib import Path

import pytest

from app.services.power import os_sleep_inspector as ins


class TestParseSystemdIni:
    def test_parses_simple_key_value(self, tmp_path: Path):
        f = tmp_path / "logind.conf"
        f.write_text("[Login]\nIdleAction=suspend\nIdleActionSec=30min\n")
        result = ins._parse_systemd_ini(f, section="Login")
        assert result == {"IdleAction": "suspend", "IdleActionSec": "30min"}

    def test_skips_comments_and_blanks(self, tmp_path: Path):
        f = tmp_path / "sleep.conf"
        f.write_text(
            "# top comment\n"
            "; semicolon comment\n"
            "\n"
            "[Sleep]\n"
            "AllowSuspend=yes\n"
            "  # inline indented comment\n"
            "AllowHibernation=no\n"
        )
        result = ins._parse_systemd_ini(f, section="Sleep")
        assert result == {"AllowSuspend": "yes", "AllowHibernation": "no"}

    def test_only_returns_requested_section(self, tmp_path: Path):
        f = tmp_path / "logind.conf"
        f.write_text(
            "[Login]\nIdleAction=ignore\n"
            "[Other]\nFoo=bar\n"
        )
        assert ins._parse_systemd_ini(f, section="Login") == {"IdleAction": "ignore"}
        assert ins._parse_systemd_ini(f, section="Other") == {"Foo": "bar"}

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert ins._parse_systemd_ini(tmp_path / "nope.conf", section="Login") == {}

    def test_malformed_lines_are_skipped(self, tmp_path: Path):
        f = tmp_path / "logind.conf"
        f.write_text("[Login]\nIdleAction=suspend\nthis line has no equals\nIdleActionSec=30min\n")
        result = ins._parse_systemd_ini(f, section="Login")
        assert result == {"IdleAction": "suspend", "IdleActionSec": "30min"}


class TestMergeDropIns:
    def test_drop_in_overrides_base(self, tmp_path: Path):
        base = {"IdleAction": "ignore", "HandleLidSwitch": "suspend"}
        drop_dir = tmp_path / "logind.conf.d"
        drop_dir.mkdir()
        (drop_dir / "30-baluhost.conf").write_text("[Login]\nIdleAction=suspend\n")
        merged = ins._merge_drop_ins(base, drop_dir, section="Login")
        assert merged["IdleAction"] == "suspend"
        assert merged["HandleLidSwitch"] == "suspend"  # untouched

    def test_drop_ins_applied_in_filename_order(self, tmp_path: Path):
        base: dict[str, str] = {}
        drop_dir = tmp_path / "logind.conf.d"
        drop_dir.mkdir()
        (drop_dir / "10-first.conf").write_text("[Login]\nIdleAction=ignore\n")
        (drop_dir / "20-second.conf").write_text("[Login]\nIdleAction=suspend\n")
        merged = ins._merge_drop_ins(base, drop_dir, section="Login")
        assert merged["IdleAction"] == "suspend"  # later filename wins

    def test_missing_directory_returns_base_unchanged(self, tmp_path: Path):
        base = {"IdleAction": "ignore"}
        merged = ins._merge_drop_ins(base, tmp_path / "nope.d", section="Login")
        assert merged == base


class TestPlatformGuard:
    def test_unsupported_platform_short_circuits(self, monkeypatch):
        monkeypatch.setattr(ins.sys, "platform", "win32")
        report = ins.inspect_os_sleep(force_refresh=True)
        assert report.platform_supported is False
        assert report.logind == {}
        assert report.sleep_conf == {}
        assert report.targets == {}
        assert report.issues == []

    def test_no_systemd_dir_short_circuits(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(ins.sys, "platform", "linux")
        monkeypatch.setattr(ins, "_SYSTEMD_DIR", tmp_path / "absent")
        report = ins.inspect_os_sleep(force_refresh=True)
        assert report.platform_supported is False
