"""Tests for scripts/generate_changelog_section.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "generate_changelog_section.py"


def _run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        input=input_text,
        cwd=str(REPO_ROOT),
        check=False,
    )


def test_groups_feat_under_added():
    # --stdin reads pre-formatted commit lines, bypassing git for unit tests
    commits = (
        "abc1234\x1ffeat: add new dashboard widget\x1f\x1e"
        "def5678\x1ffix: prevent crash on empty input\x1f\x1e"
    )
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "## [1.32.0] - 2026-05-06" in out
    assert "### Added" in out
    assert "- add new dashboard widget" in out
    assert "### Fixed" in out
    assert "- prevent crash on empty input" in out


def test_scope_renders_as_bold_prefix():
    commits = "abc1234\x1ffeat(sleep): detect Suspend + WoL capabilities\x1f\x1e"
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    assert "- **(sleep)** detect Suspend + WoL capabilities" in result.stdout


def test_chore_ci_test_style_build_are_ignored():
    commits = (
        "a\x1fchore: bump dependencies\x1f\x1e"
        "b\x1fci: tweak workflow\x1f\x1e"
        "c\x1ftest: add coverage\x1f\x1e"
        "d\x1fstyle: reformat\x1f\x1e"
        "e\x1fbuild: update tooling\x1f\x1e"
    )
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    # No bullet lines -- only the heading + date + trailing separator
    assert "\n- " not in result.stdout


def test_non_conventional_commits_are_ignored():
    commits = "abc\x1fjust a plain commit message\x1f\x1e"
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    assert "\n- " not in result.stdout


def test_breaking_change_in_subject_creates_breaking_section():
    commits = "abc1234\x1ffeat!: rewrite auth flow\x1f\x1e"
    result = _run("--version", "2.0.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "### " in out and "BREAKING CHANGES" in out
    assert "- rewrite auth flow" in out


def test_breaking_change_in_body_creates_breaking_section():
    commits = (
        "abc1234\x1ffeat: rewrite auth flow\x1f"
        "BREAKING CHANGE: removes /api/legacy/login\x1e"
    )
    result = _run("--version", "2.0.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "### " in out and "BREAKING CHANGES" in out
    assert "- rewrite auth flow" in out


def test_pr_number_extracted_from_subject_suffix():
    commits = "abc1234\x1ffix(sleep): detect Suspend + WoL capabilities (#70)\x1f\x1e"
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    assert "- **(sleep)** detect Suspend + WoL capabilities (#70)" in result.stdout


def test_empty_commits_produces_no_bullets_and_exit_zero():
    # Empty input is allowed; the workflow's emptiness check is its own concern
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text="")
    assert result.returncode == 0, result.stderr
    assert "## [1.32.0] - 2026-05-06" in result.stdout
    assert "\n- " not in result.stdout


def test_writes_to_file_when_output_path_given(tmp_path):
    target = tmp_path / "section.md"
    commits = "abc\x1ffeat: x\x1f\x1e"
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", str(target), input_text=commits)
    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8").startswith("## [1.32.0] - 2026-05-06")
    assert "- x" in target.read_text(encoding="utf-8")
