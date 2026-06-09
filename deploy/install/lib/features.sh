#!/bin/bash
# BaluHost Install System - Optional Feature Catalog & Dispatcher
# Sourced by modules/14-optional-features.sh, install.sh (for prompts), and
# verify/test-features.sh. Depends on lib/common.sh logging helpers.
#
# Each feature is gated by an ENABLE_<KEY> variable (default false, set in
# lib/config.sh). The dispatcher installs the feature's packages and runs its
# setup action by invoking the existing standalone scripts — no logic is
# duplicated here.

set -euo pipefail

# Deploy root: lib/ -> install/ -> deploy/
FEATURES_DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Ordered feature keys — drives iteration, prompts, and the docs matrix.
FEATURE_KEYS=(RAID SMART VPN CLOUD SAMBA NFS WSDD MDNS)

# Human-readable label for prompts and the summary report.
feature_label() {
    case "$1" in
        RAID)  echo "RAID array management (mdadm)";;
        SMART) echo "Disk health monitoring (smartmontools)";;
        VPN)   echo "WireGuard VPN (wireguard-tools)";;
        CLOUD) echo "Cloud import (rclone)";;
        SAMBA) echo "Samba / SMB file sharing";;
        NFS)   echo "NFS file sharing";;
        WSDD)  echo "Windows network discovery (WS-Discovery)";;
        MDNS)  echo "mDNS / Bonjour hostname (avahi)";;
        *)     echo "$1";;
    esac
}

# True when ENABLE_<KEY> == "true".
feature_enabled() {
    local var="ENABLE_$1"
    [[ "${!var:-false}" == "true" ]]
}

# apt packages installed directly by the module (empty for self-installing scripts).
feature_packages() {
    case "$1" in
        RAID)  echo "mdadm";;
        SMART) echo "smartmontools";;
        VPN)   echo "wireguard-tools";;
        CLOUD) echo "rclone";;
        *)     echo "";;
    esac
}

# Optional pre-flight warning (never fails the feature).
feature_precheck() {
    case "$1" in
        RAID)
            if [[ ! -f /proc/mdstat ]] || ! grep -q '^md' /proc/mdstat 2>/dev/null; then
                log_warn "RAID: no active arrays in /proc/mdstat — installing mdadm anyway."
            fi
            ;;
        VPN)
            if ! modinfo wireguard &>/dev/null && [[ ! -d /sys/module/wireguard ]]; then
                log_warn "VPN: WireGuard kernel module not detected — wg-quick may fail until a reboot."
            fi
            ;;
    esac
    return 0
}

# ─── Overridable primitives (test seam) ──────────────────────────────
# Install apt packages. Overridden in test-features.sh to record calls.
_apt_install() {
    [[ $# -eq 0 ]] && return 0
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
}

# Run an external setup script as a subprocess. Overridden in tests.
# stdin is redirected from /dev/null so any stray interactive prompt in a
# called script (e.g. install-avahi.sh asks "reconfigure? (y/N)" when avahi is
# already installed) cannot hang a non-interactive installer run — it reads EOF
# and takes its safe default (skip reconfiguration).
_run_script() {
    local script="$1"; shift
    if [[ ! -f "$script" ]]; then
        log_error "Setup script not found: $script"
        return 1
    fi
    bash "$script" "$@" </dev/null
}

# ─── Shared hardware sudoers (RAID + SMART) ──────────────────────────
# Installed at most once per run, regardless of how many of RAID/SMART are on.
_HW_SUDOERS_DONE=false
install_hardware_sudoers_once() {
    [[ "$_HW_SUDOERS_DONE" == "true" ]] && return 0
    BALUHOST_USER="$BALUHOST_USER" \
    TEMPLATE="$FEATURES_DEPLOY_DIR/install/templates/baluhost-hardware-sudoers" \
        _run_script "$FEATURES_DEPLOY_DIR/scripts/install-hardware-sudoers.sh"
    _HW_SUDOERS_DONE=true
}

# Feature-specific setup action (run after packages are installed).
feature_setup() {
    case "$1" in
        RAID|SMART)
            install_hardware_sudoers_once
            ;;
        VPN)
            _run_script "$FEATURES_DEPLOY_DIR/scripts/setup-wireguard.sh" "$BALUHOST_USER"
            ;;
        CLOUD)
            : # package only, runs as the service user
            ;;
        SAMBA)
            ( export SERVICE_USER="$BALUHOST_USER" STORAGE_GROUP="$BALUHOST_GROUP"
              _run_script "$FEATURES_DEPLOY_DIR/samba/setup-samba.sh" )
            ;;
        NFS)
            ( export SERVICE_USER="$BALUHOST_USER" STORAGE_GROUP="$BALUHOST_GROUP"
              _run_script "$FEATURES_DEPLOY_DIR/nfs/setup-nfs.sh" )
            ;;
        WSDD)
            _run_script "$FEATURES_DEPLOY_DIR/wsdd/setup-wsdd.sh"
            ;;
        MDNS)
            _run_script "$FEATURES_DEPLOY_DIR/scripts/install-avahi.sh"
            ;;
        *)
            log_error "Unknown feature: $1"
            return 1
            ;;
    esac
}

# Install + configure one feature. Returns non-zero if any step fails.
run_feature() {
    local key="$1"
    feature_precheck "$key" || true
    local pkgs
    pkgs="$(feature_packages "$key")"
    if [[ -n "$pkgs" ]]; then
        log_info "Installing packages: $pkgs"
        # shellcheck disable=SC2086
        _apt_install $pkgs
    fi
    feature_setup "$key"
}
