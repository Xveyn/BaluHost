#!/bin/bash
# BaluHost Install System - Shared Library
# Provides logging, OS detection, secret generation, and utility functions.

set -euo pipefail

# ─── Colors ──────────────────────────────────────────────────────────
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly NC='\033[0m' # No Color

# ─── Logging ─────────────────────────────────────────────────────────
log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*" >&2; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()  { echo -e "\n${BLUE}${BOLD}── $* ──${NC}"; }

# ─── Checks ──────────────────────────────────────────────────────────

require_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)."
        exit 1
    fi
}

detect_debian_version() {
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot detect OS: /etc/os-release not found."
        exit 1
    fi
    # shellcheck source=/dev/null
    . /etc/os-release
    if [[ "${ID:-}" != "debian" ]]; then
        log_error "Unsupported OS: ${ID:-unknown}. Only Debian is supported."
        exit 1
    fi
    DEBIAN_VERSION="${VERSION_ID:-}"
    DEBIAN_CODENAME="${VERSION_CODENAME:-}"
    if [[ "$DEBIAN_VERSION" != "12" && "$DEBIAN_VERSION" != "13" ]]; then
        log_warn "Untested Debian version: $DEBIAN_VERSION ($DEBIAN_CODENAME). Tested on 12 (bookworm) and 13 (trixie)."
    fi
    log_info "Detected Debian $DEBIAN_VERSION ($DEBIAN_CODENAME)"
}

# ─── Secret Generation ───────────────────────────────────────────────

generate_secret() {
    # Generates a 64-character URL-safe random secret
    python3 -c "import secrets; print(secrets.token_urlsafe(48))"
}

generate_fernet_key() {
    # Generates a Fernet key for AES encryption (VPN key encryption)
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

generate_db_password() {
    # Generates a 32-character alphanumeric password (safe for DB connection strings)
    python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32)))"
}

# ─── User Interaction ────────────────────────────────────────────────

confirm() {
    local prompt="${1:-Continue?}"
    if [[ "${NON_INTERACTIVE:-false}" == "true" ]]; then
        return 0
    fi
    echo -en "${CYAN}${prompt} [y/N]: ${NC}"
    read -r answer
    [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]
}

prompt_value() {
    local prompt="$1"
    local default="${2:-}"
    local value=""

    if [[ "${NON_INTERACTIVE:-false}" == "true" ]]; then
        echo "$default"
        return
    fi

    if [[ -n "$default" ]]; then
        echo -en "${CYAN}${prompt} [${default}]: ${NC}"
    else
        echo -en "${CYAN}${prompt}: ${NC}"
    fi
    read -r value
    echo "${value:-$default}"
}

prompt_password() {
    local prompt="$1"
    local value=""

    if [[ "${NON_INTERACTIVE:-false}" == "true" ]]; then
        echo ""
        return
    fi

    echo -en "${CYAN}${prompt}: ${NC}"
    read -rs value
    echo  # newline after silent read
    echo "$value"
}

# ─── Template Processing ─────────────────────────────────────────────

process_template() {
    # Replace @@PLACEHOLDER@@ tokens in a template file.
    # Usage: process_template <template_file> <output_file> KEY1=VALUE1 KEY2=VALUE2 ...
    local template="$1"
    local output="$2"
    shift 2

    if [[ ! -f "$template" ]]; then
        log_error "Template not found: $template"
        return 1
    fi

    local content
    content=$(<"$template")

    for pair in "$@"; do
        local key="${pair%%=*}"
        local val="${pair#*=}"
        content="${content//@@${key}@@/$val}"
    done

    echo "$content" > "$output"
}

# ─── Idempotency Helpers ─────────────────────────────────────────────

user_exists() {
    id "$1" &>/dev/null
}

group_exists() {
    getent group "$1" &>/dev/null
}

service_exists() {
    systemctl list-unit-files "$1" &>/dev/null 2>&1
}

pg_db_exists() {
    sudo -u postgres psql -lqt 2>/dev/null | cut -d'|' -f1 | grep -qw "$1"
}

pg_user_exists() {
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$1'" 2>/dev/null | grep -q 1
}
