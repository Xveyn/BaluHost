#!/bin/bash
# BaluHost Modular Installer
# Usage: install.sh [--module <name>] [--config <path>] [--non-interactive]
#
# Orchestrates the full installation of BaluHost on Debian 12/13.
# Modules can be run individually with --module, or all in sequence.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/config.sh"

# ─── Version ─────────────────────────────────────────────────────────
readonly INSTALLER_VERSION="1.0.0"

# ─── Module Registry ─────────────────────────────────────────────────
readonly -a MODULES=(
    "01-preflight"
    "02-system-packages"
    "03-user-setup"
    "04-app-deploy"
    "05-python-venv"
    "06-postgresql"
    "07-env-generate"
    "08-database-migrate"
    "09-frontend-build"
    "10-systemd-services"
    "11-nginx"
    "12-start-services"
)

# ─── Usage ───────────────────────────────────────────────────────────
usage() {
    cat <<EOF
BaluHost Installer v${INSTALLER_VERSION}

Usage: $(basename "$0") [OPTIONS]

Options:
  --module <name>       Run a single module (e.g., 06-postgresql)
  --config <path>       Path to config file (default: /etc/baluhost/install.conf)
  --non-interactive     Skip all prompts, use defaults/config values
  --list-modules        List available modules
  -h, --help            Show this help

Examples:
  sudo ./install.sh                          # Full interactive install
  sudo ./install.sh --non-interactive        # Automated install from config
  sudo ./install.sh --module 06-postgresql   # Run single module
EOF
}

list_modules() {
    echo "Available modules:"
    for mod in "${MODULES[@]}"; do
        echo "  $mod"
    done
}

# ─── Run a Single Module ─────────────────────────────────────────────
run_module() {
    local module_name="$1"
    local module_path="$SCRIPT_DIR/modules/${module_name}.sh"

    if [[ ! -f "$module_path" ]]; then
        log_error "Module not found: $module_path"
        return 1
    fi

    log_step "Running module: $module_name"
    # Source the module so it inherits our environment (config variables)
    if source "$module_path"; then
        log_info "Module $module_name completed successfully."
        return 0
    else
        local rc=$?
        log_error "Module $module_name failed (exit code $rc)."
        return $rc
    fi
}

# ─── Gather Interactive Input ─────────────────────────────────────────
gather_input() {
    if [[ "${NON_INTERACTIVE:-false}" == "true" ]]; then
        log_info "Non-interactive mode — using config/defaults."
        return 0
    fi

    echo ""
    echo -e "${BOLD}BaluHost Installation Setup${NC}"
    echo -e "Configure the installation parameters below."
    echo -e "Press Enter to accept defaults shown in [brackets]."
    echo ""

    INSTALL_DIR=$(prompt_value "Installation directory" "$INSTALL_DIR")
    BALUHOST_USER=$(prompt_value "System user" "$BALUHOST_USER")
    BALUHOST_GROUP=$(prompt_value "System group" "$BALUHOST_GROUP")
    FRONTEND_STATIC_DIR=$(prompt_value "Frontend static directory" "$FRONTEND_STATIC_DIR")
    GIT_REPO=$(prompt_value "Git repository URL" "$GIT_REPO")
    GIT_BRANCH=$(prompt_value "Git branch" "$GIT_BRANCH")

    echo ""
    log_step "Admin Account"
    ADMIN_USERNAME=$(prompt_value "Admin username" "$ADMIN_USERNAME")
    ADMIN_EMAIL=$(prompt_value "Admin email" "$ADMIN_EMAIL")

    if [[ -z "$ADMIN_PASSWORD" ]]; then
        while true; do
            ADMIN_PASSWORD=$(prompt_password "Admin password (min 8 chars, upper+lower+digit)")
            if [[ ${#ADMIN_PASSWORD} -lt 8 ]]; then
                log_warn "Password too short (minimum 8 characters). Try again."
                continue
            fi
            if ! [[ "$ADMIN_PASSWORD" =~ [A-Z] ]]; then
                log_warn "Password must contain an uppercase letter. Try again."
                continue
            fi
            if ! [[ "$ADMIN_PASSWORD" =~ [a-z] ]]; then
                log_warn "Password must contain a lowercase letter. Try again."
                continue
            fi
            if ! [[ "$ADMIN_PASSWORD" =~ [0-9] ]]; then
                log_warn "Password must contain a digit. Try again."
                continue
            fi
            local confirm_pw
            confirm_pw=$(prompt_password "Confirm admin password")
            if [[ "$ADMIN_PASSWORD" != "$confirm_pw" ]]; then
                log_warn "Passwords do not match. Try again."
                continue
            fi
            break
        done
    fi

    echo ""
    log_step "Configuration Summary"
    echo "  Install directory:  $INSTALL_DIR"
    echo "  System user:        $BALUHOST_USER"
    echo "  System group:       $BALUHOST_GROUP"
    echo "  Frontend directory: $FRONTEND_STATIC_DIR"
    echo "  Git repository:     $GIT_REPO"
    echo "  Git branch:         $GIT_BRANCH"
    echo "  Admin username:     $ADMIN_USERNAME"
    echo "  Admin email:        $ADMIN_EMAIL"
    echo ""

    if ! confirm "Proceed with installation?"; then
        log_info "Installation cancelled."
        exit 0
    fi
}

# ─── Main ─────────────────────────────────────────────────────────────
main() {
    local single_module=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --module)
                single_module="$2"
                shift 2
                ;;
            --config)
                BALUHOST_CONFIG="$2"
                shift 2
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            --list-modules)
                list_modules
                exit 0
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    # Banner
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║    BaluHost Installer v${INSTALLER_VERSION}          ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
    echo ""

    require_root

    # Load existing config (if any)
    load_config

    # Single module mode
    if [[ -n "$single_module" ]]; then
        log_info "Single module mode: $single_module"
        run_module "$single_module"
        exit $?
    fi

    # Full installation
    log_step "Phase 0: Preflight (mandatory)"
    run_module "01-preflight"

    # Gather user input
    gather_input

    # Save config before running modules (so we can resume on failure)
    save_config

    # Run modules 02-12
    local failed=0
    for mod in "${MODULES[@]:1}"; do  # Skip 01-preflight (already ran)
        if ! run_module "$mod"; then
            failed=1
            log_error "Installation stopped at module: $mod"
            log_error "Fix the issue and re-run: sudo $0 --module $mod"
            log_error "Then resume full install: sudo $0"
            break
        fi
        # Save config after each module (captures generated values like POSTGRES_PASSWORD)
        save_config
    done

    if [[ $failed -eq 0 ]]; then
        # Run verification
        log_step "Verification"
        if [[ -f "$SCRIPT_DIR/verify/verify-install.sh" ]]; then
            source "$SCRIPT_DIR/verify/verify-install.sh" || true
        fi

        echo ""
        echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${NC}"
        echo -e "${GREEN}${BOLD}║    Installation Complete!            ║${NC}"
        echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${NC}"
        echo ""
        echo "  Web Interface:    http://localhost"
        echo "  API Docs:         http://localhost/docs"
        echo "  Admin User:       $ADMIN_USERNAME"
        echo ""
        echo "  Config saved to:  $BALUHOST_CONFIG"
        echo "  Env file:         $INSTALL_DIR/.env.production"
        echo ""
        echo "  Services:"
        echo "    systemctl status baluhost-backend"
        echo "    systemctl status baluhost-scheduler"
        echo "    systemctl status baluhost-webdav"
        echo ""
        echo "  Logs:"
        echo "    journalctl -u baluhost-backend -f"
        echo ""
    fi

    exit $failed
}

main "$@"
