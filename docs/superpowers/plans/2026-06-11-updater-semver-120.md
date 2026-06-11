# Updater SemVer Ordering Fix (#120) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Version ordering treats a stable release as newer than its own pre-releases (`1.33.1 > 1.33.1-pre.3`) and sorts numeric pre-release counters numerically (`pre.10 > pre.2`).

**Architecture:** `parse_version` keeps its `(major, minor, patch, prerelease_str)` shape — it is the round-trip format for `version_to_string`/`get_installed_version`/`dev_backend` and is used for equality checks. A new `version_sort_key()` in `backend/app/services/update/utils.py` provides SemVer-correct ordering; the only ordering call site (`prod_backend.check_for_updates`) switches to it.

**Tech Stack:** Python (stdlib only), pytest.

**Spec:** `docs/superpowers/specs/2026-06-11-updater-version-fixes-design.md`

**Branch:** `fix/updater-semver-120` — create from `origin/main` first:

```powershell
git fetch origin
git checkout -b fix/updater-semver-120 origin/main
```

Note: working directory is `D:\Programme (x86)\Baluhost`; run pytest from `backend\`.

---

### Task 1: `version_sort_key` (TDD)

**Files:**
- Modify: `backend/app/services/update/utils.py` (new function after `parse_version`, ends line 36)
- Modify: `backend/app/services/update/__init__.py` (export)
- Test: `backend/tests/services/test_update_service.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/services/test_update_service.py`, extend the import at line 16 with `version_sort_key`:

```python
from app.services.update import (
    parse_version,
    version_to_string,
    version_sort_key,
    DevUpdateBackend,
    UpdateService,
    get_update_backend,
)
```

Then REPLACE the existing `test_version_comparison` method (lines 64-73 — it asserts the buggy
`stable < beta` ordering as documented behavior) with this test class content, keeping it inside
`TestVersionParsing` as a method plus adding a new class after `TestVersionParsing`:

```python
    def test_version_comparison(self):
        """Major/minor/patch ordering via version_sort_key."""
        assert version_sort_key("1.6.0") > version_sort_key("1.5.0")


class TestVersionSortKey:
    """SemVer-correct ordering (issue #120) — parse_version tuples are NOT ordering-safe."""

    def test_stable_ranks_above_its_prerelease(self):
        assert version_sort_key("1.33.1") > version_sort_key("1.33.1-pre.3")

    def test_numeric_prerelease_counters_sort_numerically(self):
        assert version_sort_key("1.33.1-pre.10") > version_sort_key("1.33.1-pre.2")

    def test_alphanumeric_identifiers_compare_lexically(self):
        # "pre" < "rc" lexically
        assert version_sort_key("1.33.1-pre.2") < version_sort_key("1.33.1-rc.1")

    def test_numeric_identifier_ranks_below_alphanumeric(self):
        # SemVer: numeric identifiers always have lower precedence
        assert version_sort_key("1.0.0-1") < version_sort_key("1.0.0-alpha")

    def test_fewer_identifiers_rank_lower(self):
        # SemVer: 1.0.0-alpha < 1.0.0-alpha.1
        assert version_sort_key("1.0.0-alpha") < version_sort_key("1.0.0-alpha.1")

    def test_equal_stables_and_v_prefix(self):
        assert version_sort_key("v1.36.0") == version_sort_key("1.36.0")

    def test_tolerates_non_numeric_header(self):
        # parity with parse_version's CHANGELOG "[Unreleased]" tolerance
        assert version_sort_key("Unreleased") == version_sort_key("0.0.0")
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
cd backend
python -m pytest tests/services/test_update_service.py -v --no-cov
```

Expected: collection FAILS with `ImportError: cannot import name 'version_sort_key'`.

- [ ] **Step 3: Implement `version_sort_key`**

In `backend/app/services/update/utils.py`, insert after `parse_version` (after line 36). Also
extend `parse_version`'s docstring (line 16) with the ordering warning:

```python
def parse_version(tag: str) -> tuple[int, int, int, str]:
    """Parse semver tag (e.g., 'v1.5.0' or '1.5.0-beta') into comparable tuple.

    WARNING: the returned tuple is NOT ordering-safe across pre-releases —
    tuple comparison ranks '' below 'pre.N', i.e. a stable BELOW its own
    pre-releases (issue #120). Use version_sort_key() for ordering; this
    shape is for round-trips (version_to_string) and equality checks.
    """
```

(keep the existing function body unchanged), then add:

```python
def version_sort_key(version: str) -> tuple:
    """SemVer-correct ordering key: stable > its own pre-releases, pre.10 > pre.2.

    Finals sort as (major, minor, patch, 1, ()); pre-releases as
    (major, minor, patch, 0, identifiers) where each identifier is
    (0, int, "") if numeric else (1, 0, str) — numeric identifiers compare
    numerically and rank below alphanumeric ones, per SemVer precedence.
    """
    major, minor, patch, prerelease = parse_version(version)
    if not prerelease:
        return (major, minor, patch, 1, ())
    ids = tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p)
        for p in prerelease.split(".")
    )
    return (major, minor, patch, 0, ids)
```

In `backend/app/services/update/__init__.py`, add `version_sort_key` to the `utils` import block
(after `version_to_string` on line 13) and to `__all__` (after `"version_to_string"` on line 33):

```python
from app.services.update.utils import (
    ProgressCallback,
    parse_version,
    version_to_string,
    version_sort_key,
    COMMIT_TYPE_MAP,
    _CONVENTIONAL_RE,
    _parse_conventional_commits,
)
```

```python
    "parse_version",
    "version_to_string",
    "version_sort_key",
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
python -m pytest tests/services/test_update_service.py -v --no-cov
```

Expected: PASS (all of `TestVersionSortKey` + the rewritten `test_version_comparison` + all pre-existing tests).

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/update/utils.py backend/app/services/update/__init__.py backend/tests/services/test_update_service.py
git commit -m "fix(updates): SemVer-correct version_sort_key; stable ranks above its pre-releases (#120)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Switch `check_for_updates` to `version_sort_key` (TDD)

**Files:**
- Modify: `backend/app/services/update/prod_backend.py:34-40` (import) and `:135-137` (comparison)
- Test: `backend/tests/services/test_update_github.py`

- [ ] **Step 1: Write the failing regression test**

Append to `backend/tests/services/test_update_github.py` (file uses module-level helpers
`_gh()` and `_FakeVersion` defined at lines 26-34; reuse them):

```python
@pytest.mark.asyncio
async def test_check_for_updates_offers_stable_over_running_prerelease(monkeypatch):
    """#120 regression: box runs vX.Y.Z-pre.N, matching stable vX.Y.Z exists -> offer it."""
    rel = [_gh("v1.36.1", False), _gh("v1.36.1-pre.19", True), _gh("v1.36.0", False)]
    b = ProdUpdateBackend()
    async def _ver(): return _FakeVersion("1.36.1-pre.19")
    monkeypatch.setattr(b, "get_current_version", _ver)
    async def fake_list(*a, **k): return rel
    monkeypatch.setattr(b._gh, "list_releases", fake_list)
    available, latest, changelog = await b.check_for_updates("stable")
    assert available is True and latest.version == "1.36.1"


@pytest.mark.asyncio
async def test_check_for_updates_no_update_when_on_latest_stable(monkeypatch):
    rel = [_gh("v1.36.1", False), _gh("v1.36.1-pre.19", True), _gh("v1.36.0", False)]
    b = ProdUpdateBackend()
    async def _ver(): return _FakeVersion("1.36.1")
    monkeypatch.setattr(b, "get_current_version", _ver)
    async def fake_list(*a, **k): return rel
    monkeypatch.setattr(b._gh, "list_releases", fake_list)
    available, latest, changelog = await b.check_for_updates("stable")
    assert available is False
```

- [ ] **Step 2: Run tests to verify the regression test fails**

```powershell
python -m pytest tests/services/test_update_github.py -v --no-cov
```

Expected: `test_check_for_updates_offers_stable_over_running_prerelease` FAILS
(`available is False` — buggy compare ranks `1.36.1 <= 1.36.1-pre.19`);
`test_check_for_updates_no_update_when_on_latest_stable` PASSES already.

- [ ] **Step 3: Switch the comparison**

In `backend/app/services/update/prod_backend.py`, replace the utils import (lines 34-40):
`version_sort_key` comes in, `parse_version` goes out — after this task the comparison below is
the file's only `parse_version` use, and a stale import would trip ruff F401:

```python
from app.services.update.utils import (
    ProgressCallback,
    version_sort_key,
    version_to_string,
    get_installed_version,
    _CONVENTIONAL_RE,
)
```

Replace lines 135-137:

```python
        latest_v = parse_version(latest.tag)
        current_v = parse_version(current.version)
        if latest_v <= current_v:
            return False, None, []
```

with:

```python
        latest_v = version_sort_key(latest.tag)
        current_v = version_sort_key(current.version)
        if latest_v <= current_v:
            return False, None, []
```

Verify nothing else in the file still references `parse_version`:

```powershell
git grep -n "parse_version" -- backend/app/services/update/prod_backend.py
```

Expected: no matches.

- [ ] **Step 4: Run tests to verify they pass**

```powershell
python -m pytest tests/services/test_update_github.py -v --no-cov
```

Expected: PASS (all tests including both new ones).

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/update/prod_backend.py backend/tests/services/test_update_github.py
git commit -m "fix(updates): check_for_updates compares via version_sort_key (#120)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Full targeted suite, push, PR

**Files:** none (verification + git/gh only)

- [ ] **Step 1: Run all updater-related tests**

```powershell
python -m pytest tests/services/test_update_service.py tests/services/test_update_github.py tests/services/test_github_releases.py tests/services/test_changelog_fallback.py -v --no-cov
```

Expected: ALL PASS (file existence of all four test modules verified during planning).

- [ ] **Step 2: Push the branch**

```powershell
git push -u origin fix/updater-semver-120
```

- [ ] **Step 3: Write the PR body with the Write tool** (NOT a here-string on the gh command line)

Write to `.claude\tmp-pr-body.md`:

```markdown
## Summary

`parse_version` tuples rank a stable release BELOW its own pre-releases (`"" < "pre.3"`), so a
box running `vX.Y.Z-pre.N` was never offered the matching stable `vX.Y.Z` on the stable channel.
String compare also mis-sorted numeric counters (`pre.10 < pre.2`).

New `version_sort_key()` implements SemVer precedence (finals above pre-releases; numeric
identifiers numeric and below alphanumeric); `check_for_updates` — the only remaining ordering
call site — switches to it. `parse_version` keeps its shape (round-trip format for
`version_to_string` and equality checks) and now carries an ordering warning in its docstring.

Closes #120. Note: the `get_release_notes`/`get_all_releases` ordering mentioned in the issue is
no longer affected — positional GitHub API order since the 2026-06-06 GitHub-Releases rework.

## Tests

- `TestVersionSortKey`: stable > pre, `pre.10 > pre.2`, lexical identifiers, numeric < alphanumeric,
  fewer identifiers rank lower, v-prefix, `Unreleased` tolerance.
- `check_for_updates` regression: running `1.36.1-pre.19` + stable `v1.36.1` published → update offered;
  running `1.36.1` → no self-offer.
- Full updater suite green locally (`test_update_service`, `test_update_github`, `test_github_releases`,
  `test_changelog_fallback`).

Spec: `docs/superpowers/specs/2026-06-11-updater-version-fixes-design.md` (committed with #223 PR).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 4: Create the PR**

```powershell
gh pr create --base main --title "fix(updates): SemVer-correct ordering - stable ranks above its pre-releases" --body-file ".claude\tmp-pr-body.md"
Remove-Item ".claude\tmp-pr-body.md" -Confirm:$false
```

Expected: PR URL printed. Report the PR number back to the user.
