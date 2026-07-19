# CI/CD Security

Trust model for the self-hosted production runner. Four independent layers; **never weaken any one in isolation** — they compensate for each other.

The deliberate gap: `main` does not require PR approvals. Xveyn (the sole maintainer) merges PRs manually after CI passes; there is no auto-merge bot. The `production` environment reviewer is the safety net that holds even if a malicious PR sneaks through CI on a GitHub-hosted runner.

Pre-release tags (`v*-pre.*`) are created by `deploy-production.yml` as the final step of a successful prod deploy (see Layer 3), not by a merge bot — so a tag always corresponds to code that actually reached production.

---

## The Four Layers

### Layer 1 — CODEOWNERS (`.github/CODEOWNERS`)

Owner-flag security-sensitive paths so any change surfaces in the GitHub UI as owner-tagged. Currently advisory only on `main` (see deliberate gap), but provides a paper trail and is enforced on any branch where "Require review from Code Owners" is later enabled.

Owned paths:
- `/.github/workflows/` — every workflow definition
- `/.github/workflows/tauri-build.yml` — Tauri build workflow
- `/.github/CODEOWNERS` — meta-protect the file itself
- `/client/src-tauri/` — Tauri Companion app source (Rust shell + config)
- `/deploy/` — deploy scripts, systemd units, sudoers templates, nginx config
- `/scripts/bootstrap-runner-ubuntu.sh` — VM runner provisioning (legacy)
- `/scripts/bootstrap-ci-runner.sh` — sandbox CI runner provisioning (ci-sandbox label)
- `/ci-config.example.conf` — fork CI config template (repo root)
- `/scripts/configure-ci.sh` — fork CI config apply script
- `/.claude/rules/ci-cd-security.md` — these rules
- `/.claude/rules/security.md`, `/.claude/rules/security-agent.md`

### Layer 2 — Runner Trigger Separation

| Workflow | Runner | Triggers |
|---|---|---|
| `ci-check.yml` `frontend-build` | `ubuntu-latest` | `pull_request`, `workflow_call` |
| `ci-check.yml` `backend-tests` | **upstream: `self-hosted, ci-sandbox` (hardcoded repo literal); forks: `vars.BACKEND_TEST_RUNNER`, default `ubuntu-latest`** (rootless Podman everywhere) | `pull_request` (gated by `ci-tests` env), `workflow_call` (ungated) |
| `create-release.yml` | `ubuntu-latest` | tag push (`v*-pre.*`) |
| `deploy-pi.yml` | `ubuntu-latest` | `workflow_dispatch` |
| `playwright-e2e.yml` | `ubuntu-latest` | `pull_request`, `push: main` |
| `release-stable.yml` | `ubuntu-latest` | `workflow_dispatch` |
| `deploy-production.yml` | **`self-hosted, prod`** | `push: main`, `workflow_dispatch` |
| `deploy-fork.yml` | **fork-configured via `vars.DEPLOY_FORK_RUNNER`** | `push: main`, `workflow_dispatch` — dead upstream (repo guard on every job) |
| `raid-mdadm-loopback.yml` | `ubuntu-latest` | `pull_request` (paths: raid), `workflow_dispatch` |
| `tauri-build.yml` | `ubuntu-latest` | `push: main`, tag, `workflow_dispatch` |
| `tui-build.yml` | `ubuntu-latest` | `push: main`, tag, `workflow_dispatch` |

PR-triggered workflows MUST NOT use the production-privileged `BaluNode` runner. The `ci-sandbox` runner is the **only** self-hosted runner permitted to execute PR-triggered code, and only via the two-layer isolation described below.

Self-hosted production runners (`BaluNode`) only see code that has already landed on `main` (via a manual merge by Xveyn, gated by Layer 4) or that an authorized actor explicitly dispatched.

**Sandbox runner: two-layer isolation.** The `ci-sandbox` runner (provisioned by `scripts/bootstrap-ci-runner.sh`) provides:

- **Layer A — POSIX user isolation.** Runner agent runs as `ci-runner`, an unprivileged Linux user with no sudo entry, no membership in `docker`/`sudo`/`wheel` groups, and no read access to `/opt/baluhost`, `/etc/baluhost`, or any production secrets. Confirmed at provisioning time by self-tests in the bootstrap script.
- **Layer B — Rootless Podman container.** Untrusted code (`pip install`, `pytest`, anything in the PR) never executes directly on the runner host. Workflows wrap the test invocation in `podman run --rm` against a pinned image (`docker.io/library/python:3.11-slim`), with only the workspace bind-mounted. The container sees no host filesystem outside the bind-mount; container-root is mapped to `ci-runner`'s subuid range. No Docker daemon, no `/var/run/docker.sock`, no `docker` group.

A workflow on `ci-sandbox` that runs `pip install` directly on the runner host (instead of inside `podman run`) breaks Layer B. The Reviewer Checklist below catches this.

**Fork configurability (#207).** Runner selection and workflow toggles for forks
are driven exclusively by `github.repository == 'Xveyn/BaluHost'` literals and
server-side Repository Variables (`vars.*`, set via `scripts/configure-ci.sh`).
Upstream behavior is hardcoded and needs no variables; PR code cannot influence
runner choice or environment gates through either mechanism. The `ci-tests`
gate condition on `pull_request` events is
`github.repository == 'Xveyn/BaluHost' || contains(vars.BACKEND_TEST_RUNNER, 'self-hosted')`.
`raid-mdadm-loopback.yml` is deliberately NOT runner-configurable: real mdadm on
a self-hosted box could destroy disks — only the on/off toggle
`ENABLE_RAID_LOOPBACK` exists, and `BALUHOST_MDADM_LOOPBACK=1` is never set
outside that workflow. Note: IDE/actionlint warnings like "Context access might
be invalid: ENABLE_*" on the toggle vars are expected — the variables are
intentionally unset upstream (unset → `''` → defaults apply).

**Resolved (2026-06-09)**: the dead `raid-mdadm-selfhosted.yml` (which required a non-existent `mdadm` runner label and only ran mock tests anyway) was retired and replaced by `raid-mdadm-loopback.yml` on `ubuntu-latest`. Real mdadm coverage now runs on ephemeral GitHub-hosted VMs against loop-device arrays — no self-hosted runner, no production-disk risk (issue #185).

### Layer 3 — `github.actor == 'Xveyn'` Allowlist

Hard-coded gate on the deploy job in `.github/workflows/deploy-production.yml`:

```yaml
if: >-
  !startsWith(github.event.head_commit.message, 'chore: bump version')
  && !startsWith(github.event.head_commit.message, 'chore: release v')
  && github.actor == 'Xveyn'
```

Why it works: Xveyn merges PRs manually, so the resulting `push: main` event has `github.actor == 'Xveyn'`. A direct push by anyone else, or a `workflow_dispatch` triggered by another collaborator, is silently skipped.

**Pre-release tagging.** After the deploy steps succeed, the same `deploy` job creates the pre-release tag (`v<version>-pre.<n>`, where `<n>` is the next integer above the highest existing `pre.*` tag for that version) and pushes it with `secrets.DEPLOY_PAT`. The PAT (not the job's `GITHUB_TOKEN`) is required so the tag-push event triggers `create-release.yml`. Because this step runs inside the gated `deploy` job, the tag is only ever created after Layer 4 approval + a successful deploy. The PAT is exposed only to the already-maximally-trusted `prod` runner, and only in that single step's env — not persisted into git config (push uses an inline `x-access-token` URL).

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

| Setting | Required value | Verified state (2026-07-19) |
|---|---|---|
| Required reviewers | `Xveyn` | `Xveyn` ✓ |
| `prevent_self_review` | `false` (solo dev) | `false` ✓ |
| Wait timer | 0 | 0 ✓ |
| Deployment branches and tags | All branches | `deployment_branch_policy: null` ✓ |
| `can_admins_bypass` | `false` | `false` ✓ |

The `backend-tests` job declares `environment: ci-tests` conditionally on `github.event_name == 'pull_request'`. PR runs pause for Xveyn approval; `workflow_call` runs (from `deploy-production.yml` after a manual merge to `main`) execute immediately because the code is already trusted at that point.

> **Incident 2026-07-19 — this gate was hollow for two months.** The environment
> was created 2026-05-19 but **no protection rules were ever added**
> (`protection_rules: []`, `can_admins_bypass: true`). The table above claimed
> reviewers were configured; that had never been verified — the "Verified state"
> column read "check `gh api …`" rather than an actual result. In the meantime
> every PR ran `backend-tests` on the self-hosted `ci-sandbox` runner with **no
> manual approval**. Fixed 2026-07-19 and verified against the live API.
> Lesson: a row whose evidence column says "check this yourself" is an untested
> assertion, not a verified control. Record the observed value and the date.

### Fork PR approval policy

Repo setting, **not** in any workflow file — and therefore the one PR-triggered
control that a malicious PR cannot edit.

| Setting | Required value | Verified state (2026-07-19) |
|---|---|---|
| `approval_policy` | `all_external_contributors` | `all_external_contributors` ✓ |

Check: `gh api repos/Xveyn/BaluHost/actions/permissions/fork-pr-contributor-approval`

**Why this outranks the environment gate for fork PRs.** On a `pull_request`
event the workflow definition comes from the *PR's* merge ref, not from `main`.
A malicious fork PR can therefore delete the `environment: ci-tests` line from
`ci-check.yml` and remove its own gate. The fork approval policy is evaluated
from repo settings before any workflow starts, so PR content cannot influence
it. The `ci-tests` environment remains valuable as defense-in-depth and is the
control that covers same-repo branches, where the fork policy does not apply.

Was `first_time_contributors` until 2026-07-19 — meaning any contributor who had
been merged once could run code on the self-hosted sandbox runner unattended.

---

## Repo Settings to Verify

These live as GitHub server-state and cannot be read from the repo. Verify periodically (and after any GitHub plan / org change) via `gh api`:

| Setting | Check command | Expected |
|---|---|---|
| Branch protection on `main` | `gh api repos/Xveyn/BaluHost/branches/main/protection` | Required status checks: `backend-tests`, `frontend-build` (jobs from `ci-check.yml`); `allow_force_pushes: false`; `allow_deletions: false`; `enforce_admins: false` (admin bypass — see Known Gaps) |
| Production environment | `gh api repos/Xveyn/BaluHost/environments/production` | `protection_rules` includes `required_reviewers` (Xveyn), `deployment_branch_policy.protected_branches: true`, `can_admins_bypass: false` |
| `ci-tests` environment | `gh api repos/Xveyn/BaluHost/environments/ci-tests` | `protection_rules` includes `required_reviewers` (Xveyn), `can_admins_bypass: false`. **A non-empty `protection_rules` array is the whole control** — an environment with `protection_rules: []` still resolves and the job runs unpaused, so "the environment exists" proves nothing (see incident 2026-07-19) |
| Fork PR approval policy | `gh api repos/Xveyn/BaluHost/actions/permissions/fork-pr-contributor-approval` | `approval_policy: all_external_contributors` — the only PR-triggered gate a malicious PR cannot edit, since it is repo state rather than workflow YAML |
| Self-hosted runners | `gh api repos/Xveyn/BaluHost/actions/runners` | `BaluNode` online (`self-hosted, Linux, X64, prod`) and `BaluNode-ci-sandbox` online (`self-hosted, Linux, X64, ci-sandbox`). The `prod` label is what `deploy-production.yml` targets; without it on `BaluNode` the deploy could land on the sandbox runner. |
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
- [ ] **PAT scope**: Does any new workflow use `secrets.DEPLOY_PAT`? If yes, confirm it's only used for release tagging (the `deploy-production.yml` pre-release tag push) — never for arbitrary code execution. When used on the `prod` runner, confirm it's passed only to the single tag-push step's env and not persisted into git config.
- [ ] **Sudoers / systemd**: Changes under `deploy/install/templates/` to sudoers or service units? Verify the new rules are scoped to specific binaries with explicit args (no `ALL`, no globs that match user-controlled paths).
- [ ] **Deploy script**: Changes to `deploy/scripts/ci-deploy.sh`? Verify no new shell injection surfaces (user-controlled env vars interpolated into commands), no new `sudo` invocations without sudoers entries, rollback path still works.
- [ ] **Workflow secrets**: New `secrets.*` references? Confirm the secret exists, is scoped correctly, and is not echoed/logged.
- [ ] **Fork-config gate logic**: Does a change touch the `github.repository == 'Xveyn/BaluHost'` literals or the `contains(vars.BACKEND_TEST_RUNNER, 'self-hosted')` environment-gate condition in `ci-check.yml`/`deploy-fork.yml`? If it weakens the upstream-hardcoded path or derives gates from PR-controlled data — block.
- [ ] **mdadm runner pin**: Does a change make the `raid-mdadm-loopback.yml` runner configurable, or set `BALUHOST_MDADM_LOOPBACK` outside that workflow? If yes — block (mdadm must never run on self-hosted hardware).

---

## Known Gaps & Accepted Risks

1. **`main` does not require PR approvals** — Solo-dev workflow: Xveyn merges manually after CI passes (no auto-merge bot). The `production` environment reviewer (Layer 4) is the compensating control.
2. **Two self-hosted runners with different trust levels on one host**:
    - `BaluNode` (`self-hosted, Linux, X64, prod`) — runs production deploys. Full access to `/opt/baluhost`, `.env.production`, sudo entries. Never sees PR code (Layer 2 prohibition + workflows pin to label `ci-sandbox` for PR work). The `prod` label is what `deploy-production.yml` targets — removing it from `BaluNode` would route deploys to the sandbox and break them (caught 2026-05-19).
    - `BaluNode-ci-sandbox` (`self-hosted, Linux, X64, ci-sandbox`) — runs `backend-tests` for PRs. Runs as `ci-runner` (no sudo, no production read), wraps test execution in rootless Podman. Even if a PR is maliciously approved at the `ci-tests` gate, blast radius is limited to the container workdir and outbound network (see gap #8).
    Both runners share the host kernel. A kernel-namespace escape from the Podman container would land as `ci-runner` on the host — still without sudo or production access. The bootstrap script's self-tests must pass for these guarantees to hold.
3. **`DEPLOY_PAT` is a personal access token, not a fine-grained app token** — Rotation is manual. Track in [[project_baluhost_secrets_todo]].
4. **CODEOWNERS is advisory on `main`** — See the deliberate gap above.
5. **In-repo CODEOWNERS for paths outside the repo (e.g., GitHub environment settings) is impossible** — Layer 4 protections must be re-verified manually after any account/plan change (see Repo Settings table).
6. **`enforce_admins: false` on main branch protection** — Xveyn (owner/admin) can bypass branch protection (force-push, skip status checks). Intentional for solo-dev emergency hotfix capability; the production environment reviewer (Layer 4) still gates the actual deploy.
7. **`raid-mdadm-selfhosted.yml` runner label mismatch — resolved (2026-06-09)** — The dead workflow was retired and replaced by `raid-mdadm-loopback.yml` on `ubuntu-latest` (loop-device mdadm tests). No self-hosted runner is involved, so the label-mismatch gap no longer exists (issue #185).
8. **`ci-runner` and its containers have unrestricted egress** — A maliciously approved PR can exfiltrate the workdir contents and make outbound calls to arbitrary hosts. Mitigations: the `ci-tests` environment gate (manual approval), the limited blast radius (workdir contains only PR code), no production secrets reachable. Future tightening: egress firewall allowing only `pypi.org`, `files.pythonhosted.org`, `api.github.com`, `objects.githubusercontent.com`, `registry.docker.io`.
9. **`baluhost` user may stop/start/mask/unmask `power-profiles-daemon`** — Added in `deploy/install/templates/sudoers-baluhost-power` for the CPU power authority feature (`backend/app/services/power/ppd_authority.py`). Intentional and tightly scoped: four explicit `systemctl <verb> power-profiles-daemon` invocations, no `ALL`, no wildcards, single target unit. Blast radius is limited to that one systemd unit; it grants no general service control. The verbs are exercised only behind the local-channel + admin gate (`require_local_admin`) on `PUT /api/power/authority`.
10. **`baluhost` user may invoke the plugin spawn wrapper as root** — Added in `deploy/install/templates/baluhost-plugin-sudoers` (Track B Phase 5a). Intentional and tightly scoped: exactly one binary at `/usr/local/sbin/baluhost-spawn-plugin-worker.sh` (root:root 0755, outside `/opt/baluhost` so `baluhost` cannot swap it). The wrapper validates every caller-influenced argument, always drops privilege to the unprivileged `baluhost-plugin` user, and runs the worker in a dedicated network namespace (only loopback). It grants no general command execution — blast radius is one isolated subprocess under `baluhost-plugin` with no NAS-storage or secret access.
