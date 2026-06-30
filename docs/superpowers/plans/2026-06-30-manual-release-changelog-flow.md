# Manual Release-Prep + CHANGELOG Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `release-stable.yml`'s unattended, CI-generated CHANGELOG + direct-push-to-`main` with a two-phase flow: a reviewed PR (`/release-prepare`) that carries a hand-curated `## [Unreleased]` CHANGELOG section + a README/CLAUDE.md currency checklist, followed by a thin promote step (`/release-stable`) that finalizes the section, bumps the version, and tags.

**Architecture:** New script `scripts/finalize_changelog_section.py` renames a bare `## [Unreleased]` header into the real `## [X.Y.Z] - <date>` header. `release-stable.yml` shrinks to: guard (exactly one `## [Unreleased]` section exists) → finalize → bump → README stats → commit/tag/push. `release-stable.yml`'s `chore: release v` commit-message prefix already makes `deploy-production.yml` skip redeploy/pre-release-tagging for that commit — and, because the release-prep PR's merge commit message is set to the same prefix, it skips for that merge too. No change to `deploy-production.yml` or `create-release.yml`.

**Tech Stack:** Python 3.11 (scripts + pytest), GitHub Actions (`.github/workflows/release-stable.yml`), Claude Code slash commands (`.claude/commands/release/*.md`).

## Global Constraints

- Never modify `.github/workflows/deploy-production.yml` or `.github/workflows/create-release.yml` — both are confirmed correct as-is (spec "Unchanged" section).
- The release-prep PR's merge commit message MUST start with the literal string `chore: release v` — this is what makes `deploy-production.yml` skip the redeploy/pre-release-tag for it. Squash merge is **disabled** on this repo (`allow_squash_merge: false`, verified via `gh api repos/Xveyn/BaluHost`) — only "Create a merge commit" is available, so the message must be set explicitly via `gh pr merge --merge --subject "chore: release vX.Y.Z"` (the default auto-generated merge message will NOT match).
- The `## [Unreleased]` header must be written as **exactly** `## [Unreleased]` with nothing after the closing bracket — `changelog_fallback.py`'s `_SECTION_RE` (`^##\s*\[(?P<ver>[^\]]+)\]\s*-\s*(?P<date>\S+)`) would match anything shaped like `## [Unreleased] - <text>` and leak it into the Update page's offline fallback as a bogus release.
- `pyproject.toml` / `package.json` / `CLAUDE.md` version bumps stay in the promote step (`release-stable.yml`), never in the prepare PR — `deploy-production.yml`'s pre-release tagger derives its tag from "last stable tag + 1 patch" and assumes `pyproject.toml` doesn't move until the real stable cut (spec "Why the version bump can't move into the prepare PR").
- Test file location convention for `scripts/*.py`: `backend/tests/scripts/test_*.py` (subprocess-invoked, `REPO_ROOT = Path(__file__).resolve().parents[3]`).
- `scripts/generate_changelog_section.py` stays a **local drafting aid only** — it must never be invoked from a GitHub Actions workflow after this change.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `scripts/finalize_changelog_section.py` | New | Rename the single `## [Unreleased]` header to `## [X.Y.Z] - <date>`; fail loudly on 0 or 2+ matches |
| `backend/tests/scripts/test_finalize_changelog_section.py` | New | Unit tests for the above |
| `backend/tests/services/test_changelog_fallback.py` | Modified | Add a lock-in test: a bare `## [Unreleased]` header must not be parsed as a release section |
| `.github/workflows/release-stable.yml` | Rewritten | `version` input (not `bump_type`); guard + finalize step replace the Conventional-Commits generation steps; bump/readme-stats/commit/tag steps unchanged |
| `.claude/commands/release/_release-prepare.md` | New | Phase 1 interactive command: bump-type proposal, CHANGELOG draft+curation, doc checklist, branch+PR. Replaces dead `_release.md` |
| `scripts/generate_changelog_section.py` | Modified (docstring only) | One-line note: local drafting aid only, no CI workflow invokes it anymore |
| `.claude/commands/release/_release-stable.md` | Rewritten | Phase 2 interactive command: verify `## [Unreleased]` on `main`, dispatch the simplified workflow with `-f version=X.Y.Z` |
| `.claude/commands/release/_release.md` | Deleted | Dead — targeted the retired `development` branch |
| `.claude/rules/production.md` | Modified | "Git Workflow" section describes the two-phase flow |

---

### Task 1: `scripts/finalize_changelog_section.py`

**Files:**
- Create: `scripts/finalize_changelog_section.py`
- Test: `backend/tests/scripts/test_finalize_changelog_section.py`

**Interfaces:**
- Produces: CLI `python scripts/finalize_changelog_section.py --version X.Y.Z [--date YYYY-MM-DD] --target CHANGELOG.md`. Exit `0` on success (header replaced in place). Exit `2` + a message containing the word `Unreleased` on stderr when zero or 2+ bare `## [Unreleased]` headers are found in the target file. `--date` defaults to today (ISO format) when omitted.
- Consumes: nothing (standalone script, mirrors the existing `scripts/insert_changelog_section.py` CLI shape and subprocess test style).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/scripts/test_finalize_changelog_section.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/scripts/test_finalize_changelog_section.py -v`
Expected: every test FAILs (the script doesn't exist yet — `FileNotFoundError` or non-zero exit from `subprocess.run` trying to invoke a missing file, surfacing as an assertion failure on `result.returncode`).

- [ ] **Step 3: Write the implementation**

Create `scripts/finalize_changelog_section.py`:

```python
#!/usr/bin/env python3
"""Finalize the `## [Unreleased]` CHANGELOG section into a versioned, dated one.

The prepare flow (`/release-prepare`) writes a hand-curated `## [Unreleased]`
section with no version/date so it never matches the GitHub-release-fallback
parser's `## [x.y.z] - date` pattern (`changelog_fallback.py`). This script
runs in the promote step (`release-stable.yml`) once that PR has merged,
turning the bare placeholder into the real, dated header.

Usage:
    python scripts/finalize_changelog_section.py \\
        --version 1.32.0 \\
        --date 2026-05-06 \\
        --target CHANGELOG.md
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date as date_cls
from pathlib import Path

UNRELEASED_RE = re.compile(r"^## \[Unreleased\][ \t]*$", re.MULTILINE)


def finalize(target: Path, version: str, date_iso: str) -> None:
    text = target.read_text(encoding="utf-8")
    matches = list(UNRELEASED_RE.finditer(text))
    if not matches:
        sys.stderr.write(
            f"No '## [Unreleased]' section found in {target} -- "
            "merge the release-prep PR first\n"
        )
        sys.exit(2)
    if len(matches) > 1:
        sys.stderr.write(
            f"Found {len(matches)} '## [Unreleased]' sections in {target} -- expected exactly 1\n"
        )
        sys.exit(2)

    match = matches[0]
    new_header = f"## [{version}] - {date_iso}"
    new_text = text[: match.start()] + new_header + text[match.end():]
    target.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()

    finalize(args.target, args.version, args.date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/scripts/test_finalize_changelog_section.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/finalize_changelog_section.py backend/tests/scripts/test_finalize_changelog_section.py
git commit -m "feat(release): add finalize_changelog_section.py

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Lock in `changelog_fallback.py`'s tolerance for a bare `## [Unreleased]` header

**Files:**
- Modify: `backend/tests/services/test_changelog_fallback.py`

**Interfaces:**
- Consumes: `parse_changelog` from `app.services.update.changelog_fallback` (existing, unchanged signature).
- Produces: nothing new — this is a regression-lock test, no production code is expected to change.

- [ ] **Step 1: Write the test**

Append to `backend/tests/services/test_changelog_fallback.py`:

```python
def test_ignores_bare_unreleased_header(tmp_path):
    sample = """# Changelog

---

## [Unreleased]

### Added
- in progress thing

## [1.36.0] - 2026-06-06

### Added
- thing A

## [1.35.0] - 2026-05-01

### Fixed
- thing B
"""
    p = tmp_path / "CHANGELOG.md"
    p.write_text(sample, encoding="utf-8")
    sections = parse_changelog(str(p))
    # The bare '## [Unreleased]' header (no ' - date') must not be parsed as
    # a release section -- only the real, dated sections show up.
    assert [s.version for s in sections] == ["1.36.0", "1.35.0"]
    assert all("in progress thing" not in s.body_markdown for s in sections)
```

- [ ] **Step 2: Run the test**

Run: `cd backend && python -m pytest tests/services/test_changelog_fallback.py -v`
Expected: all tests PASS, including `test_ignores_bare_unreleased_header`, **without any change** to `changelog_fallback.py` — `_SECTION_RE` already requires a trailing ` - <date>` token that a bare `## [Unreleased]` line doesn't have.

If this test unexpectedly FAILs, `_SECTION_RE` in `backend/app/services/update/changelog_fallback.py:17` needs tightening (e.g. require the date token to look like `\d{4}-\d{2}-\d{2}`) before continuing — stop and fix that first, since it would mean a real "Unreleased" entry could leak into the Update page.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/services/test_changelog_fallback.py
git commit -m "test(update): lock in changelog_fallback tolerance for bare Unreleased header

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Rewrite `.github/workflows/release-stable.yml`

**Files:**
- Modify: `.github/workflows/release-stable.yml` (full rewrite)

**Interfaces:**
- Consumes: `scripts/finalize_changelog_section.py` (Task 1), `scripts/bump_version.py` (existing, unchanged — already supports an exact-version positional arg), `scripts/generate_readme_stats.py --write` (existing, unchanged).
- Produces: a `workflow_dispatch` workflow with a single required string input `version` (e.g. `1.39.0`), replacing the old `bump_type` choice input.

- [ ] **Step 1: Replace the file contents**

Replace the full contents of `.github/workflows/release-stable.yml` with:

```yaml
name: Release Stable

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Exact target version to tag (e.g. 1.39.0) -- the release-prep PR must already be merged (CHANGELOG.md has a single '## [Unreleased]' section)"
        type: string
        required: true

permissions:
  contents: write

jobs:
  release:
    # Upstream always on; forks opt in via vars (needs DEPLOY_PAT secret) --
    # otherwise skip cleanly instead of failing (#207).
    if: github.repository == 'Xveyn/BaluHost' || vars.ENABLE_RELEASE_STABLE == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          token: ${{ secrets.DEPLOY_PAT }}

      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      - name: Validate version input
        env:
          NEW_VERSION: ${{ inputs.version }}
        run: |
          if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "::error::version input must be exact semver X.Y.Z (got: $NEW_VERSION)"
            exit 1
          fi
          CURRENT=$(grep -oP '^version\s*=\s*"\K[^"]+' backend/pyproject.toml)
          HIGHEST=$(printf '%s\n%s\n' "$CURRENT" "$NEW_VERSION" | sort -V | tail -1)
          if [ "$HIGHEST" != "$NEW_VERSION" ] || [ "$NEW_VERSION" == "$CURRENT" ]; then
            echo "::error::version $NEW_VERSION does not sort strictly above current pyproject.toml version $CURRENT"
            exit 1
          fi
          echo "Promoting to v${NEW_VERSION} (current: $CURRENT)"

      - name: Guard -- exactly one Unreleased section
        run: |
          COUNT=$(grep -c '^## \[Unreleased\]$' CHANGELOG.md || true)
          if [ "$COUNT" -ne 1 ]; then
            echo "::error::Expected exactly one '## [Unreleased]' section in CHANGELOG.md, found $COUNT -- merge the release-prep PR first"
            exit 1
          fi

      - name: Finalize CHANGELOG section
        env:
          NEW_VERSION: ${{ inputs.version }}
        run: |
          python scripts/finalize_changelog_section.py \
            --version "$NEW_VERSION" \
            --target CHANGELOG.md
          echo "--- Finalized section preview ---"
          grep -A 20 "^## \[${NEW_VERSION}\]" CHANGELOG.md || true
          echo "--- End ---"

      - name: Bump version files
        env:
          NEW_VERSION: ${{ inputs.version }}
        run: python scripts/bump_version.py "$NEW_VERSION"

      - name: Regenerate README stats
        run: python scripts/generate_readme_stats.py --write

      - name: Commit + push version bump
        env:
          NEW_VERSION: ${{ inputs.version }}
        run: |
          git add backend/pyproject.toml client/package.json CLAUDE.md CHANGELOG.md README.md
          git commit -m "chore: release v${NEW_VERSION}"
          git push origin main

      - name: Tag + push
        env:
          NEW_VERSION: ${{ inputs.version }}
        run: |
          TAG="v${NEW_VERSION}"
          git tag -a "$TAG" -m "Release $TAG"
          git push origin "$TAG"
          echo "Stable release tag $TAG pushed -- create-release.yml will create the GitHub Release"
```

- [ ] **Step 2: Read the file back and verify structure**

Read `.github/workflows/release-stable.yml` and confirm:
- The `version` input replaced `bump_type` (no `choice` type, no `options:` list remains).
- No step references `scripts/generate_changelog_section.py` or `scripts/insert_changelog_section.py` (the Conventional-Commits generation is gone).
- `scripts/finalize_changelog_section.py` is called with `--version "$NEW_VERSION" --target CHANGELOG.md`.
- The trigger (`workflow_dispatch`), runner (`ubuntu-latest`), permissions (`contents: write`), and the `if:` repository guard are unchanged from the original file.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-stable.yml
git commit -m "ci(release): release-stable.yml promotes a pre-staged Unreleased section instead of generating one

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: New command `.claude/commands/release/_release-prepare.md`

**Files:**
- Create: `.claude/commands/release/_release-prepare.md`

**Interfaces:**
- Consumes: `scripts/bump_version.py --dry-run` (preview only), `scripts/generate_changelog_section.py` (drafting aid only), `scripts/insert_changelog_section.py` (existing, unchanged), the `release:major`/`release:minor`/`release:patch` GitHub labels (already exist in the repo).
- Produces: a `release/vX.Y.Z` branch + PR to `main`, with the exact merge instructions Task 5's `/release-stable` depends on (a merged `## [Unreleased]` section on `main`).

- [ ] **Step 1: Write the file**

Create `.claude/commands/release/_release-prepare.md`:

```markdown
# Release vorbereiten (Phase 1: CHANGELOG + Doku)

Bereitet einen Stable-Release vor: Branch `release/vX.Y.Z` mit handkuratiertem
CHANGELOG-Eintrag (`## [Unreleased]`) + ggf. README/CLAUDE.md-Updates, als PR
nach `main`. Ersetzt das stillgelegte `_release.md` (zielte auf den
retirierten `development`-Branch).

## Voraussetzung

- HEAD von `main` läuft bereits als Pre-Release auf der Production-NAS (getestet)
- `gh` CLI ist authentifiziert

## Workflow

### 1. Bump-Type vorschlagen

```bash
LAST_STABLE=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
git fetch origin main
git log "$LAST_STABLE"..origin/main --pretty=format:'%s'
```

**Vorschlag basierend auf Commits:**
- Mindestens ein `feat!:` oder `BREAKING CHANGE:` im Body → `major`
- Mindestens ein `feat:` → `minor`
- Sonst → `patch`

**FRAGE DEN BENUTZER:** Welcher Bump-Type?

### 2. Zielversion berechnen (nur Vorschau)

```bash
NEW_VERSION=$(python scripts/bump_version.py <bump_type> --dry-run | tail -1)
echo "Zielversion: $NEW_VERSION"
```

Schreibt noch keine Dateien — der echte Bump passiert erst in Phase 2
(`/release-stable`). Grund: `deploy-production.yml`s Pre-Release-Tagging geht
davon aus, dass `pyproject.toml` zwischen Stable-Releases unverändert bleibt.

### 3. CHANGELOG-Entwurf generieren

```bash
python scripts/generate_changelog_section.py \
  --version DRAFT \
  --since "$LAST_STABLE" \
  --output -
```

Das ist nur ein **Rohentwurf** aus den Commit-Subjects (mechanisch nach
Conventional-Commits-Typ gruppiert). Verwirf die erste Zeile
(`## [DRAFT] - <date>`) komplett — sie wird durch eine bare
`## [Unreleased]`-Zeile ersetzt (Schritt 5). Überarbeite den Rest:
Formulierungen glätten, Duplikate zusammenführen, irrelevante/interne Punkte
entfernen.

**FRAGE DEN BENUTZER:** Entwurf zeigen, gemeinsam überarbeiten.

### 4. Doku-Checkliste: README.md + alle CLAUDE.md

```bash
git log "$LAST_STABLE"..origin/main --name-only --pretty=format: | sort -u
```

Gruppiere die geänderten Dateien nach Top-Level-Verzeichnis. Für jedes
Verzeichnis mit eigenem `CLAUDE.md` (siehe Liste im Root-`CLAUDE.md` unter
"Each major directory has its own CLAUDE.md"): prüfe, ob neue/entfernte
Dateien, Routen, Services oder Felder dort noch fehlen oder veraltet
beschrieben sind. Prüfe `README.md` (Feature-Liste, Quick-Reference-Links)
ebenso.

**FRAGE DEN BENUTZER:** Welche Doku-Fixes sollen jetzt mit rein?

Wende die vereinbarten Fixes als normale Edits an — sie gehören in den
gleichen Branch/Commit wie das CHANGELOG (Schritt 6).

### 5. Unreleased-Sektion einfügen

Schreibe die finale, kuratierte Sektion in eine Scratch-Datei
(`/tmp/unreleased-section.md`). Kopfzeile ist **exakt** `## [Unreleased]` —
nichts dahinter, sonst matcht `changelog_fallback.py`s Parser sie
versehentlich als echten Release:

```
## [Unreleased]

### Added

- ...

### Fixed

- ...

---

```

```bash
python scripts/insert_changelog_section.py \
  --section /tmp/unreleased-section.md \
  --target CHANGELOG.md
```

### 6. Branch + Commit + PR

```bash
git checkout -b "release/v${NEW_VERSION}" origin/main
git add CHANGELOG.md README.md  # + jede in Schritt 4 geänderte CLAUDE.md
git commit -m "chore: release v${NEW_VERSION}"
git push -u origin "release/v${NEW_VERSION}"
gh pr create \
  --base main \
  --head "release/v${NEW_VERSION}" \
  --title "chore: release v${NEW_VERSION}" \
  --label "release:<bump_type>" \
  --body "$(cat <<'EOF'
## Changelog

<kuratierte Bullet-Liste aus Schritt 3>

## Doku

<Liste der README/CLAUDE.md-Fixes aus Schritt 4, falls vorhanden>

---
Bereitet einen Stable-Release vor. Enthält keine Code-Änderungen (der Code
läuft bereits als Pre-Release in Production) -- nur CHANGELOG + Doku.

**Beim Mergen:** Squash-Merge ist auf diesem Repo deaktiviert
(`allow_squash_merge: false`). Bitte über
`gh pr merge <PR-Nummer> --merge --subject "chore: release v<Version>" --body ""`
mergen, NICHT über den Standard-"Merge pull request"-Button ohne die
Commit-Message anzupassen -- sonst greift der `chore: release v`-Skip-Filter
in `deploy-production.yml` nicht und es entsteht ein irrtümlich benannter
Pre-Release-Tag.
EOF
)"
```

**ZEIGE DEM BENUTZER** den PR-Link + den Merge-Hinweis aus dem PR-Body.

### 7. Nach dem Merge

Sobald CI grün ist und der PR (mit angepasster Commit-Message!) gemerged
wurde, übernimmt `/release-stable` (Phase 2) den eigentlichen Tag-Schritt.

## Regeln

- **NIEMALS** lokal `pyproject.toml` / `package.json` / `CLAUDE.md`-Version bumpen — das passiert erst in Phase 2.
- **NIEMALS** lokal Tags erstellen oder pushen.
- Die `## [Unreleased]`-Kopfzeile darf **nichts** nach `]` enthalten (kein `- <text>`).
- Bei bereits existierendem Release-PR: Benutzer informieren und fragen, ob Update gewünscht.
- Commit-Message endet mit: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
```

- [ ] **Step 2: Note the drafting-aid-only role in `generate_changelog_section.py`'s docstring**

In `scripts/generate_changelog_section.py`, the module docstring currently starts:

```python
"""Generate a Keep-a-Changelog section from Conventional Commits.

Usage:
```

Change it to:

```python
"""Generate a Keep-a-Changelog section from Conventional Commits.

Local drafting aid only -- /release-prepare uses this to seed a
hand-curated CHANGELOG section; no CI workflow invokes this script anymore.

Usage:
```

- [ ] **Step 3: Verify the files are well-formed**

Read `.claude/commands/release/_release-prepare.md` back and confirm: it covers all 7 workflow steps, the `## [Unreleased]` exact-header warning appears, and the `gh pr merge --merge --subject` instruction appears (not a squash-merge instruction). Read `scripts/generate_changelog_section.py`'s docstring back and confirm the new note is present and the rest of the docstring is unchanged.

- [ ] **Step 4: Commit**

```bash
git add ".claude/commands/release/_release-prepare.md" "scripts/generate_changelog_section.py"
git commit -m "docs(release): add /release-prepare command (phase 1: CHANGELOG + docs PR)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Rewrite `_release-stable.md`, delete dead `_release.md`

**Files:**
- Modify (full rewrite): `.claude/commands/release/_release-stable.md`
- Delete: `.claude/commands/release/_release.md`

**Interfaces:**
- Consumes: the merged release-prep PR from Task 4's command (a `## [Unreleased]` section on `main`), the rewritten `release-stable.yml` from Task 3 (`-f version=X.Y.Z` input).

- [ ] **Step 1: Replace `_release-stable.md`'s contents**

Replace the full contents of `.claude/commands/release/_release-stable.md` with:

```markdown
# Release Stable (Phase 2: Promote)

Promotet den bereits gemergten Release-Prep-PR (siehe `/release-prepare`) zu
einem Stable-Tag: verifiziert, dass `CHANGELOG.md` auf `main` eine
`## [Unreleased]`-Sektion enthält, triggert `release-stable.yml`, das die
Sektion finalisiert (`finalize_changelog_section.py`), die Version real
bumpt und taggt.

## Voraussetzung

- Der Release-Prep-PR aus `/release-prepare` ist gemerged (mit angepasster
  `chore: release vX.Y.Z`-Commit-Message)
- `gh` CLI ist authentifiziert

## Workflow

### 1. Zielversion abfragen

**FRAGE DEN BENUTZER:** Welche Version soll promotet werden? (z.B. `1.39.0` —
die in `/release-prepare` Schritt 2 berechnete Zielversion)

### 2. Verifizieren

```bash
git fetch origin main
git show origin/main:CHANGELOG.md | grep -c '^## \[Unreleased\]$'
```

Erwartet: `1`. Bei `0`: Release-Prep-PR wurde noch nicht gemerged — abbrechen,
Benutzer informieren. Bei `>1`: inkonsistenter Zustand — abbrechen, Benutzer
informieren (manuell prüfen).

### 3. Workflow triggern

**FRAGE DEN BENUTZER:** Trigger für Version `<version>` ausführen?

```bash
gh workflow run release-stable.yml --ref main -f version=<version>
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
- Die CHANGELOG-Sektion wird in Phase 1 (`/release-prepare`) geschrieben, NICHT hier — dieser Schritt finalisiert nur die bereits vorhandene `## [Unreleased]`-Sektion
- Bei Workflow-Fehler: Run-Logs anzeigen und Benutzer informieren
```

- [ ] **Step 2: Delete the dead command**

```bash
git rm ".claude/commands/release/_release.md"
```

- [ ] **Step 3: Verify**

Read `.claude/commands/release/_release-stable.md` back and confirm it no longer mentions `bump_type`, `generate_changelog_section.py`, or local CHANGELOG generation — only the verify + dispatch + status steps remain. Confirm `.claude/commands/release/_release.md` no longer exists (`git status` shows it under deletions).

- [ ] **Step 4: Commit**

```bash
git add ".claude/commands/release/_release-stable.md" ".claude/commands/release/_release.md"
git commit -m "docs(release): rewrite /release-stable as phase-2 promote step, drop dead /release

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Update `.claude/rules/production.md` Git Workflow section

**Files:**
- Modify: `.claude/rules/production.md:61`

**Interfaces:**
- Consumes: nothing (documentation-only change).

- [ ] **Step 1: Edit the Git Workflow bullet**

In `.claude/rules/production.md`, replace this line (currently line 61):

```
- Feature/fix branches branch off from `main` and PR directly back into `main`. Merging the PR creates a Pre-Release tag and deploys to production. Stable releases are cut by the manual `release-stable.yml` workflow_dispatch.
```

with:

```
- Feature/fix branches branch off from `main` and PR directly back into `main`. Merging the PR creates a Pre-Release tag and deploys to production. Stable releases are a deliberate two-phase process: `/release-prepare` opens a CHANGELOG/docs-only PR (a hand-curated `## [Unreleased]` CHANGELOG section + any README/CLAUDE.md updates, no code, no version bump) which must be merged with an overridden `chore: release vX.Y.Z` commit message (squash merge is disabled on this repo) so the merge itself doesn't trigger a redundant deploy or a mislabeled pre-release tag; `/release-stable` then promotes it via `release-stable.yml` workflow_dispatch (finalizes the CHANGELOG section, bumps the version, tags).
```

- [ ] **Step 2: Verify**

Read `.claude/rules/production.md` back and confirm the Git Workflow section now describes both `/release-prepare` and `/release-stable`, and no longer says stable releases are "cut by the manual `release-stable.yml` workflow_dispatch" as a single step.

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/production.md
git commit -m "docs(rules): describe the two-phase release-prepare/release-stable flow

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Full local verification pass

**Files:** none (verification only)

**Interfaces:** none

- [ ] **Step 1: Run the full affected test set**

```bash
cd backend && python -m pytest tests/scripts/test_finalize_changelog_section.py tests/scripts/test_insert_changelog_section.py tests/scripts/test_generate_changelog_section.py tests/scripts/test_bump_version.py tests/services/test_changelog_fallback.py -v
```

Expected: all PASS.

- [ ] **Step 2: Re-read all five changed/created files once more for self-consistency**

Read back, in one pass: `scripts/finalize_changelog_section.py`, `.github/workflows/release-stable.yml`, `.claude/commands/release/_release-prepare.md`, `.claude/commands/release/_release-stable.md`, `.claude/rules/production.md`. Confirm: the version-input name (`version`) is used consistently between the workflow file and both command files; the `chore: release v` prefix string is identical (no typos) everywhere it's referenced; the `## [Unreleased]` exact-header requirement is stated consistently in both command files.

- [ ] **Step 3: Note the deferred live dry run**

Do **not** create a real `release/vX.Y.Z` branch, PR, or trigger `release-stable.yml` against the live `Xveyn/BaluHost` repo as part of this plan — that would consume a real version number and pollute release history. The first real exercise of this flow happens at the **next actual stable release**, run by Sven with `/release-prepare` then `/release-stable`. Flag this plan as implementation-complete, pending that first live use.

- [ ] **Step 4: Final commit if any fixups were needed**

If Step 2 surfaced any inconsistency, fix it in the relevant file and commit:

```bash
git add -A
git commit -m "fix(release): consistency fixups from final self-review

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

If nothing needed fixing, skip this commit.
