"""Tests for scripts/bump_version.py --dry-run flag."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "bump_version.py"


def _read_pyproject_version() -> str:
    text = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("version not found")
    return m.group(1)


def _run_bump(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


def test_dry_run_patch_outputs_next_version_without_writing():
    current = _read_pyproject_version()
    parts = current.split(".")
    expected = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"

    result = _run_bump("patch", "--dry-run")
    assert result.returncode == 0, result.stderr
    # Expected version must appear on the last non-empty stdout line
    lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
    assert lines[-1].strip() == expected

    # Verify pyproject.toml unchanged
    assert _read_pyproject_version() == current


def test_dry_run_minor_outputs_next_version():
    current = _read_pyproject_version()
    parts = current.split(".")
    expected = f"{parts[0]}.{int(parts[1]) + 1}.0"

    result = _run_bump("minor", "--dry-run")
    assert result.returncode == 0, result.stderr
    lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
    assert lines[-1].strip() == expected
    assert _read_pyproject_version() == current


def test_dry_run_major_outputs_next_version():
    current = _read_pyproject_version()
    parts = current.split(".")
    expected = f"{int(parts[0]) + 1}.0.0"

    result = _run_bump("major", "--dry-run")
    assert result.returncode == 0, result.stderr
    lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
    assert lines[-1].strip() == expected
    assert _read_pyproject_version() == current
