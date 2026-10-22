"""Blockierende subprocess-Aufrufe duerfen nicht auf dem Event-Loop laufen (#302).

Ein haengendes `wg`, `git fetch` (Timeout 300 s) oder `lsblk` in einer
`async def` haelt den ganzen Uvicorn-Worker an. Zwei Arten von Test:

* Verhaltenstests: der gepatchte `subprocess.run` zeichnet auf, in welchem
  Thread er laeuft. Im Loop-Thread waere die Reparatur wirkungslos.
* Statische Waechter: AST-Scan ueber `app/`, damit die Klasse von Fehlern
  nicht an der naechsten Stelle wiederkommt.
"""
import ast
import errno
import os
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
_BLOCKING = {"run", "Popen", "check_output", "check_call", "call"}


class _Recorder:
    """Ersatz fuer subprocess.run, der den aufrufenden Thread festhaelt."""

    def __init__(self, stdout: str = "", returncode: int = 0):
        self.threads: list[int] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, cmd, **kwargs):
        self.threads.append(threading.get_ident())
        text = kwargs.get("text", False)
        out = self._stdout if text else self._stdout.encode()
        return subprocess.CompletedProcess(
            cmd, self._returncode, stdout=out, stderr="" if text else b""
        )

    def assert_off_loop(self):
        assert self.threads, "subprocess.run wurde nicht aufgerufen"
        assert threading.get_ident() not in self.threads, (
            "subprocess.run lief im Event-Loop-Thread"
        )


# ---------------------------------------------------------------------------
# Verhalten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sleep_backend_run_cmd_runs_off_loop(monkeypatch):
    from app.services.power.sleep_backend_linux import LinuxSleepBackend

    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec)

    ok, _ = await LinuxSleepBackend()._run_cmd(["true"])

    assert ok is True
    rec.assert_off_loop()


@pytest.mark.asyncio
async def test_sleep_backend_wol_capability_runs_off_loop(monkeypatch):
    from app.services.power.sleep_backend_linux import LinuxSleepBackend

    link = "1: lo: <LOOPBACK>\n2: eth0: <BROADCAST>\n"
    ethtool = "Wake-on: g\n"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(threading.get_ident())
        out = link if cmd[0] == "ip" else ethtool
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert await LinuxSleepBackend().get_wol_capability() == ["eth0"]
    assert len(calls) == 2  # ip + ethtool fuer eth0
    assert threading.get_ident() not in calls


@pytest.mark.asyncio
async def test_sleep_backend_data_disks_runs_off_loop(monkeypatch):
    from app.services.power.sleep_backend_linux import LinuxSleepBackend

    lsblk = (
        '{"blockdevices": [{"name": "sda", "type": "disk", "mountpoints": [null]},'
        ' {"name": "nvme0n1", "type": "disk", "children":'
        ' [{"name": "nvme0n1p2", "type": "part", "mountpoints": ["/"]}]}]}'
    )
    rec = _Recorder(stdout=lsblk)
    monkeypatch.setattr(subprocess, "run", rec)

    assert await LinuxSleepBackend().get_data_disk_devices() == ["/dev/sda"]
    rec.assert_off_loop()


@pytest.mark.asyncio
async def test_hwmon_sudo_tee_fallback_runs_off_loop(tmp_path, monkeypatch):
    from app.services.power.fan_backend_linux import LinuxFanControlBackend

    node = tmp_path / "pwm1_enable"
    node.write_text("5\n")

    def deny(self, *a, **k):
        raise OSError(errno.EACCES, os.strerror(errno.EACCES))

    monkeypatch.setattr(Path, "write_text", deny)
    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec)

    ok, code = await LinuxFanControlBackend(MagicMock())._write_hwmon_file(node, "1")

    assert (ok, code) == (True, None)
    rec.assert_off_loop()


@pytest.mark.asyncio
async def test_prod_update_git_calls_run_off_loop(tmp_path, monkeypatch):
    """`git fetch` hat 300 s Timeout -- der laengste Block im Loop vor #302."""
    from app.services.update.prod_backend import ProdUpdateBackend

    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec)

    assert await ProdUpdateBackend(repo_path=tmp_path).fetch_updates() is True
    rec.assert_off_loop()


@pytest.mark.asyncio
async def test_prod_update_git_helper_still_honours_instance_patches(tmp_path, monkeypatch):
    """Tests ersetzen `_run_git` pro Instanz -- der Async-Helfer muss das sehen."""
    from app.services.update.prod_backend import ProdUpdateBackend

    backend = ProdUpdateBackend(repo_path=tmp_path)
    monkeypatch.setattr(backend, "_run_git", lambda *a: (True, "-".join(a), ""))

    assert await backend._run_git_async("a", "b") == (True, "a-b", "")


@pytest.mark.asyncio
async def test_shutdown_benchmarks_kills_orphan_fio_off_loop(monkeypatch):
    """`pgrep` im Shutdown-Pfad (#790) -- sonst haengt ein Stall den Loop."""
    from app.services.benchmark import lifecycle

    monkeypatch.setattr(lifecycle.platform, "system", lambda: "Linux")
    rec = _Recorder(returncode=1)  # pgrep: keine fio-Prozesse
    monkeypatch.setattr(subprocess, "run", rec)
    monkeypatch.setattr(lifecycle, "recover_stale_benchmarks", lambda db: 0)

    await lifecycle.shutdown_benchmarks(MagicMock())

    rec.assert_off_loop()


def test_pgrep_for_orphan_fio_has_a_timeout(monkeypatch):
    from app.services.benchmark import lifecycle

    monkeypatch.setattr(lifecycle.platform, "system", lambda: "Linux")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    lifecycle.kill_orphan_fio_processes()

    assert seen.get("timeout"), "pgrep ohne timeout kann den Aufrufer festhalten"


def test_pgrep_timeout_is_swallowed(monkeypatch):
    """Ein haengendes pgrep darf Start/Shutdown nicht abbrechen."""
    from app.services.benchmark import lifecycle

    monkeypatch.setattr(lifecycle.platform, "system", lambda: "Linux")

    def hang(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", hang)

    lifecycle.kill_orphan_fio_processes()  # darf nicht werfen


# ---------------------------------------------------------------------------
# Statische Waechter
# ---------------------------------------------------------------------------


def _blocking_subprocess_in_async() -> list[str]:
    """subprocess.<blockierend>(...) direkt im Koerper einer async def."""
    found = []

    class V(ast.NodeVisitor):
        def __init__(self, rel):
            self.rel, self.stack = rel, []

        def _fn(self, node, is_async):
            self.stack.append(is_async)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node):
            self._fn(node, False)

        def visit_AsyncFunctionDef(self, node):
            self._fn(node, True)

        def visit_Lambda(self, node):
            self.stack.append(False)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node):
            f = node.func
            if (
                self.stack
                and self.stack[-1]
                and isinstance(f, ast.Attribute)
                and f.attr in _BLOCKING
                and isinstance(f.value, ast.Name)
                and f.value.id == "subprocess"
            ):
                found.append(f"{self.rel}:{node.lineno}")
            self.generic_visit(node)

    for path in sorted(APP_DIR.rglob("*.py")):
        rel = str(path.relative_to(APP_DIR.parent))
        V(rel).visit(ast.parse(path.read_text(encoding="utf-8")))
    return found


def test_no_blocking_subprocess_directly_in_async_def():
    """Neue Stellen gehoeren in `asyncio.to_thread(subprocess.run, ...)`."""
    assert _blocking_subprocess_in_async() == []


# Methoden von VPNService, die (transitiv) `wg`/`sudo` aufrufen.
_VPN_SUBPROCESS_METHODS = {
    "create_client_config",
    "regenerate_client_config",
    "delete_client",
    "revoke_client",
    "apply_server_config",
    "sync_server_keys_from_interface",
}


# Sync-Helfer, die intern subprocess aufrufen. Der AST-Waechter oben sieht
# nur `subprocess.*` direkt in einer `async def`; ein Aufruf ueber diese
# Helfer (#790) faellt dort durch. Datei -> Namen, die in einer `async def`
# nur ueber `asyncio.to_thread(...)` erreicht werden duerfen.
_SYNC_SUBPROCESS_HELPERS = {
    "services/power/core_uptime_rtc_guard.py": {
        "_set_rtc_alarm",
        "_acquire_delay_inhibitor",
        "_release_delay_inhibitor",
    },
    "services/benchmark/lifecycle.py": {"kill_orphan_fio_processes"},
    "core/lifespan.py": {"kill_orphan_fio_processes"},
}


def _direct_helper_calls(rel: str, names: set[str]) -> list[str]:
    """Direktaufrufe `name(...)` / `self.name(...)` im Koerper einer async def.

    `asyncio.to_thread(self.name, ...)` uebergibt den Helfer nur als Wert und
    ist deshalb kein Treffer.
    """
    tree = ast.parse((APP_DIR / rel).read_text(encoding="utf-8"))
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in names:
                found.append(f"{rel}:{node.lineno} {fn.name} -> {name}")
    return found


@pytest.mark.parametrize("rel", sorted(_SYNC_SUBPROCESS_HELPERS))
def test_sync_subprocess_helpers_not_called_directly_from_async_def(rel):
    assert _direct_helper_calls(rel, _SYNC_SUBPROCESS_HELPERS[rel]) == []


def test_vpn_routes_call_subprocess_backed_service_methods_via_to_thread():
    tree = ast.parse((APP_DIR / "api" / "routes" / "vpn.py").read_text(encoding="utf-8"))
    direct = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef):
            continue
        for node in ast.walk(fn):
            f = getattr(node, "func", None)
            if (
                isinstance(node, ast.Call)
                and isinstance(f, ast.Attribute)
                and f.attr in _VPN_SUBPROCESS_METHODS
            ):
                direct.append(f"{fn.name}:{node.lineno} -> {f.attr}")
    assert direct == []
