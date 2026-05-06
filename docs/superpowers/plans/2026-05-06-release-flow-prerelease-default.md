# Release Flow Pre-Release Default Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch PR-merges-to-main from auto-stable-releases to pre-releases by default, with a manual `workflow_dispatch` trigger for stable promotions and auto-CHANGELOG generation from Conventional Commits.

**Architecture:** Two-phase atomic switch. Phase 1 ships backend+frontend infrastructure (new schema field, tag-based version detection, pre-release badge, CHANGELOG helper scripts) under the existing flow. Phase 2 atomically replaces auto-merge bumping with pre-release tagging and adds the new `release-stable.yml` workflow.

**Tech Stack:** GitHub Actions (YAML), Python 3.11, FastAPI, Pydantic, React 18, TypeScript, Tailwind, pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-05-06-release-flow-prerelease-default-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/bump_version.py` | Modify | Add `--dry-run` flag |
| `scripts/generate_changelog_section.py` | Create | Group conventional commits into Keep-a-Changelog sections |
| `scripts/insert_changelog_section.py` | Create | Insert new section after H1 in `CHANGELOG.md` |
| `tests/scripts/test_bump_version.py` | Create | Tests for `--dry-run` |
| `tests/scripts/test_generate_changelog_section.py` | Create | Tests for grouping/parsing logic |
| `tests/scripts/test_insert_changelog_section.py` | Create | Tests for insertion |
| `backend/app/schemas/update.py` | Modify | Add `is_prerelease: bool` to `VersionInfo` |
| `backend/app/services/update/prod_backend.py` | Modify | Tag-based version detection, set `is_prerelease` |
| `backend/app/services/update/dev_backend.py` | Modify | Set `is_prerelease=False` |
| `backend/tests/services/test_update_service.py` | Modify | Tests for tag-based detection + `is_prerelease` |
| `client/src/api/updates.ts` | Modify | Add `is_prerelease` to TS `VersionInfo` |
| `client/src/contexts/VersionContext.tsx` | Modify | Add `useVersionDisplay()` hook |
| `client/src/i18n/locales/en/updates.json` | Modify | `preRelease.badge` key |
| `client/src/i18n/locales/de/updates.json` | Modify | `preRelease.badge` key |
| `client/src/components/updates/UpdateOverviewTab.tsx` | Modify | Render pre-release badge |
| `.github/workflows/release-stable.yml` | Create | `workflow_dispatch` for stable promotion |
| `.github/workflows/auto-merge.yml` | Modify | Remove bump steps, switch to pre-release tagging |
| `.github/workflows/deploy-production.yml` | Modify | Extend skip filter for `chore: release v` |
| `.github/workflows/create-release.yml` | Modify | Recognize `-pre.` as prerelease |
| `.github/workflows/ci-check.yml` | Modify | Remove `changelog-guard` job |
| `.claude/commands/release/_release.md` | Modify | Simplify (drop label/CHANGELOG steps) |
| `.claude/commands/release/_release-stable.md` | Create | Trigger `release-stable.yml` via `gh workflow run` |
| `C:\Users\SvenB\.claude\projects\D--Programme--x86--Baluhost\memory\feedback_release_workflow.md` | Modify | Update memory entry |

**Phase 1 (Tasks 1-12):** Backend + frontend infrastructure. Ships via existing release flow (last `release:patch` PR under the old system).

**Phase 2 (Tasks 13-19):** Workflow switch — must be a single atomic PR.

**Phase 3 (Tasks 20-21):** Cleanup + memory update.

---

## Phase 1: Backend & Frontend Infrastructure

### Task 1: Add `--dry-run` flag to `bump_version.py`

**Files:**
- Modify: `scripts/bump_version.py`
- Create: `tests/scripts/__init__.py` (empty, may already exist)
- Create: `tests/scripts/test_bump_version.py`

**Context:** The new `release-stable.yml` workflow needs to compute the next version *before* committing, so it can generate the CHANGELOG section with the correct version heading. `--dry-run` outputs the computed new version on stdout without modifying any files.

- [ ] **Step 1: Create the test file with failing tests**

Path: `tests/scripts/test_bump_version.py`

```python
"""Tests for scripts/bump_version.py --dry-run flag."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "bump_version.py"


def _read_pyproject_version() -> str:
    text = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("version") and "=" in s:
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("version not found")


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
```

If `tests/scripts/__init__.py` does not exist yet, also create it (empty file).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/scripts/test_bump_version.py -v`
Expected: FAIL — current `bump_version.py` does not support `--dry-run`; it would treat it as an unknown argument and exit 1.

- [ ] **Step 3: Add `--dry-run` to `bump_version.py`**

Replace the body of `main()` in `scripts/bump_version.py` with:

```python
def main() -> None:
    args = sys.argv[1:]
    dry_run = False
    if "--dry-run" in args:
        dry_run = True
        args = [a for a in args if a != "--dry-run"]

    current = read_current_version()

    if not args:
        new_version = current
        if not dry_run:
            print(f"Syncing version {new_version} to all files...")
    else:
        arg = args[0]
        if arg in ("major", "minor", "patch"):
            new_version = bump(current, arg)
        elif re.match(r"^\d+\.\d+\.\d+", arg):
            new_version = arg
        else:
            print(f"Usage: {sys.argv[0]} [major|minor|patch|X.Y.Z] [--dry-run]")
            sys.exit(1)
        if not dry_run:
            print(f"Bumping version: {current} -> {new_version}")

    if dry_run:
        # Emit only the computed version; CI captures stdout
        print(new_version)
        return

    if args and args[0] in ("major", "minor", "patch"):
        update_pyproject(new_version)
    elif args:
        update_pyproject(new_version)

    update_package_json(new_version)
    update_claude_md(new_version)

    print("Updated files:")
    print(f"  backend/pyproject.toml  -> {new_version}")
    print(f"  client/package.json     -> {new_version}")
    print(f"  CLAUDE.md               -> {new_version}")
    print()
    print("Note: Run 'cd client && npm install' to sync package-lock.json")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scripts/test_bump_version.py -v`
Expected: PASS — all three tests green.

- [ ] **Step 5: Verify normal usage still works (regression)**

Run: `python scripts/bump_version.py patch --dry-run`
Expected: prints only the computed next version on the last line, no file modifications.

Run: `python scripts/bump_version.py` (no args, no `--dry-run`)
Expected: syncs current pyproject version to package.json and CLAUDE.md (existing behavior).

- [ ] **Step 6: Commit**

```bash
git add scripts/bump_version.py tests/scripts/__init__.py tests/scripts/test_bump_version.py
git commit -m "feat(scripts): add --dry-run flag to bump_version.py"
```

---

### Task 2: Create `generate_changelog_section.py`

**Files:**
- Create: `scripts/generate_changelog_section.py`
- Create: `tests/scripts/test_generate_changelog_section.py`

**Context:** Reads commits since a given ref via `git log <since>..HEAD --pretty=format:'%H%x1f%s%x1f%b%x1e' --no-merges` and produces a Keep-a-Changelog section grouped by Conventional-Commits type. Used by `release-stable.yml` and previewed by `_release-stable.md` slash command.

- [ ] **Step 1: Write failing tests**

Path: `tests/scripts/test_generate_changelog_section.py`

```python
"""Tests for scripts/generate_changelog_section.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
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
    # No bullet lines — only the heading + date + trailing separator
    assert "- " not in result.stdout


def test_non_conventional_commits_are_ignored():
    commits = "abc\x1fjust a plain commit message\x1f\x1e"
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    assert "- " not in result.stdout


def test_breaking_change_in_subject_creates_breaking_section():
    commits = "abc1234\x1ffeat!: rewrite auth flow\x1f\x1e"
    result = _run("--version", "2.0.0", "--date", "2026-05-06", "--stdin",
                  "--output", "-", input_text=commits)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "### ⚠ BREAKING CHANGES" in out  # ⚠ char
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
    assert "### ⚠ BREAKING CHANGES" in out
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
    assert "- " not in result.stdout


def test_writes_to_file_when_output_path_given(tmp_path):
    target = tmp_path / "section.md"
    commits = "abc\x1ffeat: x\x1f\x1e"
    result = _run("--version", "1.32.0", "--date", "2026-05-06", "--stdin",
                  "--output", str(target), input_text=commits)
    assert result.returncode == 0, result.stderr
    assert target.read_text(encoding="utf-8").startswith("## [1.32.0] - 2026-05-06")
    assert "- x" in target.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/scripts/test_generate_changelog_section.py -v`
Expected: FAIL — script does not exist.

- [ ] **Step 3: Implement the script**

Path: `scripts/generate_changelog_section.py`

```python
#!/usr/bin/env python3
"""Generate a Keep-a-Changelog section from Conventional Commits.

Usage:
    python scripts/generate_changelog_section.py \\
        --version 1.32.0 \\
        --since v1.31.0 \\
        --output CHANGELOG-section.md

Or with prepared input on stdin (used by tests):
    python scripts/generate_changelog_section.py \\
        --version 1.32.0 --date 2026-05-06 --stdin --output - < commits.txt

Stdin format (each commit terminated by 0x1e, fields separated by 0x1f):
    <sha>\\x1f<subject>\\x1f<body>\\x1e

Conventional Commits mapping:
    feat:      -> ### Added
    fix:       -> ### Fixed
    refactor:  -> ### Changed
    perf:      -> ### Changed
    docs:      -> ### Documentation
    feat!: / BREAKING CHANGE: in body -> ### ⚠ BREAKING CHANGES (top of section)
    chore:/ci:/test:/style:/build: -> ignored
    Anything without a recognised prefix -> ignored
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date as date_cls
from pathlib import Path

CC_PATTERN = re.compile(
    r"^(?P<type>feat|fix|refactor|perf|docs|chore|ci|test|style|build|revert)"
    r"(?P<bang>!?)"
    r"(?:\((?P<scope>[^)]+)\))?"
    r":\s*(?P<desc>.+)$"
)

GROUP_FOR_TYPE = {
    "feat": "Added",
    "fix": "Fixed",
    "refactor": "Changed",
    "perf": "Changed",
    "docs": "Documentation",
}

IGNORED_TYPES = {"chore", "ci", "test", "style", "build", "revert"}


def parse_commits_from_stdin() -> list[tuple[str, str, str]]:
    raw = sys.stdin.read()
    if not raw:
        return []
    out: list[tuple[str, str, str]] = []
    for entry in raw.split("\x1e"):
        if not entry.strip():
            continue
        parts = entry.split("\x1f")
        # Pad to (sha, subject, body)
        while len(parts) < 3:
            parts.append("")
        sha, subject, body = parts[0], parts[1], parts[2]
        out.append((sha.strip(), subject.strip(), body.strip()))
    return out


def parse_commits_from_git(since: str) -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["git", "log", f"{since}..HEAD",
         "--pretty=format:%H\x1f%s\x1f%b\x1e",
         "--no-merges"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(f"git log failed: {result.stderr}\n")
        sys.exit(2)
    raw = result.stdout
    if not raw.strip():
        return []
    out: list[tuple[str, str, str]] = []
    for entry in raw.split("\x1e"):
        if not entry.strip():
            continue
        parts = entry.split("\x1f")
        while len(parts) < 3:
            parts.append("")
        out.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))
    return out


def classify(subject: str, body: str) -> tuple[str | None, str, bool]:
    """Return (group, formatted_description, is_breaking).

    group is one of: "Added", "Fixed", "Changed", "Documentation", or None (ignore).
    Breaking commits are also returned with their normal group, plus is_breaking=True.
    """
    m = CC_PATTERN.match(subject)
    if not m:
        return (None, "", False)
    cc_type = m.group("type")
    bang = m.group("bang") == "!"
    scope = m.group("scope")
    desc = m.group("desc").strip()
    is_breaking = bang or "BREAKING CHANGE:" in body

    if cc_type in IGNORED_TYPES and not is_breaking:
        return (None, "", False)
    group = GROUP_FOR_TYPE.get(cc_type)
    if group is None and is_breaking:
        # A breaking chore/etc. still counts under BREAKING CHANGES
        group = None
    formatted = f"**({scope})** {desc}" if scope else desc
    return (group, formatted, is_breaking)


def render_section(version: str, date_iso: str,
                   commits: list[tuple[str, str, str]]) -> str:
    breaking: list[str] = []
    buckets: dict[str, list[str]] = {
        "Added": [],
        "Changed": [],
        "Fixed": [],
        "Documentation": [],
    }
    for _sha, subject, body in commits:
        group, desc, is_breaking = classify(subject, body)
        if is_breaking and desc:
            breaking.append(desc)
        if group is not None and desc:
            buckets[group].append(desc)

    lines: list[str] = [f"## [{version}] - {date_iso}", ""]
    if breaking:
        lines.append("### ⚠ BREAKING CHANGES")
        lines.append("")
        for item in breaking:
            lines.append(f"- {item}")
        lines.append("")
    for group in ("Added", "Changed", "Fixed", "Documentation"):
        items = buckets[group]
        if not items:
            continue
        lines.append(f"### {group}")
        lines.append("")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--since", help="Git ref. Required unless --stdin.")
    parser.add_argument("--stdin", action="store_true",
                        help="Read commits from stdin (test mode)")
    parser.add_argument("--output", required=True,
                        help="Output file path or '-' for stdout")
    args = parser.parse_args()

    if args.stdin:
        commits = parse_commits_from_stdin()
    else:
        if not args.since:
            sys.stderr.write("--since is required (unless --stdin)\n")
            return 2
        commits = parse_commits_from_git(args.since)

    section = render_section(args.version, args.date, commits)

    if args.output == "-":
        sys.stdout.write(section)
    else:
        Path(args.output).write_text(section, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scripts/test_generate_changelog_section.py -v`
Expected: PASS — all eight tests green.

- [ ] **Step 5: Smoke-test against real git history**

Run: `python scripts/generate_changelog_section.py --version 1.32.0 --since 0e6c6ab --output -`
Expected: prints a section with `## [1.32.0] - <today>` heading and (likely empty) buckets since 0e6c6ab is the latest commit at plan-write time.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_changelog_section.py tests/scripts/test_generate_changelog_section.py
git commit -m "feat(scripts): add generate_changelog_section.py"
```

---

### Task 3: Create `insert_changelog_section.py`

**Files:**
- Create: `scripts/insert_changelog_section.py`
- Create: `tests/scripts/test_insert_changelog_section.py`

**Context:** Reads a section from `--section` and prepends it to `--target` (CHANGELOG.md) directly after the H1 heading (`# Changelog`), preserving the existing `---` separator style.

- [ ] **Step 1: Write failing tests**

Path: `tests/scripts/test_insert_changelog_section.py`

```python
"""Tests for scripts/insert_changelog_section.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "insert_changelog_section.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/scripts/test_insert_changelog_section.py -v`
Expected: FAIL — script does not exist.

- [ ] **Step 3: Implement the script**

Path: `scripts/insert_changelog_section.py`

```python
#!/usr/bin/env python3
"""Insert a new CHANGELOG section after the H1 heading.

Usage:
    python scripts/insert_changelog_section.py \\
        --section /tmp/changelog-section.md \\
        --target CHANGELOG.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

H1_PATTERN = re.compile(r"^# Changelog\s*$", re.MULTILINE)
# Find the first '---\n' separator after the H1 heading
SEPARATOR_AFTER_H1 = re.compile(r"^---\s*$", re.MULTILINE)


def insert(target: Path, section_text: str) -> None:
    text = target.read_text(encoding="utf-8")

    h1_match = H1_PATTERN.search(text)
    if not h1_match:
        sys.stderr.write(
            f"Target {target} does not contain '# Changelog' heading\n"
        )
        sys.exit(2)

    # Find the first --- separator after the H1
    sep_match = SEPARATOR_AFTER_H1.search(text, pos=h1_match.end())
    if sep_match:
        # Insert directly after the separator, with one blank line before the new section
        insert_at = sep_match.end()
        before = text[:insert_at]
        after = text[insert_at:]
        if not after.startswith("\n\n"):
            # Normalise so we always have exactly one blank line separator
            sep_break = "\n\n"
            after = after.lstrip("\n")
            after = sep_break + after
        new_text = before + "\n\n" + section_text.rstrip() + "\n" + after
    else:
        # No separator after H1 — insert directly after the H1 line
        insert_at = h1_match.end()
        before = text[:insert_at]
        after = text[insert_at:]
        new_text = before + "\n\n" + section_text.rstrip() + "\n" + after

    target.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    section_text = args.section.read_text(encoding="utf-8")
    insert(args.target, section_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scripts/test_insert_changelog_section.py -v`
Expected: PASS — all three tests green.

- [ ] **Step 5: Commit**

```bash
git add scripts/insert_changelog_section.py tests/scripts/test_insert_changelog_section.py
git commit -m "feat(scripts): add insert_changelog_section.py"
```

---

### Task 4: Add `is_prerelease` field to `VersionInfo` schema

**Files:**
- Modify: `backend/app/schemas/update.py`

**Context:** Pydantic schema field. Defaults to `False` so existing producers don't break before backends are updated.

- [ ] **Step 1: Find the existing `VersionInfo` definition**

Run: `python -c "from app.schemas.update import VersionInfo; import json; print(json.dumps(VersionInfo.model_json_schema(), indent=2))"` from `backend/`.

Expected: Schema includes `version`, `commit`, `commit_short`, `tag`, `date`, `is_dev_build`. No `is_prerelease` yet.

- [ ] **Step 2: Add the field**

In `backend/app/schemas/update.py`, locate the `VersionInfo` class (search for `class VersionInfo`). Add `is_prerelease: bool = False` directly after the existing `is_dev_build` field. Keep ordering consistent so schema export stays stable.

Final structure should look like:

```python
class VersionInfo(BaseModel):
    version: str
    commit: str
    commit_short: str
    tag: Optional[str] = None
    date: Optional[datetime] = None
    is_dev_build: bool = False
    is_prerelease: bool = False
```

(Existing fields may differ slightly — preserve them; only add `is_prerelease`.)

- [ ] **Step 3: Verify schema export**

Run from `backend/`:
```bash
python -c "from app.schemas.update import VersionInfo; v = VersionInfo(version='1.0.0', commit='abc', commit_short='abc', is_dev_build=False); print(v.is_prerelease)"
```
Expected: `False`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/update.py
git commit -m "feat(schemas): add is_prerelease to VersionInfo"
```

---

### Task 5: Update `ProdUpdateBackend.get_current_version()` for tag-based detection

**Files:**
- Modify: `backend/app/services/update/prod_backend.py`
- Modify: `backend/tests/services/test_update_service.py`

**Context:** The current implementation reads version from `pyproject.toml` and only detects "exact tag" as a boolean (`is_dev_build`). With pre-release tags pushed on every merge, HEAD will normally be exactly on a tag — we want the displayed `version` and `tag` to reflect the actual tag (including the `-pre.N` suffix), and a new `is_prerelease` flag to be derived from the tag name.

- [ ] **Step 1: Write failing tests**

In `backend/tests/services/test_update_service.py`, add a new test class. Find a good insertion point near the existing version-related tests (search for `class TestVersionParsing` or similar). If unsure, append at the end of the file.

```python
class TestProdBackendGetCurrentVersion:
    """Tests for tag-based version detection in ProdUpdateBackend.get_current_version."""

    @pytest.fixture
    def backend(self):
        from app.services.update.prod_backend import ProdUpdateBackend
        return ProdUpdateBackend()

    @pytest.mark.asyncio
    async def test_head_on_prerelease_tag_uses_tag_as_version(self, backend):
        """When HEAD is on a pre-release tag, version reflects the full tag name."""
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return True, "v1.31.7-pre.42", ""
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "abc1234567890abcdef1234567890abcdef12345678", ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", "unexpected"

        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        assert info.version == "1.31.7-pre.42"
        assert info.tag == "v1.31.7-pre.42"
        assert info.is_prerelease is True
        assert info.is_dev_build is False
        assert info.commit_short == "abc1234"

    @pytest.mark.asyncio
    async def test_head_on_stable_tag_marks_not_prerelease(self, backend):
        """Stable tags have no -pre/-rc suffix and is_prerelease must be False."""
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return True, "v1.32.0", ""
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", "unexpected"

        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        assert info.version == "1.32.0"
        assert info.tag == "v1.32.0"
        assert info.is_prerelease is False
        assert info.is_dev_build is False

    @pytest.mark.asyncio
    async def test_head_between_tags_falls_back_to_pyproject(self, backend):
        """When HEAD is not on a tag (local dev), falls back to pyproject + is_dev_build=True."""
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return False, "", "fatal: no exact match"
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "feedfacefeedfacefeedfacefeedfacefeedface", ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", "unexpected"

        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        # version comes from pyproject.toml (whatever the test repo has)
        assert info.is_prerelease is False
        assert info.is_dev_build is True
        assert info.tag is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tag,expected", [
        ("v1.0.0-pre.1", True),
        ("v1.0.0-rc.1", True),
        ("v1.0.0-alpha", True),
        ("v1.0.0-beta", True),
        ("v1.0.0-unstable", True),
        ("v1.0.0", False),
        ("v2.5.10", False),
    ])
    async def test_prerelease_detection_by_tag_suffix(self, backend, tag, expected):
        def fake_run_git(*args):
            cmd = args
            if cmd[:3] == ("describe", "--tags", "--exact-match"):
                return True, tag, ""
            if cmd[:2] == ("rev-parse", "HEAD"):
                return True, "0" * 40, ""
            if cmd[:3] == ("log", "-1", "--format=%cI"):
                return True, "2026-05-06T10:00:00+00:00", ""
            return False, "", ""
        backend._run_git = fake_run_git
        info = await backend.get_current_version()
        assert info.is_prerelease is expected
```

(If `pytest` and `pytest_asyncio` are not already imported at the top of the file, ensure they are — most test files in this repo already use `import pytest` and the `asyncio_mode = "auto"` from `pyproject.toml`.)

- [ ] **Step 2: Run tests to verify they fail**

Run from `backend/`:
```bash
python -m pytest tests/services/test_update_service.py::TestProdBackendGetCurrentVersion -v
```
Expected: FAIL — current implementation always reads from pyproject and never sets `is_prerelease`.

- [ ] **Step 3: Update `ProdUpdateBackend.get_current_version()`**

In `backend/app/services/update/prod_backend.py`, replace the body of `get_current_version` with:

```python
    async def get_current_version(self) -> VersionInfo:
        """Get current version from git tag (preferred) or pyproject.toml (fallback)."""
        # Try exact tag match first — succeeds for pre-release and stable tags
        exact_ok, exact_tag, _ = self._run_git("describe", "--tags", "--exact-match")
        if exact_ok and exact_tag.strip():
            tag_name = exact_tag.strip()
            version = tag_name.lstrip("v")
            is_prerelease = any(
                marker in tag_name for marker in ("-pre.", "-rc.", "-alpha", "-beta", "-unstable")
            )
            is_dev_build = False
            tag = tag_name
        else:
            # Local build between tags — fall back to pyproject.toml
            version = version_to_string(get_installed_version())
            tag = None
            is_prerelease = False
            is_dev_build = True

        # Commit metadata
        success, commit, _ = self._run_git("rev-parse", "HEAD")
        if not success:
            commit = "unknown"

        success, date_str, _ = self._run_git("log", "-1", "--format=%cI")
        date = datetime.fromisoformat(date_str) if success and date_str else None

        return VersionInfo(
            version=version,
            commit=commit,
            commit_short=commit[:7] if commit != "unknown" else "unknown",
            tag=tag,
            date=date,
            is_dev_build=is_dev_build,
            is_prerelease=is_prerelease,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_update_service.py::TestProdBackendGetCurrentVersion -v`
Expected: PASS — all parameterised cases green.

- [ ] **Step 5: Run the full update-service test class to catch regressions**

Run: `python -m pytest tests/services/test_update_service.py -v`
Expected: PASS — no existing tests broken.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/update/prod_backend.py backend/tests/services/test_update_service.py
git commit -m "feat(updates): tag-based version detection with is_prerelease"
```

---

### Task 6: Update `DevUpdateBackend.get_current_version()`

**Files:**
- Modify: `backend/app/services/update/dev_backend.py`

**Context:** Dev backend is purely simulated. Set `is_prerelease=False` for the mocked stable version so dev-mode UI behaves like production-stable.

- [ ] **Step 1: Modify the dev backend**

In `backend/app/services/update/dev_backend.py`, find `get_current_version()` (around line 46-54). Update the `VersionInfo` constructor call to include `is_prerelease=False`:

```python
    async def get_current_version(self) -> VersionInfo:
        return VersionInfo(
            version=version_to_string(self._simulated_version),
            commit=self._current_commit,
            commit_short=self._current_commit[:7],
            tag=f"v{version_to_string(self._simulated_version)}",
            date=datetime.now(timezone.utc),
            is_dev_build=True,
            is_prerelease=False,
        )
```

- [ ] **Step 2: Smoke-test in dev mode**

Run: `cd backend && NAS_MODE=dev python -c "import asyncio; from app.services.update.dev_backend import DevUpdateBackend; b = DevUpdateBackend(); v = asyncio.run(b.get_current_version()); print(v.version, v.is_prerelease)"`
Expected: prints version like `1.0.0 False`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/update/dev_backend.py
git commit -m "feat(updates): set is_prerelease=False on dev backend"
```

---

### Task 7: Add `is_prerelease` to TypeScript `VersionInfo` interface

**Files:**
- Modify: `client/src/api/updates.ts`

**Context:** Mirror the backend schema change.

- [ ] **Step 1: Locate the interface**

Open `client/src/api/updates.ts` and find `interface VersionInfo` (it lives near the top of the file alongside other API types).

- [ ] **Step 2: Add the field**

Add `is_prerelease: boolean;` after `is_dev_build`:

```typescript
export interface VersionInfo {
  version: string;
  commit: string;
  commit_short: string;
  tag: string | null;
  date: string | null;
  is_dev_build: boolean;
  is_prerelease: boolean;
}
```

(Preserve other existing fields exactly as they are.)

- [ ] **Step 3: Type-check**

Run from `client/`: `npx tsc --noEmit`
Expected: PASS — no new type errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/api/updates.ts
git commit -m "feat(api): add is_prerelease to VersionInfo TS interface"
```

---

### Task 8: Add `useVersionDisplay()` hook to `VersionContext`

**Files:**
- Modify: `client/src/contexts/VersionContext.tsx`

**Context:** Existing `useFormattedVersion()` returns just a string. The new hook returns both the formatted string and `isPrerelease` so consumers can render an optional badge alongside the version text.

- [ ] **Step 1: Add the new hook**

In `client/src/contexts/VersionContext.tsx`, append after the existing `useFormattedVersion` definition:

```typescript
/**
 * Hook to get formatted version string + is_prerelease flag for badge display.
 * Returns "v..." while loading, "v?.?.?" on error.
 */
export function useVersionDisplay(prefix: string = 'BaluHost OS'): {
  text: string;
  isPrerelease: boolean;
} {
  const { fullVersion, loading, error } = useVersion();

  if (loading) {
    return { text: `${prefix} v...`, isPrerelease: false };
  }

  if (error || !fullVersion) {
    return { text: `${prefix} v?.?.?`, isPrerelease: false };
  }

  return {
    text: `${prefix} v${fullVersion.version}`,
    isPrerelease: fullVersion.is_prerelease,
  };
}
```

- [ ] **Step 2: Type-check**

Run from `client/`: `npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add client/src/contexts/VersionContext.tsx
git commit -m "feat(version): add useVersionDisplay hook with isPrerelease"
```

---

### Task 9: Add `preRelease.badge` i18n keys

**Files:**
- Modify: `client/src/i18n/locales/en/updates.json`
- Modify: `client/src/i18n/locales/de/updates.json`

**Context:** Existing `updates` namespace has a top-level structure with sub-objects. Add a new top-level key `preRelease`.

- [ ] **Step 1: Update English translations**

In `client/src/i18n/locales/en/updates.json`, add the following at the same level as existing top-level keys (e.g., right before `"version": { ... }`):

```json
  "preRelease": {
    "badge": "Pre-Release"
  },
```

(Make sure to add the trailing comma if a sibling key follows; remove any trailing comma if it sits at the end of the object.)

- [ ] **Step 2: Update German translations**

In `client/src/i18n/locales/de/updates.json`, add:

```json
  "preRelease": {
    "badge": "Pre-Release"
  },
```

- [ ] **Step 3: Verify JSON validity**

Run from `client/`:
```bash
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/updates.json','utf8'))"
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/updates.json','utf8'))"
```
Expected: no output (= valid JSON).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/en/updates.json client/src/i18n/locales/de/updates.json
git commit -m "feat(i18n): add updates.preRelease.badge keys (en/de)"
```

---

### Task 10: Render Pre-Release badge in `UpdateOverviewTab`

**Files:**
- Modify: `client/src/components/updates/UpdateOverviewTab.tsx`

**Context:** This is the primary version-display surface (currently uses the `version.current` strings — see `client/src/i18n/locales/en/updates.json:23`). Identify the existing version render and add the badge next to it.

- [ ] **Step 1: Open the file and locate the version rendering**

Open `client/src/components/updates/UpdateOverviewTab.tsx` and find where the current version is shown. Search for either `useVersion` or `currentVersion` or `version.current` (i18n key reference). The component already consumes `VersionContext` — check whether it uses `useVersion()` or `useFormattedVersion()`.

- [ ] **Step 2: Replace `useVersion()`/`useFormattedVersion()` with `useVersionDisplay()` if the version is rendered as plain text**

Adjust the import:
```typescript
import { useVersionDisplay } from '../../contexts/VersionContext';
```

In the component body, replace existing version-text logic with:
```typescript
const { text: versionText, isPrerelease } = useVersionDisplay('BaluHost OS');
```
(Or use the prefix already in the i18n string — pass an empty prefix if the heading already says "Current Version".)

If the component uses `fullVersion.version` directly (e.g., showing `1.31.7` without the "BaluHost OS v" prefix), keep that pattern but additionally read `fullVersion.is_prerelease`:
```typescript
const { fullVersion } = useVersion();
const isPrerelease = fullVersion?.is_prerelease ?? false;
```

- [ ] **Step 3: Render the badge next to the version text**

Add the badge JSX directly after the version text element. The exact wrapper depends on the existing layout (likely an inline-flex container). Pattern:

```tsx
<div className="flex items-center gap-2">
  <span className="text-2xl font-semibold text-slate-100">{versionText}</span>
  {isPrerelease && (
    <span className="inline-flex items-center rounded-md bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-300">
      {t('preRelease.badge')}
    </span>
  )}
</div>
```

If the component already uses `useTranslation('updates')` the `t('preRelease.badge')` works directly. Otherwise, ensure the namespace is loaded — search for existing `useTranslation('updates')` usage in the same file and follow that pattern.

- [ ] **Step 4: Verify in dev mode**

Run: `python start_dev.py`
- Open `http://localhost:5173/updates` (or wherever the Updates page is routed).
- Expected: version is shown without a badge (dev mode sets `is_prerelease=false`).

For a manual production-style verification: temporarily edit `dev_backend.py` to return `is_prerelease=True` and reload the page. Expected: amber "Pre-Release" badge appears next to the version. Revert the temporary edit before committing.

- [ ] **Step 5: Type-check + build**

Run from `client/`:
```bash
npx tsc --noEmit
npm run build
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/components/updates/UpdateOverviewTab.tsx
git commit -m "feat(updates): render Pre-Release badge in UpdateOverviewTab"
```

---

### Task 11: Verify other version consumers don't need updates

**Files:**
- Read-only inspection of: `client/src/pages/Login.tsx`, `client/src/components/Layout.tsx` (if it shows version), and any sidebar/footer.

**Context:** The badge only matters in places where users care about whether they're on a Pre-Release. Other places (Login footer, etc.) can keep showing just the version text. This task is to **decide intentionally**, not to add badges everywhere.

- [ ] **Step 1: Find all consumers of version data**

Run (from repo root): `python -c "import subprocess; subprocess.run(['git', 'grep', '-n', '-E', 'useFormattedVersion|useVersion\\(|useVersionDisplay|fullVersion|is_dev_build|is_prerelease', 'client/src'])"`

Note each occurrence in a scratch file. Expected hits: `VersionContext.tsx` (definitions), `Login.tsx` (line 14), `UpdateOverviewTab.tsx` (just modified), possibly `Layout.tsx` or similar.

- [ ] **Step 2: Decide per consumer**

For each non-Updates consumer:
- **Login.tsx**: Only shows version on the login page footer. Decision: do not add badge — login page doesn't need to advertise pre-release status. No changes needed.
- **Layout.tsx / Footer / Sidebar (if present)**: If shows version, add the badge using `useVersionDisplay()` to be consistent with the Updates page.

If no other prominent consumer requires the badge, this task is complete with no code changes.

- [ ] **Step 3: Commit (only if changes were made)**

If you modified additional files:
```bash
git add <files>
git commit -m "feat(version): show Pre-Release badge in <component>"
```
Otherwise: no commit needed.

---

### Task 12: Phase 1 final verification

**Files:** N/A (verification only)

- [ ] **Step 1: Run all backend tests**

Run from `backend/`: `python -m pytest -q`
Expected: PASS — full suite green.

- [ ] **Step 2: Run all frontend tests**

Run from `client/`:
```bash
npx vitest run
```
Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run from `client/`: `npm run build`
Expected: PASS, `dist/` produced.

- [ ] **Step 4: Smoke-test the full app in dev mode**

Run: `python start_dev.py`
- Login as admin/DevMode2024
- Navigate to Updates page
- Verify version is displayed (no badge in dev mode is correct)
- Stop with Ctrl+C

- [ ] **Step 5: No commit needed** — Phase 1 ends. The changes can be merged via the existing release flow as a `release:patch` or `release:minor` PR.

---

## Phase 2: Workflow Switch (Atomic)

**IMPORTANT:** All tasks in Phase 2 must land in **one** PR. A partial state (e.g., new auto-merge.yml without updated skip-filter) would cause redundant deploys or broken tagging.

### Task 13: Create `release-stable.yml` workflow

**Files:**
- Create: `.github/workflows/release-stable.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: Release Stable

on:
  workflow_dispatch:
    inputs:
      bump_type:
        description: "Semver bump for the new stable release"
        type: choice
        required: true
        options: [patch, minor, major]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.DEPLOY_PAT }}

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      - name: Compute next version
        id: version
        env:
          BUMP_TYPE: ${{ inputs.bump_type }}
        run: |
          CURRENT=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
          NEW=$(python scripts/bump_version.py "$BUMP_TYPE" --dry-run | tail -1)
          echo "current=$CURRENT" >> "$GITHUB_OUTPUT"
          echo "new=$NEW" >> "$GITHUB_OUTPUT"
          echo "Bumping $CURRENT -> $NEW"

      - name: Find last stable tag
        id: last_stable
        run: |
          LAST=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1 || true)
          if [ -z "$LAST" ]; then
            echo "No previous stable tag found; using initial commit"
            LAST=$(git rev-list --max-parents=0 HEAD)
          fi
          echo "ref=$LAST" >> "$GITHUB_OUTPUT"
          echo "Last stable: $LAST"

      - name: Generate CHANGELOG section
        env:
          NEW_VERSION: ${{ steps.version.outputs.new }}
          LAST_REF: ${{ steps.last_stable.outputs.ref }}
        run: |
          python scripts/generate_changelog_section.py \
            --version "$NEW_VERSION" \
            --since "$LAST_REF" \
            --output /tmp/changelog-section.md
          echo "--- Generated section ---"
          cat /tmp/changelog-section.md
          echo "--- End ---"
          if ! grep -q '^- ' /tmp/changelog-section.md; then
            echo "::error::No conventional-commit changes since $LAST_REF -- refusing to create empty release"
            exit 1
          fi

      - name: Insert CHANGELOG section
        run: |
          python scripts/insert_changelog_section.py \
            --section /tmp/changelog-section.md \
            --target CHANGELOG.md

      - name: Bump version files
        env:
          BUMP_TYPE: ${{ inputs.bump_type }}
        run: python scripts/bump_version.py "$BUMP_TYPE"

      - name: Commit + push version bump
        env:
          NEW_VERSION: ${{ steps.version.outputs.new }}
        run: |
          git add backend/pyproject.toml client/package.json CLAUDE.md CHANGELOG.md
          git commit -m "chore: release v${NEW_VERSION}"
          git push origin main

      - name: Tag + push
        env:
          NEW_VERSION: ${{ steps.version.outputs.new }}
        run: |
          TAG="v${NEW_VERSION}"
          git tag -a "$TAG" -m "Release $TAG"
          git push origin "$TAG"
          echo "Stable release tag $TAG pushed -- create-release.yml will create the GitHub Release"
```

- [ ] **Step 2: YAML lint**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release-stable.yml'))"`
Expected: no output (valid YAML).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-stable.yml
git commit -m "feat(ci): add release-stable.yml for manual stable promotion"
```

---

### Task 14: Modify `auto-merge.yml` to push pre-release tags

**Files:**
- Modify: `.github/workflows/auto-merge.yml`

- [ ] **Step 1: Replace the bump + tag logic**

Open `.github/workflows/auto-merge.yml`. The current jobs we change:

**(a)** Remove the entire `Read release label before merging` block? — NO. The merge step itself stays. But the `RELEASE_LABEL` env propagation can be removed since we no longer use it. Specifically:

In the `Find and merge PR` step, remove these three lines (currently around lines 36-38):
```bash
RELEASE_LABEL=$(gh pr view "$PR_NUMBER" --repo "$REPO" --json labels --jq '[.labels[].name | select(startswith("release:"))] | first // empty')
echo "RELEASE_LABEL=$RELEASE_LABEL" >> "$GITHUB_ENV"
echo "PR_NUMBER=$PR_NUMBER" >> "$GITHUB_ENV"
```

**(b)** Delete the entire `Bump version from release label` step (currently at lines 57-75 — the step with `if: env.RELEASE_LABEL != ''`).

**(c)** Replace the `Auto-tag from pyproject.toml` step (currently at lines 77-91) with the new pre-release-tag logic:

```yaml
      - name: Auto-tag pre-release
        working-directory: /tmp/repo
        env:
          RUN_NUMBER: ${{ github.event.workflow_run.run_number }}
        run: |
          VERSION=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml || true)
          if [ -z "$VERSION" ]; then
            echo "Could not read version from pyproject.toml -- skipping pre-release tag"
            exit 0
          fi
          TAG="v${VERSION}-pre.${RUN_NUMBER}"
          if git tag -l "$TAG" | grep -q .; then
            echo "Tag $TAG already exists -- skipping"
          else
            echo "Creating pre-release tag $TAG"
            git tag -a "$TAG" -m "Pre-release $TAG"
            git push origin "$TAG"
            echo "Tag $TAG pushed -- create-release.yml will create the GitHub pre-release"
          fi
```

**(d)** Keep the final `Sync development with main` step exactly as it is.

- [ ] **Step 2: YAML lint**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/auto-merge.yml'))"`
Expected: valid YAML.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/auto-merge.yml
git commit -m "feat(ci): switch auto-merge to pre-release tags"
```

---

### Task 15: Extend skip filter in `deploy-production.yml`

**Files:**
- Modify: `.github/workflows/deploy-production.yml`

- [ ] **Step 1: Update the skip condition**

In `.github/workflows/deploy-production.yml`, locate the `deploy` job's `if:` condition. Currently:

```yaml
    if: "!startsWith(github.event.head_commit.message, 'chore: bump version')"
```

Replace with:

```yaml
    if: "!startsWith(github.event.head_commit.message, 'chore: bump version') && !startsWith(github.event.head_commit.message, 'chore: release v')"
```

- [ ] **Step 2: YAML lint**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-production.yml'))"`
Expected: valid YAML.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-production.yml
git commit -m "ci(deploy): skip redundant deploy on stable release commits"
```

---

### Task 16: Recognize `-pre.` as prerelease in `create-release.yml`

**Files:**
- Modify: `.github/workflows/create-release.yml`

- [ ] **Step 1: Update the prerelease detection**

In `.github/workflows/create-release.yml`, find the `Determine pre-release` step (around lines 39-48). Replace its `run:` block with:

```bash
          if [[ "$TAG" == *-pre.* ]] || [[ "$TAG" == *-alpha* ]] || [[ "$TAG" == *-beta* ]] || [[ "$TAG" == *-unstable* ]] || [[ "$TAG" == *-rc* ]]; then
            echo "flag=--prerelease" >> "$GITHUB_OUTPUT"
          else
            echo "flag=" >> "$GITHUB_OUTPUT"
          fi
```

(The only addition is the first `[[ "$TAG" == *-pre.* ]]` clause.)

- [ ] **Step 2: YAML lint**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/create-release.yml'))"`
Expected: valid YAML.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/create-release.yml
git commit -m "ci(release): recognize -pre. tag suffix as prerelease"
```

---

### Task 17: Remove `changelog-guard` job from `ci-check.yml`

**Files:**
- Modify: `.github/workflows/ci-check.yml`

- [ ] **Step 1: Delete the job**

In `.github/workflows/ci-check.yml`, delete the entire `changelog-guard` job (lines 57-100 in the current version). The remaining jobs are `backend-tests` and `frontend-build`.

After deletion, the file ends after the `frontend-build` job's last step.

- [ ] **Step 2: YAML lint**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci-check.yml'))"`
Expected: valid YAML.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci-check.yml
git commit -m "ci(check): remove changelog-guard job (no longer needed)"
```

---

### Task 18: Simplify `_release.md` slash command

**Files:**
- Modify: `.claude/commands/release/_release.md`

- [ ] **Step 1: Replace the file contents**

Path: `.claude/commands/release/_release.md`

Replace the entire content with:

```markdown
# Release-PR: development → main

Erstelle einen PR von `development` nach `main`. Jeder Merge erzeugt automatisch ein Pre-Release-Tag und deployt auf Production. Stable-Releases werden separat über `/release-stable` getriggert.

## Workflow

### 1. Branch-Check

Verifiziere `development`-Branch:
```bash
git branch --show-current
```
Falls nicht `development`: abbrechen mit Hinweis.

### 2. Commits seit letztem Stable anzeigen

```bash
LAST_STABLE=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
echo "Last stable: $LAST_STABLE"
git log "$LAST_STABLE"..HEAD --oneline
```

### 3. PR erstellen

**FRAGE DEN BENUTZER:** PR jetzt erstellen?

```bash
gh pr create \
  --base main \
  --head development \
  --title "<auto-generated from commit subjects>" \
  --body "$(cat <<'EOF'
## Changes

<list of commit subjects>

---
This PR will trigger a Pre-Release tag (`v<current>-pre.<N>`) and a Production-Deploy after merge.
For a Stable release, run `/release-stable` separately after the desired Pre-Release has run on production.
EOF
)"
```

**ZEIGE DEM BENUTZER** den PR-Link.

> **Was nach Merge automatisch passiert:**
> 1. CI Check läuft (Backend-Tests + Frontend-Build)
> 2. Auto-Merge merged den PR
> 3. Pre-Release-Tag `v<current>-pre.<run_number>` wird erstellt
> 4. Push auf main triggert deploy-production.yml → NAS deployt
> 5. Tag-Push triggert create-release.yml → GitHub Pre-Release
> 6. Development wird mit main synchronisiert (FF only)

## Regeln

- **NIEMALS** lokal auf main mergen — immer über PR
- **NIEMALS** lokal die Version bumpen — passiert nur beim Stable-Trigger
- **NIEMALS** Tags manuell pushen
- **NIEMALS** ohne Bestätigung des Benutzers committen oder pushen
- Bei bereits existierendem PR: Benutzer informieren und fragen ob Update gewünscht
- Commit-Message endet mit: `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/release/_release.md
git commit -m "docs(commands): simplify release PR slash command"
```

---

### Task 19: Create `_release-stable.md` slash command

**Files:**
- Create: `.claude/commands/release/_release-stable.md`

- [ ] **Step 1: Create the file**

Path: `.claude/commands/release/_release-stable.md`

```markdown
# Release Stable

Triggert den `release-stable.yml` Workflow auf GitHub. Promotet HEAD von `main` zu einem stabilen Release: Bump + CHANGELOG-Sektion + Stable-Tag + GitHub-Release als „Latest".

## Voraussetzung

- HEAD von `main` läuft auf der Production-NAS (Pre-Release wurde getestet)
- `gh` CLI ist authentifiziert

## Workflow

### 1. Bump-Type vorschlagen

Analysiere Commits seit letztem Stable-Tag:
```bash
LAST_STABLE=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
git fetch origin main
git log "$LAST_STABLE"..origin/main --pretty=format:'%s'
```

**Vorschlag basierend auf Commits:**
- Mindestens ein `feat!:` oder `BREAKING CHANGE:` im Body → `major`
- Mindestens ein `feat:` → `minor`
- Sonst → `patch`

**FRAGE DEN BENUTZER:** Welcher Bump-Type? (Vorschlag anzeigen)

### 2. CHANGELOG-Vorschau lokal generieren

```bash
NEW_VERSION=$(python scripts/bump_version.py <bump_type> --dry-run | tail -1)
python scripts/generate_changelog_section.py \
  --version "$NEW_VERSION" \
  --since "$LAST_STABLE" \
  --output -
```

(Nur Vorschau — der echte CHANGELOG wird im Workflow geschrieben.)

**FRAGE DEN BENUTZER:** Sieht die Sektion korrekt aus?

### 3. Workflow triggern

**FRAGE DEN BENUTZER:** Trigger ausführen?

```bash
gh workflow run release-stable.yml --ref main -f bump_type=<type>
```

### 4. Status-Link

```bash
sleep 3
gh run list --workflow=release-stable.yml --limit 1
```

Zeige dem Benutzer Run-URL.

## Regeln

- Workflow läuft auf `main`, nicht `development`
- NIEMALS lokal `pyproject.toml` / `package.json` / `CLAUDE.md` bumpen
- NIEMALS lokal Stable-Tags erstellen oder pushen
- NIEMALS in `CHANGELOG.md` lokal eine neue Sektion hinzufügen — der Workflow macht das
- Bei Workflow-Fehler: Run-Logs anzeigen und Benutzer informieren
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/release/_release-stable.md
git commit -m "docs(commands): add release-stable slash command"
```

---

## Phase 3: Cleanup

### Task 20: Update memory entry for new release workflow

**Files:**
- Modify: `C:\Users\SvenB\.claude\projects\D--Programme--x86--Baluhost\memory\feedback_release_workflow.md`

**Context:** The existing memory says "Tags are handled by the create-release workflow" — still true, but now the tag created on PR-merge is a Pre-Release tag, not a Stable tag. The memory should reflect the new two-step flow.

- [ ] **Step 1: Replace the file contents**

```markdown
---
name: release-workflow
description: Release workflow - PR creates Pre-Release, manual workflow_dispatch creates Stable
type: feedback
---

Don't merge development into main locally. PR development → main creates a **Pre-Release tag** (`v<current>-pre.<run_number>`) automatically and deploys to production. Stable releases are NEVER created by PR merges.

To create a Stable release, run the `release-stable.yml` workflow manually (GH UI or `/release-stable`). It bumps `pyproject.toml` / `package.json` / `CLAUDE.md`, generates a CHANGELOG section from Conventional Commits, tags HEAD as `vX.Y.Z` (no suffix), and creates a GitHub Release marked as "Latest".

**Why:** PR merges are not always stable enough to be the "Latest" version on the STABLE update channel. The two-step flow lets the production NAS run a Pre-Release first, then promote to Stable only when proven good.

**How to apply:** During release work:
- For a PR onto main: just push to development and `gh pr create --base main --head development` (no `release:*` label needed — those are obsolete).
- To promote to Stable: run `gh workflow run release-stable.yml --ref main -f bump_type=patch|minor|major` or use `/release-stable`.
- Do not `git checkout main && git merge`. Do not `git tag` or bump versions locally.
```

- [ ] **Step 2: No commit needed** — memory files are local to your machine and not in the repo.

---

### Task 21: Final E2E verification on next release cycle

**Files:** N/A (verification only — to be run after Phase 2 PR is merged into main)

**Context:** The first PR-merge after Phase 2 lands proves the new flow works. This task documents the verification checklist; do NOT execute as part of the implementation PR — execute it after the PR is merged.

- [ ] **Step 1: After Phase 2 merge — verify Pre-Release flow**

After the Phase 2 PR is merged to main:
- Verify a new tag `v<current>-pre.<run_number>` was pushed: `git fetch --tags && git tag -l | tail`
- Verify a GitHub Release marked as "Pre-Release" exists for that tag (in the GitHub UI)
- Verify Production-Deploy ran (`sudo journalctl -u baluhost-backend -n 100`)
- Verify `pyproject.toml`/`package.json`/`CLAUDE.md` are unchanged (`git diff <previous_main>..main -- backend/pyproject.toml client/package.json CLAUDE.md` should show only the changes from the Phase 2 PR itself, no version bumps)
- Verify BaluHost UI shows the pre-release version + Pre-Release badge

- [ ] **Step 2: Verify Stable flow (when ready)**

When the next Stable release is desired:
- Run `gh workflow run release-stable.yml --ref main -f bump_type=patch` (or appropriate type)
- Watch the run: `gh run watch`
- Verify a new commit `chore: release vX.Y.Z` exists on main
- Verify Production-Deploy was **skipped** (skip filter caught the commit) — check Actions UI
- Verify a new tag `vX.Y.Z` (no suffix) exists
- Verify a GitHub Release marked as "Latest" exists for that tag
- Verify CHANGELOG.md has a new section at the top
- Verify BaluHost UI shows the new stable version, no badge

- [ ] **Step 3: Verify edge case — empty stable trigger**

Immediately after creating a stable release, run the workflow again with the same `bump_type`:
- Expected: workflow fails with `::error::No conventional-commit changes since v<previous_stable>`

- [ ] **Step 4: Document any issues for follow-up**

If any verification step fails, capture logs in a new GitHub issue tagged `release-workflow`.

---

## Self-Review Notes

**Spec coverage check:** All sections of the spec are implemented:
- Pre-release tagging in auto-merge.yml — Task 14
- Skip-filter — Task 15
- create-release.yml suffix detection — Task 16
- ci-check.yml changelog-guard removal — Task 17
- Backend version endpoint — Tasks 4, 5, 6
- Frontend pre-release badge — Tasks 7, 8, 9, 10, 11
- Slash commands — Tasks 18, 19
- bump_version.py --dry-run — Task 1
- generate_changelog_section.py — Task 2
- insert_changelog_section.py — Task 3
- release-stable.yml — Task 13
- Memory + final verification — Tasks 20, 21

**Type consistency check:** The `is_prerelease` boolean is consistent across:
- `VersionInfo` Pydantic schema (Task 4)
- `ProdUpdateBackend.get_current_version()` return value (Task 5)
- `DevUpdateBackend.get_current_version()` return value (Task 6)
- TypeScript `VersionInfo` interface (Task 7)
- `useVersionDisplay()` hook return type (Task 8)
- Component consumption (Task 10)

The pre-release marker list is consistent across:
- Backend detection: `("-pre.", "-rc.", "-alpha", "-beta", "-unstable")` (Task 5)
- Frontend: derived from backend response — no duplicate logic
- create-release.yml regex: `*-pre.*`, `*-alpha*`, `*-beta*`, `*-unstable*`, `*-rc*` (Task 16)
- release-stable.yml exclusion regex when finding last stable: `-(pre|rc|alpha|beta|unstable)` (Task 13)

The skip-filter prefixes in deploy-production.yml are consistent with:
- The version-bump commit emitted by release-stable.yml: `chore: release v${NEW_VERSION}` (Task 13)
- The legacy bump prefix `chore: bump version` (kept for backward compatibility with old commits, no harm if obsolete)
