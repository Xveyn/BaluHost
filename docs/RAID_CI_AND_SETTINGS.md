# RAID settings and CI guidance

This document explains the RAID-related runtime settings and how to run RAID tests in CI, including using a self-hosted Linux runner with `mdadm`.

## Settings

Two new settings control runtime and CI behavior:

- `raid_force_dev_backend` (bool)
  - Default: `False`
  - When `True`, the application will use the `DevRaidBackend` (simulated/dev) even on Linux.
  - Useful for CI or development runners that do not have `mdadm`/real disks available.
  - Can be set via environment variable `RAID_FORCE_DEV_BACKEND=1` or in `.env`.

- `raid_assume_clean_by_default` (bool)
  - Default: `False`
  - When `True`, the mdadm-based array creation will append `--assume-clean` to `mdadm --create`.
  - WARNING: `--assume-clean` skips initial resync and can lead to data loss if used incorrectly. Keep this disabled in production.
  - Use only in controlled test environments.
  - Can be set via environment variable `RAID_ASSUME_CLEAN_BY_DEFAULT=1` or in `.env`.

### Example `.env` entries

```
# Use dev/simulated RAID backend on CI runners
RAID_FORCE_DEV_BACKEND=1

# Only set this on isolated test VMs where assume-clean is required
RAID_ASSUME_CLEAN_BY_DEFAULT=0
```

> Note: The application uses `pydantic` `BaseSettings`, so environment variables are mapped case-insensitively by name.

## CI: Running RAID tests safely

A GitHub Actions workflow was added that contains two approaches:

1. `raid-safe` job — forces `DevRaidBackend` by exporting `RAID_FORCE_DEV_BACKEND=1`. This runs reliably on hosted runners without `mdadm`.
2. `raid-mdadm` job — attempts to run tests against the real `mdadm` backend if `mdadm` is present on the runner; otherwise it is skipped.

The safe approach is recommended for public/shared runners. If you want to run `mdadm`-backed tests, use a self-hosted runner configured as described below.

## Self-hosted runner with `mdadm` (recommended for real integration tests)

If you want reproducible, real mdadm-based RAID CI, set up a self-hosted Linux runner with `mdadm` and device nodes available. Important considerations:

- Use a dedicated VM or physical machine; DO NOT run destructive mdadm tests on a multi-tenant or production host.
- Provide isolated block devices (loop devices, attached ephemeral disks, or a VM with additional virtual disks).
- Run the GitHub Actions Runner as a dedicated unprivileged user but allow specific commands via `sudo` when necessary (see below).

### Example setup (Ubuntu) — high level

1. Prepare the machine and install dependencies:

```bash
sudo apt-get update
sudo apt-get install -y mdadm util-linux curl tar
```

2. Create or attach empty block devices for tests (example using loop devices):

```bash
# create a 100MB file and map to loop device
fallocate -l 100M /var/lib/raid-test-disk1.img
sudo losetup -fP /var/lib/raid-test-disk1.img
# repeat for more devices as needed
```

3. Install and register the self-hosted runner (follow GitHub instructions for your repo/org). When configuring the runner, add a label such as `mdadm`:

- During `./config.sh` you can specify runner labels, e.g. `mdadm`, `linux`.

4. Allow the runner user to run `mdadm` and `lsblk` with minimal sudo permissions (edit `/etc/sudoers.d/github-runner`):

```
# Allow 'runner' user to run mdadm and losetup without password
runner ALL=(ALL) NOPASSWD: /sbin/mdadm, /sbin/losetup, /sbin/losetup -f, /usr/bin/losetup
```

Adjust the commands and paths to match your distribution.

5. Label the runner (if not already): add `mdadm` label — the workflow can then target `runs-on: [self-hosted, linux, mdadm]`.

### Security and safety notes

- Give the runner the minimum privileges needed. Prefer a dedicated VM which can be reprovisioned.
- Avoid running the runner as `root`. Use `sudo` only for specific commands.
- Clean up created loop devices / disks after tests.

## Example workflow for self-hosted runner

Place this in `.github/workflows/raid-mdadm-selfhosted.yml` (or adapt the provided `raid-tests.yml`):

```yaml
name: RAID Tests (self-hosted mdadm)

on:
  workflow_dispatch: {}

jobs:
  raid-mdadm-selfhosted:
    runs-on: [self-hosted, linux, mdadm]
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          cd backend
          python -m pip install -e .[dev]
      - name: Run RAID tests (mdadm)
        working-directory: backend
        run: |
          # Ensure we run against mdadm backend
          export RAID_FORCE_DEV_BACKEND=0
          pytest -q -k raid
```

This job will run only on runners that match the `self-hosted, linux, mdadm` labels.

## Summary

- Keep `raid_assume_clean_by_default` disabled in production.
- Use `RAID_FORCE_DEV_BACKEND=1` in CI on hosted runners to avoid requiring `mdadm`.
- For real integration testing, provision a self-hosted Linux runner with `mdadm` and label it (e.g., `mdadm`) and use the example workflow above.

If you want, I can:
- Add the `.env.example` entries to repository root.
- Add a short `README` snippet into `backend/README.md`.
- Produce an automated runner bootstrap script you can run on a fresh VM. Let me know which you prefer.
