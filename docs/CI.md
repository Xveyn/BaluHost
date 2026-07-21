# CI Design Decisions

Why the BaluHost pipeline is built the way it is. This is a reference for
fork maintainers and contributors — it explains intent so you don't "fix" a
deliberate non-feature. For fork setup, see `ci-config.example.conf` +
`scripts/configure-ci.sh` (walkthrough: `docs/deployment/SELF_HOSTING.en.md`).
The internal threat model and full layer-by-layer security rationale live in
`.claude/rules/ci-cd-security.md` — this document summarizes, it does not
replace it.

## Runner model

| Job (workflow) | Upstream runner | Fork variable | PR approval gate |
|---|---|---|---|
| `ci-check.yml` → `backend-tests` | `self-hosted, ci-sandbox` (hardcoded) | `BACKEND_TEST_RUNNER` (default: `ubuntu-latest`) | `ci-tests` on `pull_request`; ungated on `workflow_call` |
| `ci-check.yml` → `frontend-build` | `self-hosted, ci-sandbox` (hardcoded) | `FRONTEND_BUILD_RUNNER` (default: `ubuntu-latest`) | `ci-tests` on `pull_request`; ungated on `workflow_call` |
| `create-release.yml` → `release` | `ubuntu-latest` | — | none (tag-push only, never sees PR code) |
| `deploy-fork.yml` → `ci-check` / `deploy` | fork-supplied only; dead upstream (`github.repository != 'Xveyn/BaluHost'` guard) | `DEPLOY_FORK_RUNNER` (required once `ENABLE_DEPLOY_FORK=true`) | `environment: fork-production` (protection is opt-in — you must add required reviewers yourself) |
| `deploy-pi.yml` → `deploy` | `ubuntu-latest` | `ENABLE_DEPLOY_PI` (on/off) | none |
| `deploy-production.yml` → `deploy` | `[self-hosted, prod]` (hardcoded, not fork-configurable) | — | `environment: production` + actor allowlist (Layer 3 in the security rules) |
| `playwright-e2e.yml` → `mock-e2e` | `self-hosted, ci-sandbox` (hardcoded) | `E2E_RUNNER` (default: `ubuntu-latest`), `ENABLE_PLAYWRIGHT_E2E` (on/off) | `ci-tests` on `pull_request` |
| `playwright-e2e.yml` → `live-e2e` | `ubuntu-latest` | `ENABLE_PLAYWRIGHT_E2E` (on/off) | `environment: live-e2e` + `RUN_LIVE_E2E` secret, `workflow_dispatch` only — **neither exists yet**, see below |
| `raid-mdadm-loopback.yml` → `mdadm-loopback` | `ubuntu-latest` (hardcoded, **must not** become configurable) | `ENABLE_RAID_LOOPBACK` (on/off only — no runner variable exists) | none |
| `release-stable.yml` → `release` | `ubuntu-latest` | `ENABLE_RELEASE_STABLE` (needs a `DEPLOY_PAT` secret) | none (`workflow_dispatch` already requires repo write access) |
| `tauri-build.yml` → `build` | `ubuntu-latest` (hardcoded) | `ENABLE_TAURI_BUILD` (on/off) | none |
| `tui-build.yml` → `build` | `ubuntu-latest` (hardcoded) | `ENABLE_TUI_BUILD` (on/off) | none |

`raid-mdadm-loopback` is deliberately **not** runner-configurable — see
"Deliberate non-features" below.

### Two-layer isolation of `ci-sandbox`

PR-triggered jobs that land on the self-hosted `ci-sandbox` runner never
execute untrusted code directly on the runner host. Two independent layers,
both set up by `scripts/bootstrap-ci-runner.sh` and re-checked by that
script's self-tests on every run:

- **POSIX user isolation.** The runner agent runs as `ci-runner`, an
  unprivileged Linux user with no sudo, no membership in `docker`/`sudo`/`wheel`,
  and no read access to the production install (`/opt/baluhost`,
  `.env.production`).
- **Rootless Podman.** `pip install`, `npm ci`, and the rest of the PR's
  build/test commands run inside `podman run --rm` against a pinned image
  (`python:3.11-slim` / `node:20-slim` / `mcr.microsoft.com/playwright`), with
  only the checked-out workspace bind-mounted in. No Docker daemon, no
  `docker.sock`, no host filesystem access beyond that mount.

All three PR-facing jobs (`backend-tests`, `frontend-build`, `mock-e2e`) also
run an "assert runner identity" tripwire step (upstream only) that fails the
job outright if it somehow ends up running as `root`, outside `ci-runner`, or
in a privileged group.

The Playwright image is pinned to the exact version in
`client/package-lock.json`, because it ships matching browsers in
`/ms-playwright` — that is what removes the per-run browser download. A guard
inside the container compares `npx playwright --version` against the image tag
and fails loudly on drift, so bumping `@playwright/test` without bumping
`PLAYWRIGHT_IMAGE` cannot turn into a confusing mid-run error. Chromium also
needs `--shm-size=1g`; it segfaults on podman's 64 MB default.

### Why the upstream runner choice is hardcoded

`runs-on` for `backend-tests`, `frontend-build`, and `mock-e2e` is
`github.repository == 'Xveyn/BaluHost' && '[...]' || vars.<NAME> || '"ubuntu-latest"'`
— a repository literal, not anything derived from PR content. A PR cannot
change which runner its own job lands on: forks steer this exclusively
through server-side Repository Variables set via `scripts/configure-ci.sh`,
which PR code cannot write to either.

### Why there are two `ci-sandbox` instances

A single GitHub Actions runner processes one job at a time. `bootstrap-ci-runner.sh`
supports registering a second `ci-sandbox` instance on the same box (`--name`
/ `--dir`, sharing the same `ci-runner` user and rootless Podman store) so
that `backend-tests` and `frontend-build` — both gated, both potentially
triggered by the same PR — run in parallel instead of queuing behind each
other and roughly doubling PR turnaround time.

Since `mock-e2e` joined the sandbox there are three sandbox jobs and two
instances, so on any given PR one of them waits for a free slot. That is a
deliberate trade rather than an oversight: E2E is the slowest and least
urgent of the three, and a third instance costs RAM on a box that is also the
production NAS. Register one with `--dir runner-3` if the queueing becomes
the bottleneck.

## Approval gates

**`ci-tests` environment.** PR-triggered jobs on self-hosted hardware pause
for manual approval ("Review pending deployments") before they run at all.
GitHub groups every job in a run that's waiting on the same environment under
one prompt, so approving once releases both `backend-tests` and
`frontend-build` together. `mock-e2e` lives in a *different workflow*, so it
raises its own separate approval prompt — one extra click per PR, the price of
running E2E on the sandbox instead of a GitHub VM. `workflow_call` invocations of `ci-check.yml` (from
`deploy-production.yml`, after a PR has already been merged to `main`) skip
the gate — that code is already trusted.

**Fork PR approval is the load-bearing control, not the environment.** A pull
request from an outside contributor runs its own copy of the workflow file —
including any edits it makes to that file — so it could in principle delete
the `environment: ci-tests` line before it ever reaches the sandbox runner.
It cannot, however, edit repository settings. The repo's fork-PR-workflow
approval policy ("require approval for all external contributors") blocks
the run itself before a single step executes, regardless of what the
workflow YAML says. For same-repo branches (no fork involved), that policy
does not apply — the `ci-tests` environment is what gates those, making the
environment protection defense-in-depth relative to the fork policy rather
than the other way around. Full detail: `.claude/rules/ci-cd-security.md`.

## Deliberate non-features

- **No dependency caches on self-hosted runners.** A cache a PR can write to
  is shared mutable state between PRs — one PR could poison a package that a
  later, unrelated run then trusts. `npm ci` and `pip install` run fresh,
  inside the container, on every job.
- **No git in the CI node image.** `frontend-build` uses `node:20-slim`,
  which has no `git` binary. `client/vite.config.ts` shells out to `git` for
  the build's commit hash and branch name and falls back to `'unknown'` /
  release build type on failure — so the CI gate build silently gets
  `__GIT_COMMIT__ = 'unknown'`. That's fine: this build is a pass/fail gate
  whose artifact is discarded; the frontend that's actually deployed is built
  separately on the production host during deploy, where git is present.
  Don't "fix" this by installing git in the image.
- **`raid-mdadm-loopback` never runs on self-hosted hardware.** It's pinned
  to `ubuntu-latest` and the workflow explicitly forbids making the runner
  configurable, even for forks — only an on/off toggle
  (`ENABLE_RAID_LOOPBACK`) exists. Real `mdadm` commands against real disks
  could destroy an array; the loop-device tests only ever run on disposable
  GitHub-hosted VMs.
- **Coverage floors, not coverage targets.** Both test jobs measure coverage,
  print it to the job summary, and fail below a floor frozen just under the
  last measurement (`--cov-fail-under=65` for `backend/app`; Vitest
  `thresholds` of 23/23/23/21 for `client/src`). The floor exists to catch a
  regression, not to certify quality — the numbers are low and honest about
  it. Deliberately absent: per-diff coverage ("new code ≥ X%") and any
  third-party coverage service. Diff-coverage would need a second container
  image just to run `diff-cover`, and an external service would mean an
  unpinned action plus egress to a host that isn't on the allowlist below.
  Both become worth revisiting once the frontend test surface grows
  (issues #316, #317).
- **Resource limits on CI containers.** Both sandbox jobs run their container
  with `--cpus=4 --memory=3g`. The runner host also runs production BaluHost
  workloads, so CI must not be free to saturate it. Because `--cpus` is a CFS
  quota rather than a `cpuset`, tools that size their own worker pool from
  `os.cpu_count()` still see every host thread — `pytest` is pinned to
  `-n 4` and Vitest to `--maxWorkers=4` so neither oversubscribes the
  3 GB container and gets OOM-killed.

## Egress expectations

The three sandboxed jobs and the runner agent itself need outbound access to:
`registry.npmjs.org` (`npm ci` in `frontend-build` and `mock-e2e`), `pypi.org`
and `files.pythonhosted.org` (`pip install` in `backend-tests`),
`registry.docker.io` (pulling the pinned `python:3.11-slim` / `node:20-slim`
images), `mcr.microsoft.com` plus `*.data.mcr.microsoft.com` (pulling the
pinned Playwright image and its blobs), and `api.github.com` plus
`objects.githubusercontent.com` (job orchestration, checkout, log/artifact
upload). Any future egress firewall on the runner host must allow all of these
or CI silently breaks. Note that the Playwright image needs no
`playwright.download.prss.microsoft.com` access, because the browsers come
baked into the pinned image rather than being downloaded per run.
