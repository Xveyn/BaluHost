#!/bin/bash
# ===================================
# Let's Encrypt SSL Setup Script
# ===================================
# Automates SSL/TLS certificate setup with Let's Encrypt
# Uses Certbot with nginx plugin
#
# Usage:
#   sudo ./setup-letsencrypt.sh yourdomain.com admin@yourdomain.com
#
# Prerequisites:
#   - Nginx installed and running
#   - Domain pointing to this server (A/AAAA DNS records)
#   - Ports 80 and 443 open in firewall
#   - Root or sudo access
# ===================================

set -e  # Exit on error
set -u  # Exit on undefined variable
set -o pipefail  # Exit on pipe failure

# ===================================
# Configuration
# ===================================

# Check arguments
if [ $# -lt 2 ]; then
    echo "Usage: $0 <domain> <email>"
    echo "Example: $0 nas.example.com admin@example.com"
    exit 1
fi

DOMAIN="$1"
EMAIL="$2"
WEBROOT="/var/www/certbot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root or with sudo"
        exit 1
    fi
}

check_domain_dns() {
    log_info "Checking DNS records for $DOMAIN..."

    # Check if domain resolves
    if ! host "$DOMAIN" > /dev/null 2>&1; then
        log_error "Domain $DOMAIN does not resolve to any IP address"
        log_error "Please configure DNS A/AAAA records before continuing"
        exit 1
    fi

    # Get domain IP
    DOMAIN_IP=$(host "$DOMAIN" | grep "has address" | awk '{print $4}' | head -n1)

    # Get server public IP
    SERVER_IP=$(curl -s https://api.ipify.org || curl -s https://ifconfig.me)

    if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
        log_warn "Domain IP ($DOMAIN_IP) differs from server IP ($SERVER_IP)"
        log_warn "Make sure DNS is properly configured and propagated"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        log_info "DNS check passed: $DOMAIN points to $SERVER_IP"
    fi
}

check_nginx() {
    log_info "Checking Nginx installation..."

    if ! command -v nginx &> /dev/null; then
        log_error "Nginx is not installed"
        log_error "Install nginx first: sudo apt install nginx"
        exit 1
    fi

    if ! systemctl is-active --quiet nginx; then
        log_warn "Nginx is not running"
        log_info "Starting Nginx..."
        systemctl start nginx
    fi

    log_info "Nginx is running"
}

install_certbot() {
    log_info "Checking Certbot installation..."

    if command -v certbot &> /dev/null; then
        log_info "Certbot is already installed"
        return
    fi

    log_info "Installing Certbot..."

    # Detect distribution
    if [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        apt-get update
        apt-get install -y certbot python3-certbot-nginx
    elif [ -f /etc/redhat-release ]; then
        # RHEL/CentOS/Fedora
        yum install -y certbot python3-certbot-nginx || dnf install -y certbot python3-certbot-nginx
    else
        log_error "Unsupported distribution. Please install certbot manually."
        exit 1
    fi

    log_info "Certbot installed successfully"
}

setup_webroot() {
    log_info "Setting up webroot directory for ACME challenges..."

    mkdir -p "$WEBROOT"
    chmod 755 "$WEBROOT"
    chown www-data:www-data "$WEBROOT" 2>/dev/null || chown nginx:nginx "$WEBROOT" 2>/dev/null

    log_info "Webroot directory created: $WEBROOT"
}

obtain_certificate() {
    log_info "Obtaining SSL certificate from Let's Encrypt..."
    log_info "Domain: $DOMAIN"
    log_info "Email: $EMAIL"

    # Try with nginx plugin first
    if certbot certonly \
        --nginx \
        --agree-tos \
        --no-eff-email \
        --email "$EMAIL" \
        -d "$DOMAIN" \
        --non-interactive; then
        log_info "Certificate obtained successfully using nginx plugin"
        return 0
    fi

    log_warn "Nginx plugin failed, trying webroot method..."

    # Fallback to webroot method
    if certbot certonly \
        --webroot \
        -w "$WEBROOT" \
        --agree-tos \
        --no-eff-email \
        --email "$EMAIL" \
        -d "$DOMAIN" \
        --non-interactive; then
        log_info "Certificate obtained successfully using webroot method"
        return 0
    fi

    log_error "Failed to obtain certificate"
    log_error "Check Certbot logs: /var/log/letsencrypt/letsencrypt.log"
    exit 1
}

setup_auto_renewal() {
    log_info "Setting up automatic certificate renewal..."

    # Test renewal
    if certbot renew --dry-run; then
        log_info "Certificate renewal test passed"
    else
        log_warn "Certificate renewal test failed"
        log_warn "Check configuration before certificates expire"
    fi

    # Certbot usually installs systemd timer automatically
    if systemctl list-timers | grep -q certbot; then
        log_info "Certbot renewal timer is active"
    else
        log_warn "Certbot renewal timer not found"
        log_info "Creating cron job for renewal..."

        # Add cron job (runs twice daily)
        CRON_CMD="0 */12 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'"
        (crontab -l 2>/dev/null | grep -v "certbot renew"; echo "$CRON_CMD") | crontab -

        log_info "Cron job installed: certbot renew runs twice daily"
    fi
}

generate_dhparam() {
    log_info "Generating Diffie-Hellman parameters (this may take a while)..."

    if [ -f /etc/nginx/dhparam.pem ]; then
        log_info "dhparam.pem already exists, skipping generation"
        return
    fi

    openssl dhparam -out /etc/nginx/dhparam.pem 2048
    chmod 644 /etc/nginx/dhparam.pem

    log_info "Diffie-Hellman parameters generated"
}

install_nginx_snippets() {
    log_info "Installing Nginx configuration snippets..."

    # Create snippets directory
    mkdir -p /etc/nginx/snippets

    # Copy SSL params
    if [ -f "$(dirname "$0")/../nginx/ssl-params.conf" ]; then
        cp "$(dirname "$0")/../nginx/ssl-params.conf" /etc/nginx/snippets/
        log_info "Installed ssl-params.conf"
    else
        log_warn "ssl-params.conf not found, skipping"
    fi

    # Copy security headers
    if [ -f "$(dirname "$0")/../nginx/security-headers.conf" ]; then
        cp "$(dirname "$0")/../nginx/security-headers.conf" /etc/nginx/snippets/
        log_info "Installed security-headers.conf"
    else
        log_warn "security-headers.conf not found, skipping"
    fi

    # Copy main config
    if [ -f "$(dirname "$0")/../nginx/baluhost.conf" ]; then
        cp "$(dirname "$0")/../nginx/baluhost.conf" /etc/nginx/sites-available/

        # Replace placeholders
        sed -i "s/YOUR_DOMAIN_HERE/$DOMAIN/g" /etc/nginx/sites-available/baluhost.conf

        log_info "Installed baluhost.conf (updated with domain: $DOMAIN)"
        log_warn "IMPORTANT: Review /etc/nginx/sites-available/baluhost.conf"
        log_warn "Adjust upstream backend configuration before enabling!"
    else
        log_warn "baluhost.conf not found, skipping"
    fi
}

enable_site() {
    log_info "Enabling BaluHost site..."

    # Remove default site
    if [ -f /etc/nginx/sites-enabled/default ]; then
        rm /etc/nginx/sites-enabled/default
        log_info "Removed default nginx site"
    fi

    # Create symlink
    if [ ! -L /etc/nginx/sites-enabled/baluhost.conf ]; then
        ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/
        log_info "Enabled baluhost.conf"
    fi

    # Test configuration
    if nginx -t; then
        log_info "Nginx configuration test passed"
        systemctl reload nginx
        log_info "Nginx reloaded successfully"
    else
        log_error "Nginx configuration test failed"
        log_error "Fix errors before reloading nginx"
        exit 1
    fi
}

# ===================================
# Main Execution
# ===================================

main() {
    log_info "====================================="
    log_info "Let's Encrypt SSL Setup for BaluHost"
    log_info "====================================="
    log_info ""

    check_root
    check_domain_dns
    check_nginx
    setup_webroot
    install_certbot
    obtain_certificate
    setup_auto_renewal
    generate_dhparam
    install_nginx_snippets

    log_info ""
    log_info "====================================="
    log_info "SSL Setup Complete!"
    log_info "====================================="
    log_info ""
    log_info "Certificate location: /etc/letsencrypt/live/$DOMAIN/"
    log_info "Certificate expires in 90 days (auto-renewal configured)"
    log_info ""
    log_info "Next steps:"
    log_info "1. Review Nginx config: /etc/nginx/sites-available/baluhost.conf"
    log_info "2. Adjust backend upstream configuration"
    log_info "3. Enable site: sudo ln -s /etc/nginx/sites-available/baluhost.conf /etc/nginx/sites-enabled/"
    log_info "4. Test: sudo nginx -t"
    log_info "5. Reload: sudo systemctl reload nginx"
    log_info "6. Access: https://$DOMAIN"
    log_info ""
    log_info "Test SSL configuration: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
    log_info "Test security headers: https://securityheaders.com/?q=$DOMAIN"
    log_info ""
}

# Run main function
main "$@"
