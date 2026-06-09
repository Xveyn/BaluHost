#!/bin/bash
# BaluHost NFS Setup Script
# Run once on the production server to install and configure the NFS server.
#
# Usage: sudo bash setup-nfs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SERVICE_USER:-sven}"
STORAGE_GROUP="${STORAGE_GROUP:-baluhost}"
EXPORTS_CONF="/etc/exports.d/baluhost.exports"

echo "=== BaluHost NFS Setup ==="

echo "[1/4] Installing NFS server..."
apt-get update -qq
apt-get install -y -qq nfs-kernel-server

echo "[2/4] Creating exports config..."
mkdir -p /etc/exports.d
touch "$EXPORTS_CONF"
chown "$SERVICE_USER:$STORAGE_GROUP" "$EXPORTS_CONF"
chmod 644 "$EXPORTS_CONF"

echo "[3/4] Installing sudoers rules..."
# Substitute the @@BALUHOST_USER@@ placeholder, validate in isolation, then
# install — never write an unvalidated file into /etc/sudoers.d (a malformed
# drop-in can break sudo system-wide).
SUDOERS_TMP=$(mktemp)
trap 'rm -f "$SUDOERS_TMP"' EXIT
sed "s|@@BALUHOST_USER@@|$SERVICE_USER|g" "$SCRIPT_DIR/baluhost-nfs-sudoers" > "$SUDOERS_TMP"
if ! visudo -cf "$SUDOERS_TMP" >/dev/null 2>&1; then
    echo "ERROR: generated sudoers file fails visudo syntax check." >&2
    visudo -cf "$SUDOERS_TMP" || true
    exit 1
fi
install -m 440 -o root -g root "$SUDOERS_TMP" /etc/sudoers.d/baluhost-nfs

echo "[4/4] Enabling nfs-server..."
systemctl enable --now nfs-server

echo ""
echo "=== NFS Setup Complete ==="
echo "nfs-server status: $(systemctl is-active nfs-server)"
echo ""
echo "Next steps:"
echo "  1. Create NFS exports in BaluHost UI (System Control -> NFS)"
echo "  2. Linux client: sudo mount -t nfs $(hostname -I | awk '{print $1}'):<path> /mnt/baluhost"
