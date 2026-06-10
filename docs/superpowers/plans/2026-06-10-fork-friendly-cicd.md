# Fork-Friendly CI/CD Implementation Plan (#207)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Forks of BaluHost can run the existing CI/CD pipeline, choosing per config file which workflows run and whether backend tests run GitHub-hosted or on their own self-hosted runner, plus deploy to their own box via a new `deploy-fork` workflow — without weakening the canonical repo's 4-layer security model.

**Architecture:** Upstream behavior is hardwired to `github.repository == 'Xveyn/BaluHost'` literals (bit-identical to today, no vars needed). Forks are driven by GitHub Repository Variables with fork-safe defaults, set from a local gitignored `ci-config.conf` via `scripts/configure-ci.sh` (gh CLI). `deploy-fork.yml` reuses the already-`INSTALL_DIR`-parametrized `ci-deploy.sh`. Spec: `docs/superpowers/specs/2026-06-10-fork-friendly-cicd-design.md`.

**Tech Stack:** GitHub Actions expressions (`fromJSON`, `vars.*`), bash, gh CLI, Markdown (bilingual docs).

**Branch:** `feat/fork-friendly-cicd-207` (exists, based on `origin/main`).

**Security guardrails (check EVERY task against these):**
1. Upstream behavior must stay bit-identical (ci-sandbox runner, identity tripwire, `ci-tests` gate, Podman isolation; `deploy-production.yml` is NOT touched).
2. PR code must never influence runner choice or environment gates (only `github.repository` literals + server-side vars).
3. No `pull_request`/`pull_request_target` trigger on self-hosted runners.
4. `raid-mdadm-loopback.yml` stays pinned to `ubuntu-latest` — runner NEVER configurable (mdadm could brick real disks). `BALUHOST_MDADM_LOOPBACK=1` is never set outside that workflow.

---

### Task 1: Config file template + .gitignore

**Files:**
- Create: `ci-config.example.conf`
- Modify: `.gitignore` (add `ci-config.conf`)

- [ ] **Step 1: Create `ci-config.example.conf`** (repo root, exact content):

```bash
# BaluHost fork CI/CD configuration
# ----------------------------------
# Copy this file to ci-config.conf (gitignored), edit your values, then apply:
#   scripts/configure-ci.sh [--repo <owner>/<repo>] [--dry-run]
# The script stores these as GitHub Repository Variables via the gh CLI.
# Values equal to the documented default are DELETED from the repo variables,
# so your variable set stays minimal.
#
# Full guide: docs/deployment/SELF_HOSTING.en.md
# NOTE: This config has no effect on the canonical repo (Xveyn/BaluHost) —
# its pipeline behavior is hardcoded in the workflows.

# Where backend tests run: 'github' (default, ubuntu-latest VM) or 'self-hosted'
BACKEND_TEST_RUNNER=github

# Extra labels of your self-hosted runner (comma-separated).
# Only used with BACKEND_TEST_RUNNER=self-hosted. 'self-hosted' is always implied.
#BACKEND_TEST_RUNNER_LABELS=my-test-box

# --- Secret-free workflows (default: enabled) ---
ENABLE_PLAYWRIGHT_E2E=true
# RAID mdadm loopback tests. Toggle on/off ONLY — the runner is ALWAYS
# GitHub-hosted: real mdadm commands could destroy disks on a self-hosted box.
ENABLE_RAID_LOOPBACK=true
ENABLE_TAURI_BUILD=true
ENABLE_TUI_BUILD=true

# --- Secret-dependent / infrastructure workflows (default: disabled) ---
# Needs BALUPI_DEPLOY_KEY secret in your fork:
ENABLE_DEPLOY_PI=false
# Needs DEPLOY_PAT secret in your fork:
ENABLE_RELEASE_STABLE=false
# Deploy your fork's main branch to your own box (see SELF_HOSTING docs):
ENABLE_DEPLOY_FORK=false

# --- Only with ENABLE_DEPLOY_FORK=true ---
# Labels of the self-hosted runner on your deploy target (comma-separated):
#DEPLOY_FORK_RUNNER_LABELS=my-prod-box
# Install dir on the target (must match your deploy/install/install.sh setup):
#DEPLOY_FORK_INSTALL_DIR=/opt/baluhost
```

- [ ] **Step 2: Add to `.gitignore`** — append after the `.env.production` block:

```
# Local fork CI config (applied via scripts/configure-ci.sh)
ci-config.conf
```

- [ ] **Step 3: Verify**

Run: `git check-ignore -v ci-config.conf`
Expected: matches the new `.gitignore` line.

- [ ] **Step 4: Commit**

```bash
git add ci-config.example.conf .gitignore
git commit -m "feat(ci): add fork CI config template (#207)"
```

---

### Task 2: `scripts/configure-ci.sh`

**Files:**
- Create: `scripts/configure-ci.sh`

- [ ] **Step 1: Create the script** (exact content):

```bash
#!/usr/bin/env bash
# configure-ci.sh — apply a local ci-config.conf as GitHub Repository Variables.
#
# Usage: scripts/configure-ci.sh [--repo <owner>/<repo>] [--dry-run] [config-file]
#   config-file defaults to ./ci-config.conf (copy of ci-config.example.conf).
#   --dry-run prints the gh commands instead of executing them.
#   Requires an authenticated gh CLI (except --dry-run together with --repo).
#
# Variables equal to their fork-safe default are deleted, not set.
# Refuses to run against the canonical repo (its behavior is hardcoded).
set -euo pipefail

usage() {
    grep '^#' "$0" | sed -n '2,9p' | sed 's/^# \{0,1\}//'
}

CONFIG_FILE="ci-config.conf"
REPO=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) REPO="${2:?--repo needs a value}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 1 ;;
        *) CONFIG_FILE="$1"; shift ;;
    esac
done

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$CONFIG_FILE" ]] || die "config file not found: $CONFIG_FILE (copy ci-config.example.conf)"

# Reject anything that is not a comment, blank line, or plain KEY=VALUE.
if grep -Evq '^[[:space:]]*(#|$)|^[A-Z_]+=[A-Za-z0-9 ,./_-]*$' "$CONFIG_FILE"; then
    grep -Env '^[[:space:]]*(#|$)|^[A-Z_]+=[A-Za-z0-9 ,./_-]*$' "$CONFIG_FILE" >&2
    die "config may only contain comments and KEY=VALUE lines (letters, digits, ',./_- ')"
fi

declare -A CFG
while IFS='=' read -r key value; do
    CFG[$key]="$value"
done < <(grep -E '^[A-Z_]+=' "$CONFIG_FILE")

KNOWN_KEYS="BACKEND_TEST_RUNNER BACKEND_TEST_RUNNER_LABELS ENABLE_PLAYWRIGHT_E2E \
ENABLE_RAID_LOOPBACK ENABLE_TAURI_BUILD ENABLE_TUI_BUILD ENABLE_DEPLOY_PI \
ENABLE_RELEASE_STABLE ENABLE_DEPLOY_FORK DEPLOY_FORK_RUNNER_LABELS DEPLOY_FORK_INSTALL_DIR"
for key in "${!CFG[@]}"; do
    [[ " $KNOWN_KEYS " == *" $key "* ]] || die "unknown config key: $key"
done

if [[ -z "$REPO" ]]; then
    REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner) \
        || die "could not detect repo — pass --repo <owner>/<repo>"
fi
[[ "$REPO" != "Xveyn/BaluHost" ]] \
    || die "refusing to configure the canonical repo: its pipeline behavior is hardcoded"

set_var() {
    if [[ "$DRY_RUN" == 1 ]]; then
        echo "[dry-run] gh variable set $1 --repo $REPO --body '$2'"
    else
        gh variable set "$1" --repo "$REPO" --body "$2"
        echo "set    $1 = $2"
    fi
}

del_var() {
    if [[ "$DRY_RUN" == 1 ]]; then
        echo "[dry-run] gh variable delete $1 --repo $REPO (default — variable removed)"
    else
        gh variable delete "$1" --repo "$REPO" 2>/dev/null || true
        echo "default $1 (variable removed)"
    fi
}

# "a, b" -> ["self-hosted","a","b"] ('self-hosted' always implied, deduped)
labels_to_json() {
    local out='["self-hosted"' part
    IFS=',' read -ra parts <<< "${1:-}"
    for part in "${parts[@]}"; do
        part="${part#"${part%%[![:space:]]*}"}"; part="${part%"${part##*[![:space:]]}"}"
        [[ -z "$part" || "$part" == "self-hosted" ]] && continue
        out+=",\"$part\""
    done
    echo "$out]"
}

bool_var() {  # <name> <default>
    local name="$1" def="$2" val="${CFG[$name]:-$def}"
    [[ "$val" == "true" || "$val" == "false" ]] || die "$name must be true or false (got: $val)"
    if [[ "$val" == "$def" ]]; then del_var "$name"; else set_var "$name" "$val"; fi
}

echo "Applying $CONFIG_FILE to $REPO ..."

case "${CFG[BACKEND_TEST_RUNNER]:-github}" in
    github)      del_var BACKEND_TEST_RUNNER ;;
    self-hosted) set_var BACKEND_TEST_RUNNER "$(labels_to_json "${CFG[BACKEND_TEST_RUNNER_LABELS]:-}")" ;;
    *) die "BACKEND_TEST_RUNNER must be 'github' or 'self-hosted'" ;;
esac
if [[ "${CFG[BACKEND_TEST_RUNNER]:-github}" != "self-hosted" && -n "${CFG[BACKEND_TEST_RUNNER_LABELS]:-}" ]]; then
    echo "WARNING: BACKEND_TEST_RUNNER_LABELS is set but BACKEND_TEST_RUNNER is not 'self-hosted' — labels ignored" >&2
fi

bool_var ENABLE_PLAYWRIGHT_E2E true
bool_var ENABLE_RAID_LOOPBACK true
bool_var ENABLE_TAURI_BUILD true
bool_var ENABLE_TUI_BUILD true
bool_var ENABLE_DEPLOY_PI false
bool_var ENABLE_RELEASE_STABLE false
bool_var ENABLE_DEPLOY_FORK false

if [[ "${CFG[ENABLE_DEPLOY_FORK]:-false}" == "true" ]]; then
    [[ -n "${CFG[DEPLOY_FORK_RUNNER_LABELS]:-}" ]] \
        || die "ENABLE_DEPLOY_FORK=true requires DEPLOY_FORK_RUNNER_LABELS"
    set_var DEPLOY_FORK_RUNNER "$(labels_to_json "${CFG[DEPLOY_FORK_RUNNER_LABELS]}")"
    INSTALL_DIR_VAL="${CFG[DEPLOY_FORK_INSTALL_DIR]:-/opt/baluhost}"
    if [[ "$INSTALL_DIR_VAL" == "/opt/baluhost" ]]; then
        del_var DEPLOY_FORK_INSTALL_DIR
    else
        set_var DEPLOY_FORK_INSTALL_DIR "$INSTALL_DIR_VAL"
    fi
else
    del_var DEPLOY_FORK_RUNNER
    del_var DEPLOY_FORK_INSTALL_DIR
fi

echo "Done."
```

- [ ] **Step 2: Syntax check** (use the Bash tool, not PowerShell):

Run: `bash -n scripts/configure-ci.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Dry-run test, zero-config** — create a temp conf equal to the example defaults and verify everything resolves to deletes:

```bash
cp ci-config.example.conf /tmp/cc-default.conf
bash scripts/configure-ci.sh --dry-run --repo someone/BaluHost /tmp/cc-default.conf
```

Expected output: one `[dry-run] gh variable delete ...` line for each of `BACKEND_TEST_RUNNER`, the 7 `ENABLE_*` vars, `DEPLOY_FORK_RUNNER`, `DEPLOY_FORK_INSTALL_DIR`. No `gh variable set` lines.

- [ ] **Step 4: Dry-run test, full self-host config:**

```bash
cat > /tmp/cc-full.conf <<'EOF'
BACKEND_TEST_RUNNER=self-hosted
BACKEND_TEST_RUNNER_LABELS=my-test-box
ENABLE_TAURI_BUILD=false
ENABLE_DEPLOY_FORK=true
DEPLOY_FORK_RUNNER_LABELS=my-prod-box
DEPLOY_FORK_INSTALL_DIR=/srv/baluhost
EOF
bash scripts/configure-ci.sh --dry-run --repo someone/BaluHost /tmp/cc-full.conf
```

Expected output contains exactly these `set` lines (rest are deletes):
- `gh variable set BACKEND_TEST_RUNNER ... --body '["self-hosted","my-test-box"]'`
- `gh variable set ENABLE_TAURI_BUILD ... --body 'false'`
- `gh variable set ENABLE_DEPLOY_FORK ... --body 'true'`
- `gh variable set DEPLOY_FORK_RUNNER ... --body '["self-hosted","my-prod-box"]'`
- `gh variable set DEPLOY_FORK_INSTALL_DIR ... --body '/srv/baluhost'`

- [ ] **Step 5: Negative tests:**

```bash
bash scripts/configure-ci.sh --dry-run --repo Xveyn/BaluHost /tmp/cc-default.conf
# Expected: exit 1, "refusing to configure the canonical repo"
printf 'ENABLE_DEPLOY_FORK=true\n' > /tmp/cc-bad.conf
bash scripts/configure-ci.sh --dry-run --repo someone/BaluHost /tmp/cc-bad.conf
# Expected: exit 1, "requires DEPLOY_FORK_RUNNER_LABELS"
printf 'FOO=bar\n' > /tmp/cc-unknown.conf
bash scripts/configure-ci.sh --dry-run --repo someone/BaluHost /tmp/cc-unknown.conf
# Expected: exit 1, "unknown config key: FOO"
```

- [ ] **Step 6: Ensure LF line endings** — repo runs `core.autocrlf=true` on Windows; the script executes on Linux. Verify the blob is LF: `git add scripts/configure-ci.sh` then `git diff --cached --stat` (git normalizes on commit). If `.gitattributes` exists with `*.sh` rules, no action needed.

- [ ] **Step 7: Commit**

```bash
git add scripts/configure-ci.sh
git commit -m "feat(ci): configure-ci.sh applies ci-config.conf as repo variables (#207)"
```

---

### Task 3: `ci-check.yml` — runner switch (A1) + dead triggers (A2)

**Files:**
- Modify: `.github/workflows/ci-check.yml`

- [ ] **Step 1: Replace triggers** (A2 — `development` is retired):

Old (lines 3–8):
```yaml
on:
  pull_request:
    branches: [main, development]
  push:
    branches: [development]
  workflow_call:
```

New:
```yaml
on:
  pull_request:
    branches: [main]
  workflow_call:
```

- [ ] **Step 2: Replace the `backend-tests` job header** (lines 14–16):

Old:
```yaml
  backend-tests:
    runs-on: [self-hosted, ci-sandbox]
    environment: ${{ github.event_name == 'pull_request' && 'ci-tests' || '' }}
```

New:
```yaml
  backend-tests:
    # Runner selection (#207): upstream ALWAYS uses the hardened ci-sandbox
    # runner (Layer 2, not configurable). Forks choose via the server-side
    # repo variable BACKEND_TEST_RUNNER (JSON array, set by
    # scripts/configure-ci.sh), falling back to a secret-free ubuntu-latest VM.
    # PR code cannot influence this: repository literal + vars only.
    runs-on: ${{ fromJSON(github.repository == 'Xveyn/BaluHost' && '["self-hosted","ci-sandbox"]' || vars.BACKEND_TEST_RUNNER || '"ubuntu-latest"') }}
    # ci-tests approval gate: always for upstream PRs (as before); in forks
    # only when the fork opted into a self-hosted test runner.
    environment: ${{ (github.event_name == 'pull_request' && (github.repository == 'Xveyn/BaluHost' || contains(vars.BACKEND_TEST_RUNNER, 'self-hosted'))) && 'ci-tests' || '' }}
```

- [ ] **Step 3: Gate the identity tripwire to upstream** — add one line to the "Assert runner identity" step (after `- name:`, before `run:`):

```yaml
      - name: Assert runner identity (defense-in-depth tripwire)
        # Upstream-only: asserts the hardened ci-sandbox runner identity.
        # GitHub-hosted and fork runners have different users — skip there.
        if: github.repository == 'Xveyn/BaluHost'
        run: |
```

The step body and the Podman test step stay byte-identical (Podman is preinstalled on ubuntu-latest; the container isolation path is the same for every runner).

- [ ] **Step 4: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci-check.yml', encoding='utf-8'))"`
Expected: no output. (If PyYAML is missing: `pip install pyyaml`.)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci-check.yml
git commit -m "feat(ci): configurable backend-test runner for forks, upstream pinned to ci-sandbox (#207)"
```

---

### Task 4: Toggles for playwright-e2e + raid-mdadm-loopback

**Files:**
- Modify: `.github/workflows/playwright-e2e.yml`
- Modify: `.github/workflows/raid-mdadm-loopback.yml`

- [ ] **Step 1: `playwright-e2e.yml` trigger** — drop dead `master` branch:

Old: `    branches: [ main, master ]` → New: `    branches: [ main ]`

- [ ] **Step 2: `playwright-e2e.yml` mock-e2e guard** — extend the existing `if`:

Old:
```yaml
    if: github.event_name != 'workflow_dispatch' || github.event.inputs.run == 'mock'
```

New:
```yaml
    # vars.ENABLE_PLAYWRIGHT_E2E: fork toggle (#207), default on; unset upstream.
    if: vars.ENABLE_PLAYWRIGHT_E2E != 'false' && (github.event_name != 'workflow_dispatch' || github.event.inputs.run == 'mock')
```

(`live-e2e` needs `mock-e2e`, so disabling the toggle also prevents live runs — no change needed there.)

- [ ] **Step 3: `raid-mdadm-loopback.yml` guard + runner pin comment** on the `mdadm-loopback` job:

Old:
```yaml
  mdadm-loopback:
    runs-on: ubuntu-latest
```

New:
```yaml
  mdadm-loopback:
    # vars.ENABLE_RAID_LOOPBACK: fork toggle (#207), default on; unset upstream.
    if: vars.ENABLE_RAID_LOOPBACK != 'false'
    # SECURITY: runs-on MUST stay ubuntu-latest and MUST NOT become
    # configurable. Real mdadm commands on a self-hosted runner could destroy
    # disks / the deployment system (see #185 and ci-cd-security.md).
    runs-on: ubuntu-latest
```

- [ ] **Step 4: Validate YAML**

Run: `python -c "import yaml; [yaml.safe_load(open(f, encoding='utf-8')) for f in ['.github/workflows/playwright-e2e.yml', '.github/workflows/raid-mdadm-loopback.yml']]"`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/playwright-e2e.yml .github/workflows/raid-mdadm-loopback.yml
git commit -m "feat(ci): fork toggles for e2e + raid loopback, mdadm runner pinned (#207)"
```

---

### Task 5: Toggles for tauri-build + tui-build

**Files:**
- Modify: `.github/workflows/tauri-build.yml`
- Modify: `.github/workflows/tui-build.yml`

- [ ] **Step 1: `tauri-build.yml`** — add guard to the `build` job (keep the existing security comment):

Old:
```yaml
  build:
    # MUST stay on GitHub-hosted runner per .claude/rules/ci-cd-security.md
    # Layer 2 (no self-hosted for PR-touched code paths).
    runs-on: ubuntu-latest
```

New:
```yaml
  build:
    # vars.ENABLE_TAURI_BUILD: fork toggle (#207), default on; unset upstream.
    if: vars.ENABLE_TAURI_BUILD != 'false'
    # MUST stay on GitHub-hosted runner per .claude/rules/ci-cd-security.md
    # Layer 2 (no self-hosted for PR-touched code paths).
    runs-on: ubuntu-latest
```

- [ ] **Step 2: `tui-build.yml`** — same pattern:

Old:
```yaml
  build:
    # MUST stay on a GitHub-hosted runner per .claude/rules/ci-cd-security.md
    # Layer 2 (no self-hosted for releasable / PR-touched build paths).
    runs-on: ubuntu-latest
```

New:
```yaml
  build:
    # vars.ENABLE_TUI_BUILD: fork toggle (#207), default on; unset upstream.
    if: vars.ENABLE_TUI_BUILD != 'false'
    # MUST stay on a GitHub-hosted runner per .claude/rules/ci-cd-security.md
    # Layer 2 (no self-hosted for releasable / PR-touched build paths).
    runs-on: ubuntu-latest
```

- [ ] **Step 3: Validate YAML** (same python one-liner pattern as Task 4 with both files).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tauri-build.yml .github/workflows/tui-build.yml
git commit -m "feat(ci): fork toggles for tauri/tui builds (#207)"
```

---

### Task 6: Guards for deploy-pi + release-stable (B3) and dead trigger (A2)

**Files:**
- Modify: `.github/workflows/deploy-pi.yml`
- Modify: `.github/workflows/release-stable.yml`

- [ ] **Step 1: `deploy-pi.yml` trigger** — drop retired `development`:

Old: `    branches: [main, development]` → New: `    branches: [main]`

- [ ] **Step 2: `deploy-pi.yml` guard** on the `deploy` job:

Old:
```yaml
  deploy:
    runs-on: ubuntu-latest
```

New:
```yaml
  deploy:
    # Upstream always on; forks opt in via vars (needs BALUPI_DEPLOY_KEY
    # secret) — otherwise skip cleanly instead of failing (#207).
    if: github.repository == 'Xveyn/BaluHost' || vars.ENABLE_DEPLOY_PI == 'true'
    runs-on: ubuntu-latest
```

- [ ] **Step 3: `release-stable.yml` guard** on the `release` job:

Old:
```yaml
  release:
    runs-on: ubuntu-latest
    timeout-minutes: 10
```

New:
```yaml
  release:
    # Upstream always on; forks opt in via vars (needs DEPLOY_PAT secret) —
    # otherwise skip cleanly instead of failing (#207).
    if: github.repository == 'Xveyn/BaluHost' || vars.ENABLE_RELEASE_STABLE == 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 10
```

- [ ] **Step 4: Validate YAML** (python one-liner with both files).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy-pi.yml .github/workflows/release-stable.yml
git commit -m "feat(ci): skip-guards for secret-dependent workflows in forks (#207)"
```

---

### Task 7: New `deploy-fork.yml`

**Files:**
- Create: `.github/workflows/deploy-fork.yml`

- [ ] **Step 1: Create the workflow** (exact content):

```yaml
name: Deploy Fork

# Self-host deploy for FORKS only (#207). Dead in the canonical repo
# (repository guard below); upstream deploys via deploy-production.yml.
# Prerequisites on the target box (see docs/deployment/SELF_HOSTING.en.md):
#   1. One-time install via deploy/install/install.sh (Debian).
#   2. A self-hosted runner registered with the labels in
#      vars.DEPLOY_FORK_RUNNER (set via scripts/configure-ci.sh).
#   3. Optional but recommended: protect the fork-production environment
#      with required reviewers in your fork settings.
# No pre-release tagging here — that stays exclusive to deploy-production.yml.

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      sync_permissions:
        description: "Re-apply OS-level permission grants (udev / polkit / sudoers)."
        type: boolean
        required: false
        default: false

concurrency:
  group: fork-deploy
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  ci-check:
    if: vars.ENABLE_DEPLOY_FORK == 'true' && github.repository != 'Xveyn/BaluHost'
    uses: ./.github/workflows/ci-check.yml

  deploy:
    needs: ci-check
    if: vars.ENABLE_DEPLOY_FORK == 'true' && github.repository != 'Xveyn/BaluHost'
    runs-on: ${{ fromJSON(vars.DEPLOY_FORK_RUNNER) }}
    environment: fork-production
    timeout-minutes: 30

    steps:
      - name: Run deploy script
        env:
          INSTALL_DIR: ${{ vars.DEPLOY_FORK_INSTALL_DIR || '/opt/baluhost' }}
          DEPLOY_ACTOR: ${{ github.actor }}
          SYNC_PERMISSIONS: ${{ inputs.sync_permissions == true && '1' || '0' }}
        run: |
          export GITHUB_ACTOR="$DEPLOY_ACTOR"
          "$INSTALL_DIR/deploy/scripts/ci-deploy.sh"

      - name: Show deploy state
        if: always()
        run: cat "${{ vars.DEPLOY_FORK_INSTALL_DIR || '/opt/baluhost' }}/.deploy-state" 2>/dev/null || echo "No deploy state file"
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-fork.yml', encoding='utf-8'))"`
Expected: no output.

- [ ] **Step 3: Cross-check against the security guardrails** (top of this plan): no `pull_request` trigger, repository guard present on BOTH jobs, no secrets referenced, runner comes only from vars.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy-fork.yml
git commit -m "feat(deploy): deploy-fork workflow for self-hosted fork instances (#207)"
```

---

### Task 8: B2 legacy cleanup (verified dead on BaluNode 2026-06-10)

**Verification result:** all running prod units load from `/etc/systemd/system/` sourced from `deploy/install/templates/` (`/opt/baluhost`). Only the legacy `baluhost-frontend.service` on the box still references `/home/sven` (redundant — nginx serves `/opt/baluhost/client/dist`; ops note below). `ci-deploy.sh` restarts backend/scheduler/monitoring/webdav only — no frontend. No install template for a frontend unit exists, confirming it was retired.

**Files:**
- Delete: `deploy/systemd/baluhost-backend.service`, `deploy/systemd/baluhost-frontend.service`, `deploy/systemd/baluhost-monitoring.service`, `deploy/systemd/baluhost-scheduler.service`, `deploy/systemd/baluhost-webdav.service`, `deploy/systemd/README.md` (entire `deploy/systemd/` dir)
- Delete: `deploy/scripts/install-systemd-services.sh`, `deploy/scripts/setup-production.sh`, `deploy/scripts/migrate-to-opt.sh`, `deploy/scripts/install-nginx-config.sh` (all hardcode `/home/sven`; nginx script is marked DEPRECATED in-file)
- Modify: `docs/network/WEBDAV_NETWORK_DRIVE.de.md:50,308` and `docs/network/WEBDAV_NETWORK_DRIVE.en.md` (same two spots)
- Modify: `docs/deployment/PRODUCTION_DEPLOYMENT_NOTES.de.md` + `.en.md` (ops note)

- [ ] **Step 1: Delete the files**

```bash
git rm -r deploy/systemd
git rm deploy/scripts/install-systemd-services.sh deploy/scripts/setup-production.sh deploy/scripts/migrate-to-opt.sh deploy/scripts/install-nginx-config.sh
```

- [ ] **Step 2: Fix WEBDAV doc references** — in both language files replace the path `deploy/systemd/baluhost-webdav.service` with `deploy/install/templates/baluhost-webdav.service` (two occurrences each: prose line ~50, table line ~308).

- [ ] **Step 3: Repo-wide reference check**

Run (PowerShell): `Get-ChildItem -Recurse -Include *.md,*.sh,*.yml,*.py -Exclude CHANGELOG.md | Select-String -Pattern 'deploy/systemd|install-systemd-services|setup-production\.sh|migrate-to-opt|install-nginx-config'`
Expected: hits only in `docs/superpowers/` (spec/plan) and nothing else. Fix any stragglers the same way as Step 2. `CHANGELOG.md` keeps its historical entry.

- [ ] **Step 4: Ops note** — append to `docs/deployment/PRODUCTION_DEPLOYMENT_NOTES.en.md`:

```markdown
## Legacy frontend unit (BaluNode)

As of 2026-06-10, BaluNode still runs a legacy `baluhost-frontend.service`
referencing `/home/sven/projects/BaluHost`. It is redundant: nginx serves the
static frontend from `/opt/baluhost/client/dist`. Recommended cleanup on the box:

    sudo systemctl disable --now baluhost-frontend.service
    sudo rm /etc/systemd/system/baluhost-frontend.service
    sudo systemctl daemon-reload

The repo copies of the legacy units (`deploy/systemd/`) were removed in #207.
```

And the German equivalent to `PRODUCTION_DEPLOYMENT_NOTES.de.md`:

```markdown
## Legacy-Frontend-Unit (BaluNode)

Stand 2026-06-10 läuft auf BaluNode noch eine Legacy-`baluhost-frontend.service`,
die `/home/sven/projects/BaluHost` referenziert. Sie ist redundant: nginx
serviert das statische Frontend aus `/opt/baluhost/client/dist`. Empfohlene
Bereinigung auf der Box:

    sudo systemctl disable --now baluhost-frontend.service
    sudo rm /etc/systemd/system/baluhost-frontend.service
    sudo systemctl daemon-reload

Die Repo-Kopien der Legacy-Units (`deploy/systemd/`) wurden mit #207 entfernt.
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(deploy): remove dead sven-era systemd units + setup scripts (#207)"
```

---

### Task 9: CODEOWNERS

**Files:**
- Modify: `.github/CODEOWNERS`

- [ ] **Step 1: Add entries** (after the existing `/scripts/bootstrap-ci-runner.sh` line, matching file style):

```
/ci-config.example.conf @Xveyn
/scripts/configure-ci.sh @Xveyn
```

(`deploy-fork.yml` is already covered by the existing `/.github/workflows/` entry.)

- [ ] **Step 2: Commit**

```bash
git add .github/CODEOWNERS
git commit -m "chore(ci): codeowner fork-CI config surface (#207)"
```

---

### Task 10: Update `.claude/rules/ci-cd-security.md`

**Files:**
- Modify: `.claude/rules/ci-cd-security.md`

- [ ] **Step 1: Layer 2 table** — update the `ci-check.yml backend-tests` runner cell from `**self-hosted, ci-sandbox** (rootless Podman)` to:

```
**upstream: self-hosted, ci-sandbox (hardcoded repository literal); forks: vars.BACKEND_TEST_RUNNER, default ubuntu-latest** (rootless Podman everywhere)
```

and add a row for the new workflow:

```
| `deploy-fork.yml` | **fork-configured via `vars.DEPLOY_FORK_RUNNER`** | `push: main`, `workflow_dispatch` — dead upstream (`github.repository != 'Xveyn/BaluHost'` guard on every job) |
```

- [ ] **Step 2: Add a subsection** after the "Sandbox runner: two-layer isolation" block:

```markdown
**Fork configurability (#207).** Runner selection and workflow toggles for forks
are driven exclusively by `github.repository == 'Xveyn/BaluHost'` literals and
server-side Repository Variables (`vars.*`, set via `scripts/configure-ci.sh`).
Upstream behavior is hardcoded and needs no variables; PR code cannot influence
runner choice or environment gates through either mechanism. The `ci-tests`
gate condition is `github.repository == 'Xveyn/BaluHost' || contains(vars.BACKEND_TEST_RUNNER, 'self-hosted')`
on `pull_request` events. `raid-mdadm-loopback.yml` is deliberately NOT
runner-configurable: real mdadm on a self-hosted box could destroy disks —
only the on/off toggle `ENABLE_RAID_LOOPBACK` exists, and
`BALUHOST_MDADM_LOOPBACK=1` is never set outside that workflow.
```

- [ ] **Step 3: Reviewer Checklist** — add two items:

```markdown
- [ ] **Fork-config gate logic**: Does a change touch the `github.repository == 'Xveyn/BaluHost'` literals or the `contains(vars.BACKEND_TEST_RUNNER, 'self-hosted')` environment-gate condition in `ci-check.yml`/`deploy-fork.yml`? If it weakens the upstream-hardcoded path or derives gates from PR-controlled data — block.
- [ ] **mdadm runner pin**: Does a change make the `raid-mdadm-loopback.yml` runner configurable, or set `BALUHOST_MDADM_LOOPBACK` outside that workflow? If yes — block (mdadm must never run on self-hosted hardware).
```

- [ ] **Step 4: Commit**

```bash
git add .claude/rules/ci-cd-security.md
git commit -m "docs(security): document fork-config layer + mdadm runner pin (#207)"
```

---

### Task 11: `SELF_HOSTING` docs (bilingual)

**Files:**
- Create: `docs/deployment/SELF_HOSTING.en.md`
- Create: `docs/deployment/SELF_HOSTING.de.md`

- [ ] **Step 1: Create `SELF_HOSTING.en.md`** (exact content):

````markdown
# Self-Hosting & Fork CI/CD

This guide is for developers who fork BaluHost and want to (a) run CI on their
fork and (b) optionally deploy their fork to their own machine using the same
pipeline the canonical repo uses.

> The canonical repo (`Xveyn/BaluHost`) ignores all of this configuration —
> its pipeline behavior is hardcoded in the workflows and protected by the
> security model in `.claude/rules/ci-cd-security.md`.

## Zero-config behavior

A fresh fork works without any setup:

| Workflow | Behavior in your fork |
|---|---|
| `ci-check` (backend tests + frontend build) | Runs on GitHub-hosted runners; backend tests execute inside a rootless Podman container on `ubuntu-latest` |
| `playwright-e2e` (mocked) | Runs on `ubuntu-latest` |
| `raid-mdadm-loopback` | Runs on `ubuntu-latest` (PRs touching RAID paths) |
| `tauri-build`, `tui-build` | Run on `ubuntu-latest` (push to main / tags) |
| `create-release` | Runs on tag push (only needs `GITHUB_TOKEN`) |
| `deploy-pi`, `release-stable` | Skipped (need secrets you don't have) |
| `deploy-production` | Dead (actor-gated to the maintainer) |
| `deploy-fork` | Skipped until you opt in (see below) |

Note: pushing directly to your fork's `main` does not trigger `ci-check` —
open a PR inside your fork to run CI, or enable `deploy-fork` (which calls
`ci-check` before deploying).

## Configuring your fork

1. Copy the template: `cp ci-config.example.conf ci-config.conf` (gitignored).
2. Edit the values — every key is documented in the file.
3. Apply: `scripts/configure-ci.sh` (needs an authenticated
   [gh CLI](https://cli.github.com/); use `--dry-run` to preview, `--repo
   <owner>/<repo>` to target explicitly).

The script stores your choices as GitHub Repository Variables. Values equal to
the defaults are removed again, so `gh variable list` always shows exactly
your deviations from stock behavior.

## Running backend tests on your own machine

1. Register a [self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners)
   on your fork and give it a label, e.g. `my-test-box`. Podman must be
   installed on the runner host (tests run in a rootless container).
2. In `ci-config.conf`: `BACKEND_TEST_RUNNER=self-hosted` and
   `BACKEND_TEST_RUNNER_LABELS=my-test-box`, then re-run `scripts/configure-ci.sh`.
3. **Security:** with a self-hosted test runner configured, PR-triggered test
   runs in your fork request the `ci-tests` environment. GitHub auto-creates it
   unprotected on first use — if you ever accept PRs from strangers into your
   fork, add yourself as a required reviewer for `ci-tests` in your fork's
   Settings → Environments. Never run PR code from people you don't trust on
   hardware you care about.

The RAID mdadm loopback tests are the deliberate exception: their runner is
**always GitHub-hosted** and cannot be configured. Real `mdadm` commands could
destroy disks on a physical machine; the tests only ever run on ephemeral
GitHub VMs against loop devices.

## Deploying your fork to your own box (`deploy-fork`)

Prerequisites (one-time, on a Debian box):

1. Install BaluHost via the installer: see
   [DEPLOYMENT](DEPLOYMENT.en.md) and `deploy/install/install.sh`. Note your
   install dir (default `/opt/baluhost`).
2. Register a self-hosted runner on your fork **on that box**, with a label of
   your choice, e.g. `my-prod-box`.
3. Recommended: in your fork's Settings → Environments, create
   `fork-production` and add yourself as required reviewer — every deploy then
   needs a manual click, mirroring the canonical repo's Layer-4 protection.

Then in `ci-config.conf`:

```
ENABLE_DEPLOY_FORK=true
DEPLOY_FORK_RUNNER_LABELS=my-prod-box
DEPLOY_FORK_INSTALL_DIR=/opt/baluhost
```

Re-run `scripts/configure-ci.sh`. From now on every push to your fork's `main`
runs `ci-check` and then executes the same `deploy/scripts/ci-deploy.sh` the
canonical production deploy uses (git update, dependency sync, build, service
restarts, health check, automatic rollback on failure). Pre-release tagging is
NOT part of fork deploys — that stays exclusive to the canonical pipeline.

## Troubleshooting

- **A workflow fails with "secret not found"** — you enabled a
  secret-dependent workflow (`ENABLE_DEPLOY_PI`, `ENABLE_RELEASE_STABLE`)
  without adding the secret to your fork. Disable it or add the secret.
- **`backend-tests` hangs forever** — your `BACKEND_TEST_RUNNER` points at
  labels no online runner has. Check `gh api repos/<you>/<fork>/actions/runners`.
- **`deploy-fork` fails immediately** — `ENABLE_DEPLOY_FORK=true` requires
  `DEPLOY_FORK_RUNNER_LABELS`; the runner must be online on the target box and
  the install dir must contain a completed `deploy/install/install.sh` setup.
- **First-time contributors' PRs don't run CI** — standard GitHub behavior;
  approve the run in the Actions tab ("Approve and run").
````

- [ ] **Step 2: Create `SELF_HOSTING.de.md`** — full German translation of Step 1's document, 1:1 structure, all code blocks, tables, paths and config keys identical; only prose translated. Title: `# Self-Hosting & Fork-CI/CD`. Link `DEPLOYMENT.de.md` instead of `DEPLOYMENT.en.md`.

- [ ] **Step 3: Commit**

```bash
git add docs/deployment/SELF_HOSTING.en.md docs/deployment/SELF_HOSTING.de.md
git commit -m "docs(deploy): bilingual self-hosting + fork CI guide (#207)"
```

---

### Task 12: Link the guide (CONTRIBUTING + README)

**Files:**
- Modify: `CONTRIBUTING.md` (inside `## 🧪 Testing`, which ends before `## 🔀 Git Workflow` at line ~198)
- Modify: `README.md` (in `### Deployment Pipeline`, near line ~180)

- [ ] **Step 1: CONTRIBUTING.md** — append at the end of the `## 🧪 Testing` section (immediately before `## 🔀 Git Workflow`):

```markdown
### CI in your fork

Your fork runs the BaluHost CI pipeline out of the box on GitHub-hosted
runners — open a PR inside your fork to trigger it. To choose which workflows
run, or to run backend tests / deploys on your own hardware, see
[Self-Hosting & Fork CI/CD](docs/deployment/SELF_HOSTING.en.md).
```

- [ ] **Step 2: README.md** — extend the sentence at line ~180:

Old:
```markdown
See [Infrastructure](docs/deployment/infrastructure.en.md) and [Emergency Runbook](docs/deployment/emergency-runbook.en.md) for operational details.
```

New:
```markdown
See [Infrastructure](docs/deployment/infrastructure.en.md) and [Emergency Runbook](docs/deployment/emergency-runbook.en.md) for operational details. Forks can run this pipeline themselves — see [Self-Hosting & Fork CI/CD](docs/deployment/SELF_HOSTING.en.md).
```

- [ ] **Step 3: Commit**

```bash
git add CONTRIBUTING.md README.md
git commit -m "docs: link fork CI/self-hosting guide from CONTRIBUTING + README (#207)"
```

---

### Task 13: Final verification + PR

- [ ] **Step 1: Validate all workflows parse**

Run: `python -c "import yaml, glob; [yaml.safe_load(open(f, encoding='utf-8')) for f in glob.glob('.github/workflows/*.yml')]; print('OK')"`
Expected: `OK`

- [ ] **Step 2: Re-run the configure-ci.sh test matrix** (Task 2 Steps 3–5) to confirm nothing regressed.

- [ ] **Step 3: Diff review against the security guardrails** — `git diff origin/main --stat`, then check: `deploy-production.yml` untouched; `ci-check.yml` upstream path identical (ci-sandbox literal, tripwire body unchanged, Podman step unchanged); no new secret references; mdadm runner pinned.

- [ ] **Step 4: Push + PR** — write the PR body with the Write tool to a temp file (here-strings break in both shells), then:

```bash
git push -u origin feat/fork-friendly-cicd-207
gh pr create --title "feat(ci): fork-friendly CI/CD — configurable runners, deploy-fork, self-hosting docs (#207)" --body-file <tempfile> --base main
```

PR body must include: summary per goal (A/B), the security-guardrail checklist from this plan with confirmation each holds, the B2 verification evidence (BaluNode output summary), and the **manual post-merge acceptance checklist**:
1. Create/refresh a test fork; open a PR inside it → `backend-tests` green on `ubuntu-latest` (Podman path), `frontend-build` green, nothing hangs.
2. In the test fork: `scripts/configure-ci.sh` with `ENABLE_TAURI_BUILD=false` → push to main → tauri job skipped.
3. Upstream no-op PR → `backend-tests` runs on ci-sandbox with `ci-tests` gate + tripwire exactly as before.
4. Upstream merge → `deploy-production` runs unchanged.

- [ ] **Step 5: Comment on issue #207** with the PR link and which issue items (A1, A2, B1-as-deploy-fork, B2, B3, B5-partial, B6) it covers.
