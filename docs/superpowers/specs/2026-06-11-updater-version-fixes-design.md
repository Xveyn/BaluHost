# Updater Version Fixes — Design Spec

**Date:** 2026-06-11
**Status:** Approved
**Author:** Sven (Xveyn) + Claude (via brainstorming session)
**Issues:** #223 (deploy tag never reaches prod checkout), #120 (parse_version ranks pre-release above stable)
**Branches:** `fix/deploy-tag-fetch` (#223), `fix/updater-semver-120` (#120) — two separate PRs against `main`

## Problem

Two independent defects in the updater's version handling:

### 1. Deploy pre-release tag never reaches `/opt/baluhost` (#223)

The deploy flow has a chicken-and-egg ordering: `ci-deploy.sh` fetches + resets `/opt/baluhost`
to `origin/main` (`deploy/scripts/ci-deploy.sh:394-396`), services restart, and only **then** does
`deploy-production.yml` create and push the `v…-pre.N` tag — from a separate workspace checkout.
`/opt/baluhost` never fetches that tag, so the box is permanently one tag behind itself:

- `git describe --tags --exact-match` fails on every deployed HEAD →
  `get_current_version()` (`backend/app/services/update/prod_backend.py:87`) falls back to
  `pyproject.toml` with `is_dev_build=True`.
- UI shows "Dev Build" + the stale pyproject version (`1.36.0`) instead of `v1.36.1-pre.19`.
- `check_for_updates` compares against the fallback `1.36.0`, so the `unstable` channel offers
  the box its own running commit as an "update".

Since the GitHub-Releases rework (2026-06-06) nothing in the check path runs `git fetch --tags`
anymore, so the state no longer self-heals. Verified on prod 2026-06-11 (HEAD `dbcd9f6`, local
tags end at `pre.18`, pyproject `1.36.0`).

### 2. `parse_version` ranks a pre-release above its final stable (#120)

`parse_version` (`backend/app/services/update/utils.py:15`) returns
`(major, minor, patch, prerelease_str)` with `""` for finals. Tuple comparison then yields
`(1,33,1,"") < (1,33,1,"pre.3")` — backwards per SemVer. String compare also mis-sorts numeric
counters (`pre.10 < pre.2`).

Since the GitHub-Releases rework, the only **ordering** consumer left is
`prod_backend.check_for_updates:135-137` (`latest_v <= current_v`). All other uses are
equality checks (`github_releases._find_index`, `changelog_fallback:61-62`) or rely on the
4-tuple round-trip shape (`version_to_string`, `get_installed_version`, `dev_backend`).
The `get_release_notes`/`get_all_releases` ordering mentioned in the issue text is no longer
affected (positional GitHub API order) — note this when closing #120.

## Decisions

| Topic | Decision |
|---|---|
| #223 fix | Workflow-only: fetch tags into `/opt/baluhost` after the tag push (Option A) |
| #223 alternatives rejected | Tag-before-restart (breaks "tag only after successful deploy" invariant, ghost-tag cleanup on rollback); backend self-healing fetch (display path mutating repo state, fetch storms across 4 workers, latency) |
| #120 fix | Keep `parse_version` shape (round-trip + equality stay valid); add a dedicated `version_sort_key()` for ordering |
| Delivery | Two separate branches/PRs; spec rides with PR 1 |

## Fix 1: `fix/deploy-tag-fetch` (#223)

New step in `.github/workflows/deploy-production.yml`, directly after "Auto-tag pre-release":

```yaml
- name: Sync tags to production checkout
  if: success()
  run: git -C /opt/baluhost fetch origin --tags || echo "::warning::tag fetch into /opt/baluhost failed (display-only impact)"
```

Properties:

- **Non-fatal** (`|| echo ::warning::`): the deploy is already green and tagged at this point; a
  fetch failure must not fail the run — the impact would only be today's cosmetic display state.
- Runs on the same runner/user that already writes `/opt/baluhost` via `ci-deploy.sh`; the repo
  is public, so the fetch needs no credentials — `DEPLOY_PAT` stays confined to the tag-push
  step. CI/CD security layers 1–4 unchanged (additive step only in a CODEOWNERS-owned file).
- Also runs on the tag step's skip paths (tag already exists), fetching any previously missed
  tag — self-heals the current prod state on the next deploy.
- No backend change: `get_current_version()` runs `git describe` per request, so the display
  corrects itself on the next page load.

**Verification:** workflows cannot run locally — `actionlint` + review; after merge, on the box:
`git tag --points-at HEAD` non-empty and UI shows `v1.36.1-pre.N` instead of "Dev Build".

## Fix 2: `fix/updater-semver-120` (#120)

New function in `backend/app/services/update/utils.py`:

```python
def version_sort_key(version: str) -> tuple:
    """SemVer ordering: stable > its own pre-releases, pre.10 > pre.2."""
    major, minor, patch, prerelease = parse_version(version)
    if not prerelease:
        return (major, minor, patch, 1, ())
    ids = tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p)
        for p in prerelease.split(".")
    )
    return (major, minor, patch, 0, ids)
```

This implements SemVer precedence: finals above all pre-releases of the same version
(`1, ()` > `0, …`); within pre-releases, numeric identifiers compare numerically and rank
below alphanumeric ones (SemVer rule), so `pre.10 > pre.2` and `pre.2 < rc.1`.

Changes:

- `prod_backend.check_for_updates:135-137` switches from `parse_version` to `version_sort_key`
  for the `latest <= current` comparison — the only ordering call site.
- `parse_version` gets a docstring warning: not ordering-safe across pre-releases — use
  `version_sort_key`.
- Export `version_sort_key` from `services/update/__init__.py` alongside the existing utils.

**Tests (TDD, in `backend/tests/services/test_update_service.py`):**

- `1.33.1 > 1.33.1-pre.3` (stable above its pre-release)
- `pre.10 > pre.2` (numeric identifier ordering)
- `pre.2 < rc.1` for the same base version (lexical identifier comparison, `"pre" < "rc"`)
- `1.0.0-1 < 1.0.0-alpha` (SemVer: numeric identifiers rank below alphanumeric)
- `1.0.0-alpha < 1.0.0-alpha.1` (fewer identifiers rank lower — falls out of tuple prefix compare)
- equal stables compare equal; `v`-prefix tolerated
- non-numeric headers (`Unreleased`) don't crash (parity with `parse_version` tolerance)
- review existing comparison test (`test_update_service.py:66-68`, uses `1.6.0-beta`) and fix
  its expectation if it encodes the buggy ordering

Run before PR: `python -m pytest tests/services/test_update_service.py tests/services/test_github_releases.py -v`

## Out of Scope

- `get_release_notes` / `get_all_releases` ordering (positional since the GitHub rework)
- Making `get_current_version()`'s fallback smarter (e.g. `git describe` without
  `--exact-match`) — optional polish, not required once Fix 1 lands
- Any change to tag-numbering logic or deploy ordering

## Build Order

1. PR 1 (`fix/deploy-tag-fetch`): workflow step + this spec. Closes #223.
2. PR 2 (`fix/updater-semver-120`): `version_sort_key` + tests + consumer switch. Closes #120
   (with a note about the no-longer-affected ordering paths).
