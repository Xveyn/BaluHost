# Self-Hosted Backend Tests — Sandboxed Runner with Rootless Container Execution

**Date:** 2026-05-19
**Branch:** feat/os-auto-suspend-bidirectional (spec only; implementation will land on its own branch)
**Status:** Design — awaiting review

## Problem

Backend tests in `ci-check.yml` run on `ubuntu-latest`. Recent durations: 7m17s–7m26s end-to-end. The Ryzen 5 5600GT (6c/12t, 4.6 GHz boost) with 16 GB DDR4 in the production NAS would finish the same suite in an estimated 2–3 minutes — enough to materially shorten the PR feedback loop.

Naively setting `runs-on: self-hosted` violates Layer 2 of `.claude/rules/ci-cd-security.md`:

> "PR-triggered workflows MUST use GitHub-hosted runners — code from a fork PR could otherwise execute on the production host."

The existing `BaluNode` runner shares the production host with full read access to `/opt/baluhost`, `.env.production`, and sudo rights via `/etc/sudoers.d/baluhost-deploy`. Any test that runs `pip install` executes arbitrary `setup.py` code; any `conftest.py` in a malicious PR would have direct line-of-sight to production secrets. This is Known Gap #2, explicitly accepted only because no untrusted code is allowed near `BaluNode`.

## Goal

Move `backend-tests` to the NAS while preserving the four-layer trust model. Specifically:

1. PR-triggered code must not run on `BaluNode` or any runner with access to production paths/secrets.
2. The auto-merge flow (`auto-merge.yml` → `workflow_run` of "CI Check") must keep working.
3. `deploy-production.yml` reuse via `workflow_call: ./.github/workflows/ci-check.yml` must keep working without manual approval (the code is already trusted at that point — it landed on `main`).

Out of scope: `frontend-build` (~1 min today; marginal win, not worth the operational complexity). Stays on `ubuntu-latest`.

## Approach

Three layers stacked: (1) a second runner under a dedicated unprivileged user, (2) a manual GitHub-Environment gate on PR runs, (3) Podman rootless containerization of the actual test execution.

### 1. New isolated runner: `ci-sandbox`

A second GitHub Actions runner instance on the same physical NAS host, running as a dedicated unprivileged Linux user.

| Property | `BaluNode` (existing) | `ci-sandbox` (new) |
|---|---|---|
| Linux user | `runner` (or current deploy user) | `ci-runner` (new) |
| sudo rights | mdadm, deploy script via `/etc/sudoers.d/baluhost-deploy` | **none** |
| Group memberships | as needed for deploy | **none** (specifically not `docker`, not `sudo`, not `baluhost`) |
| Read access | `/opt/baluhost/**`, `/etc/baluhost/**`, `.env.production` | **none of these** (POSIX perms) |
| Work directory | `/opt/actions-runner/_work` | `/var/lib/ci-runner/_work` |
| Container engine | n/a | Podman rootless (per-user, no daemon, no socket) |
| Runner labels | `self-hosted, Linux, X64` | `self-hosted, Linux, X64, ci-sandbox` |
| Service unit | existing | `actions.runner.Xveyn-BaluHost.<runner-name>.service` |
| Triggers it answers | `push: main`, `workflow_dispatch` (deploys + admin tasks) | `pull_request` and `workflow_call` of ci-check.yml |

The two runners are independent processes — a long deploy doesn't block a PR test run and vice versa. The runner-host process (the Actions Runner agent) runs as `ci-runner`; it has no sudo, no Docker daemon access, and cannot read production paths. That's layer A.

### 2. Manual `ci-tests` environment gate (per user request)

Add an environment gate on the `backend-tests` job that applies on `pull_request` but not on `workflow_call` (used by `deploy-production.yml`). The exact YAML shape is an implementation choice — two viable patterns:

- **A. Conditional environment expression** — `environment: ${{ github.event_name == 'pull_request' && 'ci-tests' || '' }}`. Concise but relies on GitHub treating an empty-string `environment` as "no environment". Should be smoke-tested in a draft PR before relying on it.
- **B. Split jobs sharing a composite action** — two jobs (`backend-tests-pr` with `environment: ci-tests` and `if: github.event_name == 'pull_request'`; `backend-tests-trusted` without environment and the inverse `if:`), both delegating to `.github/actions/run-backend-tests/action.yml`. More verbose but unambiguous and easy to reason about.

The implementation plan will pick one after verifying (A) works as expected; if it doesn't, fall back to (B). The conceptual model (PR-triggered = gated, workflow_call-triggered = ungated) is the same either way, so this choice doesn't affect the rest of the design.

Configure the `ci-tests` environment in GitHub repo settings:

| Setting | Value |
|---|---|
| Required reviewers | `Xveyn` |
| `prevent_self_review` | `false` (solo dev — same as `production`) |
| Wait timer | 0 |
| Deployment branches and tags | All branches |
| `can_admins_bypass` | `false` |

Behaviour:
- **PR push** → CI Check queues → "Waiting for approval (ci-tests)" → Xveyn clicks Approve → backend-tests runs on `ci-sandbox` → `auto-merge.yml` fires on success.
- **workflow_call from deploy-production.yml** → conditional resolves to no environment → runs immediately on `ci-sandbox`. (Code is already on `main` at this point; trust gate already cleared by auto-merge + Layer 3 + production environment review.)

The cost: **one click per PR push** before tests run. For solo-dev that's tolerable in exchange for an explicit, auditable "I authorised this test run" event in the GitHub Actions log.

### 3. Podman rootless container execution

The actual `pip install` + `pytest` invocation runs **inside a Podman container**, not directly on the runner host. Layer B.

Why Podman rootless and not Docker or GitHub Actions' built-in `container:` keyword:

- GitHub's Actions Runner hardcodes the Docker socket at `/var/run/docker.sock` for the `container:` and `services:` keywords and **ignores `DOCKER_HOST`** — issues [#827](https://github.com/actions/runner/issues/827) and [#2103](https://github.com/actions/runner/issues/2103); the PR adding configurable socket support ([#1754](https://github.com/actions/runner/pull/1754)) has been open for years and is still not merged in 2026. Using the native `container:` keyword therefore forces a rootful Docker daemon, which (a) requires the runner user to be in the `docker` group — effectively root, defeating Layer 1 — or (b) requires brittle socket-symlink workarounds. Neither is acceptable.
- Docker rootless works but is bolt-on: a per-user daemon (`dockerd-rootless-setuptool.sh install`), `dbus-user-session` requirement, and brittle integration with the Runner.
- Podman is daemonless and rootless-by-default. Shipped in Debian 13's main repo. No `docker` group, no daemon socket, no shared state between jobs.
- We bypass the Runner's container hardcoding entirely by writing the container call ourselves in a `run:` step. `podman run --rm ...` is a CLI invocation, not an API call to a daemon.

The test step becomes (sketch — final YAML in implementation plan):

```yaml
- name: Run backend tests in rootless container
  working-directory: ${{ github.workspace }}
  run: |
    podman run --rm \
      --network=bridge \
      -v "$PWD:/work:Z" \
      -w /work/backend \
      -e NAS_MODE=dev \
      docker.io/library/python:3.11-slim \
      bash -c "pip install -e '.[dev]' && python -m pytest -q --timeout=120 -n auto --no-cov"
```

What the test code sees:
- Filesystem: only the `python:3.11-slim` image root + the bind-mounted workspace at `/work`. **Host filesystem is invisible.**
- User: container-`root` mapped to `ci-runner`'s subuid range (no root on host).
- Network: bridge (outbound only, no inbound). `pip install` works.
- Capabilities: Podman default drops most kernel capabilities; tests get only what's needed for normal Python.

**Image strategy:** First run pulls `python:3.11-slim` (~50 MB compressed) into `~/.local/share/containers/storage` on the runner host. Subsequent runs reuse the cached image. The bootstrap script pre-pulls the image so the first PR doesn't pay the cost.

If pip-install time becomes the bottleneck, a follow-up can publish a pre-built `ghcr.io/xveyn/baluhost-test:latest` image with dependencies baked in. **Out of scope for this spec** — only do this if measurements show pip-install is the dominant cost.

### What the two layers buy us, concretely

Suppose a malicious PR is accidentally approved at the `ci-tests` gate. The PR can:

| Action | Layer A (`ci-runner` POSIX) | Layer B (Podman container) | Combined |
|---|---|---|---|
| Read `/opt/baluhost/.env.production` | blocked (perms) | blocked (not mounted) | blocked twice |
| Read `/etc/sudoers.d/baluhost-deploy` | blocked (perms) | blocked (not mounted) | blocked twice |
| Run `sudo` | blocked (no sudoers entry) | blocked (no sudo in container, no host access) | blocked twice |
| Write outside `_work/` on host | blocked (perms) | blocked (only `_work/` bind-mounted) | blocked twice |
| Read world-readable host config (e.g. `/etc/passwd`) | allowed | blocked (not mounted) | **blocked by container** |
| Outbound network call | allowed | allowed | allowed (see Open Questions) |
| Read its own PR source code | allowed | allowed | allowed (that's literally what tests need) |

Where both layers say "blocked", we have defense-in-depth: misconfiguring one doesn't open the hole. Where only the container blocks, we're relying on container isolation alone. Where both allow, we have an Open Question (egress firewall).

This replaces Layer 2 ("PRs never touch self-hosted") with Layer 2′ ("PRs touch a sandbox runner that runs untrusted code only inside a rootless container, leaving the runner host's filesystem invisible to the test code").

## Trust Model — After Change

| Layer | Today | After |
|---|---|---|
| 1. CODEOWNERS | Owns `.github/workflows/`, `deploy/`, `.claude/rules/security*` | Add `/scripts/bootstrap-ci-runner.sh` |
| 2. Runner triggers | PR ⇒ `ubuntu-latest` always | PR ⇒ `ubuntu-latest` (frontend) **or** `ci-sandbox` (backend tests in Podman rootless). `BaluNode` still never sees PR code. |
| 3. Actor allowlist | `github.actor == 'Xveyn'` on deploy | unchanged |
| 4. Environments | `production` requires Xveyn approval | `production` unchanged. New `ci-tests` requires Xveyn approval for PR-triggered backend tests. |

Layer 2 is **weakened in letter** (some PR code now runs on self-hosted) but **strengthened by adding a container boundary** the test code cannot cross to reach the host filesystem.

## Components

### File changes in this repo

1. **`.github/workflows/ci-check.yml`**
   - `backend-tests.runs-on`: `[self-hosted, ci-sandbox]`
   - `backend-tests.environment`: conditional on `github.event_name == 'pull_request'` (Pattern A or B above)
   - `backend-tests.timeout-minutes`: 15 (defensive)
   - Defense-in-depth tripwire step **on the runner host** before the container call:
     ```yaml
     - name: Assert runner identity
       run: |
         test "$(whoami)" = "ci-runner" || { echo "::error::Runner not running as ci-runner"; exit 1; }
         test "$(id -u)" -ne 0 || { echo "::error::Runner running as root"; exit 1; }
         test -x "$(command -v podman)" || { echo "::error::podman not installed"; exit 1; }
     ```
   - Test step wraps everything in `podman run --rm` per the sketch above. `pip install` and `pytest` no longer run on the runner host.
   - `frontend-build`: unchanged (`ubuntu-latest`).

2. **`scripts/bootstrap-ci-runner.sh`** (new)
   - Provisioning script for the NAS host (run once, as root).
   - **System packages:** `apt install -y podman uidmap dbus-user-session slirp4netns fuse-overlayfs` (uidmap provides `newuidmap`/`newgidmap`; slirp4netns enables rootless networking; fuse-overlayfs is the rootless storage driver).
   - **User:** create `ci-runner` with `--system --create-home --shell /bin/bash` (shell needed for runner; no login shell hardening since runner uses it).
   - **No sudo entry** — explicit comment to that effect inside the script.
   - **Subuid/subgid:** `usermod --add-subuids 100000-165535 --add-subgids 100000-165535 ci-runner`.
   - **Lingering:** `loginctl enable-linger ci-runner` so the user-systemd lives without an active login.
   - **Workdir:** `mkdir -p /var/lib/ci-runner/_work` owned by `ci-runner:ci-runner`, mode 0750.
   - **Runner install:** download GitHub Actions runner tarball under `/var/lib/ci-runner/runner/`, run `config.sh --unattended --url https://github.com/Xveyn/BaluHost --token <runner-token> --labels self-hosted,Linux,X64,ci-sandbox --work _work --name BaluNode-ci-sandbox`.
   - **Service:** `./svc.sh install ci-runner` then `./svc.sh start` (svc.sh handles systemd registration; runs as `ci-runner`).
   - **Image prefetch:** `sudo -u ci-runner -- podman pull docker.io/library/python:3.11-slim` so the first PR doesn't pay 30s of pull time.
   - **Self-tests** (script exits non-zero on any failure):
     - `sudo -u ci-runner cat /opt/baluhost/.env.production` → must return "Permission denied"
     - `sudo -u ci-runner -- sudo -n true` → must fail
     - `sudo -u ci-runner -- podman run --rm docker.io/library/hello-world` → must succeed and run as non-root on host
     - `id ci-runner` → must show no `docker`, no `sudo`, no `baluhost` group memberships
   - **Idempotent:** safe to re-run; checks for existing user/runner/image before recreating.

3. **`.claude/rules/ci-cd-security.md`**
   - Update Layer 2 table: add `ci-check.yml backend-tests` row with `self-hosted, Linux, X64, ci-sandbox` and triggers `pull_request, workflow_call`.
   - Add a new subsection under Layer 2 titled "Sandbox runner: two-layer isolation" describing the POSIX user + Podman rootless model.
   - Update Layer 4 section with the `ci-tests` environment table.
   - Update "Repo Settings to Verify" with a row for `ci-tests` environment.
   - Update Reviewer Checklist with bullets:
     - "If a workflow gains `runs-on: ci-sandbox`, does it still wrap untrusted code in `podman run` (i.e. it doesn't run `pip`/`npm` directly on the runner host)?"
     - "Does the workflow have `environment: ci-tests` (or equivalent) on PR triggers?"
   - Update Known Gap #2: split into 2a (BaluNode = production deploys, no untrusted code, runs host-direct) and 2b (ci-sandbox = PR tests, untrusted code, runs only inside rootless container).
   - Add Known Gap: `ci-runner` and its containers have unrestricted egress. Mitigated by manual gate (Layer 4). Tightening to allowlist (e.g. only `pypi.org` and `api.github.com`) deferred — see Open Questions.

4. **`.github/CODEOWNERS`**
   - Add `/scripts/bootstrap-ci-runner.sh` to `@Xveyn`.

### Out-of-repo changes (NAS host + GitHub settings)

- Run `bootstrap-ci-runner.sh` on the NAS once (as root).
- Create `ci-tests` environment in GitHub repo settings (required reviewer: Xveyn, no admin bypass).
- Verify the new runner appears as `BaluNode-ci-sandbox` in `gh api repos/Xveyn/BaluHost/actions/runners`.

## Data Flow

### PR push (new path)

```
git push origin <branch>
  → GitHub creates PR (or updates existing)
  → ci-check.yml triggers on pull_request
    → frontend-build queues on ubuntu-latest, runs ~1 min
    → backend-tests queues, `environment: ci-tests` holds it
       → GitHub UI shows "Waiting for review"
       → Xveyn clicks Approve
       → Job dispatches to ci-sandbox runner
       → "Assert runner identity" tripwire passes
       → podman run python:3.11-slim → pip install + pytest -n auto
       → Container exits, runner reports status
    → Both jobs succeed → CI Check workflow concludes "success"
  → workflow_run event fires on "CI Check"
    → auto-merge.yml runs on ubuntu-latest (unchanged)
    → gh pr merge → main updated
  → push: main triggers deploy-production.yml (unchanged)
```

### Deploy from main (path that must keep working)

```
auto-merge pushes to main (as Xveyn via DEPLOY_PAT)
  → deploy-production.yml triggers
    → ci-check job: uses ./.github/workflows/ci-check.yml (workflow_call)
      → frontend-build on ubuntu-latest
      → backend-tests: environment conditional → '' (no gate) → runs immediately on ci-sandbox in podman
    → deploy job needs ci-check, has Layer 3 + Layer 4 gates → runs on BaluNode
```

### Failure modes

| Failure | Behaviour |
|---|---|
| `ci-sandbox` runner offline | Backend-tests stays queued; CI Check does not conclude; auto-merge does not fire. No silent merge of untested code. |
| Manual gate forgotten | PR sits in "Waiting for review" indefinitely. Auto-merge does not fire. Harmless. |
| Image pull fails (network blip) | Test step fails fast with a clear error from `podman pull`. Re-run the job. |
| Podman not installed / broken on runner | "Assert runner identity" tripwire catches it before `podman run`; explicit error message. |
| Malicious PR + accidental approval | Test code runs inside rootless container as container-root mapped to a subuid; cannot read `/opt/baluhost`, cannot escape to runner host filesystem outside `_work/`. Worst case: workdir exfiltration + outbound network abuse. `BaluNode` and production unaffected. |
| Both runners busy at once | Independent processes on independent user accounts. CPU steal acceptable; deploys are rare. |
| Container escape exploit (kernel-level) | Lands as `ci-runner` on the host — still no sudo, no production read access. Layer A catches what Layer B misses. |

## Testing

### Pre-merge verification (locally + in a draft PR)

1. **Bootstrap script review**: read `bootstrap-ci-runner.sh` for shell-injection surfaces; ensure all paths quoted, no user input interpolated into commands.
2. **Manual NAS provisioning**: run the script. Confirm all self-tests pass. Additionally verify by hand:
   - `sudo -u ci-runner cat /opt/baluhost/.env.production` → "Permission denied"
   - `sudo -u ci-runner -- sudo -n true` → fails
   - `sudo -u ci-runner -- podman run --rm docker.io/library/python:3.11-slim id` → shows `uid=0(root)` inside container, but `ps -o user= -p $(pgrep -f 'podman run')` on host shows `ci-runner` (subuid mapping verified)
   - `getent group docker` does not include `ci-runner`
3. **Draft PR**: open with the workflow changes. Verify in the GitHub UI that backend-tests shows "Waiting for review (ci-tests)". Approve. Confirm:
   - Job runs on `BaluNode-ci-sandbox` (check `Runner name:` in logs).
   - "Assert runner identity" step succeeds with `whoami=ci-runner`.
   - Pytest output appears in logs (container's stdout is captured by runner).
4. **Deploy path**: after the draft PR merges, watch `deploy-production.yml` → confirm `ci-check` step runs **without** waiting for approval (workflow_call should bypass the environment gate via the conditional).
5. **Auto-merge regression check**: open a trivial second PR (e.g., comment-only change), approve the gate, confirm auto-merge still fires after CI Check succeeds.
6. **Isolation check from inside the container**: temporarily add a test step `podman run ... ls /opt /etc/baluhost 2>&1 | head` — must show "No such file or directory" or empty. Remove the test step before final merge.

### Post-merge verification

- `gh api repos/Xveyn/BaluHost/actions/runners` shows both `BaluNode` and `BaluNode-ci-sandbox` as `status: online`.
- `gh api repos/Xveyn/BaluHost/environments/ci-tests` shows `required_reviewers` set to Xveyn, `can_admins_bypass: false`.
- After 3–5 PRs over a week: time the backend-tests step. Target ≤ 3 minutes wall-clock from "container starts" to "pytest done". If pip-install dominates, evaluate the pre-built image follow-up.

## Open Questions

1. **Egress firewall on `ci-runner`** — block outbound except to `pypi.org`, `files.pythonhosted.org`, `api.github.com`, `objects.githubusercontent.com`, `registry.docker.io`? Would reduce exfiltration risk if the manual gate is ever bypassed. Trade-off: future tests needing other network resources break. **Recommendation: leave open for now; revisit if abuse signal appears.**

2. **Pre-built test image** — bake `pip install -e .[dev]` into a `ghcr.io/xveyn/baluhost-test:<sha>` image and skip pip on every run. Cuts ~30-60s if pip dominates. Adds a separate image-publish workflow. **Recommendation: defer until measurements show it's worth it.**

3. **One click per PR push is friction** — bypass when `github.actor == 'Xveyn'`? GitHub Environments don't have actor-conditional approval directly, but split-job Pattern B with `if: github.actor != 'Xveyn'` on the gated variant would work. **Recommendation: don't optimise yet — see how it feels for a week.**

4. **mdadm tests** — `raid-mdadm-selfhosted.yml` requires `mdadm` label; neither runner has it. The new sandbox is also unsuitable (no sudo, no loopback). If mdadm tests are ever needed: third runner in a real VM. Out of scope.

5. **Naming** — runner display name `BaluNode-ci-sandbox` chosen. Labels are what `runs-on` matches; the display name is cosmetic.

6. **`--security-opt no-new-privileges` and `--cap-drop=ALL`** on the `podman run` invocation — extra hardening. Tradeoff: some pytest plugins or subprocess-spawning tests might break. **Recommendation: start without, add if no breakage.**

## Decision Log

- **Why a second runner on the same physical host, not a separate VM?** Lower operational overhead. POSIX user isolation + Podman rootless isolation already give container-level isolation against the relevant threat model (PR test code). A VM would defend against kernel-namespace escape, which is rare for unprivileged userspace code. Trade-off accepted.
- **Why Podman rootless, not Docker rootless?** Daemonless, native rootless, in Debian 13 main repo, no `docker` group footgun. Docker rootless is bolt-on, needs `dbus-user-session`, brittle integration with the Runner (#2103).
- **Why not the GitHub Actions `container:` keyword?** Runner hardcodes `/var/run/docker.sock`, ignores `DOCKER_HOST` (#827, PR #1754 still open in 2026). Using `container:` would force a rootful daemon. We sidestep entirely by invoking `podman run` from a `run:` step.
- **Why keep `frontend-build` on `ubuntu-latest`?** Saves ~1 minute at most; adds operational complexity (node version pinning, npm cache on the runner, image management). Not worth it.
- **Why manual approval instead of fully automatic?** User explicit request — "ähnlich zum Deployment". Audit trail + safety against runner-misconfiguration regressions.
- **Why not just keep `ubuntu-latest`?** Save 4–5 minutes per PR. ~40 min/week saved (10 PRs/week typical for solo dev) — material context-switch reduction.
- **Why not venv?** venv isolates Python packages, not the filesystem or process boundary. A malicious `setup.py` runs as the calling user regardless of venv. The container gives us the actual isolation that matters; venv would be a hygiene-only addition with no security value.

## References

- [actions/runner#1754 — Adding support for custom DOCKER_HOST / Rootless docker](https://github.com/actions/runner/pull/1754) (PR still open in 2026)
- [actions/runner#827 — Runner ignores DOCKER_HOST variable when starting container](https://github.com/actions/runner/issues/827)
- [actions/runner#2103 — Self-hosted runners with rootless Docker broken after 2.296.1](https://github.com/actions/runner/issues/2103)
- [containers/podman discussion #22675 — GitHub Actions with Podman Improvements](https://github.com/containers/podman/discussions/22675)
- [Bernd Konnerth — Setting up a GitHub self-hosted runner for rootless Docker](https://medium.com/@djbernd.konnerth/setting-up-a-github-self-hosted-runner-for-rootless-docker-operation-2ff8864c597a)
- [SealingTech — How to Set Up a Rootless GitHub Container Building Pipeline](https://www.sealingtech.com/2024/04/29/how-to-set-up-a-rootless-github-container-building-pipeline/)
- [SUSE — Running Podman in Rootless Mode](https://documentation.suse.com/smart/container/html/rootless-podman/index.html)
- [Luca Berton — Podman vs Docker 2026: Rootful, Rootless, and Benchmarks](https://lucaberton.com/blog/podman-vs-docker-2026/)
- [OneUptime — How to Configure Self-Hosted Runners in GitHub Actions (2026)](https://oneuptime.com/blog/post/2026-01-25-github-actions-self-hosted-runners/view)
