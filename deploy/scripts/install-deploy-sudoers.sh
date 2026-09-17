#!/bin/bash
# Re-install (or update) the baluhost-deploy sudoers file on an existing host.
#
# Use case: the deploy sudoers template adds new lines (e.g. permission-grant
# scripts), but ci-deploy.sh does not re-run installer modules. Operators
# call this once after pulling such a change so the deploy user can use the
# new sudo rules without a full re-install.
#
# Run as root.

set -euo pipefail

# Where this script lives, the repo lives — the one source for the install
# directory that is correct on every box without anyone passing it in (#581).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${INSTALL_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
TEMPLATE="${TEMPLATE:-$INSTALL_DIR/deploy/install/templates/baluhost-deploy-sudoers}"
TARGET="/etc/sudoers.d/baluhost-deploy"
SERVICE="${SERVICE:-baluhost-backend.service}"

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)." >&2
    exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    # Single quotes: backticks inside double quotes would RUN `git pull` as
    # root in whatever directory this happens to be called from.
    echo "Did you 'git pull' $INSTALL_DIR first?" >&2
    exit 1
fi

# Derive the service user from baluhost-backend.service 'User=' so the rules are
# granted to whoever actually runs the backend — not a hardcoded name.
# Order: explicit BALUHOST_USER override > systemd 'User=' > error out.
#
# This used to fall back to "sven", the upstream maintainer's login (#581), and
# this file is the worst place for that guess: rendering it for the wrong name
# strips the real deploy user of every NOPASSWD right in one go, and the next
# deploy then dies restarting the services. Failing loudly is strictly better.
#
# 'User=' is the right source even though the grantee here is the deploy user:
# module 10 renders THIS file and baluhost-backend.service from the same
# $BALUHOST_USER (10-systemd-services.sh), so deriving from the unit reproduces
# exactly what the installer wrote. A box whose runner uses a different account
# has to say so via BALUHOST_USER — the installer never granted that account
# anything either.
SERVICE_USER="$(systemctl show -p User --value "$SERVICE" 2>/dev/null || true)"
BALUHOST_USER="${BALUHOST_USER:-${SERVICE_USER:-}}"
if [[ -z "$BALUHOST_USER" ]]; then
    echo "ERROR: could not determine the service user from '$SERVICE' (User=)" >&2
    echo "       and BALUHOST_USER is unset. Set BALUHOST_USER explicitly." >&2
    exit 1
fi
echo "  ..  rendering deploy sudoers for user: $BALUHOST_USER (install dir: $INSTALL_DIR)"

# Substitute the @@…@@ placeholders. Every token the template carries must be
# listed here — an unknown one would survive verbatim into the live sudoers
# file and its rule would never match (#126).
#
# Bash replacement rather than sed, mirroring lib/template.sh's
# process_template: in a sed replacement '&' means "the whole match", '|' is the
# delimiter and '\' escapes, so an install path containing any of them would
# render a mangled path that visudo still accepts — a silently broken rule,
# which is the exact failure mode this issue is about.
#
# patsub_replacement (bash >= 5.2, ON by default — Debian 13 ships 5.2) gives
# '&' that same meaning in ${var//pat/repl}. Measured, not assumed:
#   $ T='X@@D@@Y'; R='/opt/balu&host'; echo "${T//@@D@@/$R}"
#   X/opt/balu@@D@@hostY
# Turning it off is a no-op on older bash, and then no character is special.
shopt -u patsub_replacement 2>/dev/null || true

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
CONTENT="$(<"$TEMPLATE")"
CONTENT="${CONTENT//@@BALUHOST_USER@@/$BALUHOST_USER}"
CONTENT="${CONTENT//@@INSTALL_DIR@@/$INSTALL_DIR}"
printf '%s\n' "$CONTENT" >"$TMP"

# Validate before installing
if ! visudo -cf "$TMP" >/dev/null 2>&1; then
    echo "ERROR: generated sudoers file fails visudo syntax check." >&2
    visudo -cf "$TMP" || true
    exit 1
fi

# Timestamped backup of the existing live file, like install-hardware-sudoers.sh
# and install-power-sudoers.sh already do. This file is the one whose loss
# cannot be repaired by another script — every other permission sync needs the
# rules in it to run at all — so a way back matters most here.
if [[ -f "$TARGET" ]]; then
    BACKUP="${TARGET}.bak.$(date +%Y%m%d%H%M%S)"
    cp -p "$TARGET" "$BACKUP"
    echo "  OK  backed up existing file to: $BACKUP"
fi

install -m 440 -o root -g root "$TMP" "$TARGET"
echo "  OK  installed: $TARGET"
visudo -cf "$TARGET" >/dev/null && echo "  OK  visudo syntax check passed"
