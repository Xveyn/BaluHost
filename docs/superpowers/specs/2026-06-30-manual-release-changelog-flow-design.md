# Manual Release-Prep + CHANGELOG Flow — Design Spec

**Date:** 2026-06-30
**Status:** Approved
**Author:** Sven (Xveyn) + Claude (via brainstorming session)
**Branch:** `feat/manual-release-changelog-flow`

## Problem

`release-stable.yml` (workflow_dispatch) currently does everything unattended, in one CI run,
**without any PR or review**:

1. Bumps `backend/pyproject.toml` / `client/package.json` / `CLAUDE.md`.
2. Generates a CHANGELOG section mechanically from Conventional Commits since the last stable tag
   (`scripts/generate_changelog_section.py`) — drops anything that isn't `feat/fix/refactor/perf/docs`,
   produces bullet text straight from commit subjects.
3. Inserts it (`scripts/insert_changelog_section.py`), regenerates README stats, commits
   `chore: release vX.Y.Z`, **pushes straight to `main`** with `DEPLOY_PAT`, tags `vX.Y.Z`, pushes the tag.

Consequences:

- The CHANGELOG entry quality is whatever the raw commit subjects happen to read like — no curation,
  no grouping beyond the mechanical type→section map, no chance to fix wording before it's public.
- This is the **only** path that pushes content to `main` outside of a reviewed PR — every other change
  goes through CI + manual merge (`production.md` Git Workflow; `ci-cd-security.md` Known Gap #1 already
  flags `main` has no required PR approvals, but this path skips even *that* informal review).
- There's no structured point to check whether `README.md` or any of the per-directory `CLAUDE.md` files
  are still accurate before calling a version "stable" and publishing it as the GitHub "latest" release.
- `.claude/commands/release/_release.md` ("Release-PR: development → main") is dead: it targets the
  `development` branch, retired 2026-05-06 (`production.md`). It's the "release command" workflow Sven
  remembered existing.

## Goal

Make the **CHANGELOG entry for a stable release a hand-curated, PR-reviewed artifact** (same spirit as
the sibling `Zeiterfassung` repo's manual `CHANGELOG.md` + `release:*`-label convention), and give the
stable-release process a natural point to check `README.md`/`CLAUDE.md*` currency — **without**
reintroducing a pre-release tag for the release-prep merge itself, and without touching
`deploy-production.yml`.

Explicitly unchanged: the per-merge pre-release flow (every regular feature PR merge to `main` still
auto-tags `v<x>.<y>.<z+1>-pre.<n>` and deploys, exactly as today). Stable releases stay a **deliberate,
separate** step — not label-triggered-on-merge like `Zeiterfassung`.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Trigger model | Deliberate two-phase flow stays manual/separate (not label-triggers-release-on-any-merge) |
| CHANGELOG authoring | Hand-curated text in a reviewed PR; `generate_changelog_section.py` becomes a **local drafting aid only**, never run by CI |
| Doc-currency checklist | **Prompting-based** (the prepare command walks README.md + all CLAUDE.md files), not a CI gate — can be revisited later |
| Pre-release tag during release-prep | **None** — reuse the existing `chore: release v` commit-message skip-filter in `deploy-production.yml`; no change to that file |
| Version bump timing | Stays in the **promote** step (not in the prepare PR) — preserves the existing invariant that `pyproject.toml` only advances at the moment of the real stable cut |
| Merge strategy for the prepare PR | **Squash merge required**, commit title `chore: release vX.Y.Z` |
| Frontend changelog display | **Out of scope** — separate future spec |

## Why the version bump can't move into the prepare PR

`deploy-production.yml`'s auto-pre-release-tagger derives the tag from the **last stable tag + 1
patch**, never from `pyproject.toml`, specifically because `pyproject.toml` is documented to "hold the
last RELEASED version" between stable cuts:

```bash
LAST_STABLE=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | grep -Ev -- '-(pre|rc|alpha|beta|unstable)' | sort -V | tail -1)
BASE=${LAST_STABLE#v}
IFS=. read -r MAJ MIN PAT <<< "$BASE"
VERSION="${MAJ}.${MIN}.$((PAT + 1))"          # e.g. 1.38.1, regardless of the upcoming bump type
```

If the prepare PR bumped `pyproject.toml` to e.g. `1.39.0` before the stable tag exists, a normal
merge would still pass through `deploy-production.yml` and mis-tag a pre-release as `v1.38.1-pre.1` —
wrong number, confusing in the GitHub Releases list / Update page. Keeping the bump in the promote step
avoids this entirely; **no change to `deploy-production.yml` is needed.**

## Architecture

```
Phase 1 — /release-prepare   (NEW command, replaces dead _release.md)
  Prereq: HEAD of main already deployed + tested as the latest pre-release.
  │
  ├─ Propose bump type from commits since last stable tag (as today) → user confirms
  ├─ Compute target version: scripts/bump_version.py <type> --dry-run   (PREVIEW ONLY, no write)
  ├─ Draft CHANGELOG bullets: scripts/generate_changelog_section.py --since <last_stable> --output -
  │     → starting point only; Claude/Sven hand-edit wording/grouping
  ├─ Doc-currency checklist: walk README.md + every CLAUDE.md against the diff since last stable;
  │     apply fixes where something is stale
  ├─ Write the curated text as a new `## [Unreleased]` section (no version/date) right after the
  │     `# Changelog` / `---` header — same insertion point insert_changelog_section.py already uses
  ├─ Branch `release/vX.Y.Z` off main; commit CHANGELOG.md + any README/CLAUDE.md doc fixes
  └─ Open PR → main, title `chore: release vX.Y.Z`, label `release:<type>` (labels already exist)
       Tell the user: MUST be squash-merged so the commit message matches `chore: release v`

  ── normal PR review: CI (backend-tests, frontend-build), Xveyn reviews + squash-merges ──

  Merge effect: github.event.head_commit.message starts with "chore: release v"
  → deploy-production.yml's `deploy` job condition is false → entire job skipped
  → no redeploy attempt, no auto pre-release tag (no code changed anyway — same reasoning
    deploy-production.yml already uses for its own "chore: release v" commits today)

Phase 2 — /release-stable   (REWRITTEN — thin "promote" step, replaces today's full generation)
  │
  ├─ Verify CHANGELOG.md on main has exactly one `## [Unreleased]` section (fail loudly if 0 or 2+)
  ├─ gh workflow run release-stable.yml --ref main -f version=<X.Y.Z>
  │     (workflow_dispatch input is now an exact target version, not a bump_type —
  │      the version was already pinned when the prepare PR was opened)
  │
  release-stable.yml (simplified):
  ├─ Guard: CHANGELOG.md must contain exactly one `## [Unreleased]` section — else fail
  ├─ scripts/bump_version.py <version>             (real bump this time: pyproject.toml/package.json/CLAUDE.md)
  ├─ scripts/finalize_changelog_section.py          (NEW — rename `## [Unreleased]` → `## [X.Y.Z] - <date>`)
  ├─ scripts/generate_readme_stats.py --write       (unchanged)
  ├─ commit "chore: release vX.Y.Z", push to main, tag "vX.Y.Z", push tag
  │     (this push ALSO matches the "chore: release v" skip-filter → no redeploy/pre-release-tag
  │      triggered by it either — same as today, confirmed known behaviour, not a new gap)
  └─ tag push triggers create-release.yml (UNCHANGED) — awk-extracts `## [X.Y.Z]`, publishes as latest
```

## Components

### New

| File | Purpose |
|---|---|
| `.claude/commands/release/_release-prepare.md` | Interactive prepare flow: bump-type proposal, CHANGELOG draft+curation, doc-currency checklist, branch+PR. Replaces dead `_release.md`. |
| `scripts/finalize_changelog_section.py` | Renames the single `## [Unreleased]` header to `## [X.Y.Z] - <date>`. Fails if zero or more than one `## [Unreleased]` section exists. |
| `backend/tests/scripts/test_finalize_changelog_section.py` | Unit tests for the new script (mirrors `test_insert_changelog_section.py`'s style). |

### Modified

| File | Change |
|---|---|
| `.claude/commands/release/_release-stable.md` | Rewritten: now the "promote" step only — verify `## [Unreleased]` present, dispatch `release-stable.yml` with `-f version=X.Y.Z`, show run link. Updated "Regeln" (CHANGELOG section is now written in Phase 1, not by the workflow's old generation step). |
| `.github/workflows/release-stable.yml` | Replace `bump_type` choice input with a `version` string input. Remove the "Generate CHANGELOG section" + "Insert CHANGELOG section" steps (Conventional-Commits generation). Add the "Unreleased present" guard + call `finalize_changelog_section.py`. Keep `bump_version.py`, `generate_readme_stats.py --write`, commit/push/tag/push steps. Trigger/runner/permissions unchanged (`workflow_dispatch`, `ubuntu-latest`, `contents: write`). |
| `scripts/generate_changelog_section.py` | No code change — repurposed as a local-only drafting aid invoked by `/release-prepare`; never invoked from a workflow anymore. Docstring gets a one-line note about this. |
| `scripts/insert_changelog_section.py` | Reused as-is by `/release-prepare` to insert the `## [Unreleased]` block at the same H1/`---` anchor point it already targets. |
| `.claude/commands/release/_release.md` | **Deleted** (dead — targeted the retired `development` branch). |
| `.claude/rules/production.md` | "Git Workflow" section updated to describe the two-phase prepare/promote flow instead of "Stable releases are cut by the manual `release-stable.yml` workflow_dispatch." |

### Unchanged (verified, no action needed)

- `.github/workflows/deploy-production.yml` — the existing `chore: release v` skip-filter already covers
  both the prepare-PR squash-merge and the promote commit; no edit needed.
- `.github/workflows/create-release.yml` — still does literal `## \[$VERSION\]` awk-extraction; works
  unchanged once the promote step has finalized the header.
- `backend/app/services/update/changelog_fallback.py` — its `_SECTION_RE` only matches
  `## [x.y.z] - date`; a `## [Unreleased]` heading (no version/date in that shape) won't match and is
  simply skipped. **Verification task, not a code change**: add a test case confirming the parser
  tolerates an `## [Unreleased]` section sitting above the real entries without erroring.

## Edge Cases & Error Handling

| Case | Handling |
|---|---|
| Prepare PR merged via "Create a merge commit" instead of squash | Commit message becomes `Merge pull request #N from ...`, doesn't match the skip-filter → `deploy-production.yml` runs normally: harmless redeploy of identical code, but creates a **mislabeled** pre-release tag. Mitigated by `/release-prepare` explicitly instructing squash-merge with the exact title; not hard-blocked by CI (out of scope to add a check). |
| `## [Unreleased]` missing at promote time | `release-stable.yml` guard fails fast, no tag created. |
| Two or more `## [Unreleased]` sections (e.g. stale leftover) | `finalize_changelog_section.py` fails loudly rather than guessing which one. |
| Other feature PRs merge while the release-prep PR is open | Expected, unaffected — each still gets a correctly-numbered pre-release tag since `pyproject.toml` hasn't moved. Release-prep branch may need a rebase only if a doc file it touched (README/CLAUDE.md) also changed elsewhere — handled like any normal merge conflict. |
| `version` input isn't a valid forward bump from the current `pyproject.toml` version | `bump_version.py` (exact-version mode, already supported today: `python scripts/bump_version.py 1.21.0`) just sets it — add a light sanity check in the workflow that the new version sorts strictly above the current one before proceeding. |

## Out of Scope

- Frontend display of changelog entries for full releases (separate future spec — the existing Update
  page already renders `body_markdown` per release; whether/how that changes is a distinct piece of work).
- CI-enforced doc-currency checks (the checklist is prompting-based for now; an automated guard could be
  a later addition).
- Any change to `deploy-production.yml`'s pre-release tagging logic, `create-release.yml`, or the
  pre-release-per-merge flow — all confirmed to need no changes.

## Tests

- `backend/tests/scripts/test_finalize_changelog_section.py` (NEW): renames a single `## [Unreleased]`
  correctly; fails on zero matches; fails on 2+ matches; preserves surrounding content byte-for-byte
  outside the header line.
- `backend/tests/services/test_changelog_fallback.py`: add a case with an `## [Unreleased]` header
  present above real `## [x.y.z] - date` sections — parser must skip it and return the real sections
  unaffected.
- Manual dry run: trigger the rewritten `release-stable.yml` against a throwaway tag/branch in a fork
  (or `workflow_dispatch` with a disposable patch version) before relying on it for a real release.

## Build Order

1. `scripts/finalize_changelog_section.py` + its tests (TDD).
2. `changelog_fallback.py` test case for `## [Unreleased]` tolerance (should already pass; add the test
   to lock it in).
3. Rewrite `.github/workflows/release-stable.yml` (version input, guard, finalize step, drop generation
   steps).
4. Write `.claude/commands/release/_release-prepare.md`; rewrite `.claude/commands/release/_release-stable.md`;
   delete `.claude/commands/release/_release.md`.
5. Update `.claude/rules/production.md` Git Workflow section.
6. Manual dry run of the full prepare→PR→squash-merge→promote→tag cycle against a disposable version
   before the next real stable release.
