# Fix Core Uptime Polkit Denial on Production Server

**Date:** 2026-05-02
**Status:** Open
**Server:** BaluNode (Debian 13, service user `sven`, UID 1000)

## Problem

Core Operating Hours feature does not block third-party suspend on production.
Backend log shows the inhibitor failing every 60s:

```
systemd-inhibit exited immediately (rc=1) — likely polkit denial.
Install /etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules.
stderr='Failed to inhibit: Interactive authentication required.'
```

Result: `mate-screensaver` triggers `systemctl suspend` every ~15 min and
logind grants it because no block-sleep inhibitor is held.

## Root Cause

PR #65 (`10e9daf`) added the `systemd-inhibit` block-lock + a polkit rule
template at `deploy/install/templates/50-baluhost-inhibit-sleep.rules`.
The rule is installed only by `deploy/install/modules/10-systemd-services.sh`
during a full install. Update path (`git pull` + `systemctl restart`) does
not re-run that module, so the polkit rule was never written to
`/etc/polkit-1/rules.d/` on this host.

Code-side everything is correct — subprocess spawns, polkit denies,
exit-code-1 path is logged exactly as designed.

## TODO

### On the production server (BaluNode)

- [ ] **Confirm core-uptime windows exist** (table is plural `core_uptime_windows`):
  ```bash
  sudo -u postgres psql baluhost -c "SELECT id, enabled, weekdays, start_time, end_time, label FROM core_uptime_windows;"
  ```
  Expect at least one row with `enabled = t` and weekdays/time covering "now".

- [ ] **Install the polkit rule for service user `sven`**:
  ```bash
  sudo tee /etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules > /dev/null <<'EOF'
  // BaluHost — allow the service user to acquire logind block-sleep inhibitors.
  polkit.addRule(function(action, subject) {
      if (action.id == "org.freedesktop.login1.inhibit-block-sleep" &&
          subject.user == "sven") {
          return polkit.Result.YES;
      }
  });
  EOF
  sudo chmod 644 /etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules
  ```

- [ ] **Restart backend** (cleaner than waiting for the 60s schedule loop):
  ```bash
  sudo systemctl restart baluhost-backend
  ```

- [ ] **Verify inhibitor subprocess is alive**:
  ```bash
  ps -ef | grep "systemd-inhibit.*BaluHost" | grep -v grep
  sudo journalctl -u baluhost-backend --since "1 minute ago" | grep -iE "inhibitor (acquired|polkit)"
  ```
  Expect `Core uptime sleep inhibitor acquired (pid=..., reason=core_uptime_active)`.

- [ ] **Smoketest — manual suspend must be refused inside an active window**:
  ```bash
  sudo systemctl suspend
  ```
  Expect: `Call failed: Operation refused, ... currently inhibiting suspend`.

- [ ] **Soak — confirm `mate-screensaver` no longer suspends inside windows**.
  Watch `journalctl --since "1 hour ago" | grep -iE "Reached target sleep|Delay lock"` —
  no new entries should appear during an active Core Uptime window.

### Repo-side follow-up (so this doesn't bite the next host)

- [ ] **Make the polkit rule survive update deploys.** Options:
  - Have the update path (`update_service.py` / Self-Hosted-Update mechanism)
    explicitly call `bash deploy/install/modules/10-systemd-services.sh` so
    polkit/sudoers/udev rules get re-applied.
  - Or extract polkit-rule install into its own idempotent module that the
    backend's startup hook can run on first launch when the file is missing.
  - Decide which approach matches the existing update philosophy before coding.

- [ ] **Surface the polkit-denial state in the UI.** When
  `CoreUptimeInhibitor.acquire()` returns False, the sleep manager should
  expose a status flag (e.g. `core_uptime_inhibitor_state: "denied"`) so the
  Core Uptime panel can render an actionable warning (`"Polkit-Regel fehlt
  — Drittanbieter-Suspend wird nicht blockiert"`) instead of silently
  degrading. Today the only signal is a journal warning every 60s.

- [ ] **Add a self-test endpoint** (`GET /api/sleep/core-uptime/inhibitor-test`,
  admin-only) that calls `CoreUptimeInhibitor.acquire("selftest")` for ~1s
  and reports success/denial. Lets users verify polkit setup without
  reading journals.

## Notes

- Service user `sven` is unusual but valid (the install was done with
  `BALUHOST_USER=sven`). The hardcoded `subject.user == "sven"` in the
  rule above is correct *for this host only* — when the install module
  is re-run via the template, `${BALUHOST_USER}` will be substituted
  correctly anyway.
- `loginctl list-inhibitors` is missing on this host's systemd build
  (`Unknown command verb`). Use `ps -ef | grep systemd-inhibit` instead
  to verify the lock is held.
