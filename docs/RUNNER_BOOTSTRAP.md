# Runner bootstrap (non-interactive)

This document describes the non-interactive wrapper and the systemd unit template included in `scripts/`.

Files added:

- `scripts/bootstrap-runner-ubuntu.sh` — interactive/automated bootstrap that installs dependencies, creates loop devices, and registers the runner.
- `scripts/bootstrap-runner-noninteractive.sh` — small wrapper that reads env vars and calls the bootstrap script via `sudo`.
- `scripts/actions-runner.service.template` — systemd unit template you can customize and install for the runner service.

Usage (non-interactive):

```bash
export BOOTSTRAP_REPO_URL="https://github.com/OWNER/REPO"
export BOOTSTRAP_RUNNER_TOKEN="<token>"
export BOOTSTRAP_LABELS="self-hosted,linux,mdadm"
export BOOTSTRAP_RUNNER_USER="runner"
export BOOTSTRAP_WORK_DIR="/opt/actions-runner"
export BOOTSTRAP_LOOP_DEVICES=3

sudo bash scripts/bootstrap-runner-noninteractive.sh
```

Install systemd unit (example):

```bash
# After the runner is registered and installed at /opt/actions-runner:
sudo cp scripts/actions-runner.service.template /etc/systemd/system/actions-runner-runner.service
sudo sed -i 's|{{WORK_DIR}}|/opt/actions-runner|g' /etc/systemd/system/actions-runner-runner.service
sudo systemctl daemon-reload
sudo systemctl enable --now actions-runner-runner.service
```

Security notes:
- Use a dedicated VM for the runner.
- The bootstrap script adds a sudoers entry allowing the runner user to run `mdadm`/`losetup` without a password. Keep the machine isolated.

Cleanup:
- Remove loop devices with `sudo losetup -a` and `sudo losetup -d /dev/loopX`.
- To unregister the runner: `/opt/actions-runner/config.sh remove --unattended --token <token>`.
