"""Tests for scripts/finalize_changelog_section.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "finalize_changelog_section.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
        encoding="utf-8",
    )


def test_finalizes_single_unreleased_section(tmp_path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\n"
        "All notable changes...\n\n"
        "---\n\n"
        "## [Unreleased]\n\n"
        "### Added\n\n"
        "- new feature\n\n"
        "---\n\n"
        "## [1.31.7] - 2026-05-04\n\n"
        "### Fixed\n\n"
        "- something\n\n"
        "---\n",
        encoding="utf-8",
    )

    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--target", str(target))
    assert result.returncode == 0, result.stderr

    out = target.read_text(encoding="utf-8")
    assert "## [1.32.0] - 2026-05-06" in out
    assert "## [Unreleased]" not in out
    assert "- new feature" in out
    # Older section untouched
    assert "## [1.31.7] - 2026-05-04" in out
    assert "- something" in out


def test_defaults_date_to_today(tmp_path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\n---\n\n## [Unreleased]\n\n### Added\n\n- x\n\n---\n",
        encoding="utf-8",
    )

    result = _run("--version", "2.0.0", "--target", str(target))
    assert result.returncode == 0, result.stderr

    out = target.read_text(encoding="utf-8")
    assert out.startswith("# Changelog\n\n---\n\n## [2.0.0] - ")
    assert "## [Unreleased]" not in out


def test_fails_when_no_unreleased_section(tmp_path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\n---\n\n## [1.31.7] - 2026-05-04\n\n### Fixed\n\n- something\n\n---\n",
        encoding="utf-8",
    )

    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--target", str(target))
    assert result.returncode != 0
    assert "Unreleased" in result.stderr


def test_fails_when_multiple_unreleased_sections(tmp_path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\n---\n\n"
        "## [Unreleased]\n\n### Added\n\n- a\n\n---\n\n"
        "## [Unreleased]\n\n### Added\n\n- b\n\n---\n",
        encoding="utf-8",
    )

    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--target", str(target))
    assert result.returncode != 0
    assert "Unreleased" in result.stderr


def test_ignores_unreleased_with_trailing_text(tmp_path):
    """'## [Unreleased] - TBD' is NOT the bare marker this script looks for --
    it must not be mistaken for the real placeholder (it has trailing text
    after the closing bracket, unlike the bare header the prepare flow writes)."""
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\n---\n\n## [Unreleased] - TBD\n\n### Added\n\n- a\n\n---\n",
        encoding="utf-8",
    )

    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--target", str(target))
    assert result.returncode != 0
