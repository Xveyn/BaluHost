#!/bin/bash
# ===================================
# Nginx Installation and Configuration Script
# ===================================
# Automates Nginx installation and initial setup for BaluHost
#
# Usage:
#   sudo ./install-nginx.sh
#
# Prerequisites:
#   - Ubuntu/Debian or RHEL/CentOS/Fedora
#   - Root or sudo access
#   - Internet connection
# ===================================

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure

# ===================================
# Configuration
# ===================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ===================================
# Functions
# ===================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root or with sudo"
        exit 1
    fi
}

detect_os() {
    if [ -f /etc/debian_version ]; then
        OS="debian"
        log_info "Detected Debian/Ubuntu-based system"
    elif [ -f /etc/redhat-release ]; then
        OS="redhat"
        log_info "Detected RHEL/CentOS/Fedora-based system"
    else
        log_error "Unsupported operating system"
        exit 1
    fi
}

install_nginx() {
    log_step "Installing Nginx..."

    if command -v nginx &> /dev/null; then
        log_info "Nginx is already installed"
        nginx -v
        return
    fi

    if [ "$OS" = "debian" ]; then
        apt-get update
        apt-get install -y nginx
    elif [ "$OS" = "redhat" ]; then
        yum install -y nginx || dnf install -y nginx
    fi

    log_info "Nginx installed successfully"
    nginx -v
}

configure_firewall() {
    log_step "Configuring firewall..."

    if command -v ufw &> /dev/null; then
        # UFW (Ubuntu/Debian)
        log_info "Configuring UFW firewall..."
        ufw allow 'Nginx Full'
        ufw allow OpenSSH
        log_info "UFW rules added (HTTP, HTTPS, SSH)"

    elif command -v firewall-cmd &> /dev/null; then
        # firewalld (RHEL/CentOS)
        log_info "Configuring firewalld..."
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --reload
        log_info "Firewalld rules added (HTTP, HTTPS)"

    else
        log_warn "No supported firewall detected"
        log_warn "Manually open ports 80 (HTTP) and 443 (HTTPS)"
    fi
}

create_directories() {
    log_step "Creating directories..."

    # Nginx snippets directory
    mkdir -p /etc/nginx/snippets
    log_info "Created /etc/nginx/snippets"

    # Sites directories (Debian/Ubuntu)
    if [ "$OS" = "debian" ]; then
        mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
        log_info "Created sites-available and sites-enabled directories"
    fi

    # Certbot webroot
    mkdir -p /var/www/certbot
    chmod 755 /var/www/certbot
    chown www-data:www-data /var/www/certbot 2>/dev/null || chown nginx:nginx /var/www/certbot 2>/dev/null
    log_info "Created certbot webroot: /var/www/certbot"

    # Cache directory for OCSP
    mkdir -p /var/cache/nginx
    chmod 755 /var/cache/nginx
    chown www-data:www-data /var/cache/nginx 2>/dev/null || chown nginx:nginx /var/cache/nginx 2>/dev/null
    log_info "Created nginx cache directory"

    # Log directory
    mkdir -p /var/log/nginx
    log_info "Created nginx log directory"
}

optimize_nginx_config() {
    log_step "Optimizing main Nginx configuration..."

    NGINX_CONF="/etc/nginx/nginx.conf"

    # Backup original config
    cp "$NGINX_CONF" "$NGINX_CONF.backup.$(date +%Y%m%d_%H%M%S)"
    log_info "Backed up nginx.conf"

    # Hide nginx version
    if ! grep -q "server_tokens off;" "$NGINX_CONF"; then
        sed -i '/http {/a \    server_tokens off;' "$NGINX_CONF"
        log_info "Added: server_tokens off"
    fi

    # Increase worker connections (if low)
    if ! grep -q "worker_connections 2048;" "$NGINX_CONF"; then
        sed -i 's/worker_connections [0-9]*;/worker_connections 2048;/' "$NGINX_CONF"
        log_info "Increased worker_connections to 2048"
    fi

    # Enable gzip compression (if not already enabled)
    if ! grep -q "gzip on;" "$NGINX_CONF"; then
        sed -i '/http {/a \    gzip on;\n    gzip_vary on;\n    gzip_min_length 1024;\n    gzip_comp_level 6;' "$NGINX_CONF"
        log_info "Enabled gzip compression"
    fi

    # Set client_max_body_size
    if ! grep -q "client_max_body_size" "$NGINX_CONF"; then
        sed -i '/http {/a \    client_max_body_size 10G;' "$NGINX_CONF"
        log_info "Set client_max_body_size to 10G"
    fi

    log_info "Nginx main configuration optimized"
}

install_config_files() {
    log_step "Installing BaluHost configuration files..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    DEPLOY_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

    # Install SSL params
    if [ -f "$DEPLOY_DIR/deploy/nginx/ssl-params.conf" ]; then
        cp "$DEPLOY_DIR/deploy/nginx/ssl-params.conf" /etc/nginx/snippets/
        log_info "Installed ssl-params.conf"
    else
        log_warn "ssl-params.conf not found"
    fi

    # Install security headers
    if [ -f "$DEPLOY_DIR/deploy/nginx/security-headers.conf" ]; then
        cp "$DEPLOY_DIR/deploy/nginx/security-headers.conf" /etc/nginx/snippets/
        log_info "Installed security-headers.conf"
    else
        log_warn "security-headers.conf not found"
    fi

    # Install main site config (but don't enable yet)
    if [ -f "$DEPLOY_DIR/deploy/nginx/baluhost.conf" ]; then
        cp "$DEPLOY_DIR/deploy/nginx/baluhost.conf" /etc/nginx/sites-available/ 2>/dev/null || \
        cp "$DEPLOY_DIR/deploy/nginx/baluhost.conf" /etc/nginx/conf.d/baluhost.conf.disabled
        log_info "Installed baluhost.conf"
        log_warn "Site NOT enabled - configure domain and backend first!"
    else
        log_warn "baluhost.conf not found"
    fi
}

test_nginx_config() {
    log_step "Testing Nginx configuration..."

    if nginx -t; then
        log_info "Nginx configuration test passed"
        return 0
    else
        log_error "Nginx configuration test failed"
        return 1
    fi
}

start_nginx() {
    log_step "Starting Nginx service..."

    systemctl enable nginx
    log_info "Nginx enabled (will start on boot)"

    if systemctl is-active --quiet nginx; then
        log_info "Nginx is already running, reloading..."
        systemctl reload nginx
    else
        log_info "Starting Nginx..."
        systemctl start nginx
    fi

    if systemctl is-active --quiet nginx; then
        log_info "Nginx is running"
    else
        log_error "Failed to start Nginx"
        exit 1
    fi
}

show_next_steps() {
    log_info ""
    log_info "====================================="
    log_info "Nginx Installation Complete!"
    log_info "====================================="
    log_info ""
    log_info "Nginx is installed and running"
    log_info "Default site: http://$(hostname -I | awk '{print $1}')"
    log_info ""
    log_info "Next steps:"
    log_info "1. Deploy BaluHost with Docker:"
    log_info "   cd /path/to/baluhost"
    log_info "   docker-compose up -d"
    log_info ""
    log_info "2. Configure domain and SSL:"
    log_info "   sudo ./deploy/ssl/setup-letsencrypt.sh yourdomain.com admin@yourdomain.com"
    log_info ""
    log_info "3. Update nginx config:"
    log_info "   sudo nano /etc/nginx/sites-available/baluhost.conf"
    log_info "   - Replace YOUR_DOMAIN_HERE with your actual domain"
    log_info "   - Configure upstream backend (Docker or systemd)"
    log_info ""
    log_info "4. Enable site:"
    log_info "   sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/"
    log_info "   sudo nginx -t"
    log_info "   sudo systemctl reload nginx"
    log_info ""
    log_info "Useful commands:"
    log_info "  - Test config: sudo nginx -t"
    log_info "  - Reload: sudo systemctl reload nginx"
    log_info "  - Restart: sudo systemctl restart nginx"
    log_info "  - Status: sudo systemctl status nginx"
    log_info "  - Logs: sudo tail -f /var/log/nginx/error.log"
    log_info ""
}

# ===================================
# Main Execution
# ===================================

main() {
    log_info "====================================="
    log_info "Nginx Installation for BaluHost"
    log_info "====================================="
    log_info ""

    check_root
    detect_os
    install_nginx
    configure_firewall
    create_directories
    optimize_nginx_config
    install_config_files

    if test_nginx_config; then
        start_nginx
        show_next_steps
    else
        log_error "Nginx configuration has errors"
        log_error "Fix errors before starting nginx"
        exit 1
    fi
}

# Run main function
main "$@"
