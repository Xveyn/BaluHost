#!/usr/bin/env bash
# Installs the OpenCode reverse-proxy nginx site (LAN-only HTTPS on :8443).
#
# Usage:
#   sudo ./setup-opencode-proxy.sh
#
# What it does:
#   1. Copies deploy/nginx/opencode-https.conf -> /etc/nginx/sites-available/opencode
#   2. Symlinks it into sites-enabled/
#   3. Opens TCP/8443 in UFW if UFW is active
#   4. Runs nginx -t and reloads nginx on success
#
# Removal:
#   sudo rm /etc/nginx/sites-enabled/opencode /etc/nginx/sites-available/opencode
#   sudo systemctl reload nginx
#   sudo ufw delete allow 8443/tcp   # if UFW

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
SRC="$DEPLOY_DIR/nginx/opencode-https.conf"
DST="/etc/nginx/sites-available/opencode"
LINK="/etc/nginx/sites-enabled/opencode"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR ]${NC} $1" >&2; }

if [ "$EUID" -ne 0 ]; then
    err "Must be run as root or with sudo."
    exit 1
fi

if [ ! -f "$SRC" ]; then
    err "Source config not found: $SRC"
    exit 1
fi

# Sanity: the main baluhost site must already be enabled (defines $connection_upgrade)
if [ ! -e /etc/nginx/sites-enabled/baluhost ]; then
    err "The main baluhost site is not enabled. Run setup-selfsigned.sh first."
    exit 1
fi

# Sanity: the self-signed cert must exist
if [ ! -f /etc/nginx/ssl/baluhost.crt ] || [ ! -f /etc/nginx/ssl/baluhost.key ]; then
    err "Self-signed cert/key missing under /etc/nginx/ssl/."
    err "Run setup-selfsigned.sh first."
    exit 1
fi

log "Installing site config: $DST"
cp "$SRC" "$DST"

log "Enabling site: $LINK"
ln -sf "$DST" "$LINK"

# Firewall
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    if ufw status | grep -qE "8443/tcp.*ALLOW"; then
        log "UFW already allows 8443/tcp"
    else
        ufw allow 8443/tcp comment "OpenCode reverse proxy (LAN-only)"
        log "UFW: opened 8443/tcp"
    fi
elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port=8443/tcp
    firewall-cmd --reload
    log "firewalld: opened 8443/tcp"
else
    warn "No active UFW/firewalld detected. Ensure TCP/8443 is reachable on your LAN."
fi

log "Running nginx -t ..."
if ! nginx -t; then
    err "nginx config test failed. Not reloading. Inspect $DST and $LINK."
    exit 1
fi

log "Reloading nginx ..."
systemctl reload nginx

LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}' || hostname -I | awk '{print $1}')
echo ""
log "Done. OpenCode is now reachable at:"
echo "    https://baluhost.local:8443/"
echo "    https://${LAN_IP}:8443/"
echo ""
warn "OpenCode has NO authentication. The deny-all/allow-LAN ACL is the only"
warn "thing protecting this endpoint. Implement OPENCODE_SERVER_PASSWORD before"
warn "exposing this to anything beyond your LAN."
