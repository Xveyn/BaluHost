# AMD GPU Power Management — sysfs Permissions

**Audience:** Admins enabling GPU Power Management on a host with an AMD GPU and seeing **`WRITE PERMISSION: missing`** in the UI.

**Symptom:** Under System Control → GPU Power Management the badge in the top-right reads *missing*, and the logs contain:

```
AMD apply_state failed: [Errno 13] Permission denied:
'/sys/class/drm/card0/device/power_dpm_force_performance_level'
```

---

## Background

The AMDGPU kernel driver exposes power control via two sysfs files that BaluHost writes to when switching the GPU between Active / Standby / Deep Idle:

| File | Purpose |
|---|---|
| `/sys/class/drm/card*/device/power_dpm_force_performance_level` | Forces a performance level (`auto`, `low`, `high`, `manual`) |
| `/sys/class/drm/card*/device/pp_power_profile_mode` | Selects a profile (3D, Compute, VR, …) |

Default permissions on Debian 13:

```
-rw-r--r-- 1 root root /sys/class/drm/card0/device/power_dpm_force_performance_level
-rw-r--r-- 1 root root /sys/class/drm/card0/device/pp_power_profile_mode
```

→ Only `root` can write. The BaluHost backend runs as **`sven`** (or whichever user was selected at install time), so it hits a `Permission denied` error.

## Fix: udev rule + `video` group

Same pattern we use for `cpufreq`:

1. A udev rule re-chowns the two sysfs files to group `video` and adds the group-write bit on every drm `add`/`change` event (boot, hot-plug, suspend resume).
2. The BaluHost service user is added to the `video` group.
3. Restart the backend so the process picks up its new group membership.

## Apply in production

Three ways:

### A) One-shot manual (quickest on the current server)

On the server, **as root**:

```bash
cd /opt/baluhost
sudo BALUHOST_USER=sven bash deploy/scripts/install-amd-gpu-permissions.sh
```

Immediate effect; backend is restarted automatically.

### B) Via the GitHub Actions auto-deploy

Starting with the branch that introduces the `SYNC_PERMISSIONS` variable:

1. **One time** (on the server, as root): refresh the deploy sudoers file so
   the CI deploy can install the udev rule passwordless:

   ```bash
   cd /opt/baluhost
   git pull
   sudo BALUHOST_USER=sven bash deploy/scripts/install-deploy-sudoers.sh
   ```

   After this `bash /opt/baluhost/deploy/scripts/install-amd-gpu-permissions.sh`
   is on the deploy-user sudoers allow-list.

2. **Then** in GitHub: Actions → "Deploy Production" → **Run workflow**
   → tick *Re-apply OS-level permission grants* → Run.

   The CI deploy runs as normal (git pull, alembic upgrade, build, restart),
   plus a step "OS Permission Grants (sync requested)" that runs the
   standalone script idempotently.

3. **Regular push deploys** to `main` do **not** re-sync permissions
   (variable default = false). Database handling is unchanged.

### C) Fresh install on a new host

Nothing to do. `deploy/install/modules/10-systemd-services.sh` ships the
udev rule and adds the user to the `video` group automatically.

The script:

1. Writes `/etc/udev/rules.d/70-baluhost-amd-gpu.rules`
2. Adds `sven` (or `$BALUHOST_USER`) to the `video` group if not already a member
3. Reloads udev and re-triggers the DRM subsystem
4. Restarts `baluhost-backend.service` so the process picks up the new group

## Verification

**1. sysfs permissions:**

```bash
ls -la /sys/class/drm/card0/device/power_dpm_force_performance_level
# Expected: -rw-rw-r-- 1 root video
```

**2. backend user in `video` group:**

```bash
groups sven
# Expected: ... video ...
```

**3. UI / API:**

```bash
# In the UI: System Control → GPU Power Management → "WRITE PERMISSION: ok"
# Or via API:
curl -s -H "Authorization: Bearer <admin-jwt>" \
  http://localhost:8000/api/gpu-power/status | jq '.has_write_permission'
# Expected: true
```

**4. Logs clean:**

```bash
sudo journalctl -u baluhost-backend --since "5 minutes ago" | grep "AMD apply_state failed"
# Expected: no matches
```

## NVIDIA GPUs

For NVIDIA cards we use `nvidia-smi` as the write interface — it works for non-root users with the right capabilities, no sysfs permission tricks required. The rule documented here is AMD-specific.

## New AMD cards / hot-plug

The udev rule fires on every `add|change` event in the DRM subsystem. A freshly added AMD card (hot-plug or new PCIe slot after reboot) gets correct permissions automatically — no need to re-run the script.

## Relation to other permission grants

This rule is an independent fix for GPU Power Management. It is **unrelated** to:

- `polkit` for the logind sleep inhibitor (file `50-baluhost-inhibit-sleep.rules`)
- `cpufreq` group for CPU Power Management
- Sudoers rules for the self-hosted update mechanism

If the UI shows *missing* on several power cards, each level has its own fix — see the individual deployment wiki entries.

## Related files

- `deploy/install/templates/70-baluhost-amd-gpu.rules` — udev rule template
- `deploy/scripts/install-amd-gpu-permissions.sh` — standalone setup script
- `deploy/install/modules/10-systemd-services.sh` — installer hook for fresh installs
- `backend/app/services/power/gpu/amd_backend.py` — code that writes to the sysfs files
