# Self-Hosted GitHub Actions Runners

BaluHost runs **two** self-hosted runners on the NAS host (`BaluNode`), with
deliberately different trust levels. Do not conflate them.

| Runner | Labels | Triggers | Runs as | Isolation |
|---|---|---|---|---|
| **`BaluNode`** | `self-hosted, Linux, X64, **prod**` | production deploy (`deploy-production.yml`: `push: main` / `workflow_dispatch`) | deploy user with scoped passwordless sudo | none — full access to `/opt/baluhost`, `.env.production` |
| **`BaluNode-ci-sandbox`** | `self-hosted, Linux, X64, **ci-sandbox**` | PR `backend-tests` (gated by the `ci-tests` environment) | unprivileged `ci-runner` (no sudo, not in `docker`/`sudo`/`wheel`, no read on `/opt/baluhost`, `/etc/baluhost`, or secrets) | runs untrusted PR code inside **rootless Podman** (pinned `docker.io/library/python:3.11-slim`, only the workspace bind-mounted) |

> ⚠️ **The `prod` label on `BaluNode` is load-bearing.** `deploy-production.yml`
> targets `runs-on: [self-hosted, prod]`. If the `prod` label is removed,
> production deploys route to the sandbox runner and break (caught 2026-05-19).
>
> ⚠️ **PR-triggered workflows must NEVER run on `BaluNode`.** Only the
> `ci-sandbox` runner executes PR code, and only via the two-layer isolation
> (unprivileged `ci-runner` user + rootless Podman). See the Reviewer Checklist
> in `.claude/rules/ci-cd-security.md`.

The full trust model (four independent layers — CODEOWNERS, runner trigger
separation, the `github.actor == 'Xveyn'` deploy gate, and the `production`
environment reviewer) is documented authoritatively in
**`.claude/rules/ci-cd-security.md`**. This file is just the operational setup;
that file is the source of truth for *why* it's wired this way.

---

## Production runner — `BaluNode` (one-time setup)

### 1. Create runner directory

```bash
sudo mkdir -p /opt/actions-runner
sudo chown sven:sven /opt/actions-runner
cd /opt/actions-runner
```

### 2. Download and configure

Go to **Settings > Actions > Runners > New self-hosted runner** for the latest
download command, then:

```bash
# Download (check GitHub for the latest version)
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/v2.332.0/actions-runner-linux-x64-2.332.0.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

# Configure (use the token from GitHub Settings)
./config.sh --url https://github.com/Xveyn/BaluHost --token <TOKEN>
```

When prompted:
- **Runner group**: Default
- **Runner name**: `BaluNode`
- **Labels**: add **`prod`** → `self-hosted,Linux,X64,prod` (the `prod` label is **required** — see the warning above)
- **Work folder**: `_work` (default)

### 3. Install as a systemd service

```bash
sudo ./svc.sh install sven
sudo ./svc.sh start
sudo systemctl enable actions.runner.Xveyn-BaluHost.BaluNode.service
```

### 4. Verify

```bash
sudo systemctl status actions.runner.Xveyn-BaluHost.BaluNode.service
```

The runner should appear "Online" with the `prod` label in
**Settings > Actions > Runners**. Confirm the label with:

```bash
gh api repos/Xveyn/BaluHost/actions/runners
```

---

## CI sandbox runner — `BaluNode-ci-sandbox`

Provisioned by **`scripts/bootstrap-ci-runner.sh`**, which creates the
unprivileged `ci-runner` user, installs rootless Podman, and registers the
runner with the `ci-sandbox` label. This runner executes untrusted PR code, so
the bootstrap script's self-tests (no sudo for `ci-runner`, no `docker` group,
no read access to production paths) **must pass** for the isolation guarantees
to hold.

```bash
# As an admin on the NAS host (NOT as ci-runner):
sudo bash scripts/bootstrap-ci-runner.sh
```

PR `backend-tests` runs are additionally gated by the `ci-tests` GitHub
environment (required reviewer: `Xveyn`). Forks configure runner selection via
Repository Variables with `scripts/configure-ci.sh`; upstream behavior is
hardcoded to `github.repository == 'Xveyn/BaluHost'` and needs no variables.

---

## Maintenance

```bash
# Status (either runner)
./deploy/runner/check-runner.sh
sudo systemctl status actions.runner.Xveyn-BaluHost.BaluNode.service

# Restart the production runner
sudo systemctl restart actions.runner.Xveyn-BaluHost.BaluNode.service
```

GitHub auto-updates the runner binary. For a manual update:

```bash
cd /opt/actions-runner
sudo ./svc.sh stop
# download the new version, extract over the existing install
sudo ./svc.sh start
```

---

## Security notes (summary — see `.claude/rules/ci-cd-security.md` for the full model)

- **Layer separation:** `BaluNode` (`prod`) only ever sees code already on
  `main` (merged manually by Xveyn) or explicitly dispatched. `BaluNode-ci-sandbox`
  (`ci-sandbox`) is the only self-hosted runner permitted to run PR code, and
  only inside rootless Podman as the unprivileged `ci-runner`.
- **Scoped sudo:** the deploy uses passwordless sudo only for specific service
  actions (`deploy/install/templates/baluhost-deploy-sudoers`) — never blanket
  `ALL`.
- **Deploy gate:** `deploy-production.yml` runs only when `github.actor == 'Xveyn'`
  and pauses on the `production` environment for reviewer approval before
  executing on `BaluNode`.
- Both runners share the host kernel; a container escape from the sandbox lands
  as the unprivileged `ci-runner` — still without sudo or production access.

---

## Prerequisites (NAS host)

- Git, Node.js 20+, Python 3.11+, npm
- PostgreSQL running and accessible
- Network access to GitHub
- For `BaluNode`: scoped passwordless sudo for service restarts (installed by deploy module 10)
- For `BaluNode-ci-sandbox`: rootless Podman + subuid/subgid range for `ci-runner` (set up by `scripts/bootstrap-ci-runner.sh`)
