"""Tests for scripts/insert_changelog_section.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "insert_changelog_section.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
        encoding="utf-8",
    )


def test_inserts_section_after_h1_heading(tmp_path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\n"
        "All notable changes...\n\n"
        "---\n\n"
        "## [1.31.7] - 2026-05-04\n\n"
        "### Fixed\n\n"
        "- something\n\n"
        "---\n",
        encoding="utf-8",
    )
    section = tmp_path / "section.md"
    section.write_text(
        "## [1.32.0] - 2026-05-06\n\n"
        "### Added\n\n"
        "- new feature\n\n"
        "---\n",
        encoding="utf-8",
    )

    result = _run("--section", str(section), "--target", str(target))
    assert result.returncode == 0, result.stderr

    out = target.read_text(encoding="utf-8")
    # H1 + preamble preserved
    assert out.startswith("# Changelog\n\nAll notable changes...\n\n---\n\n")
    # New section sits immediately after the preamble's --- separator
    assert "---\n\n## [1.32.0] - 2026-05-06" in out
    # Old section still present
    assert "## [1.31.7] - 2026-05-04" in out
    # New section appears before the old one
    new_idx = out.index("[1.32.0]")
    old_idx = out.index("[1.31.7]")
    assert new_idx < old_idx


def test_inserts_when_no_existing_sections(tmp_path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text(
        "# Changelog\n\nAll notable changes...\n\n---\n",
        encoding="utf-8",
    )
    section = tmp_path / "section.md"
    section.write_text(
        "## [1.0.0] - 2026-05-06\n\n### Added\n\n- first release\n\n---\n",
        encoding="utf-8",
    )

    result = _run("--section", str(section), "--target", str(target))
    assert result.returncode == 0, result.stderr

    out = target.read_text(encoding="utf-8")
    assert "## [1.0.0] - 2026-05-06" in out
    assert "- first release" in out


def test_fails_when_target_lacks_h1(tmp_path):
    target = tmp_path / "CHANGELOG.md"
    target.write_text("Not a real changelog\n", encoding="utf-8")
    section = tmp_path / "section.md"
    section.write_text("## [1.0.0]\n", encoding="utf-8")

    result = _run("--section", str(section), "--target", str(target))
    assert result.returncode != 0
