# PPD-Sudoers Deploy-Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ci-deploy.sh` (under `SYNC_PERMISSIONS=1`) provision `/etc/sudoers.d/baluhost-power` idempotently from the repo template, rendered with the real service user, and clear the obsolete `baluhost-ppd` workaround.

**Architecture:** A new standalone installer script `install-power-sudoers.sh` mirrors the existing `install-hardware-sudoers.sh` (derive user from systemd → `sed @@BALUHOST_USER@@` → `visudo -cf` before replace → backup → install 0440 root:root → cleanup `baluhost-ppd`). `ci-deploy.sh` calls it in the `SYNC_PERMISSIONS` block. The `baluhost-deploy-sudoers` template whitelists the new script's pinned absolute path.

**Tech Stack:** Bash, sudoers/visudo, systemd. No application code, no pytest. Verification via `bash -n` and template-render inspection.

**Spec:** `docs/superpowers/specs/2026-06-07-ppd-sudoers-deploy-provisioning-design.md`

**Reference file (clone source):** `deploy/scripts/install-hardware-sudoers.sh`

---

## File Structure

- **Create:** `deploy/scripts/install-power-sudoers.sh` — standalone idempotent power-sudoers installer + `baluhost-ppd` cleanup.
- **Modify:** `deploy/scripts/ci-deploy.sh` — add power-sudoers hook in the `SYNC_PERMISSIONS` block (replace the `# Future permission scripts go here` placeholder, currently lines 461-462).
- **Modify:** `deploy/install/templates/baluhost-deploy-sudoers` — add two pinned whitelist lines after the hardware block (currently after line 19).

All three live under `/deploy/` → CODEOWNERS-tagged `@Xveyn`.

---

### Task 1: Create `install-power-sudoers.sh`

**Files:**
- Create: `deploy/scripts/install-power-sudoers.sh`

- [ ] **Step 1: Write the script**

Create `deploy/scripts/install-power-sudoers.sh` with exactly this content:

```bash
#!/bin/bash
# Re-install (or update) the baluhost-power sudoers file on an existing host.
#
# Why: the power sudoers template (logind idle helper, power-profiles-daemon
# stop/start/mask/unmask for the CPU power-authority feature, and sddm desktop
# toggle) is rendered once at install time by module 13, but ci-deploy.sh does
# NOT re-run installer modules on a routine deploy. Template fixes therefore
# never reach an already-installed box — e.g. the four power-profiles-daemon
# rules (#123) left the CPU power authority returning HTTP 500 on prod, and a
# stale pre-@@-token file left the literal placeholder in the live sudoers file
# (#126). Operators run this script — or a SYNC_PERMISSIONS=1 deploy, which
# calls it — to push template changes onto /etc/sudoers.d/baluhost-power.
#
# It also clears the obsolete /etc/sudoers.d/baluhost-ppd workaround (manual
# four-line PPD grant) once the regular baluhost-power file supersedes it.
#
# Safe by construction:
#   - renders @@BALUHOST_USER@@ from the actual service user,
#   - validates with `visudo -cf` BEFORE replacing the live file,
#   - keeps a timestamped backup of the previous live file,
#   - installs -m 0440 -o root -g root,
#   - removes baluhost-ppd ONLY after baluhost-power is validated + installed.
#
# Run as root.

set -euo pipefail

TEMPLATE="${TEMPLATE:-/opt/baluhost/deploy/install/templates/sudoers-baluhost-power}"
TARGET="/etc/sudoers.d/baluhost-power"
SERVICE="${SERVICE:-baluhost-backend.service}"
WORKAROUND="/etc/sudoers.d/baluhost-ppd"

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)." >&2
    exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    echo "Did you 'git pull' /opt/baluhost first?" >&2
    exit 1
fi

# Derive the service user from baluhost-backend.service 'User=' so the sudoers
# rules are granted to whoever actually runs the backend — not a hardcoded name.
# Order: explicit BALUHOST_USER override > systemd 'User=' > error out.
SERVICE_USER="$(systemctl show -p User --value "$SERVICE" 2>/dev/null || true)"
BALUHOST_USER="${BALUHOST_USER:-${SERVICE_USER:-}}"
if [[ -z "$BALUHOST_USER" ]]; then
    echo "ERROR: could not determine the service user from '$SERVICE' (User=)" >&2
    echo "       and BALUHOST_USER is unset. Set BALUHOST_USER explicitly." >&2
    exit 1
fi
echo "  ..  rendering power sudoers for user: $BALUHOST_USER"

# Substitute @@BALUHOST_USER@@ placeholder into a temp file.
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
sed "s|@@BALUHOST_USER@@|$BALUHOST_USER|g" "$TEMPLATE" >"$TMP"

# Validate BEFORE touching the live file — never leave an invalid sudoers file.
if ! visudo -cf "$TMP" >/dev/null 2>&1; then
    echo "ERROR: generated sudoers file fails visudo syntax check; live file untouched." >&2
    visudo -cf "$TMP" || true
    exit 1
fi

# Timestamped backup of the existing live file (if any), so a bad change can be
# rolled back by hand.
if [[ -f "$TARGET" ]]; then
    BACKUP="${TARGET}.bak.$(date +%Y%m%d%H%M%S)"
    cp -p "$TARGET" "$BACKUP"
    echo "  OK  backed up existing file to: $BACKUP"
fi

install -m 0440 -o root -g root "$TMP" "$TARGET"
echo "  OK  installed: $TARGET"
visudo -cf "$TARGET" >/dev/null && echo "  OK  visudo syntax check passed"

# Clear the obsolete manual PPD workaround ONLY now that the regular
# baluhost-power file is validated and live — never leave a gap without rules.
if [[ -f "$WORKAROUND" ]]; then
    WB="${WORKAROUND}.bak.$(date +%Y%m%d%H%M%S)"
    cp -p "$WORKAROUND" "$WB"
    rm -f "$WORKAROUND"
    echo "  OK  removed obsolete workaround $WORKAROUND (backed up to $WB)"
fi
```

- [ ] **Step 2: Verify shell syntax**

Run: `bash -n deploy/scripts/install-power-sudoers.sh`
Expected: no output, exit code 0 (a syntax error would print a line/message).

- [ ] **Step 3: Verify the template renders to a valid sudoers body**

This mimics exactly what the script's `sed` does, without needing root/visudo. Run:

```bash
sed 's|@@BALUHOST_USER@@|sven|g' deploy/install/templates/sudoers-baluhost-power > /tmp/power-sudoers.rendered
```

Then Read `/tmp/power-sudoers.rendered` and confirm:
- It contains the four lines `sven ALL=(root) NOPASSWD: /usr/bin/systemctl {stop,start,mask,unmask} power-profiles-daemon`.
- No literal `@@BALUHOST_USER@@` remains anywhere.

Expected: four PPD lines present, zero `@@` occurrences.

- [ ] **Step 4: Commit**

```bash
git add deploy/scripts/install-power-sudoers.sh
git commit -m "feat(deploy): install-power-sudoers.sh — idempotent baluhost-power provisioning (#126)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Wire the hook into `ci-deploy.sh`

**Files:**
- Modify: `deploy/scripts/ci-deploy.sh` (replace the placeholder comment at lines 461-462)

- [ ] **Step 1: Replace the placeholder block**

Find this exact block in `deploy/scripts/ci-deploy.sh` (currently lines 461-462, inside the `if [[ "${SYNC_PERMISSIONS:-0}" == "1" ... ]]` branch, right after the hardware-sudoers block closes):

```bash
    # Future permission scripts go here following the same pattern:
    # if [[ -f "$INSTALL_DIR/deploy/scripts/install-<thing>-permissions.sh" ]]; then ...
```

Replace it with:

```bash
    # Power sudoers: power-profiles-daemon stop/start/mask/unmask + logind idle
    # helper + sddm desktop-toggle grants. The installer renders @@BALUHOST_USER@@
    # from the running service user and validates with visudo before replacing the
    # live file. This is the path by which sudoers-baluhost-power template changes
    # reach an installed box; it also clears the obsolete /etc/sudoers.d/baluhost-ppd
    # workaround once superseded. Invoked with no env vars (like the others): the
    # deploy sudoers rule whitelists this exact `bash <abs-path>` invocation, and the
    # script's internal TEMPLATE default (/opt/baluhost/...) matches the prod INSTALL_DIR.
    POWER_SUDOERS_SCRIPT="$INSTALL_DIR/deploy/scripts/install-power-sudoers.sh"
    if [[ -f "$POWER_SUDOERS_SCRIPT" ]]; then
        log_info "Re-applying power sudoers..."
        if sudo bash "$POWER_SUDOERS_SCRIPT"; then
            log_info "Power sudoers sync OK."
        else
            log_warn "Power sudoers sync failed (non-fatal — deploy continues)."
        fi
    else
        log_warn "Power sudoers script not found at $POWER_SUDOERS_SCRIPT (skipping)."
    fi

    # Future permission scripts go here following the same pattern:
    # if [[ -f "$INSTALL_DIR/deploy/scripts/install-<thing>-permissions.sh" ]]; then ...
```

(The trailing `# Future permission scripts go here` comment is kept so the extension point survives for the next script.)

- [ ] **Step 2: Verify shell syntax**

Run: `bash -n deploy/scripts/ci-deploy.sh`
Expected: no output, exit code 0.

- [ ] **Step 3: Commit**

```bash
git add deploy/scripts/ci-deploy.sh
git commit -m "feat(deploy): call install-power-sudoers.sh in SYNC_PERMISSIONS block (#126)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Whitelist the new script in the deploy-sudoers template

**Files:**
- Modify: `deploy/install/templates/baluhost-deploy-sudoers` (add two lines after line 19)

- [ ] **Step 1: Add the pinned whitelist lines**

Find this exact block (lines 18-19) in `deploy/install/templates/baluhost-deploy-sudoers`:

```
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /bin/bash /opt/baluhost/deploy/scripts/install-hardware-sudoers.sh
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/bash /opt/baluhost/deploy/scripts/install-hardware-sudoers.sh
```

Replace it with (appends the two power lines immediately after):

```
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /bin/bash /opt/baluhost/deploy/scripts/install-hardware-sudoers.sh
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/bash /opt/baluhost/deploy/scripts/install-hardware-sudoers.sh
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /bin/bash /opt/baluhost/deploy/scripts/install-power-sudoers.sh
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/bash /opt/baluhost/deploy/scripts/install-power-sudoers.sh
```

- [ ] **Step 2: Verify the rendered template is valid sudoers syntax (no root needed)**

Render with the real-user substitution and inspect:

```bash
sed 's|@@BALUHOST_USER@@|sven|g' deploy/install/templates/baluhost-deploy-sudoers > /tmp/deploy-sudoers.rendered
```

Read `/tmp/deploy-sudoers.rendered` and confirm both `install-power-sudoers.sh` lines are present (one `/bin/bash`, one `/usr/bin/bash`) and no `@@` remains.
Expected: two new power lines present, zero `@@` occurrences.

> Note: a full `visudo -cf` check requires a Linux box; it runs for real during the bootstrap step on BaluNode (see spec). The render inspection is the local gate.

- [ ] **Step 3: Commit**

```bash
git add deploy/install/templates/baluhost-deploy-sudoers
git commit -m "feat(deploy): whitelist install-power-sudoers.sh in deploy sudoers (#126)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Final verification + PR

- [ ] **Step 1: Re-run both syntax checks together**

```bash
bash -n deploy/scripts/install-power-sudoers.sh && bash -n deploy/scripts/ci-deploy.sh && echo "OK: both scripts parse"
```
Expected: `OK: both scripts parse`

- [ ] **Step 2: Confirm the working tree is clean and on the feature branch**

```bash
git status
git log --oneline -4
```
Expected: branch `fix/ppd-sudoers-deploy-provisioning`, clean tree, the three feature commits (+ spec commit) present.

- [ ] **Step 3: Open the PR**

Per project rule (`feedback_pr_body_quoting`): write the PR body with the Write tool to a temp file, then `gh pr create --body-file`. The PR description must:
- Reference issue #126 ("Closes #126").
- Summarize the three changes.
- Flag the CI/CD-security-sensitive whitelist change for the CODEOWNERS reviewer.
- Include the BaluNode bootstrap steps from the spec (one-time `install-deploy-sudoers.sh` + `SYNC_PERMISSIONS=1` deploy) and the three verification commands.

---

## Notes for the executor

- **No application/pytest changes** — this is deploy/shell only. Do not invent tests beyond the syntax + render checks above.
- **CRLF:** repo runs `core.autocrlf=true`; the new `.sh` file will be stored LF and that warning is expected/harmless.
- **Bootstrap reality:** the whitelist lines only become live on BaluNode after `/etc/sudoers.d/baluhost-deploy` is re-rendered (`install-deploy-sudoers.sh`). That is an operator step documented in the spec, NOT part of these repo commits.
- **Do not** modify `process_template` or fold power rules into the hardware sudoers file — both explicitly out of scope (see spec).
