#!/bin/bash
# Offline (no-root) tests for the optional-feature dispatcher in lib/features.sh.
# Mocks the apt + external-script primitives so nothing is actually installed.
# Run: bash deploy/install/verify/test-features.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"  # deploy/install
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/features.sh"
set +e  # common.sh/features.sh enable -e; disable so assertions can run fully

MOCK_LOG="$(mktemp)"
trap 'rm -f "$MOCK_LOG"' EXIT

# Override primitives: record calls to the log instead of executing them.
_apt_install() { echo "apt:$*" >>"$MOCK_LOG"; }
_run_script()  { echo "script:$1 SERVICE_USER=${SERVICE_USER:-} STORAGE_GROUP=${STORAGE_GROUP:-} ARG1=${2:-}" >>"$MOCK_LOG"; }

BALUHOST_USER="testuser"
BALUHOST_GROUP="testgroup"

PASS=0; FAILED=0
ok()   { PASS=$((PASS+1)); echo "  ok  - $1"; }
bad()  { FAILED=$((FAILED+1)); echo "  BAD - $1"; }
reset(){ : >"$MOCK_LOG"; _HW_SUDOERS_DONE=false; }
logcount() { grep -c -- "$1" "$MOCK_LOG" 2>/dev/null || true; }  # grep -c prints 0 on no match; || true swallows its exit 1

echo "== feature_enabled =="
ENABLE_RAID=false
feature_enabled RAID && bad "RAID enabled when false" || ok "RAID disabled by default"
ENABLE_RAID=true
feature_enabled RAID && ok "RAID enabled when true" || bad "RAID not enabled when true"
ENABLE_RAID=false

echo "== run_feature CLOUD (package only) =="
reset
run_feature CLOUD
[[ "$(logcount '^apt:rclone$')" == "1" ]] && ok "CLOUD installs rclone" || bad "CLOUD did not install rclone"
[[ "$(logcount '^script:')" == "0" ]] && ok "CLOUD runs no script" || bad "CLOUD ran a script"

echo "== run_feature SAMBA (env propagation, self-installs) =="
reset
run_feature SAMBA
[[ "$(logcount 'setup-samba.sh SERVICE_USER=testuser STORAGE_GROUP=testgroup')" == "1" ]] \
  && ok "SAMBA passes configured user/group" || bad "SAMBA env not propagated"
[[ "$(logcount '^apt:')" == "0" ]] && ok "SAMBA installs no module packages" || bad "SAMBA apt-installed packages"

echo "== run_feature NFS (env propagation, self-installs) =="
reset
run_feature NFS
[[ "$(logcount 'setup-nfs.sh SERVICE_USER=testuser STORAGE_GROUP=testgroup')" == "1" ]] \
  && ok "NFS passes configured user/group" || bad "NFS env not propagated"
[[ "$(logcount '^apt:')" == "0" ]] && ok "NFS installs no module packages" || bad "NFS apt-installed packages"

echo "== run_feature WSDD (self-installs, no user/pkg) =="
reset
run_feature WSDD
[[ "$(logcount 'setup-wsdd.sh')" == "1" ]] && ok "WSDD runs its setup script" || bad "WSDD script not run"
[[ "$(logcount '^apt:')" == "0" ]] && ok "WSDD installs no module packages" || bad "WSDD apt-installed packages"

echo "== run_feature MDNS (self-installs avahi) =="
reset
run_feature MDNS
[[ "$(logcount 'install-avahi.sh')" == "1" ]] && ok "MDNS runs install-avahi.sh" || bad "MDNS script not run"
[[ "$(logcount '^apt:')" == "0" ]] && ok "MDNS installs no module packages" || bad "MDNS apt-installed packages"

echo "== run_feature VPN (package + user arg) =="
reset
run_feature VPN
[[ "$(logcount '^apt:wireguard-tools$')" == "1" ]] && ok "VPN installs wireguard-tools" || bad "VPN missing package"
[[ "$(logcount 'setup-wireguard.sh .* ARG1=testuser')" == "1" ]] && ok "VPN passes user arg" || bad "VPN user arg wrong"

echo "== RAID+SMART share hardware sudoers, installed once =="
reset
run_feature RAID
run_feature SMART
[[ "$(logcount 'install-hardware-sudoers.sh')" == "1" ]] \
  && ok "hardware sudoers installed exactly once" || bad "hardware sudoers not single-run"
[[ "$(logcount '^apt:mdadm$')" == "1" ]] && ok "RAID installs mdadm" || bad "RAID missing mdadm"
[[ "$(logcount '^apt:smartmontools$')" == "1" ]] && ok "SMART installs smartmontools" || bad "SMART missing smartmontools"

echo "== run_feature returns non-zero when setup fails =="
reset
_run_script() { return 1; }  # simulate a failing setup script
run_feature SAMBA
[[ $? -ne 0 ]] && ok "run_feature propagates failure" || bad "run_feature swallowed failure"
_run_script() { echo "script:$1 SERVICE_USER=${SERVICE_USER:-} STORAGE_GROUP=${STORAGE_GROUP:-} ARG1=${2:-}" >>"$MOCK_LOG"; }

echo ""
echo "PASS=$PASS FAILED=$FAILED"
[[ $FAILED -eq 0 ]]
