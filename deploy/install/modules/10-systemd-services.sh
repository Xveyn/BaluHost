#!/bin/bash
# BaluHost Install - Module 10: Systemd Services
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Variables ──────────────────────────────────────────────────────

VENV_BIN="${VENV_BIN:-$INSTALL_DIR/backend/.venv/bin}"
TEMPLATE_DIR="$SCRIPT_DIR/templates"
SYSTEMD_DIR="/etc/systemd/system"

SERVICES=(
    "baluhost-backend"
    "baluhost-scheduler"
    "baluhost-webdav"
    "baluhost-monitoring"
)

# ─── Main ───────────────────────────────────────────────────────────

log_step "Systemd Services"

require_root

# --- Generate service files from templates ---
for service in "${SERVICES[@]}"; do
    TEMPLATE="$TEMPLATE_DIR/${service}.service"
    OUTPUT="$SYSTEMD_DIR/${service}.service"

    if [[ ! -f "$TEMPLATE" ]]; then
        log_error "Template not found: $TEMPLATE"
        exit 1
    fi

    log_info "Generating $OUTPUT..."
    process_template "$TEMPLATE" "$OUTPUT" \
        "BALUHOST_USER=$BALUHOST_USER" \
        "INSTALL_DIR=$INSTALL_DIR" \
        "VENV_BIN=$VENV_BIN"

    chmod 644 "$OUTPUT"
    log_info "Created $OUTPUT"
done

# --- Install update sudoers rule ---
log_step "Update Sudoers"

SUDOERS_TEMPLATE="$TEMPLATE_DIR/baluhost-update-sudoers"
SUDOERS_OUTPUT="/etc/sudoers.d/baluhost-update"

if [[ -f "$SUDOERS_TEMPLATE" ]]; then
    process_template "$SUDOERS_TEMPLATE" "$SUDOERS_OUTPUT" \
        "BALUHOST_USER=$BALUHOST_USER" \
        "INSTALL_DIR=$INSTALL_DIR"
    chmod 440 "$SUDOERS_OUTPUT"
    log_info "Installed sudoers rule: $SUDOERS_OUTPUT"

    # Validate sudoers syntax
    if visudo -cf "$SUDOERS_OUTPUT" &>/dev/null; then
        log_info "Sudoers syntax OK."
    else
        log_error "Sudoers syntax check failed! Removing $SUDOERS_OUTPUT"
        rm -f "$SUDOERS_OUTPUT"
        exit 1
    fi
else
    log_warn "Update sudoers template not found: $SUDOERS_TEMPLATE (skipping)"
fi

# --- Install deploy sudoers rule ---
log_step "Deploy Sudoers"

DEPLOY_SUDOERS_TEMPLATE="$TEMPLATE_DIR/baluhost-deploy-sudoers"
DEPLOY_SUDOERS_OUTPUT="/etc/sudoers.d/baluhost-deploy"

if [[ -f "$DEPLOY_SUDOERS_TEMPLATE" ]]; then
    process_template "$DEPLOY_SUDOERS_TEMPLATE" "$DEPLOY_SUDOERS_OUTPUT" \
        "BALUHOST_USER=$BALUHOST_USER"
    chmod 440 "$DEPLOY_SUDOERS_OUTPUT"
    log_info "Installed deploy sudoers rule: $DEPLOY_SUDOERS_OUTPUT"

    if visudo -cf "$DEPLOY_SUDOERS_OUTPUT" &>/dev/null; then
        log_info "Deploy sudoers syntax OK."
    else
        log_error "Deploy sudoers syntax check failed! Removing $DEPLOY_SUDOERS_OUTPUT"
        rm -f "$DEPLOY_SUDOERS_OUTPUT"
        exit 1
    fi
else
    log_warn "Deploy sudoers template not found: $DEPLOY_SUDOERS_TEMPLATE (skipping)"
fi

# --- Install polkit rule for core-uptime sleep inhibitor ---
log_step "Polkit Rule (Core Uptime Inhibitor)"

POLKIT_TEMPLATE="$TEMPLATE_DIR/50-baluhost-inhibit-sleep.rules"
POLKIT_OUTPUT="/etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules"

if [[ -f "$POLKIT_TEMPLATE" ]]; then
    process_template "$POLKIT_TEMPLATE" "$POLKIT_OUTPUT" \
        "BALUHOST_USER=$BALUHOST_USER"
    chmod 644 "$POLKIT_OUTPUT"
    log_info "Installed polkit rule: $POLKIT_OUTPUT"

    # polkit reloads rules.d files on next request — no daemon-reload needed.
else
    log_warn "Polkit rule template not found: $POLKIT_TEMPLATE (skipping)"
    log_warn "Core uptime inhibitor will degrade to BaluHost-internal guards only."
fi

# --- Install udev rule for AMD GPU power sysfs ---
log_step "Udev Rule (AMD GPU Power)"

UDEV_TEMPLATE="$TEMPLATE_DIR/70-baluhost-amd-gpu.rules"
UDEV_OUTPUT="/etc/udev/rules.d/70-baluhost-amd-gpu.rules"

if [[ -f "$UDEV_TEMPLATE" ]]; then
    process_template "$UDEV_TEMPLATE" "$UDEV_OUTPUT" \
        "BALUHOST_USER=$BALUHOST_USER"
    chmod 644 "$UDEV_OUTPUT"
    log_info "Installed udev rule: $UDEV_OUTPUT"

    # Ensure the service user is in the video group so the rule's
    # chgrp + g+w bit actually grants access.
    if id -nG "$BALUHOST_USER" | tr ' ' '\n' | grep -qx video; then
        log_info "$BALUHOST_USER already in 'video' group."
    else
        usermod -aG video "$BALUHOST_USER"
        log_info "Added $BALUHOST_USER to 'video' group."
    fi

    udevadm control --reload-rules || log_warn "udevadm reload-rules failed (non-fatal)"
    udevadm trigger --subsystem-match=drm || log_warn "udevadm trigger drm failed (non-fatal)"
    log_info "Udev rules reloaded and drm subsystem re-triggered."
else
    log_warn "Udev rule template not found: $UDEV_TEMPLATE (skipping)"
    log_warn "GPU Power Management will report 'WRITE PERMISSION: missing' until applied manually."
fi

# --- Reload systemd ---
log_step "Reloading Systemd"

systemctl daemon-reload
log_info "systemd daemon reloaded."

# --- Enable services ---
log_step "Enabling Services"

for service in "${SERVICES[@]}"; do
    if systemctl is-enabled "$service" &>/dev/null; then
        log_info "$service is already enabled."
    else
        systemctl enable "$service"
        log_info "$service enabled."
    fi
done

# --- Verify ---
log_step "Service Verification"

ALL_OK=true
for service in "${SERVICES[@]}"; do
    if [[ -f "$SYSTEMD_DIR/${service}.service" ]]; then
        ENABLED_STATE=$(systemctl is-enabled "$service" 2>/dev/null || echo "unknown")
        log_info "$service: installed, enabled=$ENABLED_STATE"
    else
        log_error "$service: service file missing!"
        ALL_OK=false
    fi
done

if [[ "$ALL_OK" != "true" ]]; then
    log_error "One or more service files are missing."
    exit 1
fi

# --- Summary ---
log_step "Systemd Summary"
log_info "VENV_BIN:   $VENV_BIN"
log_info "Services:   ${SERVICES[*]}"
log_info "Status:     all installed and enabled (not yet started)"
log_info "Systemd service setup complete."

exit 0
