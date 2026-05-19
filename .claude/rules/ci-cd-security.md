# CI/CD Security

Trust model for the self-hosted production runner. Four independent layers; **never weaken any one in isolation** — they compensate for each other.

The deliberate gap: `main` does not require PR approvals (would deadlock `auto-merge.yml`, which uses `secrets.DEPLOY_PAT` to merge once `ci-check` passes). The `production` environment reviewer is the safety net that holds even if a malicious PR sneaks through CI on a GitHub-hosted runner.

---

## The Four Layers

### Layer 1 — CODEOWNERS (`.github/CODEOWNERS`)

Owner-flag security-sensitive paths so any change surfaces in the GitHub UI as owner-tagged. Currently advisory only on `main` (see deliberate gap), but provides a paper trail and is enforced on any branch where "Require review from Code Owners" is later enabled.

Owned paths:
- `/.github/workflows/` — every workflow definition
- `/.github/CODEOWNERS` — meta-protect the file itself
- `/deploy/` — deploy scripts, systemd units, sudoers templates, nginx config
- `/scripts/bootstrap-runner-ubuntu.sh` — VM runner provisioning (legacy)
- `/scripts/bootstrap-ci-runner.sh` — sandbox CI runner provisioning (ci-sandbox label)
- `/.claude/rules/ci-cd-security.md` — these rules
- `/.claude/rules/security.md`, `/.claude/rules/security-agent.md`

### Layer 2 — Runner Trigger Separation

| Workflow | Runner | Triggers |
|---|---|---|
| `auto-merge.yml` | `ubuntu-latest` | `workflow_run` (CI Check completed) |
| `ci-check.yml` `frontend-build` | `ubuntu-latest` | `pull_request`, `workflow_call` |
| `ci-check.yml` `backend-tests` | **`self-hosted, ci-sandbox`** (rootless Podman) | `pull_request` (gated by `ci-tests` env), `workflow_call` (ungated) |
| `create-release.yml` | `ubuntu-latest` | tag push (`v*-pre.*`) |
| `deploy-pi.yml` | `ubuntu-latest` | `workflow_dispatch` |
| `playwright-e2e.yml` | `ubuntu-latest` | `pull_request`, `push: main` |
| `release-stable.yml` | `ubuntu-latest` | `workflow_dispatch` |
| `deploy-production.yml` | **`self-hosted`** | `push: main`, `workflow_dispatch` |
| `raid-mdadm-selfhosted.yml` | **`self-hosted, linux, mdadm`** | `workflow_dispatch` only |

PR-triggered workflows MUST NOT use the production-privileged `BaluNode` runner. The `ci-sandbox` runner is the **only** self-hosted runner permitted to execute PR-triggered code, and only via the two-layer isolation described below.

Self-hosted production runners (`BaluNode`) only see code that has already landed on `main` (via auto-merge through Layer 4) or that an authorized actor explicitly dispatched.

**Sandbox runner: two-layer isolation.** The `ci-sandbox` runner (provisioned by `scripts/bootstrap-ci-runner.sh`) provides:

- **Layer A — POSIX user isolation.** Runner agent runs as `ci-runner`, an unprivileged Linux user with no sudo entry, no membership in `docker`/`sudo`/`wheel` groups, and no read access to `/opt/baluhost`, `/etc/baluhost`, or any production secrets. Confirmed at provisioning time by self-tests in the bootstrap script.
- **Layer B — Rootless Podman container.** Untrusted code (`pip install`, `pytest`, anything in the PR) never executes directly on the runner host. Workflows wrap the test invocation in `podman run --rm` against a pinned image (`docker.io/library/python:3.11-slim`), with only the workspace bind-mounted. The container sees no host filesystem outside the bind-mount; container-root is mapped to `ci-runner`'s subuid range. No Docker daemon, no `/var/run/docker.sock`, no `docker` group.

A workflow on `ci-sandbox` that runs `pip install` directly on the runner host (instead of inside `podman run`) breaks Layer B. The Reviewer Checklist below catches this.

**Stale-label gap (2026-05-12)**: `raid-mdadm-selfhosted.yml` requires the `mdadm` label, but the `BaluNode` runner only has `self-hosted, Linux, X64`. The workflow currently cannot acquire a runner and would hang indefinitely if dispatched. Either add the `mdadm` label to `BaluNode` (config in `/opt/actions-runner/.runner` or via the GitHub UI) or change the workflow to drop the label requirement.

### Layer 3 — `github.actor == 'Xveyn'` Allowlist

Hard-coded gate on the deploy job in `.github/workflows/deploy-production.yml`:

```yaml
if: >-
  !startsWith(github.event.head_commit.message, 'chore: bump version')
  && !startsWith(github.event.head_commit.message, 'chore: release v')
  && github.actor == 'Xveyn'
```

Why it works with auto-merge: `auto-merge.yml` uses `secrets.DEPLOY_PAT` (Xveyn's PAT) to perform the merge, so the resulting `push: main` event has `github.actor == 'Xveyn'`. A direct push by anyone else, or a `workflow_dispatch` triggered by another collaborator, is silently skipped.

### Layer 4 — `production` Environment

Server-side protection (configured in GitHub repo settings, not in the repo):

| Setting | Required value | Verified state (2026-05-12) |
|---|---|---|
| Required reviewers | `Xveyn` | `Xveyn` ✓ |
| `prevent_self_review` | `false` (solo dev) | `false` ✓ |
| Wait timer | 0 | 0 ✓ |
| Deployment branches and tags | Protected branches only | `protected_branches: true` ✓ (currently only `main` is protected) |
| `can_admins_bypass` | `false` | `false` ✓ |

The deploy job declares `environment: production`, so any run pauses for reviewer approval before executing on the self-hosted runner. Even if Layers 1–3 are bypassed, this gate halts the deploy. Solo-dev workflow: Xveyn approves his own deploys — that's the intended gate (forces a manual click, not a second human).

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

---

## Repo Settings to Verify

These live as GitHub server-state and cannot be read from the repo. Verify periodically (and after any GitHub plan / org change) via `gh api`:

| Setting | Check command | Expected |
|---|---|---|
| Branch protection on `main` | `gh api repos/Xveyn/BaluHost/branches/main/protection` | Required status checks: `backend-tests`, `frontend-build` (jobs from `ci-check.yml`); `allow_force_pushes: false`; `allow_deletions: false`; `enforce_admins: false` (admin bypass — see Known Gaps) |
| Production environment | `gh api repos/Xveyn/BaluHost/environments/production` | `protection_rules` includes `required_reviewers` (Xveyn), `deployment_branch_policy.protected_branches: true`, `can_admins_bypass: false` |
| `ci-tests` environment | `gh api repos/Xveyn/BaluHost/environments/ci-tests` | `protection_rules` includes `required_reviewers` (Xveyn), `can_admins_bypass: false` |
| Self-hosted runners | `gh api repos/Xveyn/BaluHost/actions/runners` | `BaluNode` online (`self-hosted, Linux, X64`) and `BaluNode-ci-sandbox` online (`self-hosted, Linux, X64, ci-sandbox`) |
| Default workflow permissions | `gh api repos/Xveyn/BaluHost/actions/permissions/workflow` | `default_workflow_permissions: read`, `can_approve_pull_request_reviews: false` |
| `DEPLOY_PAT` secret | repo Settings → Secrets → Actions | Present, owned by Xveyn, has `repo` + `workflow` scopes only |

---

## Reviewer Checklist

When reviewing changes that touch CI/CD, deploy scripts, or these rules:

- [ ] **Runner change**: Is anything new switching to `runs-on: self-hosted`? If yes, does it trigger only on `push: main` or `workflow_dispatch`? PRs MUST never run on self-hosted.
- [ ] **Sandbox host-direct execution**: Does a workflow on `ci-sandbox` run `pip install`, `npm install`, or any untrusted code directly on the runner host (not inside `podman run`)? If yes — block. That breaks Layer B isolation.
- [ ] **PR gate**: Does a workflow on `ci-sandbox` triggered by `pull_request` have `environment: ci-tests` (or equivalent approval gate)? If yes — proceed. If no — block.
- [ ] **Trigger change**: Does a self-hosted workflow gain a `pull_request` or `pull_request_target` trigger? If yes — block. That removes Layer 2.
- [ ] **Actor gate**: Is `github.actor == 'Xveyn'` still on the deploy job in `deploy-production.yml`? If a change weakens or removes it, require explicit justification.
- [ ] **Environment**: Does the deploy job still declare `environment: production`? If removed, Layer 4 is gone.
- [ ] **CODEOWNERS**: Does the change touch `.github/workflows/`, `deploy/`, or `.claude/rules/security*`? Confirm CODEOWNERS still maps these to `@Xveyn`.
- [ ] **PAT scope**: Does any new workflow use `secrets.DEPLOY_PAT`? If yes, confirm it's only used for `gh pr merge` (auto-merge) or release tagging — never for arbitrary code execution on self-hosted.
- [ ] **Sudoers / systemd**: Changes under `deploy/install/templates/` to sudoers or service units? Verify the new rules are scoped to specific binaries with explicit args (no `ALL`, no globs that match user-controlled paths).
- [ ] **Deploy script**: Changes to `deploy/scripts/ci-deploy.sh`? Verify no new shell injection surfaces (user-controlled env vars interpolated into commands), no new `sudo` invocations without sudoers entries, rollback path still works.
- [ ] **Workflow secrets**: New `secrets.*` references? Confirm the secret exists, is scoped correctly, and is not echoed/logged.

---

## Known Gaps & Accepted Risks

1. **`main` does not require PR approvals** — Required to keep `auto-merge.yml` functional. The `production` environment reviewer (Layer 4) is the compensating control.
2. **Two self-hosted runners with different trust levels on one host**:
    - `BaluNode` (`self-hosted, Linux, X64`) — runs production deploys. Full access to `/opt/baluhost`, `.env.production`, sudo entries. Never sees PR code (Layer 2 prohibition + workflows pin to label `ci-sandbox` for PR work).
    - `BaluNode-ci-sandbox` (`self-hosted, Linux, X64, ci-sandbox`) — runs `backend-tests` for PRs. Runs as `ci-runner` (no sudo, no production read), wraps test execution in rootless Podman. Even if a PR is maliciously approved at the `ci-tests` gate, blast radius is limited to the container workdir and outbound network (see gap #8).
    Both runners share the host kernel. A kernel-namespace escape from the Podman container would land as `ci-runner` on the host — still without sudo or production access. The bootstrap script's self-tests must pass for these guarantees to hold.
3. **`DEPLOY_PAT` is a personal access token, not a fine-grained app token** — Rotation is manual. Track in [[project_baluhost_secrets_todo]].
4. **CODEOWNERS is advisory on `main`** — See the deliberate gap above.
5. **In-repo CODEOWNERS for paths outside the repo (e.g., GitHub environment settings) is impossible** — Layer 4 protections must be re-verified manually after any account/plan change (see Repo Settings table).
6. **`enforce_admins: false` on main branch protection** — Xveyn (owner/admin) can bypass branch protection (force-push, skip status checks). Intentional for solo-dev emergency hotfix capability; the production environment reviewer (Layer 4) still gates the actual deploy.
7. **`raid-mdadm-selfhosted.yml` runner label mismatch** — Workflow requires `mdadm` label, `BaluNode` runner only has `self-hosted, Linux, X64`. Not a security risk (workflow simply cannot acquire a runner); flagged for cleanup if/when the workflow is needed.
8. **`ci-runner` and its containers have unrestricted egress** — A maliciously approved PR can exfiltrate the workdir contents and make outbound calls to arbitrary hosts. Mitigations: the `ci-tests` environment gate (manual approval), the limited blast radius (workdir contains only PR code), no production secrets reachable. Future tightening: egress firewall allowing only `pypi.org`, `files.pythonhosted.org`, `api.github.com`, `objects.githubusercontent.com`, `registry.docker.io`.
