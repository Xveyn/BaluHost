"""Der eigentliche Neustart-Befehl."""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from app.services.power import scheduled_reboot


def test_dev_mode_does_not_reboot(monkeypatch):
    called = []
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", True, raising=False)
    monkeypatch.setattr(
        scheduled_reboot.subprocess, "run",
        lambda *a, **k: called.append(a) or MagicMock(returncode=0),
    )
    ok, detail = scheduled_reboot.run_reboot_command()
    assert ok is True
    assert "dev" in detail.lower()
    assert called == []


def test_prod_calls_systemctl_reboot_with_list_args(monkeypatch):
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)
    seen = {}

    def _run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(scheduled_reboot.subprocess, "run", _run)
    ok, _ = scheduled_reboot.run_reboot_command()
    assert ok is True
    assert seen["cmd"] == ["sudo", "systemctl", "reboot"]
    assert seen["kwargs"].get("shell") in (None, False)  # niemals shell=True


def test_nonzero_exit_reports_stderr(monkeypatch):
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)
    monkeypatch.setattr(
        scheduled_reboot.subprocess, "run",
        lambda *a, **k: MagicMock(returncode=1, stdout="", stderr="sudo: no entry"),
    )
    ok, detail = scheduled_reboot.run_reboot_command()
    assert ok is False
    assert "sudo: no entry" in detail


def test_timeout_is_handled(monkeypatch):
    monkeypatch.setattr(scheduled_reboot.settings, "is_dev_mode", False, raising=False)

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="systemctl", timeout=30)

    monkeypatch.setattr(scheduled_reboot.subprocess, "run", _boom)
    ok, detail = scheduled_reboot.run_reboot_command()
    assert ok is False
    assert "timeout" in detail.lower()


def test_sudoers_template_has_exactly_one_reboot_line():
    """Ein Verb, keine Argumente, keine Wildcards."""
    template = Path(__file__).resolve().parents[3] / (
        "deploy/install/templates/sudoers-baluhost-power"
    )
    lines = [
        line.strip()
        for line in template.read_text(encoding="utf-8").splitlines()
        if "reboot" in line and not line.strip().startswith("#")
    ]
    assert lines == [
        "@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/systemctl reboot"
    ]
