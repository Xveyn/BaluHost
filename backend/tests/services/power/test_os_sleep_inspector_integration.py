"""Integration tests for inspect_os_sleep — file resolution, subprocess, cache, resilience."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.power import os_sleep_inspector as ins


@pytest.fixture(autouse=True)
def _clean_cache():
    ins._cache_clear()
    yield
    ins._cache_clear()


@pytest.fixture
def linux_fs(tmp_path: Path, monkeypatch):
    """Layout a fake /etc/systemd tree under tmp_path and point the module at it."""
    systemd = tmp_path / "etc" / "systemd"
    systemd.mkdir(parents=True)
    (systemd / "logind.conf.d").mkdir()
    (systemd / "sleep.conf.d").mkdir()
    monkeypatch.setattr(ins, "_SYSTEMD_DIR", systemd)
    monkeypatch.setattr(ins, "_LOGIND_CONF", systemd / "logind.conf")
    monkeypatch.setattr(ins, "_LOGIND_DROPIN_DIRS", (systemd / "logind.conf.d",))
    monkeypatch.setattr(ins, "_SLEEP_CONF", systemd / "sleep.conf")
    monkeypatch.setattr(ins, "_SLEEP_DROPIN_DIRS", (systemd / "sleep.conf.d",))
    monkeypatch.setattr(ins, "_LID_SENSOR", tmp_path / "no-lid")
    monkeypatch.setattr(ins.sys, "platform", "linux")
    return systemd


def _fake_systemctl(targets: dict[str, str]):
    """Build a subprocess.run replacement that emits one status per target."""
    def runner(cmd, *args, **kwargs):
        # Return order matches argv order after the leading systemctl args.
        names = cmd[2:]  # ["systemctl", "is-enabled", *names]
        out = "\n".join(targets.get(n, "disabled") for n in names) + "\n"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=out, stderr="")
    return runner


def test_full_report_resolves_drop_ins_and_targets(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "logind.conf.d" / "30-baluhost.conf").write_text("[Login]\nIdleAction=suspend\nIdleActionSec=30min\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    with patch.object(ins.subprocess, "run", side_effect=_fake_systemctl({
        "sleep.target": "enabled",
        "suspend.target": "masked",
        "hibernate.target": "disabled",
        "hybrid-sleep.target": "disabled",
        "suspend-then-hibernate.target": "disabled",
    })):
        report = ins.inspect_os_sleep(force_refresh=True)

    assert report.platform_supported is True
    assert report.logind["IdleAction"] == "suspend"
    assert report.sleep_conf["AllowSuspend"] == "yes"
    assert report.targets["suspend.target"] == "masked"
    keys = {i.key for i in report.issues}
    assert "logind.idle_action.suspend" in keys
    assert "targets.suspend.masked" in keys
    # logind.conf and the drop-in were both read; sleep.conf too.
    assert any("logind.conf" in s for s in report.sources)
    assert any("30-baluhost.conf" in s for s in report.sources)
    assert any("sleep.conf" in s for s in report.sources)


def test_cache_hit_skips_subprocess(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    with patch.object(ins.subprocess, "run", side_effect=_fake_systemctl({})) as run_mock:
        ins.inspect_os_sleep(force_refresh=False)
        ins.inspect_os_sleep(force_refresh=False)
    assert run_mock.call_count == 1


def test_force_refresh_bypasses_cache(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    with patch.object(ins.subprocess, "run", side_effect=_fake_systemctl({})) as run_mock:
        ins.inspect_os_sleep(force_refresh=True)
        ins.inspect_os_sleep(force_refresh=True)
    assert run_mock.call_count == 2


def test_subprocess_timeout_does_not_raise(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=5)
    with patch.object(ins.subprocess, "run", side_effect=boom):
        report = ins.inspect_os_sleep(force_refresh=True)
    assert report.platform_supported is True
    assert report.targets == {}


def test_subprocess_failure_does_not_raise(linux_fs: Path):
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    def boom(*args, **kwargs):
        raise FileNotFoundError("systemctl not found")
    with patch.object(ins.subprocess, "run", side_effect=boom):
        report = ins.inspect_os_sleep(force_refresh=True)
    assert report.platform_supported is True
    assert report.targets == {}


def test_unexpected_exception_yields_inspector_failed(linux_fs: Path):
    """If a helper raises unexpectedly, return a report with an inspector.failed issue."""
    with patch.object(ins, "_parse_systemd_ini", side_effect=RuntimeError("kaboom")):
        report = ins.inspect_os_sleep(force_refresh=True)
    assert report.platform_supported is True
    assert any(i.key == "inspector.failed" and i.severity == "error" for i in report.issues)


def test_systemctl_line_count_mismatch_discards_targets(linux_fs: Path):
    """If systemctl returns fewer lines than queried (alias collapse on some
    systemd versions), positional zip would silently misalign — drop the dict."""
    (linux_fs / "logind.conf").write_text("[Login]\nIdleAction=ignore\n")
    (linux_fs / "sleep.conf").write_text("[Sleep]\nAllowSuspend=yes\n")

    def short_runner(cmd, *args, **kwargs):
        # Returns 4 lines for 5 queried targets — would misalign suspend.target=masked
        # to hibernate.target if positional zipping continued.
        return subprocess.CompletedProcess(
            args=cmd, returncode=0,
            stdout="enabled\nmasked\ndisabled\ndisabled\n", stderr="",
        )

    with patch.object(ins.subprocess, "run", side_effect=short_runner):
        report = ins.inspect_os_sleep(force_refresh=True)
    assert report.platform_supported is True
    assert report.targets == {}
    # Critically: classifier must not see a phantom "suspend.target": "masked"
    assert not any(i.key == "targets.suspend.masked" for i in report.issues)
