#!/bin/bash
# BaluHost Install - Module 14: Optional Features
# Installs and configures features opted in via ENABLE_<KEY> flags.
# No flags set => nothing installed (core NAS only).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/features.sh"

log_step "Optional Features"

require_root

# Collect opted-in features.
selected=()
for key in "${FEATURE_KEYS[@]}"; do
    if feature_enabled "$key"; then
        selected+=("$key")
    fi
done

if [[ ${#selected[@]} -eq 0 ]]; then
    log_info "No optional features enabled. Skipping."
    exit 0
fi

log_info "Enabled features: ${selected[*]}"

# Refresh package index once before installing feature packages.
# Guard it: under `set -e` a bare failing apt-get update would abort the module
# before the per-feature loop can record failures and print the summary.
log_info "Updating package index..."
if ! apt-get update -qq; then
    log_warn "apt-get update failed; continuing with the existing (possibly stale) index."
fi

declare -a OK_FEATURES=()
declare -a FAILED_FEATURES=()
for key in "${selected[@]}"; do
    log_step "Feature: $(feature_label "$key")"
    if run_feature "$key"; then
        log_info "$key configured."
        OK_FEATURES+=("$key")
    else
        log_error "Feature setup failed: $key"
        FAILED_FEATURES+=("$key")
    fi
done

log_step "Optional Features Summary"
if [[ ${#OK_FEATURES[@]} -gt 0 ]]; then
    log_info "Installed: ${OK_FEATURES[*]}"
fi
if [[ ${#FAILED_FEATURES[@]} -gt 0 ]]; then
    log_error "Failed: ${FAILED_FEATURES[*]}"
    log_error "The core NAS is unaffected. Re-run after fixing: sudo ./install.sh --module 14-optional-features"
    exit 1
fi

log_info "Optional features module complete."
exit 0
