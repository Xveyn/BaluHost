# Self-Hosted GitHub Actions Runner

BaluHost uses a self-hosted runner on the NAS for production deployments.

## Setup (One-Time)

### 1. Create runner directory

```bash
sudo mkdir -p /opt/actions-runner
sudo chown sven:sven /opt/actions-runner
cd /opt/actions-runner
```

### 2. Download and configure

Go to the repository **Settings > Actions > Runners > New self-hosted runner** and follow the instructions. Summary:

```bash
# Download (check GitHub for latest version)
curl -o actions-runner-linux-x64.tar.gz -L https://github.com/actions/runner/releases/download/v2.332.0/actions-runner-linux-x64-2.332.0.tar.gz
tar xzf actions-runner-linux-x64.tar.gz

# Configure (use the token from GitHub Settings)
./config.sh --url https://github.com/Xveyn/BaluHost --token <TOKEN>
```

When prompted:
- **Runner group**: Default
- **Runner name**: `baluhost-nas`
- **Labels**: `self-hosted,Linux,X64` (defaults are fine)
- **Work folder**: `_work` (default)

### 3. Install as systemd service

```bash
sudo ./svc.sh install sven
sudo ./svc.sh start
sudo systemctl enable actions.runner.Xveyn-BaluHost.BaluNode.service
```

### 4. Verify

```bash
sudo ./svc.sh status
# Or:
sudo systemctl status actions.runner.Xveyn-BaluHost.BaluNode.service
```

The runner should appear as "Online" in GitHub Settings > Actions > Runners.

## Maintenance

### Check runner status

```bash
./deploy/runner/check-runner.sh
```

### Restart runner

```bash
sudo systemctl restart actions.runner.Xveyn-BaluHost.BaluNode.service
```

### Update runner

GitHub auto-updates the runner binary. If manual update is needed:

```bash
cd /opt/actions-runner
sudo ./svc.sh stop
# Download new version
sudo ./svc.sh start
```

## Security Notes

- Runner executes as `sven` (same user as BaluHost services)
- Deploy script uses passwordless sudo for `systemctl restart/reload` only (see `deploy/install/templates/baluhost-deploy-sudoers`)
- Runner only triggers on `push to main` (after CI checks pass on GitHub-hosted runners)
- The `production` environment in GitHub can be configured with required reviewers for additional protection

## Prerequisites

The NAS must have:
- Git, Node.js 20+, Python 3.11+, npm
- PostgreSQL running and accessible
- Network access to GitHub (for runner communication)
- Passwordless sudo for service restarts (installed by module 10)
