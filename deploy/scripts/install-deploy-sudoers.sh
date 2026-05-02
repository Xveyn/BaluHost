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

BALUHOST_USER="${BALUHOST_USER:-sven}"
TEMPLATE="${TEMPLATE:-/opt/baluhost/deploy/install/templates/baluhost-deploy-sudoers}"
TARGET="/etc/sudoers.d/baluhost-deploy"

if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: must run as root (use sudo)." >&2
    exit 1
fi

if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    echo "Did you `git pull` /opt/baluhost first?" >&2
    exit 1
fi

# Substitute @@BALUHOST_USER@@ placeholder
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
sed "s|@@BALUHOST_USER@@|$BALUHOST_USER|g" "$TEMPLATE" >"$TMP"

# Validate before installing
if ! visudo -cf "$TMP" >/dev/null 2>&1; then
    echo "ERROR: generated sudoers file fails visudo syntax check." >&2
    visudo -cf "$TMP" || true
    exit 1
fi

install -m 440 -o root -g root "$TMP" "$TARGET"
echo "  OK  installed: $TARGET"
visudo -cf "$TARGET" >/dev/null && echo "  OK  visudo syntax check passed"
