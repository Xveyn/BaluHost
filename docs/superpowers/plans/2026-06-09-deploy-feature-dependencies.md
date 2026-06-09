# Optional Feature Modules & Dependency Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional-feature installer module (interactive + config-flag driven) that fully sets up RAID/SMART/VPN/Cloud/Samba/NFS/WSDD/mDNS by invoking the existing setup scripts, plus a central bilingual dependency-matrix document and a clearly-stated Debian-only restriction.

**Architecture:** A declarative feature catalog (`deploy/install/lib/features.sh`) drives a new installer module (`modules/14-optional-features.sh`). The catalog maps each feature to its packages and a setup action that calls the existing standalone scripts with the configured service user. Config flags `ENABLE_<KEY>` (default `false`, so existing automated installs are unaffected) select features; an interactive block in `gather_input()` sets them. The same catalog backs the documentation matrix.

**Tech Stack:** Bash (Debian 12/13, bash 5.x), the existing modular installer in `deploy/install/`, GNU coreutils, apt.

---

## Background / verified facts (read before starting)

- Installer entrypoint: `deploy/install/install.sh` runs modules `01-preflight` … `13-power-helpers` from the `MODULES` array. It sources `lib/common.sh` and `lib/config.sh`.
- `lib/common.sh` provides: `log_info/log_warn/log_error/log_step`, `require_root`, `confirm` (returns 0 in `NON_INTERACTIVE`), `process_template`, `detect_debian_version`. `confirm "Prompt?"` reads y/N.
- `lib/config.sh` sets defaults via `: "${VAR:=default}"` at source time, and `save_config()` writes a fixed `KEY=VALUE` list to `/etc/baluhost/install.conf` (mode 600). `load_config()` sources that file with `set -a` (so values become exported). `BALUHOST_USER` / `BALUHOST_GROUP` are derived from the install-dir owner.
- Existing setup scripts (all invoked as `bash <path>`, NOT sourced — they use `$0`/`BASH_SOURCE` for relative paths and set their own `set -e`):
  - `deploy/scripts/setup-wireguard.sh` — takes the service user as `$1`; installs its own sudoers; **assumes `wg`/`wg-quick` already installed** (so we must apt-install `wireguard-tools` first).
  - `deploy/scripts/install-hardware-sudoers.sh` — installs `/etc/sudoers.d/baluhost-hardware` (covers RAID/mdadm **and** SMART). Reads `BALUHOST_USER` and `TEMPLATE` from env. visudo-validated, idempotent.
  - `deploy/samba/setup-samba.sh` — installs `samba samba-common-bin`; reads `SERVICE_USER` / `STORAGE_GROUP` from env (defaults `sven`/`baluhost`).
  - `deploy/nfs/setup-nfs.sh` — installs `nfs-kernel-server`; reads `SERVICE_USER` / `STORAGE_GROUP` from env.
  - `deploy/wsdd/setup-wsdd.sh` — installs `wsdd2`/`wsdd`; no user param needed.
  - `deploy/scripts/install-avahi.sh` — installs `avahi-daemon avahi-utils` itself. **On first install it is non-interactive**, but on a re-run (avahi already present) its `main()` prompts `read -p "reconfigure? (y/N)"`. The dispatcher's `_run_script` redirects stdin from `/dev/null`, so a re-run reads EOF and safely skips reconfiguration instead of hanging.
- Template `deploy/install/templates/baluhost-hardware-sudoers` exists.
- A module's `SCRIPT_DIR` is `deploy/install` (computed as `dirname/..`). The deploy root is therefore `$SCRIPT_DIR/..`.

**Feature catalog (authoritative):**

| Key | Packages (apt-installed by module) | Setup action | Precheck (warn only) |
|---|---|---|---|
| RAID | `mdadm` | `install-hardware-sudoers.sh` (once for RAID∪SMART) | arrays in `/proc/mdstat` |
| SMART | `smartmontools` | `install-hardware-sudoers.sh` (once for RAID∪SMART) | — |
| VPN | `wireguard-tools` | `setup-wireguard.sh "$BALUHOST_USER"` | `wireguard` kernel module |
| CLOUD | `rclone` | — (none) | — |
| SAMBA | (none — script self-installs) | `SERVICE_USER/STORAGE_GROUP env → samba/setup-samba.sh` | — |
| NFS | (none — script self-installs) | `SERVICE_USER/STORAGE_GROUP env → nfs/setup-nfs.sh` | — |
| WSDD | (none — script self-installs) | `wsdd/setup-wsdd.sh` | — |
| MDNS | (none — script self-installs) | `scripts/install-avahi.sh` | — |

---

## File structure

**New:**
- `deploy/install/lib/features.sh` — feature catalog + dispatcher (`FEATURE_KEYS`, `feature_label`, `feature_enabled`, `feature_packages`, `feature_precheck`, `feature_setup`, `run_feature`, overridable `_apt_install`/`_run_script`, `install_hardware_sudoers_once` guard).
- `deploy/install/modules/14-optional-features.sh` — iterates `FEATURE_KEYS`, runs enabled features, end-of-module summary, non-zero on any failure.
- `deploy/install/verify/test-features.sh` — offline no-root harness asserting dispatch logic via mocked primitives.
- `docs/deployment/FEATURE_DEPENDENCIES.de.md` + `.en.md` — dependency matrix, activation guide, Debian-only explanation.

**Modified:**
- `deploy/install/lib/config.sh` — `ENABLE_*` defaults + save lines.
- `deploy/install/install.sh` — source `features.sh`; add module to `MODULES`; add "Optional Features" block in `gather_input()`.
- `README.md`, `docs/deployment/DEPLOYMENT.de.md`, `docs/deployment/DEPLOYMENT.en.md` — "Supported OS" note + link.

---

## Task 1: Config flags for optional features

**Files:**
- Modify: `deploy/install/lib/config.sh`

- [ ] **Step 1: Add `ENABLE_*` defaults**

In `deploy/install/lib/config.sh`, after the existing default block (after the `: "${GIT_BRANCH:=main}"` line, line ~31), add:

```bash

# ─── Optional Feature Flags ──────────────────────────────────────────
# Each gates a feature in module 14-optional-features. Default false so an
# install without explicit opt-in behaves exactly as before (core NAS only).
: "${ENABLE_RAID:=false}"
: "${ENABLE_SMART:=false}"
: "${ENABLE_VPN:=false}"
: "${ENABLE_CLOUD:=false}"
: "${ENABLE_SAMBA:=false}"
: "${ENABLE_NFS:=false}"
: "${ENABLE_WSDD:=false}"
: "${ENABLE_MDNS:=false}"
```

- [ ] **Step 2: Persist the flags in `save_config()`**

In the same file, inside the `save_config()` heredoc, after the `GIT_BRANCH=${GIT_BRANCH}` line, add:

```bash
ENABLE_RAID=${ENABLE_RAID}
ENABLE_SMART=${ENABLE_SMART}
ENABLE_VPN=${ENABLE_VPN}
ENABLE_CLOUD=${ENABLE_CLOUD}
ENABLE_SAMBA=${ENABLE_SAMBA}
ENABLE_NFS=${ENABLE_NFS}
ENABLE_WSDD=${ENABLE_WSDD}
ENABLE_MDNS=${ENABLE_MDNS}
```

- [ ] **Step 3: Syntax check**

Run: `bash -n deploy/install/lib/config.sh`
Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
git add deploy/install/lib/config.sh
git commit -m "feat(deploy): add ENABLE_* optional-feature flags to installer config (#182)"
```

---

## Task 2: Feature catalog + dispatcher (test-first)

**Files:**
- Create: `deploy/install/verify/test-features.sh`
- Create: `deploy/install/lib/features.sh`

- [ ] **Step 1: Write the offline test harness first**

Create `deploy/install/verify/test-features.sh`:

```bash
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
```

- [ ] **Step 2: Run the test to verify it fails (features.sh missing)**

Run: `bash deploy/install/verify/test-features.sh`
Expected: FAIL — error sourcing `lib/features.sh` (No such file), non-zero exit.

- [ ] **Step 3: Implement `deploy/install/lib/features.sh`**

Create `deploy/install/lib/features.sh`:

```bash
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash deploy/install/verify/test-features.sh`
Expected: every assertion prints `ok`, the final line shows `FAILED=0` (the `PASS=` number is informational, not asserted), exit 0.

- [ ] **Step 5: Syntax check both files**

Run: `bash -n deploy/install/lib/features.sh && bash -n deploy/install/verify/test-features.sh`
Expected: no output, exit 0.

- [ ] **Step 6: Commit**

```bash
git add deploy/install/lib/features.sh deploy/install/verify/test-features.sh
git commit -m "feat(deploy): optional-feature catalog + dispatcher with offline test (#182)"
```

---

## Task 3: Installer module 14-optional-features

**Files:**
- Create: `deploy/install/modules/14-optional-features.sh`

- [ ] **Step 1: Implement the module**

Create `deploy/install/modules/14-optional-features.sh`:

```bash
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
```

- [ ] **Step 2: Syntax check**

Run: `bash -n deploy/install/modules/14-optional-features.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Verify the "no features" fast-path runs without root or apt**

Run: `NON_INTERACTIVE=true bash deploy/install/modules/14-optional-features.sh; echo "exit=$?"`
Expected: prints `No optional features enabled. Skipping.` and `exit=0`. (Note: `require_root` exits 1 if not root — if running as non-root locally, instead verify the skip logic via the offline harness; on the target box this path is reached as root. If the local run aborts at `require_root`, that is acceptable and expected off-box.)

- [ ] **Step 4: Commit**

```bash
git add deploy/install/modules/14-optional-features.sh
git commit -m "feat(deploy): module 14-optional-features runs opted-in feature setups (#182)"
```

---

## Task 4: Wire the module into the installer + interactive prompts

**Files:**
- Modify: `deploy/install/install.sh`

- [ ] **Step 1: Source `features.sh` in `install.sh`**

In `deploy/install/install.sh`, after the existing line `source "$SCRIPT_DIR/lib/config.sh"` (~line 12), add:

```bash
source "$SCRIPT_DIR/lib/features.sh"
```

- [ ] **Step 2: Register the module**

The `MODULES` array is declared `readonly -a MODULES=( … )` (around line 18). Insert `"14-optional-features"` as a new line **inside** that literal, immediately after the `"13-power-helpers"` line and before the closing `)`. Do NOT append with `MODULES+=(…)` — the array is read-only and that would fail at runtime.

```bash
    "13-power-helpers"
    "14-optional-features"
)
```

- [ ] **Step 3: Add the interactive feature-selection block**

In `gather_input()`, immediately before the final `log_step "Configuration Summary"` block, add:

```bash
    echo ""
    log_step "Optional Features"
    echo "Enable extra features now? Each pulls in additional system packages."
    echo "Answer N to any you don't need — you can enable them later by setting"
    echo "ENABLE_<NAME>=true in the config and re-running module 14-optional-features."
    echo ""
    for fkey in "${FEATURE_KEYS[@]}"; do
        if confirm "Enable $(feature_label "$fkey")?"; then
            export "ENABLE_$fkey=true"
        else
            export "ENABLE_$fkey=false"
        fi
    done
```

- [ ] **Step 4: Add the selected features to the configuration summary (optional clarity)**

In `gather_input()`, inside the `log_step "Configuration Summary"` echo block, after the `Admin email` line, add:

```bash
    local _enabled_summary=""
    for fkey in "${FEATURE_KEYS[@]}"; do
        local _v="ENABLE_$fkey"
        [[ "${!_v:-false}" == "true" ]] && _enabled_summary+="$fkey "
    done
    echo "  Optional features:  ${_enabled_summary:-none}"
```

- [ ] **Step 5: Syntax check + module listing**

Run: `bash -n deploy/install/install.sh && bash deploy/install/install.sh --list-modules`
Expected: syntax OK; the module list includes `14-optional-features` as the last entry.

- [ ] **Step 6: Commit**

```bash
git add deploy/install/install.sh
git commit -m "feat(deploy): wire 14-optional-features into installer chain + prompts (#182)"
```

---

## Task 5: Central dependency documentation (bilingual)

**Files:**
- Create: `docs/deployment/FEATURE_DEPENDENCIES.en.md`
- Create: `docs/deployment/FEATURE_DEPENDENCIES.de.md`

- [ ] **Step 1: Write the English doc**

Create `docs/deployment/FEATURE_DEPENDENCIES.en.md`:

```markdown
# Feature Dependencies

Single source of truth for which system packages each BaluHost feature needs,
how to enable it, and which setup script configures it.

## Supported OS

BaluHost's production installer supports **Debian 12 (bookworm) and Debian 13
(trixie) only**. The preflight check (`deploy/install/modules/01-preflight.sh`)
aborts on any other OS. This is deliberate: package names, systemd unit
assumptions, and the deploy scripts are tested only on Debian. Ubuntu, Fedora,
Arch, and RHEL are not supported. (The mDNS script `install-avahi.sh` happens to
handle several distros, but the rest of the install chain does not — there is no
half-supported path.)

## What a default install gives you

Running `sudo ./install.sh` without enabling any optional feature installs the
**core NAS**: PostgreSQL, Nginx, the FastAPI backend, the built frontend, and
the base toolchain (Python, Node, git, build-essential, curl). Files, users,
monitoring, and the web UI work immediately.

Everything in the table below is **off by default** and stays dark until enabled.

## Dependency matrix

| Feature | Packages | Setup script | Default install |
|---|---|---|---|
| RAID array management | `mdadm` | `deploy/scripts/install-hardware-sudoers.sh` | off |
| Disk health (SMART) | `smartmontools` | `deploy/scripts/install-hardware-sudoers.sh` | off |
| WireGuard VPN | `wireguard-tools` | `deploy/scripts/setup-wireguard.sh` | off |
| Cloud import | `rclone` | (none — runs as the service user) | off |
| Samba / SMB sharing | `samba`, `samba-common-bin` | `deploy/samba/setup-samba.sh` | off |
| NFS sharing | `nfs-kernel-server` | `deploy/nfs/setup-nfs.sh` | off |
| Windows discovery (WS-Discovery) | `wsdd2` / `wsdd` | `deploy/wsdd/setup-wsdd.sh` | off |
| mDNS / Bonjour (`baluhost.local`) | `avahi-daemon`, `avahi-utils` | `deploy/scripts/install-avahi.sh` | off |

RAID and SMART share one sudoers file (`/etc/sudoers.d/baluhost-hardware`); the
installer renders it once when either is enabled.

## How to enable features

### During installation (interactive)

The installer asks, per feature, whether to enable it. Answer `y` to pull in the
packages and run that feature's setup.

### Non-interactive / after installation

Set the flag(s) in `/etc/baluhost/install.conf` and re-run the optional-features
module:

```bash
# /etc/baluhost/install.conf
ENABLE_RAID=true
ENABLE_VPN=true
```

```bash
sudo /opt/baluhost/deploy/install/install.sh --module 14-optional-features
```

Available flags: `ENABLE_RAID`, `ENABLE_SMART`, `ENABLE_VPN`, `ENABLE_CLOUD`,
`ENABLE_SAMBA`, `ENABLE_NFS`, `ENABLE_WSDD`, `ENABLE_MDNS`. Unset = `false`.

### Manual alternative

Each setup script can be run directly (as root), e.g.:

```bash
sudo SERVICE_USER=<baluhost-user> STORAGE_GROUP=<baluhost-group> \
    bash /opt/baluhost/deploy/samba/setup-samba.sh
```

## Per-feature notes

- **RAID / SMART** — backend uses `mdadm` and `smartctl`; without them RAID and
  disk-health pages show no data. The shared hardware sudoers grants the service
  user the specific commands it needs.
- **VPN** — `wireguard-tools` provides `wg`/`wg-quick`; `setup-wireguard.sh`
  installs the per-command sudoers and enables IP forwarding. A reboot may be
  required for the WireGuard kernel module.
- **Cloud import** — `rclone` only; no sudoers, runs as the service user.
- **Samba / NFS** — each setup script installs its package, writes a hardened
  config, creates the share/export config owned by the service user, and installs
  scoped sudoers.
- **WS-Discovery / mDNS** — make BaluHost discoverable from Windows Explorer and
  from Bonjour/zeroconf clients respectively.

## Verifying an enabled feature

After enabling, confirm the package and (where applicable) the service:

```bash
dpkg -s mdadm | grep Status        # package installed
systemctl status smbd              # Samba running (SAMBA)
sudo -n -u <baluhost-user> wg show  # VPN sudoers in place (VPN)
```
```

- [ ] **Step 2: Write the German doc**

Create `docs/deployment/FEATURE_DEPENDENCIES.de.md` with the same content translated to German (same structure, same matrix table, same flag names and commands). Keep the table columns: `Feature | Pakete | Setup-Skript | Standard-Installation`. Translate prose; do **not** translate flag names (`ENABLE_RAID`, …), paths, or commands.

- [ ] **Step 3: Verify both render (no broken table syntax)**

Run: `bash -n /dev/null; echo "manual check"` then open both files and confirm the matrix tables have matching column counts and no `TBD`/placeholder text.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment/FEATURE_DEPENDENCIES.en.md docs/deployment/FEATURE_DEPENDENCIES.de.md
git commit -m "docs(deploy): central feature dependency matrix + Debian-only note (#182)"
```

---

## Task 6: Cross-link from README and DEPLOYMENT docs

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment/DEPLOYMENT.de.md`
- Modify: `docs/deployment/DEPLOYMENT.en.md`

- [ ] **Step 1: Inspect the current deployment sections**

Read each file's existing "deployment"/"installation"/"requirements" section so the new note matches the surrounding style and heading level. Find the installation/OS section in each:

Run: `bash -n /dev/null` (no-op) — then read `README.md`, `docs/deployment/DEPLOYMENT.en.md`, `docs/deployment/DEPLOYMENT.de.md` and locate where OS/requirements are mentioned.

- [ ] **Step 2: Add the note to `README.md`**

In the installation/deployment section of `README.md`, add a short note (match the existing heading depth):

```markdown
> **Supported OS:** The production installer targets **Debian 12/13 only**.
> Optional features (RAID, SMART, VPN, Samba, NFS, Cloud, mDNS) are off by
> default — see [Feature Dependencies](docs/deployment/FEATURE_DEPENDENCIES.en.md)
> for the package matrix and how to enable them.
```

- [ ] **Step 3: Add the note to `docs/deployment/DEPLOYMENT.en.md`**

Add near the top requirements/installation section:

```markdown
> **Supported OS:** Debian 12 (bookworm) / 13 (trixie) only.
> See [Feature Dependencies](./FEATURE_DEPENDENCIES.en.md) for the per-feature
> package matrix and activation (interactive prompt or `ENABLE_*` config flags).
```

- [ ] **Step 4: Add the note to `docs/deployment/DEPLOYMENT.de.md`**

Add the German equivalent near the top requirements/installation section:

```markdown
> **Unterstütztes OS:** Nur Debian 12 (bookworm) / 13 (trixie).
> Siehe [Feature-Abhängigkeiten](./FEATURE_DEPENDENCIES.de.md) für die Paket-
> Matrix pro Feature und die Aktivierung (interaktive Abfrage oder `ENABLE_*`-
> Config-Flags).
```

- [ ] **Step 5: Verify links resolve**

Confirm the three relative links point to existing files:
- `docs/deployment/FEATURE_DEPENDENCIES.en.md` (from README)
- `./FEATURE_DEPENDENCIES.en.md` and `./FEATURE_DEPENDENCIES.de.md` (from the DEPLOYMENT docs)

Run: `ls docs/deployment/FEATURE_DEPENDENCIES.en.md docs/deployment/FEATURE_DEPENDENCIES.de.md`
Expected: both paths listed, no error.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/deployment/DEPLOYMENT.en.md docs/deployment/DEPLOYMENT.de.md
git commit -m "docs: link feature-dependency matrix + Debian-only note from README/DEPLOYMENT (#182)"
```

---

## Task 7: Final verification & PR

**Files:** none (verification only)

- [ ] **Step 1: Run all static checks**

```bash
bash -n deploy/install/lib/config.sh
bash -n deploy/install/lib/features.sh
bash -n deploy/install/modules/14-optional-features.sh
bash -n deploy/install/install.sh
bash -n deploy/install/verify/test-features.sh
```
Expected: all exit 0, no output.

- [ ] **Step 2: Run the offline dispatcher test**

Run: `bash deploy/install/verify/test-features.sh`
Expected: final line shows `FAILED=0`, exit 0 (every assertion prints `ok`).

- [ ] **Step 3: Confirm module registration**

Run: `bash deploy/install/install.sh --list-modules`
Expected: list ends with `14-optional-features`.

- [ ] **Step 4: shellcheck (if installed)**

Run: `command -v shellcheck && shellcheck deploy/install/lib/features.sh deploy/install/modules/14-optional-features.sh deploy/install/verify/test-features.sh || echo "shellcheck not installed — skipping"`
Expected: no errors, or a clean skip.

- [ ] **Step 5: Push branch and open PR**

```bash
git push -u origin docs/deploy-dependencies-182
```
Then open a PR into `main` (use `gh pr create` with a body file per the repo's PR-body convention) titled:
`feat(deploy): optional feature modules + dependency docs (#182)`
Body must reference: closes #182, summary of the new module + flags, the new docs, and a note that default (no-flag) installs are unchanged. Per `.claude/rules/ci-cd-security.md`, this PR touches `deploy/` (CODEOWNERS-owned) and adds an installer module — call that out for review.

---

## Self-review notes (for the implementer)

- **Spec coverage:** Task 1–4 = optional feature modules (full setup per feature, config flags, default none, interactive prompts). Task 2 = catalog + single-run guard + offline tests. Task 5–6 = bilingual dependency matrix + Debian-only documentation. Task 7 = the three-tier verification from the spec (static, offline dispatcher, real-on-box documented).
- **Single-run guard** (`_HW_SUDOERS_DONE`) is asserted by the RAID+SMART test in Task 2.
- **Default behavior preserved:** `ENABLE_*` default `false` (Task 1); module fast-path exits 0 with no installs when nothing is selected (Task 3).
- **No real package install happens in tests** — primitives are overridden; the only real `apt`/script execution is on the target box (Task 7 Step 5 / manual).
```
