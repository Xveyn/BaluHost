RAID Scrub: Overview and Safe Defaults

This document explains the automatic RAID scrub scheduler and the immediate scrub API in BaluHost.

Purpose
- Periodic scrubbing (also called "check") detects and repairs silent data corruption and verifies RAID integrity.

Configuration (recommended safe defaults)
- `RAID_SCRUB_ENABLED=false` (default)
  - Keep disabled in CI or on runners that use loop devices unless you intend to run real scrub operations.
- `RAID_SCRUB_INTERVAL_HOURS=168` (1 week)
  - Typical production cadence is weekly or bi-weekly; choose based on hardware and I/O load.
- `RAID_ASSUME_CLEAN_BY_DEFAULT=false`
  - Never enable `--assume-clean` in production; only enable for controlled test environments.

How it works
- The scheduler uses APScheduler (optional). If APScheduler is not installed the scheduler is skipped but the immediate trigger API still works.
- On app startup the scheduler is started when `RAID_SCRUB_ENABLED=true` and stopped on shutdown.
- The scheduler triggers the same code path as the admin API `POST /api/raid/scrub`.

Immediate scrub (admin API)
- Endpoint: `POST /api/raid/scrub`
- Body: JSON `{}` to trigger all arrays, or `{ "array": "md0" }` to scrub a single array.
- Requires an admin user. The endpoint calls the RAID backend to set `sync_action` to `check` (Dev backend) or triggers kernel/`mdadm` sync for mdadm-backed hosts.

CI and Self-hosted Runner Guidance
- For CI (GitHub Actions) use the `DevRaidBackend` by setting `RAID_FORCE_DEV_BACKEND=1` in the workflow environment. This prevents destructive operations and allows tests to simulate scrubs.
- For a self-hosted runner that should exercise real `mdadm` scrubs:
  - Provision dedicated loop devices or spare disks.
  - Ensure `mdadm`, `lsblk`, and required utilities are installed.
  - Run the runner under a dedicated, isolated VM or container to avoid affecting unrelated host disks.
  - Configure system-level safeguards (sudoers, limited wrapper scripts) as described in `scripts/bootstrap-runner-*.sh`.

APScheduler (optional) & CI install
- APScheduler is an optional runtime dependency used only for in-process scheduled jobs (RAID scrubs, SMART scans, notification jobs). The application will run normally without it; scheduled jobs are skipped when APScheduler is not available but the immediate API triggers still work.
- To enable scheduler jobs in a runner or production host, install the scheduler extra or the `apscheduler` package. Example GitHub Actions step to install the backend with the scheduler extra:

```yaml
- name: Install backend with scheduler extra
  run: |
    cd backend
    # install dev extras + scheduler helpers
    python -m pip install -e .[dev,scheduler]
```

- Alternatively, install APScheduler directly in the environment:

```bash
cd backend
python -m pip install apscheduler
```

- If you plan to enable automatic scrubbing in CI or integration jobs, set the scheduler and safety env vars explicitly. Example (only enable scrubs when you control the runner environment):

```yaml
env:
  RAID_SCRUB_ENABLED: '1'            # enable periodic scrubs
  RAID_FORCE_DEV_BACKEND: '0'        # use mdadm when the runner is provisioned for it
  NAS_MODE: 'production'             # or leave unset for production behaviour
```

- For typical CI runs you should keep scrubbing disabled and prefer the dev backend to avoid touching host disks:

```yaml
env:
  RAID_SCRUB_ENABLED: '0'
  RAID_FORCE_DEV_BACKEND: '1'
  NAS_MODE: 'dev'
```

Operational notes
- Scrubbing is I/O intensive. Prefer low-traffic windows (overnight) and tune `RAID_SCRUB_INTERVAL_HOURS` accordingly.
- Monitor `sync_action` and resync progress via `GET /api/raid/status`.
- If using mdadm, ensure kernel sync_action sysfs entries are writable by the service user or use a privileged wrapper.

Troubleshooting
- If the scheduler does not start, confirm `APScheduler` is installed (`pip install apscheduler`) or leave scrub scheduler disabled and trigger scrubs via the API.
  - Preferred install: install optional scheduler extra from the repository root:
    ```bash
    pip install -e .[scheduler]
    ```
    Or install the package normally with extras: `pip install .[scheduler]`.
- On systems without `mdadm`, `scrub_now()` will raise if there are no arrays; use the Dev backend for testing.

Security
- Only admin users may trigger immediate scrubs via the API.
- Do not enable `RAID_ASSUME_CLEAN_BY_DEFAULT` on production systems.

Questions or changes
- If you'd like a cron-style window (only run at night), I can add a time-window config and job trigger (e.g. `start_at_hour`/`end_at_hour`) and implement it in the scheduler.
