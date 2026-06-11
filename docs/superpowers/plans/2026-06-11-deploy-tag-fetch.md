# Deploy Tag Fetch Fix (#223) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After `deploy-production.yml` pushes the pre-release tag, fetch tags into `/opt/baluhost` so `git describe --tags --exact-match` succeeds and the UI stops showing "Dev Build".

**Architecture:** Single additive workflow step on the prod runner (same machine/user as `ci-deploy.sh`). Non-fatal by design — a fetch failure must never fail an already-green deploy. No backend changes; `get_current_version()` re-runs `git describe` per request, so the display self-heals.

**Tech Stack:** GitHub Actions YAML only.

**Spec:** `docs/superpowers/specs/2026-06-11-updater-version-fixes-design.md`

**Branch:** `fix/deploy-tag-fetch` (already exists, branched from `origin/main`, spec + plans committed).

---

### Task 1: Add "Sync tags to production checkout" step to the deploy workflow

**Files:**
- Modify: `.github/workflows/deploy-production.yml` (append after the "Auto-tag pre-release" step, which currently ends the file at line 116)

- [ ] **Step 1: Append the new step**

The file currently ends with the "Auto-tag pre-release" step (last line: `echo "Tag $TAG pushed -- create-release.yml will create the GitHub pre-release"`). Append this step at the same indentation level as the other steps (6 spaces for `- name:`):

```yaml
      # The tag above is pushed from this workspace checkout, not from
      # /opt/baluhost — without a fetch, the prod clone is permanently one tag
      # behind itself and `git describe --tags --exact-match` fails, so the UI
      # shows "Dev Build" + the stale pyproject version (#223). Fetch here on
      # the same runner/user that ci-deploy.sh already uses. Non-fatal: the
      # deploy is green and tagged at this point; a fetch failure only leaves
      # today's cosmetic display state. Also runs on the tag step's skip paths,
      # back-filling any previously missed tag on the next deploy.
      - name: Sync tags to production checkout
        if: success()
        run: git -C /opt/baluhost fetch origin --tags || echo "::warning::tag fetch into /opt/baluhost failed (display-only impact)"
```

- [ ] **Step 2: Validate the YAML parses**

Run (PowerShell, repo root — PyYAML is available in the backend venv; plain `python` works too if PyYAML is installed globally):

```powershell
python -c "import yaml, io; yaml.safe_load(io.open('.github/workflows/deploy-production.yml', encoding='utf-8')); print('YAML OK')"
```

Expected: `YAML OK`. If PyYAML is not importable, fall back to a careful visual diff review (`git diff`) — indentation of `- name:` must match the sibling steps.

- [ ] **Step 3: CI/CD security checklist self-review**

Verify against `.claude/rules/ci-cd-security.md` Reviewer Checklist (this file is CODEOWNERS-owned):
- No new runner targets, no new triggers, actor gate (`github.actor == 'Xveyn'`) untouched, `environment: production` untouched.
- New step uses no secrets (public-repo fetch); `DEPLOY_PAT` still confined to the tag-push step env.

Expected: all checks pass (the step is purely additive).

- [ ] **Step 4: Commit**

```powershell
git add .github/workflows/deploy-production.yml
git commit -m "fix(ci): sync pre-release tag into /opt/baluhost after deploy tagging (#223)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Push branch and open PR

**Files:** none (git/gh only)

- [ ] **Step 1: Push the branch**

```powershell
git push -u origin fix/deploy-tag-fetch
```

- [ ] **Step 2: Write the PR body with the Write tool** (NOT a here-string on the gh command line — known quoting pitfall)

Write to `.claude\tmp-pr-body.md`:

```markdown
## Summary

After `deploy-production.yml` pushes the `v…-pre.N` tag (from its workspace checkout), the new
"Sync tags to production checkout" step runs `git -C /opt/baluhost fetch origin --tags` so the
prod clone finally sees the tag for its own HEAD. Fixes the permanent "Dev Build" + stale
version display (`get_current_version()` exact-match fallback).

Closes #223.

## Design

- Non-fatal (`|| echo ::warning::`): the deploy is already green and tagged; a fetch failure
  must not fail the run (display-only impact).
- Same runner/user that already writes `/opt/baluhost`; public repo → no credentials,
  `DEPLOY_PAT` stays confined to the tag-push step. CI/CD layers 1-4 unchanged (additive step
  in a CODEOWNERS-owned file; no new triggers/runners/secrets).
- Also runs on the tag step's skip paths, back-filling a previously missed tag — self-heals the
  current prod state on the next deploy.

Spec: `docs/superpowers/specs/2026-06-11-updater-version-fixes-design.md` (committed here).

## Verification

Workflows can't run locally: YAML parse check + security-checklist review. Post-merge on the
box: `git tag --points-at HEAD` non-empty, update page shows `v1.36.1-pre.N` instead of
"Dev Build".

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 3: Create the PR**

```powershell
gh pr create --base main --title "fix(ci): sync pre-release tag into /opt/baluhost after deploy tagging" --body-file ".claude\tmp-pr-body.md"
Remove-Item ".claude\tmp-pr-body.md" -Confirm:$false
```

Expected: PR URL printed. Report the PR number back to the user.
