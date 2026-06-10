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

Your IDE's GitHub Actions extension may warn "Context access might be invalid"
on `vars.ENABLE_*` — that is expected: unset variables are part of the design
(unset means default behavior).

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
