"""Argument-validation tests for the root-owned spawn wrapper.

Linux-only: needs bash + coreutils realpath. The privilege-dropping chain
(prlimit/unshare/setpriv) is shimmed via PATH so the test asserts the wrapper's
*validation* and the *reconstructed exec line*, not real privilege drop.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bash wrapper, POSIX only")

WRAPPER = Path(__file__).resolve().parents[4] / "deploy" / "install" / "bin" / "spawn-plugin-worker.sh"


def _run(args, extra_path: Path):
    """Invoke the wrapper with `prlimit` shimmed on PATH to echo its argv."""
    env = dict(os.environ)
    env["PATH"] = f"{extra_path}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(WRAPPER), *args],
        capture_output=True, text=True, env=env,
    )


@pytest.fixture
def prlimit_shim(tmp_path: Path) -> Path:
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir()
    shim = shim_dir / "prlimit"
    shim.write_text('#!/bin/bash\necho "$@"\nexit 0\n')
    shim.chmod(0o755)
    return shim_dir


def test_rejects_bad_plugin_name(prlimit_shim):
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", "/tmp", "--plugin-name", "../evil"], prlimit_shim)
    assert r.returncode == 64


def test_rejects_bad_connect(prlimit_shim):
    r = _run(["--connect", "a;b", "--plugin-dir", "/tmp", "--plugin-name", "demo"], prlimit_shim)
    assert r.returncode == 67


def test_rejects_unresolvable_dir(prlimit_shim):
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", "/nope/does/not/exist", "--plugin-name", "demo"], prlimit_shim)
    assert r.returncode == 65


def test_rejects_dir_outside_jail(prlimit_shim, tmp_path):
    outside = tmp_path / "demo"
    outside.mkdir()
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", str(outside), "--plugin-name", "demo"], prlimit_shim)
    assert r.returncode == 66


@pytest.mark.skipif(getattr(os, "geteuid", lambda: 0)() != 0, reason="needs root to create the canonical jail dir")
def test_happy_path_builds_exec_chain(prlimit_shim):
    jail = Path("/var/lib/baluhost/plugins/demo")
    jail.mkdir(parents=True, exist_ok=True)
    r = _run(["--connect", "/run/x.sock", "--plugin-dir", str(jail),
              "--plugin-name", "demo", "-m", "app.plugins.sandbox.worker"], prlimit_shim)
    assert r.returncode == 0
    out = r.stdout
    assert "unshare --net" in out
    assert "setpriv --reuid baluhost-plugin" in out
    assert "--plugin-dir /var/lib/baluhost/plugins/demo" in out
    assert "--plugin-name demo" in out
    assert "-m app.plugins.sandbox.worker" in out
