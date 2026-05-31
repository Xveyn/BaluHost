#!/bin/bash
# Re-install (or update) the baluhost-hardware sudoers file on an existing host.
#
# Why: the hardware sudoers template (RAID/mdadm, SMART, fan + CPU-freq sysfs,
# dmidecode, suspend, rtcwake, ethtool) is rendered once at install time, but
# ci-deploy.sh does NOT re-run installer modules on a routine deploy. Template
# fixes therefore never reach an already-installed box — e.g. the
# `systemctl can-suspend` + `ethtool` capability-probe rules (added 2026-05-04)
# left the Sleep page's Suspend/WoL badges greyed out on prod even though both
# features worked. Operators run this script — or a SYNC_PERMISSIONS=1 deploy,
# which calls it — to push template changes onto /etc/sudoers.d/baluhost-hardware.
#
# Safe by construction:
#   - renders @@BALUHOST_USER@@ from the actual service user,
#   - validates with `visudo -cf` BEFORE replacing the live file,
#   - keeps a timestamped backup of the previous live file,
#   - installs -m 0440 -o root -g root.
#
# Run as root.

set -euo pipefail

TEMPLATE="${TEMPLATE:-/opt/baluhost/deploy/install/templates/baluhost-hardware-sudoers}"
TARGET="/etc/sudoers.d/baluhost-hardware"
SERVICE="${SERVICE:-baluhost-backend.service}"

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
echo "  ..  rendering hardware sudoers for user: $BALUHOST_USER"

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
