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

# This module is optional from install.sh's point of view: a failure here is
# reported as a warning, not as a failed installation. It still exits non-zero
# so `--module 13-power-helpers` tells the operator the truth.
abort_module() {
    log_error "$1"
    exit 1
}

# Install helper
log_info "Installing $HELPER_DEST..."
[[ -f "$HELPER_SRC" ]] || abort_module "Helper script not found: $HELPER_SRC"
mkdir -p "$HELPER_DEST_DIR" || abort_module "Could not create $HELPER_DEST_DIR"
cp "$HELPER_SRC" "$HELPER_DEST" || abort_module "Could not copy $HELPER_SRC to $HELPER_DEST"
chmod 0755 "$HELPER_DEST" || abort_module "Could not chmod $HELPER_DEST"
chown root:root "$HELPER_DEST" || abort_module "Could not chown $HELPER_DEST"

# Install sudoers (template-substituted, validated, removed again if invalid)
log_info "Installing $SUDOERS_DEST..."
[[ -f "$SUDOERS_TEMPLATE" ]] || abort_module "Sudoers template not found: $SUDOERS_TEMPLATE"
install_sudoers_file "$SUDOERS_TEMPLATE" "$SUDOERS_DEST" "BALUHOST_USER=$BALUHOST_USER" \
    || abort_module "Power sudoers not installed: $SUDOERS_DEST"
chown root:root "$SUDOERS_DEST" || abort_module "Could not chown $SUDOERS_DEST"

log_info "Power helpers installed successfully."
