"""Die Fallback-Leiter von _write_hwmon_file (#554).

Die Funktion wird in mehreren Testdateien gemockt, aber nirgends ausgefuehrt.
Seit #552 fuehrt auch der Rechte-Probe seinen Write ueber sie -- ihre Leiter
liegt damit im Startpfad jeder Prod-Instanz.

Sie hat vier Ausgaenge, und der dritte ist der, der schon einmal zu einer
falschen Fehlermeldung gefuehrt hat: nach einem gescheiterten sudo-tee meldet
sie `EACCES`, obwohl der privilegierte Write am Kernel und nicht an den
Rechten gescheitert sein kann. Der errno gehoert deshalb genannt, nicht
gedeutet (Vorgabe aus #534).
"""
import errno
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.power.fan_backend_linux import LinuxFanControlBackend


@pytest.fixture
def backend():
    return LinuxFanControlBackend(MagicMock())


@pytest.fixture
def node(tmp_path) -> Path:
    """Ein hwmon-Knoten mit Inhalt -- angelegt, bevor write_text gepatcht wird."""
    path = tmp_path / "pwm1_enable"
    path.write_text("5\n")
    return path


def _write_raises(code: int):
    def _write(self, *args, **kwargs):
        raise OSError(code, os.strerror(code))
    return _write


class _Result:
    def __init__(self, returncode: int):
        self.returncode = returncode
        self.stdout = b""
        self.stderr = b"tee: failed\n"


@pytest.mark.asyncio
async def test_a_direct_write_succeeds_and_sets_the_flag(backend, node):
    ok, code = await backend._write_hwmon_file(node, "1")

    assert (ok, code) == (True, None)
    assert node.read_text().strip() == "1"
    assert backend._has_write_permission is True


@pytest.mark.asyncio
async def test_a_missing_node_reports_no_errno(backend, tmp_path):
    """Kein Knoten ist kein Rechteproblem -- der Aufrufer darf das unterscheiden."""
    ok, code = await backend._write_hwmon_file(tmp_path / "nicht_da", "1")

    assert (ok, code) == (False, None)
    assert backend._has_write_permission is False


@pytest.mark.asyncio
async def test_eacces_falls_back_to_sudo_tee(backend, node, monkeypatch):
    monkeypatch.setattr(Path, "write_text", _write_raises(errno.EACCES))
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Result(0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, code = await backend._write_hwmon_file(node, "1")

    assert (ok, code) == (True, None)
    assert backend._has_write_permission is True
    assert calls[0][:3] == ["sudo", "-n", "tee"], calls


@pytest.mark.asyncio
async def test_a_failed_sudo_tee_reports_the_direct_errno(backend, node, monkeypatch):
    """Der Fallstrick: gemeldet wird EACCES vom direkten Versuch.

    Der privilegierte Write kann am Kernel gescheitert sein (EINVAL, EBUSY) --
    das sieht diese Funktion nicht. Wer die Meldung formuliert, muss den errno
    nennen statt ihn als "keine Rechte" zu deuten.
    """
    monkeypatch.setattr(Path, "write_text", _write_raises(errno.EACCES))
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _Result(1))

    ok, code = await backend._write_hwmon_file(node, "1")

    assert ok is False
    assert code == errno.EACCES
    assert backend._has_write_permission is False


@pytest.mark.asyncio
async def test_another_errno_skips_sudo_entirely(backend, node, monkeypatch):
    """EBUSY ist kein Rechteproblem -- sudo wuerde daran nichts aendern.

    Der nct6775 liefert genau das fuer pwm-Writes im Auto-Modus.
    """
    monkeypatch.setattr(Path, "write_text", _write_raises(errno.EBUSY))
    called = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: called.append(cmd))

    ok, code = await backend._write_hwmon_file(node, "1")

    assert (ok, code) == (False, errno.EBUSY)
    assert called == [], "sudo wurde trotz EBUSY versucht"


@pytest.mark.asyncio
async def test_a_hanging_sudo_does_not_escape_into_the_loop(backend, node, monkeypatch):
    """Ein Timeout darf die Regelschleife nicht mitreissen."""
    monkeypatch.setattr(Path, "write_text", _write_raises(errno.EACCES))

    def timing_out(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(subprocess, "run", timing_out)

    ok, code = await backend._write_hwmon_file(node, "1")

    assert (ok, code) == (False, errno.EACCES)
