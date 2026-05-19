# Self-Hosted Backend Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `backend-tests` from `ubuntu-latest` to a new self-hosted runner on the BaluHost NAS that executes tests inside a rootless Podman container, gated by a manual GitHub Environment approval on PR triggers.

**Architecture:** A second GitHub Actions runner instance on the NAS runs as a dedicated unprivileged user `ci-runner` (no sudo, no read on production paths). The runner agent itself runs on the host; the actual `pip install` + `pytest` invocation happens inside `podman run --rm` against the `python:3.11-slim` image, so test code can never see the host filesystem outside the bind-mounted workspace. A new `ci-tests` GitHub Environment requires Xveyn approval before each PR-triggered run; `workflow_call` invocations from `deploy-production.yml` bypass the gate (code is already trusted at that point).

**Tech Stack:** Bash (provisioning), GitHub Actions YAML, Podman rootless (Debian 13), GitHub Actions Runner agent, systemd user services.

**Spec:** `docs/superpowers/specs/2026-05-19-self-hosted-backend-tests-design.md`

---

## Pre-flight

Before starting Task 1, confirm:

- Working on branch `feat/ci-self-hosted-backend-tests` (the spec already committed here).
- `gh` CLI is authenticated and points at `Xveyn/BaluHost`.
- You can SSH into the BaluNode NAS as a user with `sudo` privileges.
- The existing `BaluNode` runner is online: `gh api repos/Xveyn/BaluHost/actions/runners` should return at least one runner with `status: online`.

---

## File Map

| Path | Action | Responsibility |
|---|---|---|
| `scripts/bootstrap-ci-runner.sh` | Create | Provision the `ci-runner` Linux user, Podman rootless, GitHub Actions runner agent, and run self-tests. Idempotent. |
| `.github/CODEOWNERS` | Modify | Add the new script to Xveyn-owned paths. |
| `.claude/rules/ci-cd-security.md` | Modify | Document the two-layer sandbox (POSIX + Podman), add `ci-tests` environment row, update Layer 2 table, update Reviewer Checklist, update Known Gaps. |
| `.github/workflows/ci-check.yml` | Modify | `backend-tests` job: `runs-on: [self-hosted, ci-sandbox]`, conditional `environment: ci-tests`, identity tripwire, `podman run` wrapper. `frontend-build` unchanged. |
| Out-of-repo: NAS host | Run script | Execute `bootstrap-ci-runner.sh` once. |
| Out-of-repo: GitHub Settings | UI / API | Create `ci-tests` Environment with required reviewer Xveyn. |

---

## Task 1: Author `scripts/bootstrap-ci-runner.sh`

**Files:**
- Create: `scripts/bootstrap-ci-runner.sh`

The script provisions everything needed on the NAS. It is run **once** as root on the BaluNode host. It is idempotent: safe to re-run if a step fails or to refresh the runner registration.

- [ ] **Step 1: Create the script file with the full content below**

The file MUST be created with LF line endings (Unix shell scripts; CRLF would break the shebang on some Bash configurations). Set the executable bit after writing.

```bash
#!/usr/bin/env bash
# bootstrap-ci-runner.sh
#
# Provision the BaluHost CI sandbox runner on the NAS.
#
# - Creates an unprivileged 'ci-runner' Linux user (no sudo, no production read access).
# - Installs Podman and rootless prerequisites.
# - Configures subuid/subgid + systemd lingering for rootless containers.
# - Installs and registers a GitHub Actions self-hosted runner instance as 'ci-runner'
#   with labels: self-hosted,Linux,X64,ci-sandbox.
# - Pre-pulls docker.io/library/python:3.11-slim into ci-runner's storage.
# - Runs self-tests; aborts with a clear error if any isolation guarantee is violated.
#
# Idempotent: safe to re-run.
#
# Usage:
#   sudo ./bootstrap-ci-runner.sh --token <RUNNER_REGISTRATION_TOKEN>
#
# Get the token from: https://github.com/Xveyn/BaluHost/settings/actions/runners/new
# (Click "New self-hosted runner", copy the value passed to --token in the displayed
# config.sh command. Token is single-use, expires in ~1 hour.)
#
# Reference: docs/superpowers/specs/2026-05-19-self-hosted-backend-tests-design.md

set -euo pipefail

# ---------- Configuration ----------
RUNNER_USER="ci-runner"
RUNNER_HOME="/var/lib/ci-runner"
RUNNER_WORK="${RUNNER_HOME}/_work"
RUNNER_DIR="${RUNNER_HOME}/runner"
REPO_URL="https://github.com/Xveyn/BaluHost"
RUNNER_LABELS="self-hosted,Linux,X64,ci-sandbox"
RUNNER_NAME="${RUNNER_NAME:-BaluNode-ci-sandbox}"
TEST_IMAGE="docker.io/library/python:3.11-slim"
SUBUID_RANGE="100000-165535"
SUBGID_RANGE="100000-165535"

# ---------- Arg parsing ----------
RUNNER_TOKEN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --token) RUNNER_TOKEN="$2"; shift 2 ;;
    --name)  RUNNER_NAME="$2";  shift 2 ;;
    -h|--help)
      sed -n '1,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "ERROR: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: must be run as root (sudo)." >&2
  exit 1
fi

if [[ -z "$RUNNER_TOKEN" ]]; then
  echo "ERROR: --token is required. Get one from $REPO_URL/settings/actions/runners/new" >&2
  exit 2
fi

log() { echo "[bootstrap-ci-runner] $*"; }
as_runner() { sudo -u "$RUNNER_USER" -H "$@"; }

# ---------- Step 1: install packages ----------
log "Installing system packages (podman, uidmap, slirp4netns, fuse-overlayfs, dbus-user-session)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  podman uidmap slirp4netns fuse-overlayfs dbus-user-session \
  curl tar ca-certificates jq

# ---------- Step 2: create ci-runner user ----------
if id -u "$RUNNER_USER" >/dev/null 2>&1; then
  log "User '$RUNNER_USER' already exists; reusing."
else
  log "Creating user '$RUNNER_USER' with home '$RUNNER_HOME'..."
  useradd --system --create-home --home-dir "$RUNNER_HOME" \
          --shell /bin/bash "$RUNNER_USER"
fi

# Defensive: ensure NOT in docker/sudo/baluhost groups (even if added previously).
for grp in docker sudo wheel baluhost; do
  if id -nG "$RUNNER_USER" | tr ' ' '\n' | grep -qx "$grp"; then
    log "Removing '$RUNNER_USER' from group '$grp' (isolation requirement)."
    gpasswd -d "$RUNNER_USER" "$grp" || true
  fi
done

mkdir -p "$RUNNER_WORK"
chown -R "$RUNNER_USER:$RUNNER_USER" "$RUNNER_HOME"
chmod 0750 "$RUNNER_HOME"

# ---------- Step 3: subuid/subgid ----------
log "Configuring subuid/subgid (range $SUBUID_RANGE)..."
if ! grep -q "^${RUNNER_USER}:" /etc/subuid; then
  usermod --add-subuids "$SUBUID_RANGE" "$RUNNER_USER"
fi
if ! grep -q "^${RUNNER_USER}:" /etc/subgid; then
  usermod --add-subgids "$SUBGID_RANGE" "$RUNNER_USER"
fi

# ---------- Step 4: systemd lingering ----------
log "Enabling systemd lingering for '$RUNNER_USER'..."
loginctl enable-linger "$RUNNER_USER"

# ---------- Step 5: GitHub Actions runner agent ----------
if [[ -x "$RUNNER_DIR/config.sh" ]] && [[ -f "$RUNNER_DIR/.runner" ]]; then
  log "Runner agent already installed; skipping download. Re-registration follows."
else
  log "Downloading latest GitHub Actions Runner..."
  install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0750 "$RUNNER_DIR"
  ASSET_URL=$(curl -sSL https://api.github.com/repos/actions/runner/releases/latest \
              | jq -r '.assets[] | select(.name | test("actions-runner-linux-x64.*\\.tar\\.gz$")) | .browser_download_url')
  if [[ -z "$ASSET_URL" || "$ASSET_URL" == "null" ]]; then
    echo "ERROR: could not resolve latest runner asset URL." >&2
    exit 1
  fi
  log "Fetching $ASSET_URL"
  as_runner bash -c "curl -sSL '$ASSET_URL' -o '$RUNNER_DIR/runner.tar.gz' && tar -xzf '$RUNNER_DIR/runner.tar.gz' -C '$RUNNER_DIR' && rm '$RUNNER_DIR/runner.tar.gz'"
fi

# (Re-)register against the repo. If a previous registration exists, remove it first.
if [[ -f "$RUNNER_DIR/.runner" ]]; then
  log "Removing previous runner registration (best-effort)..."
  as_runner bash -c "cd '$RUNNER_DIR' && ./config.sh remove --unattended --token '$RUNNER_TOKEN'" || true
fi

log "Registering runner '$RUNNER_NAME' with labels '$RUNNER_LABELS'..."
as_runner bash -c "cd '$RUNNER_DIR' && ./config.sh --unattended \
  --url '$REPO_URL' \
  --token '$RUNNER_TOKEN' \
  --name '$RUNNER_NAME' \
  --labels '$RUNNER_LABELS' \
  --work '_work' \
  --replace"

# Install + start the systemd service for the runner. svc.sh requires root because
# it writes a unit file under /etc/systemd/system; the unit itself runs as ci-runner.
log "Installing runner systemd service..."
( cd "$RUNNER_DIR" && ./svc.sh install "$RUNNER_USER" )
( cd "$RUNNER_DIR" && ./svc.sh start )

# ---------- Step 6: pre-pull test image ----------
log "Pre-pulling $TEST_IMAGE as $RUNNER_USER (first pull, ~50 MB)..."
as_runner podman pull "$TEST_IMAGE"

# ---------- Step 7: self-tests ----------
log "Running isolation self-tests..."

fail() { echo "::error::SELF-TEST FAILED: $*" >&2; exit 1; }

# 7a: ci-runner cannot read .env.production (POSIX layer A).
if as_runner cat /opt/baluhost/.env.production >/dev/null 2>&1; then
  fail "ci-runner can read /opt/baluhost/.env.production — POSIX isolation broken."
fi
log "  [OK] ci-runner cannot read /opt/baluhost/.env.production"

# 7b: ci-runner has no sudo.
if as_runner sudo -n true >/dev/null 2>&1; then
  fail "ci-runner has passwordless sudo — must not."
fi
log "  [OK] ci-runner has no sudo"

# 7c: ci-runner not in docker/sudo/wheel groups.
RUNNER_GROUPS=$(id -nG "$RUNNER_USER")
for grp in docker sudo wheel; do
  if echo "$RUNNER_GROUPS" | tr ' ' '\n' | grep -qx "$grp"; then
    fail "ci-runner is in group '$grp' — must not be."
  fi
done
log "  [OK] ci-runner not in docker/sudo/wheel groups (current: $RUNNER_GROUPS)"

# 7d: rootless podman works.
HELLO_OUT=$(as_runner podman run --rm docker.io/library/hello-world 2>&1 || true)
if ! echo "$HELLO_OUT" | grep -q "Hello from Docker"; then
  fail "rootless podman hello-world failed. Output:
$HELLO_OUT"
fi
log "  [OK] rootless podman runs hello-world as $RUNNER_USER"

# 7e: container cannot see /opt/baluhost (no bind-mount).
ESCAPE_TRY=$(as_runner podman run --rm "$TEST_IMAGE" ls /opt/baluhost 2>&1 || true)
if ! echo "$ESCAPE_TRY" | grep -qE "No such file|cannot access"; then
  fail "container could enumerate /opt/baluhost — should be invisible. Output:
$ESCAPE_TRY"
fi
log "  [OK] container cannot see /opt/baluhost"

# 7f: GitHub Actions runner service is active.
SVC_NAME="actions.runner.Xveyn-BaluHost.${RUNNER_NAME}.service"
if ! systemctl is-active --quiet "$SVC_NAME"; then
  fail "runner service '$SVC_NAME' is not active. Check: systemctl status $SVC_NAME"
fi
log "  [OK] $SVC_NAME is active"

log "All self-tests passed. Runner '$RUNNER_NAME' is online."
log "Verify via: gh api repos/Xveyn/BaluHost/actions/runners"
```

Save the file to `D:/Programme (x86)/Baluhost/scripts/bootstrap-ci-runner.sh`.

- [ ] **Step 2: Set the executable bit and ensure LF line endings**

On Windows (current working environment), git may convert LF→CRLF. Configure this file to stay LF:

```bash
# From the repo root
git config core.autocrlf input # one-time, repo-local — does not affect other files retroactively
printf '%s\n' '*.sh text eol=lf' >> .gitattributes 2>/dev/null || true
# If .gitattributes does not yet exist OR does not contain the rule, append it.
```

Check if `.gitattributes` already covers `*.sh`:

```bash
grep -E '^\*\.sh ' .gitattributes 2>/dev/null || echo "Need to add *.sh text eol=lf to .gitattributes"
```

If a rule is missing, add it. Then re-checkout the script to apply:

```bash
git add .gitattributes
git rm --cached scripts/bootstrap-ci-runner.sh 2>/dev/null || true
git add scripts/bootstrap-ci-runner.sh
```

Set the executable bit so git records it as executable:

```bash
git update-index --chmod=+x scripts/bootstrap-ci-runner.sh
```

- [ ] **Step 3: Syntax-check the script**

Run:

```bash
bash -n scripts/bootstrap-ci-runner.sh
```

Expected: no output, exit code 0.

- [ ] **Step 4: ShellCheck (if available)**

ShellCheck is not required but recommended. Try:

```bash
shellcheck scripts/bootstrap-ci-runner.sh
```

If ShellCheck isn't installed locally, skip — this is a best-effort check; the NAS will run the script regardless. If it IS installed: address any warnings. Common ones (`SC2086` quoting) — fix; `SC2002` (useless cat) — fix; `SC2155` (declare + assign on one line) — fix.

- [ ] **Step 5: Commit**

```bash
git add scripts/bootstrap-ci-runner.sh .gitattributes
git commit -m "feat(ci): bootstrap script for ci-runner sandbox

Provisions an unprivileged 'ci-runner' Linux user with Podman rootless,
registers a self-hosted GitHub Actions runner with the 'ci-sandbox'
label, and runs isolation self-tests (no sudo, no .env.production read,
container cannot see host filesystem).

Idempotent. Run once on the NAS as root."
```

---

## Task 2: Update `.github/CODEOWNERS`

**Files:**
- Modify: `.github/CODEOWNERS`

- [ ] **Step 1: Add the new bootstrap script to Xveyn-owned paths**

Insert immediately after the existing `bootstrap-runner-ubuntu.sh` line:

```text
/scripts/bootstrap-ci-runner.sh      @Xveyn
```

The resulting block under "Deploy scripts, systemd units, sudoers templates, runner bootstrap" should read:

```text
# Deploy scripts, systemd units, sudoers templates, runner bootstrap
/deploy/             @Xveyn
/scripts/bootstrap-runner-ubuntu.sh  @Xveyn
/scripts/bootstrap-ci-runner.sh      @Xveyn
```

- [ ] **Step 2: Commit**

```bash
git add .github/CODEOWNERS
git commit -m "chore(codeowners): own scripts/bootstrap-ci-runner.sh"
```

---

## Task 3: Update `.claude/rules/ci-cd-security.md`

**Files:**
- Modify: `.claude/rules/ci-cd-security.md`

This is the source of truth for the trust model. Five edits, applied sequentially.

- [ ] **Step 1: Update Layer 1 owned-paths list**

Find the block:

```markdown
Owned paths:
- `/.github/workflows/` — every workflow definition
- `/.github/CODEOWNERS` — meta-protect the file itself
- `/deploy/` — deploy scripts, systemd units, sudoers templates, nginx config
- `/scripts/bootstrap-runner-ubuntu.sh` — runner provisioning
- `/.claude/rules/ci-cd-security.md` — these rules
- `/.claude/rules/security.md`, `/.claude/rules/security-agent.md`
```

Replace with:

```markdown
Owned paths:
- `/.github/workflows/` — every workflow definition
- `/.github/CODEOWNERS` — meta-protect the file itself
- `/deploy/` — deploy scripts, systemd units, sudoers templates, nginx config
- `/scripts/bootstrap-runner-ubuntu.sh` — VM runner provisioning (legacy)
- `/scripts/bootstrap-ci-runner.sh` — sandbox CI runner provisioning (ci-sandbox label)
- `/.claude/rules/ci-cd-security.md` — these rules
- `/.claude/rules/security.md`, `/.claude/rules/security-agent.md`
```

- [ ] **Step 2: Update Layer 2 runner-trigger table**

Find the workflow table under "### Layer 2 — Runner Trigger Separation" and replace the `ci-check.yml` row:

```markdown
| `ci-check.yml` | `ubuntu-latest` | `pull_request`, `workflow_call` |
```

with:

```markdown
| `ci-check.yml` `frontend-build` | `ubuntu-latest` | `pull_request`, `workflow_call` |
| `ci-check.yml` `backend-tests` | **`self-hosted, ci-sandbox`** (rootless Podman) | `pull_request` (gated by `ci-tests` env), `workflow_call` (ungated) |
```

Then update the paragraph below the table. Find:

```markdown
PR-triggered workflows MUST use GitHub-hosted runners — code from a fork PR could otherwise execute on the production host. Self-hosted runners only see code that has already landed on `main` (via auto-merge through Layer 4) or that an authorized actor explicitly dispatched.
```

Replace with:

```markdown
PR-triggered workflows MUST NOT use the production-privileged `BaluNode` runner. The `ci-sandbox` runner is the **only** self-hosted runner permitted to execute PR-triggered code, and only via the two-layer isolation described below.

Self-hosted production runners (`BaluNode`) only see code that has already landed on `main` (via auto-merge through Layer 4) or that an authorized actor explicitly dispatched.

**Sandbox runner: two-layer isolation.** The `ci-sandbox` runner (provisioned by `scripts/bootstrap-ci-runner.sh`) provides:

- **Layer A — POSIX user isolation.** Runner agent runs as `ci-runner`, an unprivileged Linux user with no sudo entry, no membership in `docker`/`sudo`/`wheel` groups, and no read access to `/opt/baluhost`, `/etc/baluhost`, or any production secrets. Confirmed at provisioning time by self-tests in the bootstrap script.
- **Layer B — Rootless Podman container.** Untrusted code (`pip install`, `pytest`, anything in the PR) never executes directly on the runner host. Workflows wrap the test invocation in `podman run --rm` against a pinned image (`docker.io/library/python:3.11-slim`), with only the workspace bind-mounted. The container sees no host filesystem outside the bind-mount; container-root is mapped to `ci-runner`'s subuid range. No Docker daemon, no `/var/run/docker.sock`, no `docker` group.

A workflow on `ci-sandbox` that runs `pip install` directly on the runner host (instead of inside `podman run`) breaks Layer B. The Reviewer Checklist below catches this.
```

- [ ] **Step 3: Update Layer 4 environments section**

Find the table under "### Layer 4 — `production` Environment". After the existing table for `production`, append a new subsection:

```markdown
#### `ci-tests` Environment

Gates PR-triggered backend test runs on `ci-sandbox`. Configured in GitHub repo settings.

| Setting | Required value | Verified state |
|---|---|---|
| Required reviewers | `Xveyn` | check `gh api repos/Xveyn/BaluHost/environments/ci-tests` |
| `prevent_self_review` | `false` (solo dev) | check above |
| Wait timer | 0 | check above |
| Deployment branches and tags | All branches | check above |
| `can_admins_bypass` | `false` | check above |

The `backend-tests` job declares `environment: ci-tests` conditionally on `github.event_name == 'pull_request'`. PR runs pause for Xveyn approval; `workflow_call` runs (from `deploy-production.yml` after auto-merge) execute immediately because the code is already trusted at that point.
```

- [ ] **Step 4: Update "Repo Settings to Verify" table**

Find the table under "## Repo Settings to Verify". Insert a new row after the `Production environment` row:

```markdown
| `ci-tests` environment | `gh api repos/Xveyn/BaluHost/environments/ci-tests` | `protection_rules` includes `required_reviewers` (Xveyn), `can_admins_bypass: false` |
```

Then update the `Self-hosted runner` row to reflect that there are now two runners:

Replace:

```markdown
| Self-hosted runner | `gh api repos/Xveyn/BaluHost/actions/runners` | Runner `BaluNode` online with labels `self-hosted, Linux, X64` |
```

with:

```markdown
| Self-hosted runners | `gh api repos/Xveyn/BaluHost/actions/runners` | `BaluNode` online (`self-hosted, Linux, X64`) and `BaluNode-ci-sandbox` online (`self-hosted, Linux, X64, ci-sandbox`) |
```

- [ ] **Step 5: Update Reviewer Checklist**

Find the section "## Reviewer Checklist". Add two new bullets after the existing "Runner change" bullet:

```markdown
- [ ] **Sandbox host-direct execution**: Does a workflow on `ci-sandbox` run `pip install`, `npm install`, or any untrusted code directly on the runner host (not inside `podman run`)? If yes — block. That breaks Layer B isolation.
- [ ] **PR gate**: Does a workflow on `ci-sandbox` triggered by `pull_request` have `environment: ci-tests` (or equivalent approval gate)? If yes — proceed. If no — block.
```

- [ ] **Step 6: Update Known Gaps**

Find "## Known Gaps & Accepted Risks". Replace gap #2:

```markdown
2. **Self-hosted runner is shared with the production host** — `runs-on: self-hosted` has full access to `/opt/baluhost`, `.env.production`, and `sudo` rules in `/etc/sudoers.d/baluhost-deploy`. There is no sandboxing. This is acceptable only because Layers 1–4 ensure no untrusted code ever reaches this runner.
```

with:

```markdown
2. **Two self-hosted runners with different trust levels on one host**:
    - `BaluNode` (`self-hosted, Linux, X64`) — runs production deploys. Full access to `/opt/baluhost`, `.env.production`, sudo entries. Never sees PR code (Layer 2 prohibition + workflows pin to label `ci-sandbox` for PR work).
    - `BaluNode-ci-sandbox` (`self-hosted, Linux, X64, ci-sandbox`) — runs `backend-tests` for PRs. Runs as `ci-runner` (no sudo, no production read), wraps test execution in rootless Podman. Even if a PR is maliciously approved at the `ci-tests` gate, blast radius is limited to the container workdir and outbound network (see gap #11).
    Both runners share the host kernel. A kernel-namespace escape from the Podman container would land as `ci-runner` on the host — still without sudo or production access. The bootstrap script's self-tests must pass for these guarantees to hold.
```

Then add a new gap at the end:

```markdown
11. **`ci-runner` and its containers have unrestricted egress** — A maliciously approved PR can exfiltrate the workdir contents and make outbound calls to arbitrary hosts. Mitigations: the `ci-tests` environment gate (manual approval), the limited blast radius (workdir contains only PR code), no production secrets reachable. Future tightening: egress firewall allowing only `pypi.org`, `files.pythonhosted.org`, `api.github.com`, `objects.githubusercontent.com`, `registry.docker.io`.
```

- [ ] **Step 7: Commit**

```bash
git add .claude/rules/ci-cd-security.md
git commit -m "docs(security): document ci-sandbox runner and ci-tests environment

Two-layer isolation: ci-runner POSIX user + rootless Podman container.
Updates Layer 2 table, adds ci-tests environment to Layer 4, expands
Reviewer Checklist with sandbox-specific bullets, splits Known Gap #2
into BaluNode (production) and ci-sandbox (PR tests), adds new gap
for unrestricted container egress."
```

---

## Task 4: Update `.github/workflows/ci-check.yml`

**Files:**
- Modify: `.github/workflows/ci-check.yml`

This is the workflow change. We implement Pattern A (conditional environment expression). If the post-merge smoke test in Task 7 shows Pattern A doesn't work, Task 7 includes the fallback to Pattern B.

- [ ] **Step 1: Replace the `backend-tests` job**

The full new file content:

```yaml
name: CI Check

on:
  pull_request:
    branches: [main, development]
  push:
    branches: [development]
  workflow_call:

jobs:
  backend-tests:
    runs-on: [self-hosted, ci-sandbox]
    environment: ${{ github.event_name == 'pull_request' && 'ci-tests' || '' }}
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - name: Assert runner identity (defense-in-depth tripwire)
        run: |
          set -euo pipefail
          test "$(whoami)" = "ci-runner" || { echo "::error::Runner not running as ci-runner (got: $(whoami))"; exit 1; }
          test "$(id -u)" -ne 0 || { echo "::error::Runner running as root"; exit 1; }
          command -v podman >/dev/null || { echo "::error::podman not installed on runner host"; exit 1; }
          # Confirm ci-runner is NOT in docker/sudo/wheel.
          for grp in docker sudo wheel; do
            if id -nG "$(whoami)" | tr ' ' '\n' | grep -qx "$grp"; then
              echo "::error::ci-runner is in group '$grp' — isolation broken"
              exit 1
            fi
          done
          echo "Identity OK: $(whoami) uid=$(id -u) groups=$(id -nG)"

      - name: Run backend tests in rootless Podman container
        env:
          TEST_IMAGE: docker.io/library/python:3.11-slim
        run: |
          set -euo pipefail
          podman run --rm \
            --network=bridge \
            -v "${{ github.workspace }}:/work:Z" \
            -w /work/backend \
            -e NAS_MODE=dev \
            "$TEST_IMAGE" \
            bash -c "set -euo pipefail; pip install --no-cache-dir -e '.[dev]' && python -m pytest -q --timeout=120 -n auto --no-cov"

  frontend-build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: client/package-lock.json

      - name: Install dependencies
        working-directory: client
        run: npm ci

      - name: Build
        working-directory: client
        run: npm run build

      - name: Run unit tests
        working-directory: client
        run: npx vitest run
```

Notes for the implementer:
- The conditional `environment:` expression resolves to the literal string `'ci-tests'` on `pull_request` events and to `''` (empty string) on `workflow_call` and `push` events. GitHub's documented behavior is to treat an empty-string environment as "no environment". If Task 7's smoke test shows this is broken, Task 7 contains the Pattern B fallback.
- `--network=bridge` is Podman's rootless default; explicit for clarity. If the network ever needs to be `slirp4netns` mode (older kernels), the bootstrap script installs `slirp4netns` already.
- `:Z` SELinux relabel on the bind-mount is a no-op on Debian 13 (AppArmor instead of SELinux) but harmless — kept for portability.
- The `--no-cache-dir` on `pip install` avoids cluttering the container's tmpfs; speed difference is negligible.

- [ ] **Step 2: Lint with actionlint (if available)**

```bash
actionlint .github/workflows/ci-check.yml
```

If actionlint is not installed: skip; we'll catch issues in Task 7. If you want to install it locally: `go install github.com/rhysd/actionlint/cmd/actionlint@latest`.

- [ ] **Step 3: Validate YAML parses**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci-check.yml'))"
```

Expected: no output, exit code 0.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci-check.yml
git commit -m "ci: move backend-tests to ci-sandbox runner with rootless Podman

backend-tests now runs on the self-hosted 'ci-sandbox' runner, executing
pip install + pytest inside docker.io/library/python:3.11-slim via
'podman run --rm'. Pull-request triggers pause for approval via the new
'ci-tests' environment; workflow_call (from deploy-production.yml)
bypasses the gate.

frontend-build unchanged."
```

---

## Task 5: MANUAL — Provision the NAS host

**Where:** SSH session on the BaluNode NAS.

**Prerequisite:** Push the branch and copy the bootstrap script onto the NAS. Easiest path: `git pull` the feature branch from the NAS itself if the repo is already checked out there, OR `scp` the file.

- [ ] **Step 1: Generate a runner registration token**

Open in browser: `https://github.com/Xveyn/BaluHost/settings/actions/runners/new`

Choose Linux x64. Copy the value passed to `./config.sh --token <VALUE>` in the displayed command. The token is single-use and expires in ~1 hour.

Alternative via CLI (if you have admin scope on `gh`):

```bash
gh api -X POST repos/Xveyn/BaluHost/actions/runners/registration-token --jq .token
```

- [ ] **Step 2: Copy the bootstrap script to the NAS**

From your local repo (Windows):

```bash
scp "scripts/bootstrap-ci-runner.sh" balunode:/tmp/bootstrap-ci-runner.sh
```

Or if you maintain a git checkout on the NAS: pull the branch and use the script in place.

- [ ] **Step 3: Run the bootstrap script as root**

On the NAS:

```bash
sudo bash /tmp/bootstrap-ci-runner.sh --token <TOKEN_FROM_STEP_1>
```

Expected output ends with:

```
[bootstrap-ci-runner] All self-tests passed. Runner 'BaluNode-ci-sandbox' is online.
[bootstrap-ci-runner] Verify via: gh api repos/Xveyn/BaluHost/actions/runners
```

If any self-test fails: the script aborts with `::error::SELF-TEST FAILED: ...`. Read the message, fix the underlying issue (most likely: stale group memberships, sudoers misconfig from a previous attempt), and re-run.

- [ ] **Step 4: Verify both runners are online**

From your workstation:

```bash
gh api repos/Xveyn/BaluHost/actions/runners --jq '.runners[] | {name, status, labels: [.labels[].name]}'
```

Expected: two entries, both `"status": "online"`. The new one has labels including `ci-sandbox`.

---

## Task 6: MANUAL — Create the `ci-tests` GitHub Environment

**Where:** GitHub repo settings UI, or via `gh api` PUT.

- [ ] **Step 1: Create the environment via API**

Fetch Xveyn's numeric user id, then PUT the environment with full JSON body (more reliable than gh's `-f` array syntax for nested fields):

```bash
XVEYN_ID=$(gh api users/Xveyn --jq .id)
echo "Xveyn id: $XVEYN_ID"

gh api --method PUT repos/Xveyn/BaluHost/environments/ci-tests \
  --input - <<EOF
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "can_admins_bypass": false,
  "reviewers": [
    { "type": "User", "id": $XVEYN_ID }
  ]
}
EOF
```

Expected: JSON describing the new environment with `protection_rules` containing a `required_reviewers` entry.

If the command errors with "Bad credentials" or similar: your `gh` token may not have the `repo` scope with admin privileges. Re-auth with `gh auth refresh -s repo` or use a PAT explicitly.

- [ ] **Step 2: Restrict deployments to protected branches (optional but recommended)**

```bash
gh api --method PUT repos/Xveyn/BaluHost/environments/ci-tests/deployment-branch-policies \
  -f protected_branches=true \
  -f custom_branch_policies=false 2>/dev/null || true
```

Note: GitHub's API for branch-policy on environments has changed shape over the years. If the above fails, fall back to the UI: go to `Settings → Environments → ci-tests`, scroll to "Deployment branches and tags", select "All branches" (since PRs can come from any branch). The required-reviewer is the real gate; branch policy is defense-in-depth.

- [ ] **Step 3: Verify the environment settings**

```bash
gh api repos/Xveyn/BaluHost/environments/ci-tests --jq '{name, protection_rules: [.protection_rules[] | {type, reviewers: (.reviewers // [])}]}'
```

Expected: at least one protection rule of type `required_reviewers` with Xveyn in the reviewer list.

---

## Task 7: End-to-end verification via draft PR

**Files:** none (verification only)

- [ ] **Step 1: Push the branch and open a DRAFT PR**

```bash
git push -u origin feat/ci-self-hosted-backend-tests
gh pr create --draft \
  --title "feat(ci): self-hosted backend tests with rootless Podman sandbox" \
  --body "Implements docs/superpowers/specs/2026-05-19-self-hosted-backend-tests-design.md. Draft until E2E verification on the new ci-sandbox runner is complete."
```

- [ ] **Step 2: Observe CI Check run**

Watch the new run:

```bash
gh pr checks --watch
```

Two jobs appear: `frontend-build` (on ubuntu-latest, runs immediately) and `backend-tests` (on ci-sandbox).

Expected for `backend-tests`:
- Status starts as "Waiting" with a deployment-protection-rule pending — GitHub Actions UI shows "Waiting for review on ci-tests".

If Pattern A is broken (the empty-string `environment: ''` causes GitHub to look up an environment named "", which would error or behave oddly), you'll see one of:
- The job fails immediately with "Environment '' not found" or similar.
- The job runs without waiting for approval (empty string treated as "no environment" — desired).

If Pattern A fails, **skip to Step 6** for the Pattern B fallback. If Pattern A works, continue.

- [ ] **Step 3: Approve the deployment**

In the GitHub UI for the PR, click "Review deployments" → check `ci-tests` → "Approve and deploy".

Or via CLI:

```bash
RUN_ID=$(gh run list --branch feat/ci-self-hosted-backend-tests --workflow="CI Check" --limit 1 --json databaseId --jq '.[0].databaseId')
gh api repos/Xveyn/BaluHost/actions/runs/"$RUN_ID"/pending_deployments \
  --jq '.[] | .environment.id' | while read env_id; do
    gh api --method POST repos/Xveyn/BaluHost/actions/runs/"$RUN_ID"/pending_deployments \
      -f "environment_ids[]=$env_id" -f state=approved -f comment="smoke test"
  done
```

- [ ] **Step 4: Verify the job runs on ci-sandbox and tests pass**

```bash
gh run watch "$RUN_ID"
```

In the run logs, the "Assert runner identity" step must show:

```
Identity OK: ci-runner uid=<non-zero> groups=ci-runner
```

The "Run backend tests in rootless Podman container" step must show pytest output ending with a passing summary.

If `whoami` shows `runner` (not `ci-runner`): the workflow landed on `BaluNode` instead of `ci-sandbox`. The label `ci-sandbox` must be missing on the new runner or stale on `BaluNode`. Fix: `gh api repos/Xveyn/BaluHost/actions/runners --jq '.runners[] | {name, labels: [.labels[].name]}'` and adjust labels in the runner's GitHub settings UI.

If the container can't pull `python:3.11-slim` (network error): ensure the NAS has outbound HTTPS to `registry-1.docker.io` and `auth.docker.io`.

- [ ] **Step 5: Verify the deploy-production.yml workflow_call path (Pattern A specific)**

After step 4 succeeds, the most important regression to check is that the `workflow_call` from `deploy-production.yml` still works WITHOUT requiring approval (Pattern A's conditional must resolve to no-environment for workflow_call).

We can't safely merge this draft PR yet (untested deploy path), so simulate the call. Open a temporary disposable PR with a NO-OP change:

```bash
git checkout main
git checkout -b ci-test-workflow-call-noop
echo "# ci probe $(date -u +%FT%TZ)" >> docs/CI_PROBE.md
git add docs/CI_PROBE.md
git commit -m "chore: probe workflow_call path for ci-tests env"
git push -u origin ci-test-workflow-call-noop
gh pr create --title "chore: probe workflow_call path" --body "Disposable. Will close without merging."
```

Wait for CI Check to run on this disposable PR with the **OLD** ci-check.yml (since the spec-branch changes aren't on main yet). Confirm it still goes green. Then close without merging:

```bash
gh pr close ci-test-workflow-call-noop --delete-branch
```

This isn't actually a Pattern A verification — it's a sanity check that nothing OTHER than what we changed is broken. The real Pattern A vs workflow_call verification happens AFTER the feature PR merges (Step 7 below).

- [ ] **Step 6: Pattern B fallback (only if Pattern A failed in Step 2)**

Replace the `backend-tests` block in `.github/workflows/ci-check.yml` with two jobs sharing a composite action.

First, create `.github/actions/run-backend-tests/action.yml`:

```yaml
name: Run backend tests
description: Identity tripwire + rootless Podman pytest

runs:
  using: composite
  steps:
    - name: Assert runner identity (defense-in-depth tripwire)
      shell: bash
      run: |
        set -euo pipefail
        test "$(whoami)" = "ci-runner" || { echo "::error::Runner not running as ci-runner (got: $(whoami))"; exit 1; }
        test "$(id -u)" -ne 0 || { echo "::error::Runner running as root"; exit 1; }
        command -v podman >/dev/null || { echo "::error::podman not installed on runner host"; exit 1; }
        for grp in docker sudo wheel; do
          if id -nG "$(whoami)" | tr ' ' '\n' | grep -qx "$grp"; then
            echo "::error::ci-runner is in group '$grp' — isolation broken"
            exit 1
          fi
        done
        echo "Identity OK: $(whoami) uid=$(id -u) groups=$(id -nG)"

    - name: Run backend tests in rootless Podman container
      shell: bash
      env:
        TEST_IMAGE: docker.io/library/python:3.11-slim
      run: |
        set -euo pipefail
        podman run --rm \
          --network=bridge \
          -v "${{ github.workspace }}:/work:Z" \
          -w /work/backend \
          -e NAS_MODE=dev \
          "$TEST_IMAGE" \
          bash -c "set -euo pipefail; pip install --no-cache-dir -e '.[dev]' && python -m pytest -q --timeout=120 -n auto --no-cov"
```

Then replace the `backend-tests` block in `ci-check.yml` with:

```yaml
  backend-tests-pr:
    if: github.event_name == 'pull_request'
    runs-on: [self-hosted, ci-sandbox]
    environment: ci-tests
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/run-backend-tests

  backend-tests-trusted:
    if: github.event_name != 'pull_request'
    runs-on: [self-hosted, ci-sandbox]
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/run-backend-tests
```

Important: GitHub's required-status-check on `main` branch protection currently lists `backend-tests` as a required check. With Pattern B, the check name changes. Update branch protection:

```bash
gh api repos/Xveyn/BaluHost/branches/main/protection/required_status_checks --jq .contexts
```

Expected today: `["backend-tests", "frontend-build"]`. After Pattern B, replace with `["backend-tests-pr", "frontend-build"]` (PR runs are what gate auto-merge; `backend-tests-trusted` only runs after merge).

```bash
gh api --method PATCH repos/Xveyn/BaluHost/branches/main/protection/required_status_checks \
  -f contexts[]=backend-tests-pr -f contexts[]=frontend-build -F strict=true
```

Commit:

```bash
git add .github/workflows/ci-check.yml .github/actions/run-backend-tests/action.yml
git commit -m "ci: fall back to split-jobs pattern for conditional ci-tests env

Pattern A (conditional environment expression) failed smoke test —
GitHub did not treat the empty-string environment as 'no environment'.
Pattern B splits into backend-tests-pr (gated) and backend-tests-trusted
(ungated, for workflow_call), sharing the test logic via a composite
action."
```

- [ ] **Step 7: Mark PR ready for review**

```bash
gh pr ready
```

- [ ] **Step 8: Verify auto-merge fires after self-approval**

The PR has Layer 4 production approval but no Layer 2-equivalent on auto-merge. Once CI Check concludes green, `auto-merge.yml` should fire, merge to main, and trigger `deploy-production.yml`. **THIS deploys to production.** Make sure that's intended for this PR (it is — this is the deploy of the new CI setup itself).

Watch the merge:

```bash
gh pr view --json mergedAt,state
```

After merge:

```bash
gh run watch  # pick the new deploy-production.yml run; approve at the production env gate
```

Confirm `ci-check` job inside `deploy-production.yml` runs on `ci-sandbox` WITHOUT pausing for ci-tests approval (this is the real Pattern A workflow_call verification).

---

## Task 8: Post-merge cleanup

**Files:**
- None (verification + monitoring)

- [ ] **Step 1: Measure**

Capture timing of the first 3 PR runs on `ci-sandbox`:

```bash
gh run list --workflow "CI Check" --branch '!main' --limit 3 --json databaseId,createdAt,updatedAt --jq '.[] | {id: .databaseId, duration_seconds: ((.updatedAt | fromdate) - (.createdAt | fromdate))}'
```

Target: ≤ 180 seconds (3 min) per backend-tests step. If consistently > 240s, investigate (likely: pip install dominates; consider pre-built test image — see spec Open Question 2).

- [ ] **Step 2: Update `production.md` performance notes** (if numbers warrant)

If timing is on-target, no update needed. If you publish a pre-built test image later, note it in `.claude/rules/production.md` under a new "CI Performance" subsection.

- [ ] **Step 3: Move the design + plan docs out of "specs/plans" into permanent docs (optional)**

If the team treats `docs/superpowers/specs/` as throwaway, copy the spec to `docs/ci-cd/sandbox-runner.md` and link from `.claude/rules/ci-cd-security.md`. **Recommendation: defer this. The spec is fine where it is.**

---

## Self-Review

This section is a checklist I run on the plan against the spec. Findings are inlined as fixes above; this section documents that the check happened.

**1. Spec coverage check:**

| Spec section | Covered by task(s) |
|---|---|
| Approach §1 (new isolated runner `ci-sandbox`) | Task 1 (bootstrap script), Task 5 (manual NAS provisioning) |
| Approach §2 (manual `ci-tests` environment gate) | Task 4 (Pattern A in workflow), Task 6 (env creation), Task 7 §6 (Pattern B fallback) |
| Approach §3 (Podman rootless container execution) | Task 1 (image prefetch), Task 4 (`podman run` wrapper) |
| What "isolated" means (both layers) | Task 1 self-tests (Layer A), Task 4 identity tripwire (Layer A re-check), `podman run` invocation (Layer B) |
| Trust Model — After Change | Task 3 (security.md updates) |
| Components → ci-check.yml | Task 4 |
| Components → bootstrap-ci-runner.sh | Task 1 |
| Components → ci-cd-security.md | Task 3 |
| Components → CODEOWNERS | Task 2 |
| Out-of-repo: bootstrap on NAS | Task 5 |
| Out-of-repo: create ci-tests environment | Task 6 |
| Data Flow — PR push | Task 7 §1-§4 verify this end-to-end |
| Data Flow — Deploy from main | Task 7 §8 verifies the workflow_call ungated path |
| Failure modes | Task 1 self-tests cover most; Task 7 covers Pattern A failure mode explicitly |
| Testing | Task 7 (pre-merge), Task 8 (post-merge) |
| Open Questions | Deferred per spec ("recommendation: defer"); Open Question 2 (pre-built image) revisited in Task 8 §1 |
| Decision Log | No tasks needed (rationale only) |

No gaps.

**2. Placeholder scan:** none found. All steps include exact commands, file contents, and expected output.

**3. Type/name consistency:** `ci-runner` (user) / `ci-sandbox` (label) / `BaluNode-ci-sandbox` (runner display name) / `ci-tests` (environment) used consistently throughout. `python:3.11-slim` image referenced identically in Task 1 (prefetch), Task 4 (workflow), Task 7 §6 (Pattern B). The composite-action path `.github/actions/run-backend-tests/action.yml` in Pattern B is referenced by both jobs that use it.
