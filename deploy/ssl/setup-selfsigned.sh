#!/bin/bash
# ===================================
# Self-Signed SSL Setup Script
# ===================================
# Sets up HTTPS for BaluHost with a self-signed certificate.
# Intended for LAN-only / VPN-only deployments without a public domain.
#
# What this script does:
#   1. Generates a self-signed certificate (10 years, RSA 2048, SHA256)
#   2. Generates Diffie-Hellman parameters (if missing)
#   3. Installs Nginx SSL config with self-signed paths
#   4. Opens port 443 in the firewall
#   5. Adds https:// CORS origins to .env.production
#   6. Tests and reloads Nginx + restarts backend
#
# Usage:
#   sudo ./setup-selfsigned.sh [OPTIONS]
#
# Options:
#   --ip <IP>           LAN IP address (auto-detected if omitted)
#   --hostname <NAME>   Hostname (default: baluhost)
#   --cert-days <DAYS>  Certificate validity in days (default: 3650)
#   --env-file <PATH>   Path to .env.production (default: auto-detect)
#   --nginx-conf <PATH> Path to Nginx site config (default: auto-detect)
#   --skip-firewall     Skip firewall configuration
#   --skip-backend      Skip backend restart
#   --dry-run           Show what would be done without making changes
#
# Prerequisites:
#   - Nginx installed and running (HTTP on port 80)
#   - BaluHost backend running via systemd
#   - Root or sudo access
# ===================================

set -euo pipefail

# ===================================
# Configuration
# ===================================
CERT_DIR="/etc/nginx/ssl"
SNIPPETS_DIR="/etc/nginx/snippets"
DH_PARAM="/etc/nginx/dhparam.pem"

HOSTNAME_DEFAULT="baluhost"
CERT_DAYS_DEFAULT=3650
LAN_IP=""
HOSTNAME_NAME="$HOSTNAME_DEFAULT"
CERT_DAYS="$CERT_DAYS_DEFAULT"
ENV_FILE=""
NGINX_CONF=""
SKIP_FIREWALL=false
SKIP_BACKEND=false
DRY_RUN=false

# Paths to search for env file
ENV_SEARCH_PATHS=(
    "/home/sven/projects/BaluHost/backend/.env.production"
    "/home/sven/projects/BaluHost/.env.production"
    "/opt/baluhost/backend/.env.production"
    "/etc/baluhost/.env.production"
)

# Paths to search for nginx config
NGINX_SEARCH_PATHS=(
    "/etc/nginx/sites-available/baluhost"
    "/etc/nginx/sites-available/baluhost.conf"
    "/etc/nginx/conf.d/baluhost.conf"
)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ===================================
# Functions
# ===================================

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}${BOLD}▸ $1${NC}"; }
log_dry()   { echo -e "${YELLOW}[DRY-RUN]${NC} Would: $1"; }

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root or with sudo"
        exit 1
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --ip)         LAN_IP="$2";       shift 2 ;;
            --hostname)   HOSTNAME_NAME="$2"; shift 2 ;;
            --cert-days)  CERT_DAYS="$2";    shift 2 ;;
            --env-file)   ENV_FILE="$2";     shift 2 ;;
            --nginx-conf) NGINX_CONF="$2";   shift 2 ;;
            --skip-firewall) SKIP_FIREWALL=true; shift ;;
            --skip-backend)  SKIP_BACKEND=true;  shift ;;
            --dry-run)       DRY_RUN=true;       shift ;;
            -h|--help)
                echo "Usage: sudo $0 [--ip <IP>] [--hostname <NAME>] [--cert-days <DAYS>]"
                echo "       [--env-file <PATH>] [--nginx-conf <PATH>]"
                echo "       [--skip-firewall] [--skip-backend] [--dry-run]"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

detect_lan_ip() {
    if [ -n "$LAN_IP" ]; then
        log_info "Using provided IP: $LAN_IP"
        return
    fi

    log_info "Detecting LAN IP address..."

    # Try multiple methods
    LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}') || true

    if [ -z "$LAN_IP" ]; then
        LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}') || true
    fi

    if [ -z "$LAN_IP" ]; then
        LAN_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1) || true
    fi

    if [ -z "$LAN_IP" ]; then
        log_error "Could not detect LAN IP. Use --ip <IP> to specify manually."
        exit 1
    fi

    log_info "Detected LAN IP: $LAN_IP"
}

detect_env_file() {
    if [ -n "$ENV_FILE" ]; then
        if [ ! -f "$ENV_FILE" ]; then
            log_error "Specified env file not found: $ENV_FILE"
            exit 1
        fi
        log_info "Using env file: $ENV_FILE"
        return
    fi

    for path in "${ENV_SEARCH_PATHS[@]}"; do
        if [ -f "$path" ]; then
            ENV_FILE="$path"
            log_info "Found env file: $ENV_FILE"
            return
        fi
    done

    log_warn "No .env.production found. CORS origins will not be updated automatically."
    log_warn "You will need to add https:// origins to CORS_ORIGINS manually."
}

detect_nginx_conf() {
    if [ -n "$NGINX_CONF" ]; then
        if [ ! -f "$NGINX_CONF" ]; then
            log_error "Specified Nginx config not found: $NGINX_CONF"
            exit 1
        fi
        log_info "Using Nginx config: $NGINX_CONF"
        return
    fi

    for path in "${NGINX_SEARCH_PATHS[@]}"; do
        if [ -f "$path" ]; then
            NGINX_CONF="$path"
            log_info "Found Nginx config: $NGINX_CONF"
            return
        fi
    done

    log_error "No Nginx config found. Use --nginx-conf <PATH> to specify."
    exit 1
}

check_nginx() {
    log_info "Checking Nginx..."

    if ! command -v nginx &>/dev/null; then
        log_error "Nginx is not installed"
        exit 1
    fi

    if ! systemctl is-active --quiet nginx; then
        log_warn "Nginx is not running — starting..."
        systemctl start nginx
    fi

    log_info "Nginx is running"
}

# ===================================
# Step 1: Generate Self-Signed Certificate
# ===================================
generate_certificate() {
    log_step "Step 1: Generating self-signed certificate..."

    if [ -f "$CERT_DIR/baluhost.crt" ] && [ -f "$CERT_DIR/baluhost.key" ]; then
        log_warn "Certificate already exists at $CERT_DIR/"

        # Show existing cert info
        EXPIRY=$(openssl x509 -enddate -noout -in "$CERT_DIR/baluhost.crt" 2>/dev/null | cut -d= -f2)
        log_info "Existing cert expires: $EXPIRY"

        read -p "Overwrite existing certificate? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Keeping existing certificate"
            return
        fi
    fi

    if $DRY_RUN; then
        log_dry "Generate certificate at $CERT_DIR/ (CN=${HOSTNAME_NAME}.local, SAN=DNS:${HOSTNAME_NAME}.local,DNS:${HOSTNAME_NAME},IP:${LAN_IP})"
        return
    fi

    mkdir -p "$CERT_DIR"

    # Generate certificate with SAN (Subject Alternative Name)
    openssl req -x509 -nodes \
        -days "$CERT_DAYS" \
        -newkey rsa:2048 \
        -keyout "$CERT_DIR/baluhost.key" \
        -out "$CERT_DIR/baluhost.crt" \
        -subj "/C=DE/O=BaluHost/CN=${HOSTNAME_NAME}.local" \
        -addext "subjectAltName=DNS:${HOSTNAME_NAME}.local,DNS:${HOSTNAME_NAME},DNS:localhost,IP:${LAN_IP},IP:127.0.0.1"

    # Restrict key permissions
    chmod 600 "$CERT_DIR/baluhost.key"
    chmod 644 "$CERT_DIR/baluhost.crt"

    log_info "Certificate generated:"
    log_info "  Cert: $CERT_DIR/baluhost.crt"
    log_info "  Key:  $CERT_DIR/baluhost.key"
    log_info "  Valid for $CERT_DAYS days"
    log_info "  SANs: ${HOSTNAME_NAME}.local, ${HOSTNAME_NAME}, localhost, ${LAN_IP}, 127.0.0.1"
}

# ===================================
# Step 2: Generate DH Parameters
# ===================================
generate_dhparam() {
    log_step "Step 2: Generating Diffie-Hellman parameters..."

    if [ -f "$DH_PARAM" ]; then
        log_info "dhparam.pem already exists, skipping"
        return
    fi

    if $DRY_RUN; then
        log_dry "Generate DH params at $DH_PARAM (2048-bit)"
        return
    fi

    log_info "This may take 1-2 minutes..."
    openssl dhparam -out "$DH_PARAM" 2048
    chmod 644 "$DH_PARAM"
    log_info "DH parameters generated"
}

# ===================================
# Step 3: Install SSL Nginx Snippets
# ===================================
install_ssl_snippets() {
    log_step "Step 3: Installing SSL configuration snippets..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

    mkdir -p "$SNIPPETS_DIR"

    # Install ssl-params.conf (with OCSP stapling disabled for self-signed)
    if [ -f "$DEPLOY_DIR/nginx/ssl-params.conf" ]; then
        if $DRY_RUN; then
            log_dry "Install ssl-params.conf to $SNIPPETS_DIR/ (OCSP stapling disabled)"
        else
            # Copy and disable OCSP stapling (not compatible with self-signed certs)
            sed \
                -e 's/^ssl_stapling on;/# ssl_stapling on;  # Disabled: requires CA-signed certificate/' \
                -e 's/^ssl_stapling_verify on;/# ssl_stapling_verify on;  # Disabled: requires CA-signed certificate/' \
                -e '/^ssl_stapling_file/s/^/# /' \
                "$DEPLOY_DIR/nginx/ssl-params.conf" > "$SNIPPETS_DIR/ssl-params.conf"
            log_info "Installed ssl-params.conf (OCSP stapling disabled for self-signed)"
        fi
    else
        log_warn "ssl-params.conf not found in $DEPLOY_DIR/nginx/"
    fi

    # Install security-headers.conf as-is
    if [ -f "$DEPLOY_DIR/nginx/security-headers.conf" ]; then
        if $DRY_RUN; then
            log_dry "Install security-headers.conf to $SNIPPETS_DIR/"
        else
            cp "$DEPLOY_DIR/nginx/security-headers.conf" "$SNIPPETS_DIR/"
            log_info "Installed security-headers.conf"
        fi
    else
        log_warn "security-headers.conf not found in $DEPLOY_DIR/nginx/"
    fi
}

# ===================================
# Step 4: Update Nginx Site Config
# ===================================
update_nginx_config() {
    log_step "Step 4: Updating Nginx site configuration..."

    if $DRY_RUN; then
        log_dry "Backup $NGINX_CONF"
        log_dry "Update SSL certificate paths to self-signed"
        log_dry "Update server_name to: ${HOSTNAME_NAME} ${HOSTNAME_NAME}.local ${LAN_IP}"
        return
    fi

    # Backup current config
    BACKUP="${NGINX_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$NGINX_CONF" "$BACKUP"
    log_info "Backed up Nginx config to $BACKUP"

    # Determine if config already has SSL (listen 443)
    if grep -q "listen 443" "$NGINX_CONF"; then
        log_info "Config already has HTTPS server block — updating certificate paths..."

        # Replace Let's Encrypt cert paths with self-signed
        sed -i \
            -e "s|ssl_certificate /etc/letsencrypt/.*fullchain.pem;|ssl_certificate $CERT_DIR/baluhost.crt;|" \
            -e "s|ssl_certificate_key /etc/letsencrypt/.*privkey.pem;|ssl_certificate_key $CERT_DIR/baluhost.key;|" \
            "$NGINX_CONF"

        # Uncomment self-signed paths if they were commented out
        sed -i \
            -e "s|# *ssl_certificate $CERT_DIR/baluhost.crt;|ssl_certificate $CERT_DIR/baluhost.crt;|" \
            -e "s|# *ssl_certificate_key $CERT_DIR/baluhost.key;|ssl_certificate_key $CERT_DIR/baluhost.key;|" \
            "$NGINX_CONF"

    else
        log_info "Config is HTTP-only — upgrading to HTTPS..."

        # The current prod config is HTTP-only. Install the full HTTPS template.
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
        TEMPLATE="$DEPLOY_DIR/nginx/baluhost.conf"

        if [ ! -f "$TEMPLATE" ]; then
            log_error "Nginx template not found: $TEMPLATE"
            log_error "Cannot upgrade HTTP config to HTTPS automatically."
            exit 1
        fi

        # Copy template and configure for self-signed
        cp "$TEMPLATE" "$NGINX_CONF"
        log_info "Installed HTTPS Nginx config from template"

        # Set self-signed certificate paths
        sed -i \
            -e "s|ssl_certificate /etc/letsencrypt/.*fullchain.pem;|ssl_certificate $CERT_DIR/baluhost.crt;|" \
            -e "s|ssl_certificate_key /etc/letsencrypt/.*privkey.pem;|ssl_certificate_key $CERT_DIR/baluhost.key;|" \
            "$NGINX_CONF"

        # Production serves static files directly, not via Docker proxy
        # Activate "Option 3" (static files) and deactivate Docker proxy
        sed -i \
            -e '/# Option 2: Docker Compose/,/proxy_set_header X-Forwarded-Proto/s/^/#/' \
            -e "s|# root /var/www/baluhost/frontend;|root /var/www/baluhost;|" \
            -e "s|# try_files \$uri \$uri/ /index.html;|try_files \$uri \$uri/ /index.html;|" \
            "$NGINX_CONF"

        # Same for static assets: switch from Docker proxy to direct serving
        sed -i \
            -e '/# For Docker: Proxy to frontend/s/^/#/' \
            -e '/proxy_pass http:\/\/localhost:80;/{
                /# Static Assets/,/}/{
                    s/^/#/
                }
            }' \
            -e "s|# root /var/www/baluhost/frontend;|root /var/www/baluhost;|" \
            -e "s|# expires 1y;|expires 1y;|" \
            -e 's|# add_header Cache-Control "public, immutable";|add_header Cache-Control "public, immutable";|' \
            -e "s|# access_log off;|access_log off;|" \
            "$NGINX_CONF"
    fi

    # Update server_name in all server blocks
    sed -i "s/server_name .*/server_name ${HOSTNAME_NAME} ${HOSTNAME_NAME}.local ${LAN_IP};/" "$NGINX_CONF"

    log_info "Nginx config updated with self-signed certificate paths"
}

# ===================================
# Step 5: Firewall
# ===================================
configure_firewall() {
    log_step "Step 5: Configuring firewall..."

    if $SKIP_FIREWALL; then
        log_info "Skipping firewall (--skip-firewall)"
        return
    fi

    # UFW
    if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
        if $DRY_RUN; then
            log_dry "ufw allow 443/tcp"
        else
            ufw allow 443/tcp
            log_info "Opened port 443 in UFW"
        fi
        return
    fi

    # firewalld
    if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
        if $DRY_RUN; then
            log_dry "firewall-cmd --permanent --add-service=https && firewall-cmd --reload"
        else
            firewall-cmd --permanent --add-service=https
            firewall-cmd --reload
            log_info "Opened HTTPS in firewalld"
        fi
        return
    fi

    # iptables fallback
    if command -v iptables &>/dev/null; then
        if iptables -L INPUT -n 2>/dev/null | grep -q "dpt:443"; then
            log_info "Port 443 already open in iptables"
        else
            if $DRY_RUN; then
                log_dry "iptables -A INPUT -p tcp --dport 443 -j ACCEPT"
            else
                iptables -A INPUT -p tcp --dport 443 -j ACCEPT
                log_info "Opened port 443 in iptables"
                log_warn "iptables rules are not persistent — install iptables-persistent to keep them"
            fi
        fi
        return
    fi

    log_warn "No firewall detected — ensure port 443 is accessible"
}

# ===================================
# Step 6: Update CORS Origins
# ===================================
update_cors_origins() {
    log_step "Step 6: Updating CORS origins..."

    if [ -z "$ENV_FILE" ]; then
        log_warn "No .env.production — skipping CORS update"
        log_warn "Add these origins manually: https://${HOSTNAME_NAME}.local,https://${LAN_IP},https://localhost"
        return
    fi

    # Build the list of https origins to add
    HTTPS_ORIGINS="https://${HOSTNAME_NAME}.local,https://${LAN_IP},https://localhost,https://127.0.0.1"

    if $DRY_RUN; then
        log_dry "Add HTTPS origins to CORS_ORIGINS in $ENV_FILE"
        log_dry "Origins to add: $HTTPS_ORIGINS"
        return
    fi

    if grep -q "^CORS_ORIGINS=" "$ENV_FILE"; then
        # Append https origins to existing CORS_ORIGINS line
        CURRENT=$(grep "^CORS_ORIGINS=" "$ENV_FILE" | cut -d= -f2-)

        # Check if https origins are already present
        if echo "$CURRENT" | grep -q "https://${HOSTNAME_NAME}.local"; then
            log_info "HTTPS origins already present in CORS_ORIGINS"
            return
        fi

        # Append
        NEW_ORIGINS="${CURRENT},${HTTPS_ORIGINS}"
        sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=${NEW_ORIGINS}|" "$ENV_FILE"
        log_info "Updated CORS_ORIGINS with HTTPS origins"
    else
        # Add new CORS_ORIGINS line with both HTTP and HTTPS
        echo "CORS_ORIGINS=http://localhost,http://${HOSTNAME_NAME}.local,http://127.0.0.1,${HTTPS_ORIGINS}" >> "$ENV_FILE"
        log_info "Added CORS_ORIGINS to $ENV_FILE"
    fi

    log_info "CORS origins: $(grep '^CORS_ORIGINS=' "$ENV_FILE" | cut -d= -f2-)"
}

# ===================================
# Step 7: Test and Reload
# ===================================
reload_services() {
    log_step "Step 7: Testing and reloading services..."

    if $DRY_RUN; then
        log_dry "nginx -t"
        log_dry "systemctl reload nginx"
        if ! $SKIP_BACKEND; then
            log_dry "systemctl restart baluhost-backend"
        fi
        return
    fi

    # Test Nginx config
    if nginx -t; then
        log_info "Nginx configuration test passed"
    else
        log_error "Nginx configuration test FAILED"
        log_error "Check the config manually: nginx -t"
        log_error "Restore backup if needed"
        exit 1
    fi

    # Reload Nginx
    systemctl reload nginx
    log_info "Nginx reloaded"

    # Restart backend (for CORS changes)
    if ! $SKIP_BACKEND; then
        if systemctl is-active --quiet baluhost-backend; then
            systemctl restart baluhost-backend
            log_info "Backend restarted (CORS origins updated)"
        else
            log_warn "baluhost-backend service not running — skipping restart"
        fi
    else
        log_info "Skipping backend restart (--skip-backend)"
        log_warn "Restart manually for CORS changes: sudo systemctl restart baluhost-backend"
    fi
}

# ===================================
# Step 8: Verify & Print Summary
# ===================================
print_summary() {
    log_step "Step 8: Verification..."

    if $DRY_RUN; then
        log_info "Dry run complete — no changes were made"
        return
    fi

    echo ""
    echo -e "${GREEN}${BOLD}====================================${NC}"
    echo -e "${GREEN}${BOLD} Self-Signed SSL Setup Complete!${NC}"
    echo -e "${GREEN}${BOLD}====================================${NC}"
    echo ""
    echo -e "  Certificate: ${BOLD}$CERT_DIR/baluhost.crt${NC}"
    echo -e "  Key:         ${BOLD}$CERT_DIR/baluhost.key${NC}"
    echo -e "  Valid:       ${BOLD}$CERT_DAYS days${NC}"
    echo ""
    echo -e "  ${BOLD}Access BaluHost:${NC}"
    echo -e "    https://${HOSTNAME_NAME}.local"
    echo -e "    https://${LAN_IP}"
    echo ""

    # Quick connection test
    if command -v curl &>/dev/null; then
        HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" "https://${LAN_IP}" 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
            echo -e "  ${GREEN}HTTPS is working (HTTP $HTTP_CODE)${NC}"
        elif [ "$HTTP_CODE" = "000" ]; then
            echo -e "  ${YELLOW}Could not connect — check firewall and Nginx status${NC}"
        else
            echo -e "  ${YELLOW}HTTPS responded with HTTP $HTTP_CODE${NC}"
        fi
        echo ""
    fi

    echo -e "${BOLD}  Client Trust (einmalig pro Geraet):${NC}"
    echo ""
    echo -e "  ${BOLD}Browser:${NC}"
    echo "    Open https://${LAN_IP}, accept the warning, or import the certificate."
    echo ""
    echo -e "  ${BOLD}Android (BaluApp):${NC}"
    echo "    Copy baluhost.crt to phone > Settings > Security > Install certificate"
    echo "    Or add to network_security_config.xml for the app."
    echo ""
    echo -e "  ${BOLD}BaluDesk (Electron):${NC}"
    echo "    Import cert or set NODE_EXTRA_CA_CERTS=$CERT_DIR/baluhost.crt"
    echo ""
    echo -e "  ${BOLD}Linux CLI:${NC}"
    echo "    sudo cp $CERT_DIR/baluhost.crt /usr/local/share/ca-certificates/baluhost.crt"
    echo "    sudo update-ca-certificates"
    echo ""
    echo -e "  ${BOLD}Export certificate for clients:${NC}"
    echo "    scp root@${LAN_IP}:$CERT_DIR/baluhost.crt ."
    echo ""
    echo -e "  ${BOLD}Verify certificate:${NC}"
    echo "    openssl x509 -in $CERT_DIR/baluhost.crt -noout -text"
    echo "    echo | openssl s_client -connect ${LAN_IP}:443 -servername ${HOSTNAME_NAME}.local 2>/dev/null | openssl x509 -noout -dates"
    echo ""
}

# ===================================
# Main
# ===================================
main() {
    echo -e "${BLUE}${BOLD}"
    echo "====================================="
    echo " BaluHost Self-Signed SSL Setup"
    echo "====================================="
    echo -e "${NC}"

    parse_args "$@"
    check_root
    detect_lan_ip
    check_nginx
    detect_nginx_conf
    detect_env_file

    echo ""
    echo -e "${BOLD}Configuration:${NC}"
    echo "  Hostname:    ${HOSTNAME_NAME}.local"
    echo "  LAN IP:      ${LAN_IP}"
    echo "  Cert days:   ${CERT_DAYS}"
    echo "  Nginx conf:  ${NGINX_CONF}"
    echo "  Env file:    ${ENV_FILE:-<not found>}"
    echo "  Dry run:     ${DRY_RUN}"
    echo ""

    if ! $DRY_RUN; then
        read -p "Continue with these settings? (Y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            log_info "Aborted"
            exit 0
        fi
    fi

    generate_certificate
    generate_dhparam
    install_ssl_snippets
    update_nginx_config
    configure_firewall
    update_cors_origins
    reload_services
    print_summary
}

main "$@"
