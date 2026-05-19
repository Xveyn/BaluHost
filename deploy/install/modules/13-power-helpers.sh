#!/bin/bash
# BaluHost Install - Module 13: Power Helpers
# Installs the logind idle helper + sudoers entry for the BaluHost service user.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

HELPER_SRC="$SCRIPT_DIR/scripts/baluhost-write-logind-idle.sh"
HELPER_DEST_DIR="/usr/local/lib/baluhost"
HELPER_DEST="$HELPER_DEST_DIR/baluhost-write-logind-idle"
SUDOERS_TEMPLATE="$SCRIPT_DIR/templates/sudoers-baluhost-power"
SUDOERS_DEST="/etc/sudoers.d/baluhost-power"

log_step "Power Helpers"

require_root

# Install helper
log_info "Installing $HELPER_DEST..."
mkdir -p "$HELPER_DEST_DIR"
cp "$HELPER_SRC" "$HELPER_DEST"
chmod 0755 "$HELPER_DEST"
chown root:root "$HELPER_DEST"

# Install sudoers (template-substituted)
log_info "Installing $SUDOERS_DEST..."
process_template "$SUDOERS_TEMPLATE" "$SUDOERS_DEST" \
    "BALUHOST_USER=$BALUHOST_USER"
chmod 0440 "$SUDOERS_DEST"
chown root:root "$SUDOERS_DEST"

# Validate
if ! visudo -cf "$SUDOERS_DEST" >/dev/null; then
    log_error "Generated sudoers file failed validation: $SUDOERS_DEST"
    rm -f "$SUDOERS_DEST"
    exit 1
fi

log_info "Power helpers installed successfully."
